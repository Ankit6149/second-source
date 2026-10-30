"""Authenticated HTTP -> existing mock engine -> simulated private Storage.

Local SQLite and fake HTTPS are explicit test substitutes, not cloud acceptance.
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from second_source.backend.asgi import build_cloud_app
from second_source.backend.artifacts import verify_bundle
from second_source.backend.contracts import Principal, CodeStage, EngineResult
from second_source.backend.cloud_artifacts import SupabaseArtifactStore
from second_source.backend.on_demand import OnDemandMockExecutor
from second_source.backend.service import BackendService
from second_source.backend.settings import CloudSettings
from second_source.backend.store import SQLiteStore
from second_source.model_gateway import MetaProvider
from second_source.reconstruct import create_scope
from test_backend_cloud_artifacts import FakeStorage, raw_report


TOKEN = "a" * 32 + "." + "b" * 32 + "." + "c" * 48
OTHER = "x" * 32 + "." + "y" * 32 + "." + "z" * 48
OWNER = "a186fb18-72b4-4071-9794-e8746c3e4231"
HEADERS = {"Authorization": "Bearer " + TOKEN}


class LocalAcceptanceStore(SQLiteStore):
    """Only the test profile; cloud factory otherwise requires PostgresStore."""
    def __init__(self, path):
        super().__init__(path)
        self.refs = {}

    def record_artifact_ref(self, principal, run_id, reference, *, lease_token):
        assert isinstance(lease_token, str) and lease_token
        key = (principal.owner_id, run_id, reference.artifact_id)
        assert key not in self.refs or self.refs[key] == reference
        self.refs[key] = reference


def config(enabled=True):
    return CloudSettings(database_url="NOT_A_CREDENTIAL_" + "d" * 24,
        publishable_key="sb_publishable_" + "x" * 30,
        storage_key="NOT_A_CREDENTIAL_" + "s" * 24,
        cors_origins=("https://ui.example",), enable_mock_execution=enabled)


def identity(token):
    if token == TOKEN:
        return Principal(owner_id=OWNER)
    if token == OTHER:
        return Principal(owner_id="194d8e1f-b8d2-4b59-a387-92698d47678c")
    return None


def prepare(client):
    inv = client.post("/v1/investigations", headers={**HEADERS, "Idempotency-Key": "first"},
        json={"title": "PRIVATE_TITLE_SENTINEL", "scope": create_scope(0).model_dump(mode="json")})
    assert inv.status_code == 201, inv.text
    inv = inv.json()
    response = client.post(f"/v1/investigations/{inv['investigation_id']}/authorize", headers=HEADERS,
        json={"expected_revision": inv["revision"], "scope_digest": inv["scope_digest"]})
    assert response.status_code == 200
    path = f"/v1/investigations/{inv['investigation_id']}/runs"
    run = client.post(path, headers={**HEADERS, "Idempotency-Key": "run"}, json={"kind": "g3_mock"})
    assert run.status_code == 201
    assert client.post(path, headers={**HEADERS, "Idempotency-Key": "run"}, json={"kind": "g3_mock"}).json() == run.json()
    return inv, run.json()


def test_authenticated_actual_non_ai_http_worker_storage_export_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(MetaProvider, "complete", lambda *a, **k: pytest.fail("Provider transport forbidden"))
    db, transport = LocalAcceptanceStore(tmp_path / "state.sqlite"), FakeStorage()
    app = build_cloud_app(config(), store=db, transport=transport, identity=identity)
    with TestClient(app) as client:
        assert client.get("/v1/session").status_code == 401
        assert client.get("/v1/session", headers=HEADERS).json()["owner_id"] == OWNER
        assert client.get("/v1/capabilities", headers=HEADERS).json()["execution_mode"] == "on_demand_mock"
        inv, queued = prepare(client)
        path = f"/v1/runs/{queued['run_id']}"
        assert queued["status"] == "queued" and queued["result"] is None
        assert client.post(path + "/execute", headers={"Authorization": "Bearer " + OTHER},
                           json={"expected_revision": 1}).status_code == 404
        done = client.post(path + "/execute", headers=HEADERS, json={"expected_revision": 1})
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "completed"
        result = done.json()["result"]
        assert result["real"] is False and result["origin"] == "mock"
        assert result["evaluation"] == {"passed": 22, "failed": 3, "indeterminate": 0, "total": 25}
        assert result["usage"]["estimated_cost_usd"] == result["usage"]["uncertain_cost_usd"] == 0
        verified = client.get(path + "/verification", headers=HEADERS).json()
        assert verified["evaluation"] == result["evaluation"] and verified["real"] is False
        assert verified["repair_history_availability"] == "engine_integration_pending"
        assert client.get(path + "/events", headers=HEADERS).json()["items"]
        assert client.get(path + "/verification", headers={"Authorization": "Bearer " + OTHER}).status_code == 404
        calls = len(transport.calls)
        assert client.post(path + "/execute", headers=HEADERS, json={"expected_revision": 1}).json() == done.json()
        assert len(transport.calls) == calls
        proof = client.get(path + "/export.zip", headers=HEADERS)
        assert verify_bundle(proof.content)["valid"]
        assert b"PRIVATE_TITLE_SENTINEL" not in proof.content and str(tmp_path).encode() not in proof.content
        assert any(key[2] == "private:candidate.v1.json" for key in db.refs)
        assert client.get(path + "/report", headers={"Authorization": "Bearer " + OTHER}).status_code == 404
    restarted = build_cloud_app(config(False), store=LocalAcceptanceStore(tmp_path / "state.sqlite"),
                                transport=transport, identity=identity)
    with TestClient(restarted) as client:
        assert client.get(path, headers=HEADERS).json() == done.json()
        assert client.get(path + "/export.zip", headers=HEADERS).content == proof.content
        assert client.post(path + "/execute", headers=HEADERS, json={"expected_revision": 1}).status_code == 409


def test_exact_cors_and_authority_no_cookie_or_wildcard(tmp_path):
    app = build_cloud_app(config(False), store=LocalAcceptanceStore(tmp_path / "state.sqlite"),
                          transport=FakeStorage(), identity=identity)
    with TestClient(app) as client:
        for origin, expected in [("https://ui.example", 200), ("https://evil.example", 400)]:
            response = client.options("/v1/investigations", headers={"Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type,Idempotency-Key"})
            assert response.status_code == expected
            assert "access-control-allow-credentials" not in response.headers
        schema = client.get("/openapi.json").json()
        assert "/v1/session" in schema["paths"] and "/v1/runs/{run_id}/execute" in schema["paths"]


@pytest.mark.parametrize("origin", ["*", "http://ui.example", "https://user:pass@ui.example", "https://ui.example/path", "https://ui.example?x=1"])
def test_invalid_cors_configuration_is_rejected(origin):
    with pytest.raises(ValueError):
        CloudSettings(**{**config().model_dump(), "cors_origins": (origin,)})


def test_environment_configuration_errors_never_disclose_values():
    marker = "PRIVATE_PASSWORD_SENTINEL"
    with pytest.raises(ValueError) as error:
        CloudSettings.from_environment({"SECOND_SOURCE_DATABASE_URL": marker,
                                       "SECOND_SOURCE_CORS_ORIGINS": marker})
    assert marker not in str(error.value)
    assert marker not in repr(config())


def test_unexpected_request_exception_does_not_reach_server_logs(tmp_path, caplog):
    app = build_cloud_app(config(False), store=LocalAcceptanceStore(tmp_path / "state.sqlite"),
                          transport=FakeStorage(), identity=identity)

    @app.get("/v1/synthetic-failure")
    def failure():
        raise RuntimeError("PRIVATE_FAILURE_SENTINEL")

    with TestClient(app) as client:
        response = client.get("/v1/synthetic-failure", headers=HEADERS)
        assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"
        assert "PRIVATE_FAILURE_SENTINEL" not in response.text + caplog.text
        assert TOKEN not in caplog.text


def test_uncertain_publication_is_quarantined_without_replay(tmp_path):
    db, transport = LocalAcceptanceStore(tmp_path / "state.sqlite"), FakeStorage()
    service = BackendService(store=db)
    artifacts = SupabaseArtifactStore(transport, authorize_run=service.get_run)
    calls = []

    class Engine:
        def __init__(self, root, reports, **kwargs):
            self.reports = reports

        def execute(self, lease, stage, cancelled):
            calls.append(lease.run.run_id)
            for value in CodeStage:
                stage(value)
            reference = self.reports.publish_report(lease.run.run_id, raw_report())
            return EngineResult(stop_reason="completed_mock_run", report=reference)

    executor = OnDemandMockExecutor(service, artifacts, record_artifact=db.record_artifact_ref,
                                    engine_factory=Engine)
    app = build_cloud_app(config(), store=db, transport=transport, identity=identity, executor=executor)
    with TestClient(app) as client:
        _, run = prepare(client)
        path = f"/v1/runs/{run['run_id']}"
        transport.overrides.append(OSError("PRIVATE_STORAGE_ERROR_SENTINEL"))
        response = client.post(path + "/execute", headers=HEADERS, json={"expected_revision": 1})
        assert response.status_code == 200
        assert response.json()["status"] == "needs_reconciliation"
        assert response.json()["error_code"] == "ARTIFACT_PUBLICATION_UNCERTAIN"
        assert "PRIVATE_STORAGE_ERROR_SENTINEL" not in response.text
        assert client.post(path + "/execute", headers=HEADERS, json={"expected_revision": 1}).json() == response.json()
        assert len(calls) == len(transport.calls) == 1


def test_owner_scoped_expired_lease_reconciliation_does_not_requeue(tmp_path):
    db, transport = LocalAcceptanceStore(tmp_path / "state.sqlite"), FakeStorage()
    app = build_cloud_app(config(False), store=db, transport=transport, identity=identity)
    service = BackendService(store=db)
    with TestClient(app) as client:
        _, run = prepare(client)
        lease = service.claim("lost_worker", run_id=run["run_id"])
        with db.transaction() as connection:
            connection.execute("UPDATE runs SET lease_expires=0 WHERE run_id=?", (run["run_id"],))
        path = f"/v1/runs/{run['run_id']}/reconcile"
        assert client.post(path, headers={"Authorization": "Bearer " + OTHER},
                           json={"expected_revision": lease.run.revision}).status_code == 404
        response = client.post(path, headers=HEADERS, json={"expected_revision": lease.run.revision})
        assert response.json()["status"] == "needs_reconciliation"
        assert service.claim("replacement", run_id=run["run_id"]) is None
