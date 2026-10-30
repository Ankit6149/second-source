"""Hermetic private Storage acceptance; synthetic rows/bytes, no real keys/HTTP."""
import hashlib
import io
import json
import traceback
from urllib.parse import urlsplit
import zipfile

import pytest

from second_source.backend import cloud_artifacts as cloud
from second_source.backend.artifacts import sanitized_report, verify_bundle
from second_source.backend.contracts import (
    ArtifactReference, AuthorizeInvestigation, BackendError, CodeStage,
    CreateInvestigation, CreateRun, EngineResult, EvaluationSummary, Principal,
)
from second_source.backend.service import BackendService
from second_source.g2_persistence import canonical
from second_source.reconstruct import create_scope


class FakeStorage:
    def __init__(self):
        self.objects, self.calls, self.overrides = {}, [], []
        self.duplicate_status = 409

    def request(self, method, url, **options):
        assert options["follow_redirects"] is False
        assert 0.1 <= options["timeout_seconds"] <= 30
        assert url.startswith(cloud.PROJECT_ORIGIN + "/storage/v1/object/")
        assert "/public/" not in url and "/sign/" not in url
        self.calls.append((method, url, options))
        if self.overrides:
            response = self.overrides.pop(0)
            if isinstance(response, BaseException):
                raise response
            return response
        key = urlsplit(url).path.replace("/object/authenticated/", "/object/")
        if method == "POST":
            assert options["headers"]["x-upsert"] == "false"
            if key in self.objects:
                return cloud.StorageResponse(self.duplicate_status, {}, b'{"error":"Duplicate"}')
            self.objects[key] = options["body"]
            return cloud.StorageResponse(200, {}, b"{}")
        if key not in self.objects:
            return cloud.StorageResponse(404, {}, b"{}")
        raw = self.objects[key]
        return cloud.StorageResponse(200, {"content-length": str(len(raw))}, raw)


def raw_report(**updates):
    report = {"origin": "mock", "real": False, "stop_reason": "completed_mock_run",
        "usage": {"attempts": 1},
        "evaluation": {"passed": 22, "failed": 3, "indeterminate": 0, "total": 25},
        "spec_digest": "sha256:" + "a" * 64,
        "original_model_output": "PRIVATE_ORIGINAL_SENTINEL", "private_path": "/PRIVATE_PATH_SENTINEL",
        "sealed_cases": ["SEALED_SENTINEL"]}
    report.update(updates)
    return report


def test_repair_projection_rejects_inconsistent_selection_and_redacts_feedback():
    from second_source.backend.artifacts import sanitized_report
    digest = "sha256:" + "a" * 64
    evaluation = {"passed": 22, "failed": 3, "indeterminate": 0, "total": 25}
    report = raw_report(selected={"version": "initial", "candidate_digest": digest,
        "evaluation": evaluation}, repair_history={"verdict": "no_change",
        "stop_reason": "rounds_exhausted", "versions": [
            {"round": 0, "candidate_digest": digest, "evaluation": evaluation,
             "feedback": "SEALED_SENTINEL"},
            {"round": 1, "candidate_digest": "sha256:" + "b" * 64, "evaluation": evaluation,
             "files": {"candidate": "/PRIVATE_PATH_SENTINEL"}},
        ]})
    projected = sanitized_report(report)
    assert sanitized_report(projected) == projected
    assert "SEALED_SENTINEL" not in str(projected) and "PRIVATE_PATH_SENTINEL" not in str(projected)
    report["selected"]["version"] = "repair-1"  # ties must keep the original
    report["selected"]["candidate_digest"] = report["spec_digest"] = "sha256:" + "b" * 64
    with pytest.raises(BackendError):
        sanitized_report(report)


@pytest.fixture
def configured(tmp_path):
    service = BackendService(tmp_path / "state.sqlite")
    principal = Principal(owner_id="private_owner_123")
    investigation = service.create_investigation(principal,
        CreateInvestigation(title="PRIVATE_TITLE_SENTINEL", scope=create_scope(0)), "i")
    investigation = service.authorize_investigation(principal, investigation.investigation_id,
        AuthorizeInvestigation(expected_revision=investigation.revision, scope_digest=investigation.scope_digest))
    run = service.create_run(principal, investigation.investigation_id, CreateRun(), "r")
    transport = FakeStorage()
    store = cloud.SupabaseArtifactStore(transport, authorize_run=service.get_run)
    return service, principal, investigation, run, transport, store


def completed(configured):
    service, principal, investigation, run, transport, store = configured
    owned = store.for_owner(principal)
    reference = owned.publish_report(run.run_id, raw_report())
    lease = service.claim("synthetic_worker")
    for stage in CodeStage:
        service.stage(run.run_id, lease.token, stage)
    result = EngineResult(stop_reason="completed_mock_run",
        usage={"attempts": 1}, evaluation=EvaluationSummary(passed=22, failed=3, indeterminate=0, total=25), report=reference)
    run = service.finish(run.run_id, lease.token, result)
    return owned, run


def test_existing_report_and_proof_contract_round_trip_without_private_data(configured):
    service, principal, investigation, queued, transport, store = configured
    owned, run = completed(configured)
    expected = canonical(sanitized_report(raw_report()))
    assert owned.read(run.run_id, run.result.report) == expected
    archive = owned.export_bundle(investigation, run, service.events(principal, investigation.investigation_id))
    assert verify_bundle(archive)["valid"] and verify_bundle(archive)["origin"] == "mock"
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        assert json.loads(zipped.read("report.json"))["evaluation"]["passed"] == 22
        assert sorted(zipped.namelist()) == ["events.json", "manifest.json", "report.json", "run.json"]
    for marker in (b"PRIVATE_ORIGINAL", b"PRIVATE_PATH", b"SEALED_SENTINEL", b"PRIVATE_TITLE", principal.owner_id.encode()):
        assert marker not in archive
    for _, url, options in transport.calls:
        assert principal.owner_id not in url and run.run_id not in url
        assert "Authorization" not in options["headers"]  # credentials belong to server transport only
    assert not hasattr(owned, "read_private") and not hasattr(owned, "retain_private")


@pytest.mark.parametrize("duplicate", [400, 409])
def test_immutable_duplicate_is_idempotent_only_after_exact_readback(configured, duplicate):
    _, principal, _, run, transport, store = configured
    owned = store.for_owner(principal)
    transport.duplicate_status = duplicate
    first = owned.publish_report(run.run_id, raw_report())
    assert owned.publish_report(run.run_id, raw_report()) == first
    assert [call[0] for call in transport.calls] == ["POST", "GET", "POST", "GET"]
    changed = raw_report(evaluation={"passed": 23, "failed": 2, "indeterminate": 0, "total": 25})
    with pytest.raises(BackendError, match="integrity"):
        owned.publish_report(run.run_id, changed)
    assert owned.read(run.run_id, first) == canonical(sanitized_report(raw_report()))


def test_owner_run_authorization_precedes_every_transport_and_export(configured):
    service, principal, investigation, run, transport, store = configured
    reference = store.for_owner(principal).publish_report(run.run_id, raw_report())
    stranger = store.for_worker(Principal(owner_id="other_owner"))
    before = len(transport.calls)
    for operation in (
        lambda: stranger.read(run.run_id, reference),
        lambda: stranger.publish_report(run.run_id, raw_report()),
        lambda: stranger.retain_private(run.run_id, "candidate.v1.json", b"{}", expected_sha256=hashlib.sha256(b"{}").hexdigest()),
    ):
        with pytest.raises(BackendError) as error:
            operation()
        assert error.value.code == "NOT_FOUND"
    assert len(transport.calls) == before
    owned, finished = completed(configured)
    forged = investigation.model_copy(update={"owner_id": "other_owner"})
    before = len(transport.calls)
    with pytest.raises(BackendError):
        owned.export_bundle(forged, finished, service.events(principal, investigation.investigation_id))
    assert len(transport.calls) == before


@pytest.mark.parametrize("name", sorted(cloud.PRIVATE_ARTIFACT_NAMES))
def test_private_original_retention_uses_separate_namespace_and_never_public_read(configured, name):
    _, principal, _, run, transport, store = configured
    raw = b'{"original":"PRIVATE_ORIGINAL_SENTINEL"}'
    worker = store.for_worker(principal)
    reference = worker.retain_private(run.run_id, name, raw, expected_sha256=hashlib.sha256(raw).hexdigest())
    assert reference.artifact_id == "private:" + name
    assert worker.read_private(run.run_id, reference) == raw
    assert "/private/" in transport.calls[0][1]
    before = len(transport.calls)
    with pytest.raises(BackendError):
        store.for_owner(principal).read(run.run_id, reference)
    assert len(transport.calls) == before


@pytest.mark.parametrize("name", ["suite.json", "sealed/suite.json", ".env", "MODEL_API_KEY", "../candidate.v1.json", "broker.generation.v1.json", "stdout.private.log"])
def test_private_classification_fail_closed_no_arbitrary_paths_or_sealed_suite(configured, name):
    _, principal, _, run, transport, store = configured
    with pytest.raises(BackendError):
        store.for_worker(principal).retain_private(run.run_id, name, b"{}", expected_sha256=hashlib.sha256(b"{}").hexdigest())
    assert transport.calls == []


def test_original_sensitive_bytes_cannot_enter_existing_public_proof(configured):
    service, principal, investigation, run, _, store = configured
    worker = store.for_worker(principal)
    raw = b'{"secret_observation":"ORIGINAL_RETAINED_PRIVATELY"}'
    worker.retain_private(run.run_id, "generation-result.v1.private.json", raw, expected_sha256=hashlib.sha256(raw).hexdigest())
    owned, run = completed(configured)
    bundle = owned.export_bundle(investigation, run, service.events(principal, investigation.investigation_id))
    assert b"ORIGINAL_RETAINED_PRIVATELY" not in bundle
    assert b"generation-result" not in bundle


@pytest.mark.parametrize("fault", ["outage", "redirect", "truncated", "oversized", "encoding", "invalid_response", "missing"])
def test_storage_failure_redaction_and_no_redirect_or_retry(configured, fault):
    _, principal, _, run, transport, store = configured
    owned = store.for_owner(principal)
    reference = owned.publish_report(run.run_id, raw_report())
    failures = {
        "outage": RuntimeError("SECRET_TOKEN_SENTINEL private_url=?credential=SECRET_TOKEN_SENTINEL"),
        "redirect": cloud.StorageResponse(307, {"location": "https://evil.invalid/SECRET_TOKEN_SENTINEL"}, b""),
        "truncated": cloud.StorageResponse(200, {"content-length": "9999"}, b"{}"),
        "oversized": cloud.StorageResponse(200, {}, b"x" * (cloud.MAX_ARTIFACT_BYTES + 1)),
        "encoding": cloud.StorageResponse(200, {"content-encoding": "gzip"}, b"{}"),
        "invalid_response": "SECRET_TOKEN_SENTINEL",
        "missing": cloud.StorageResponse(404, {}, b"SECRET_TOKEN_SENTINEL"),
    }
    transport.overrides = [failures[fault]]
    before = len(transport.calls)
    with pytest.raises(BackendError) as error:
        owned.read(run.run_id, reference)
    assert len(transport.calls) == before + 1
    rendered = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert "SECRET_TOKEN_SENTINEL" not in rendered and "evil.invalid" not in rendered


def test_changed_bytes_hash_and_size_fail_closed(configured):
    _, principal, _, run, transport, store = configured
    owned = store.for_owner(principal)
    reference = owned.publish_report(run.run_id, raw_report())
    key = next(iter(transport.objects))
    original = transport.objects[key]
    for raw in (original[:-1], original[:-1] + b"x"):
        transport.objects[key] = raw
        with pytest.raises(BackendError) as error:
            owned.read(run.run_id, reference)
        assert error.value.code == "ARTIFACT_INTEGRITY"


def test_invalid_input_or_hash_never_uploads(configured):
    _, principal, _, run, transport, store = configured
    worker = store.for_worker(principal)
    for report in (raw_report(real=True), raw_report(usage={"estimated_cost_usd": 1}), {"PRIVATE": "SECRET"}):
        with pytest.raises(BackendError):
            worker.publish_report(run.run_id, report)
    for raw, witness in ((b"{}", "0" * 64), (b"x" * (cloud.MAX_ARTIFACT_BYTES + 1), "0" * 64)):
        with pytest.raises(BackendError):
            worker.retain_private(run.run_id, "candidate.v1.json", raw, expected_sha256=witness)
    assert transport.calls == []


class FakeResponse:
    def __init__(self, status=200, body=b"{}", headers=None):
        self.status, self.buffer = status, io.BytesIO(body)
        self.headers = [("Content-Length", str(len(body)))] if headers is None else headers

    def getheaders(self):
        return self.headers

    def read1(self, size):
        return self.buffer.read(size)


class FakeConnection:
    def __init__(self, response):
        self.response, self.requests, self.closed, self.sock = response, [], False, None

    def request(self, method, path, body, headers):
        self.requests.append((method, path, body, headers))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def test_explicit_http_transport_constructor_is_offline_and_credentials_are_server_only(monkeypatch):
    calls = []
    connection = FakeConnection(FakeResponse())
    def factory(host, **kwargs):
        calls.append((host, kwargs))
        return connection
    monkeypatch.setattr(cloud.http.client, "HTTPSConnection", factory)
    transport = cloud.SupabaseHTTPTransport(access_token="FAKE_SERVER_SECRET", api_key="FAKE_API_KEY")
    assert calls == [] and "FAKE_SERVER_SECRET" not in repr(transport)
    key = "v1/" + "a" * 64 + "/" + "b" * 64 + "/report/report.json"
    response = transport.request("GET", cloud.PROJECT_ORIGIN + "/storage/v1/object/authenticated/" + cloud.PRIVATE_BUCKET + "/" + key,
        headers={}, body=None, max_response_bytes=100, timeout_seconds=1, follow_redirects=False)
    assert response.body == b"{}" and connection.closed
    assert calls[0][0] == "jpqcqqbzriizxhigvjki.supabase.co"
    assert connection.requests[0][3]["Authorization"] == "Bearer FAKE_SERVER_SECRET"
    assert connection.requests[0][3]["apikey"] == "FAKE_API_KEY"
    assert "FAKE_SERVER_SECRET" not in repr(response)


@pytest.mark.parametrize("fault", ["host", "redirect_enabled", "header", "upsert", "truncated", "oversized", "duplicate_length", "compressed"])
def test_http_transport_enforces_fixed_target_no_redirect_bounds_and_redacts(monkeypatch, fault):
    headers = [("Content-Length", "2")]
    body = b"{}"
    if fault == "truncated":
        headers = [("Content-Length", "5")]
    if fault == "oversized":
        headers = [("Content-Length", "101")]
    if fault == "duplicate_length":
        headers *= 2
    if fault == "compressed":
        headers.append(("Content-Encoding", "gzip"))
    connection = FakeConnection(FakeResponse(body=body, headers=headers))
    calls = []
    def factory(*args, **kwargs):
        calls.append(True)
        return connection
    monkeypatch.setattr(cloud.http.client, "HTTPSConnection", factory)
    transport = cloud.SupabaseHTTPTransport(access_token="FAKE_SERVER_SECRET", api_key="FAKE_API_KEY")
    key = "v1/" + "a" * 64 + "/" + "b" * 64 + "/report/report.json"
    url = cloud.PROJECT_ORIGIN + "/storage/v1/object/authenticated/" + cloud.PRIVATE_BUCKET + "/" + key
    method, outgoing, payload = "GET", {}, None
    if fault == "host":
        url = url.replace(cloud.PROJECT_ORIGIN, "https://evil.invalid")
    if fault == "header":
        outgoing = {"Authorization": "PRIVATE_HEADER_SENTINEL"}
    if fault == "upsert":
        method, outgoing, payload = "POST", {"x-upsert": "true"}, b"{}"
        url = url.replace("/object/authenticated/", "/object/")
    with pytest.raises(BackendError) as error:
        transport.request(method, url, headers=outgoing, body=payload, max_response_bytes=100,
                          timeout_seconds=1, follow_redirects=fault == "redirect_enabled")
    assert "FAKE_SERVER_SECRET" not in str(error.value) and "PRIVATE_HEADER" not in str(error.value)
    if fault in {"host", "redirect_enabled", "header", "upsert"}:
        assert calls == []
    else:
        assert connection.closed
