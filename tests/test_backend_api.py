"""NON_AI HTTP acceptance against the same durable service used by workers."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import json
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from second_source.backend.api import create_app
from second_source.backend.contracts import CodeStage, EngineResult, EvaluationSummary, Principal
from second_source.backend.service import BackendService
from second_source.live_experiment import create_scope


TOKEN = "NON_AI_" + "a" * 40
OTHER_TOKEN = "NON_AI_" + "b" * 40
TOKENS = {hashlib.sha256(TOKEN.encode()).hexdigest(): "owner",
          hashlib.sha256(OTHER_TOKEN.encode()).hexdigest(): "other"}
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
OTHER_HEADERS = {"Authorization": f"Bearer {OTHER_TOKEN}"}


@pytest.fixture
def service(tmp_path):
    return BackendService(tmp_path / "api.sqlite")


@pytest.fixture
def client(service):
    with TestClient(create_app(service, TOKENS), raise_server_exceptions=False) as test_client:
        yield test_client


def investigation(client, key="investigation"):
    return client.post("/v1/investigations", headers={**HEADERS, "Idempotency-Key": key},
                       json={"title": "NON_AI API acceptance", "scope": create_scope(0, 1).model_dump(mode="json")})


def authorized(client):
    response = investigation(client)
    assert response.status_code == 201, response.text
    item = response.json()
    response = client.post(f"/v1/investigations/{item['investigation_id']}/authorize", headers=HEADERS,
                           json={"expected_revision": item["revision"], "scope_digest": item["scope_digest"]})
    assert response.status_code == 200, response.text
    return response.json()


def queued(client):
    item = authorized(client)
    response = client.post(f"/v1/investigations/{item['investigation_id']}/runs",
                           headers={**HEADERS, "Idempotency-Key": "run"}, json={})
    assert response.status_code == 201, response.text
    return item, response.json()


def assert_safe(response, status, secret=None):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"code", "message", "correlation_id"}
    assert len(body["correlation_id"]) == 32
    assert body["correlation_id"] == response.headers["x-correlation-id"]
    assert response.headers["cache-control"] == "no-store"
    if secret:
        assert secret not in response.text
    return body


def test_durable_api_lifecycle_reuses_service_and_resume_state(client, service):
    item, run = queued(client)
    assert run["status"] == "queued"
    assert client.get(f"/v1/runs/{run['run_id']}", headers=HEADERS).json() == run
    listed = client.get(f"/v1/investigations/{item['investigation_id']}/runs", headers=HEADERS)
    assert listed.json()["items"] == [run]
    first = client.get(f"/v1/investigations/{item['investigation_id']}/events?limit=2", headers=HEADERS).json()
    assert len(first["items"]) == 2
    next_page = client.get(f"/v1/investigations/{item['investigation_id']}/events?after={first['next_after']}", headers=HEADERS).json()
    assert [e["event_type"] for e in first["items"] + next_page["items"]] == [
        "investigation_created", "investigation_authorized_mock_only", "run_queued"]
    resumed = BackendService(service.store.path)
    assert resumed.get_run(Principal(owner_id="owner"), run["run_id"]).model_dump(mode="json") == run
    response = client.post(f"/v1/runs/{run['run_id']}/cancel", headers=HEADERS,
                           json={"expected_revision": run["revision"]})
    assert response.status_code == 200 and response.json()["status"] == "cancelled"


@pytest.mark.parametrize("authorization", [None, "Basic secret", "Bearer short", "Bearer " + "x" * 300,
                                         "bearer " + TOKEN, "Bearer " + TOKEN + " secret", "Bearer " + "c" * 40])
def test_bearer_authentication_fails_closed(client, authorization):
    response = client.get("/v1/investigations", headers={} if authorization is None else {"Authorization": authorization})
    assert_safe(response, 401, TOKEN)
    assert response.headers["www-authenticate"] == "Bearer"


def test_auth_before_body_and_duplicate_authorization(client):
    response = client.post("/v1/investigations", content="sensitive" * 20_000,
                           headers={"content-type": "application/json"})
    assert_safe(response, 401, "sensitive")
    response = client.get("/v1/capabilities", headers=[("Authorization", "Bearer " + TOKEN),
                                                    ("Authorization", "Bearer " + OTHER_TOKEN)])
    assert_safe(response, 401)


def test_owner_is_derived_from_token_and_other_owners_are_not_found(client):
    item, run = queued(client)
    investigation_id, run_id = item["investigation_id"], run["run_id"]
    for path in (f"/v1/investigations/{investigation_id}", f"/v1/investigations/{investigation_id}/runs",
                 f"/v1/investigations/{investigation_id}/events", f"/v1/runs/{run_id}",
                 f"/v1/runs/{run_id}/report", f"/v1/runs/{run_id}/export.zip"):
        assert_safe(client.get(path, headers=OTHER_HEADERS), 404)
    assert client.get("/v1/investigations", headers=OTHER_HEADERS).json()["items"] == []
    response = client.post(f"/v1/runs/{run_id}/cancel", headers=OTHER_HEADERS,
                           json={"expected_revision": run["revision"]})
    assert_safe(response, 404)
    body = {"title": "spoof", "owner_id": "other", "scope": item["scope"]}
    assert_safe(client.post("/v1/investigations", headers={**HEADERS, "Idempotency-Key": "spoof"}, json=body), 422)


def test_idempotent_create_and_stale_mutations(client):
    first = investigation(client)
    repeat = investigation(client)
    assert first.status_code == repeat.status_code == 201
    assert first.json() == repeat.json()
    item = first.json()
    changed = {"title": "changed request", "scope": item["scope"]}
    assert_safe(client.post("/v1/investigations", json=changed,
                            headers={**HEADERS, "Idempotency-Key": "investigation"}), 409)
    url = f"/v1/investigations/{item['investigation_id']}/authorize"
    body = {"expected_revision": item["revision"], "scope_digest": item["scope_digest"]}
    assert client.post(url, headers=HEADERS, json=body).status_code == 200
    assert_safe(client.post(url, headers=HEADERS, json=body), 409)
    run_url = f"/v1/investigations/{item['investigation_id']}/runs"
    first_run = client.post(run_url, json={}, headers={**HEADERS, "Idempotency-Key": "run"})
    repeat_run = client.post(run_url, json={}, headers={**HEADERS, "Idempotency-Key": "run"})
    assert first_run.status_code == 201 and repeat_run.json() == first_run.json()


def test_no_runs_before_scope_approval_or_paid_modes(client):
    item = investigation(client).json()
    path = f"/v1/investigations/{item['investigation_id']}"
    assert_safe(client.post(path + "/runs", headers={**HEADERS, "Idempotency-Key": "premature"}, json={}), 409)
    for addition in ({"mode": "real"}, {"maximum_model_spend_usd": 0.5}):
        body = {"expected_revision": 1, "scope_digest": item["scope_digest"], **addition}
        assert_safe(client.post(path + "/authorize", headers=HEADERS, json=body), 422)


@pytest.mark.parametrize("path", ["/v1/investigations?limit=0", "/v1/investigations?limit=101",
                                   "/v1/investigations?after=%2E%2E", "/v1/investigations/invalid%20id",
                                   "/v1/investigations/a/events?after=-1", "/v1/investigations/a/events?limit=501"])
def test_bounded_query_and_identifier_validation(client, path):
    assert_safe(client.get(path, headers=HEADERS), 422)


def test_invalid_body_header_and_internal_errors_do_not_echo_inputs(client, service, monkeypatch, caplog):
    secret = "DO_NOT_ECHO_PRIVATE_PROVIDER_RESPONSE"
    response = client.post("/v1/investigations", headers={**HEADERS, "Idempotency-Key": "invalid"},
                           json={"title": secret, "scope": {"private": secret}})
    assert_safe(response, 422, secret)
    assert_safe(client.post("/v1/investigations", headers={**HEADERS, "Idempotency-Key": secret + "!"}, json={}), 422, secret)
    assert_safe(client.post("/v1/investigations", headers={**HEADERS, "content-type": "application/json"},
                           content='{"private":"' + secret), 422, secret)
    def fail(*args, **kwargs):
        raise RuntimeError("C:/private/evidence/" + secret)
    monkeypatch.setattr(service, "list_investigations", fail)
    response = client.get("/v1/investigations", headers={**HEADERS, "X-Correlation-ID": secret})
    body = assert_safe(response, 500, secret)
    assert body["correlation_id"] != secret
    assert secret not in caplog.text
    assert body["correlation_id"] in caplog.text


def test_body_media_size_and_repeated_idempotency_boundaries(client):
    assert_safe(client.post("/v1/investigations", headers=HEADERS, content="not json"), 415)
    assert_safe(client.post("/v1/investigations", headers={**HEADERS, "Content-Encoding": "gzip"}, json={}), 415)
    assert_safe(client.post("/v1/investigations", headers={**HEADERS, "Content-Type": "application/json"}, content="x" * 65_537), 413)
    # A generator has no Content-Length; enforce the same bound on streamed data.
    assert_safe(client.post("/v1/investigations", headers={**HEADERS, "Content-Type": "application/json"},
                            content=iter([b"x" * 40_000, b"x" * 40_000])), 413)
    assert_safe(client.post("/v1/investigations", headers=[*HEADERS.items(), ("Idempotency-Key", "a"),
                                                         ("Idempotency-Key", "b")], json={}), 400)


def test_owner_rate_limit_and_readiness_are_nonbillable(service, monkeypatch):
    app = create_app(service, TOKENS, requests_per_minute=1)
    with TestClient(app) as client:
        assert client.get("/v1/capabilities", headers=HEADERS).json()["real"] is False
        assert_safe(client.get("/v1/capabilities", headers=HEADERS), 429)
        assert client.get("/v1/capabilities", headers=OTHER_HEADERS).status_code == 200
        assert client.get("/health/live").json() == {"status": "ok"}
        assert client.get("/health/ready").status_code == 200
        monkeypatch.setattr(service, "readiness", lambda: False)
        response = client.get("/health/ready")
        assert response.status_code == 503 and response.json() == {"status": "not_ready"}


def test_api_concurrency_is_bounded_without_starting_second_transaction(service, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = service.list_investigations
    def wait(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(service, "list_investigations", wait)
    app = create_app(service, TOKENS, max_concurrent_requests=1)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.get, "/v1/investigations", headers=HEADERS)
        try:
            assert entered.wait(5)
            assert_safe(client.get("/v1/capabilities", headers=HEADERS), 503)
        finally:
            release.set()
        assert future.result().status_code == 200
        assert client.get("/v1/capabilities", headers=HEADERS).status_code == 200


def test_openapi_has_typed_bodies_owner_auth_errors_and_no_paid_authority(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == "1.0.0"
    for path, methods in schema["paths"].items():
        for method in methods.values():
            if path.startswith("/v1/"):
                assert method["security"] == [{"OwnerToken": []}]
                for status in ("401", "409", "422", "500"):
                    assert method["responses"][status]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorBody"}
    create = schema["paths"]["/v1/investigations"]["post"]
    assert create["requestBody"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/CreateInvestigation"}
    assert schema["components"]["schemas"]["CreateInvestigation"]["additionalProperties"] is False
    assert schema["components"]["schemas"]["AuthorizeInvestigation"]["properties"]["mode"]["const"] == "mock"
    assert client.get("/v1/capabilities", headers=HEADERS).json() == {
        "api_version": "v1", "enabled_run_kinds": ["g3_mock"], "real": False,
        "real_inference_enabled": False, "paid_authorization_enabled": False}
    assert_safe(client.get("/v1/unknown", headers=HEADERS), 404)
    assert "access-control-allow-origin" not in client.get("/v1/capabilities", headers={**HEADERS, "Origin": "https://hostile.test"}).headers


@pytest.mark.parametrize("hashes", [{}, [], ["invalid config"], {TOKEN: "owner"}, {"a" * 64: "bad owner!"}])
def test_app_requires_hash_only_valid_owner_configuration(service, hashes):
    with pytest.raises(ValueError):
        create_app(service, hashes)


def test_report_and_export_require_completed_report_and_correct_owner(client):
    _, run = queued(client)
    for suffix in ("report", "export.zip"):
        assert_safe(client.get(f"/v1/runs/{run['run_id']}/{suffix}", headers=HEADERS), 404)


def test_incomplete_request_times_out_before_any_service_operation(service, monkeypatch):
    called = []
    monkeypatch.setattr(service, "create_investigation", lambda *args: called.append(args))
    app = create_app(service, TOKENS, body_timeout_seconds=0.01)
    messages = []
    async def receive():
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"{}", "more_body": False}
    async def send(message):
        messages.append(message)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": "/v1/investigations", "raw_path": b"/v1/investigations",
             "query_string": b"", "headers": [(b"authorization", ("Bearer " + TOKEN).encode()),
                                                (b"content-type", b"application/json")],
             "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 80)}
    asyncio.run(app(scope, receive, send))
    assert messages[0]["status"] == 408
    body = json.loads(messages[1]["body"])
    assert body["code"] == "REQUEST_TIMEOUT"
    assert called == []


def test_total_receive_deadline_cannot_be_extended_by_immediate_empty_chunks(service, monkeypatch):
    from second_source.backend import api
    clock = [0.0]
    monkeypatch.setattr(api, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    app = create_app(service, TOKENS, body_timeout_seconds=1)
    messages, chunks = [], []
    async def receive():
        chunks.append(True)
        clock[0] += 0.5
        # Even immediately available empty chunks must not reset the deadline.
        return {"type": "http.request", "body": b"", "more_body": len(chunks) < 10}
    async def send(message):
        messages.append(message)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": "/v1/investigations", "raw_path": b"/v1/investigations",
             "query_string": b"", "headers": [(b"authorization", ("Bearer " + TOKEN).encode()),
                                                (b"content-type", b"application/json")],
             "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 80)}
    asyncio.run(app(scope, receive, send))
    assert messages[0]["status"] == 408
    assert len(chunks) == 2


def test_verified_artifact_http_export_is_private_sanitized_and_checksum_valid(service, tmp_path):
    from second_source.backend.artifacts import ArtifactStore, verify_bundle
    artifacts = ArtifactStore(tmp_path / "artifacts")
    with TestClient(create_app(service, TOKENS, artifacts)) as client:
        item, run = queued(client)
        lease = service.claim("non_ai_worker")
        for stage in CodeStage:
            service.stage(run["run_id"], lease.token, stage)
        reference = artifacts.publish_report(run["run_id"], {
            "origin": "mock", "real": False, "stop_reason": "completed_mock_run",
            "usage": {}, "evaluation": {"passed": 25, "failed": 0, "indeterminate": 0, "total": 25},
            "raw_model_output": "PRIVATE_DO_NOT_EXPORT", "private_suite_path": "C:/private/suite.json"})
        service.finish(run["run_id"], lease.token, EngineResult(stop_reason="completed_mock_run", report=reference,
            evaluation=EvaluationSummary(passed=25, failed=0, indeterminate=0, total=25)))
        report = client.get(f"/v1/runs/{run['run_id']}/report", headers=HEADERS)
        assert report.status_code == 200
        assert report.json()["real"] is False
        bundle = client.get(f"/v1/runs/{run['run_id']}/export.zip", headers=HEADERS)
        assert bundle.status_code == 200
        assert bundle.headers["content-type"] == "application/zip"
        assert verify_bundle(bundle.content)["valid"] is True
        for response in (report, bundle):
            assert b"PRIVATE_DO_NOT_EXPORT" not in response.content
            assert b"C:/private" not in response.content
            assert response.headers["cache-control"] == "no-store"
        for suffix in ("report", "export.zip"):
            assert_safe(client.get(f"/v1/runs/{run['run_id']}/{suffix}", headers=OTHER_HEADERS), 404)
        artifacts.root.joinpath(run["run_id"], "report.json").write_bytes(b"tampered")
        assert_safe(client.get(f"/v1/runs/{run['run_id']}/report", headers=HEADERS), 409)


def test_http_export_rejects_overflow_instead_of_silently_truncating(service, tmp_path, monkeypatch):
    from second_source.backend.contracts import ArtifactReference, LifecycleEvent
    class UnusedArtifactStore:
        def export_bundle(self, *args):
            pytest.fail("Overflow must be rejected before packaging")
    with TestClient(create_app(service, TOKENS, UnusedArtifactStore())) as client:
        item, run = queued(client)
        lease = service.claim("worker")
        for stage in CodeStage:
            service.stage(run["run_id"], lease.token, stage)
        service.finish(run["run_id"], lease.token, EngineResult(stop_reason="completed_mock_run",
            report=ArtifactReference(artifact_id="report", sha256="a" * 64, size_bytes=1, media_type="application/json")))
        def events(principal, investigation_id, after=0, limit=100):
            return [LifecycleEvent(event_id=number, investigation_id=investigation_id,
                run_id=run["run_id"], event_type="stage_started", stage=None,
                created_at=run["created_at"], revision=1) for number in range(after + 1, min(after + limit, 1001) + 1)]
        monkeypatch.setattr(service, "events", events)
        response = client.get(f"/v1/runs/{run['run_id']}/export.zip", headers=HEADERS)
        assert assert_safe(response, 409)["code"] == "EXPORT_LIMIT"

