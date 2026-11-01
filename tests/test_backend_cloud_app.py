"""Authenticated HTTP -> existing mock engine -> simulated private Storage.

Local SQLite and fake HTTPS are explicit test substitutes, not cloud acceptance.
"""
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from second_source.backend.asgi import build_cloud_app
from second_source.backend.artifacts import verify_bundle
from second_source.backend.contracts import BackendError, Principal, CodeStage, EngineResult
from second_source.backend.cloud_artifacts import SupabaseArtifactStore
from second_source.backend.on_demand import OnDemandMockExecutor
from second_source.backend.service import BackendService
from second_source.backend.settings import CloudSettings
from second_source.backend.store import SQLiteStore
from second_source.model_gateway import MetaProvider
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
    target, = client.get('/v1/targets', headers=HEADERS).json()
    inv = client.post("/v1/investigations", headers={**HEADERS, "Idempotency-Key": "first"},
        json={"title": "PRIVATE_TITLE_SENTINEL", "scope": target['scope']})
    assert inv.status_code == 201, inv.text
    inv = inv.json()
    assert inv['scope_digest'] == target['scope_digest']
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
        assert client.post(path + "/execute", headers=HEADERS,
                           json={"expected_revision": 1, "repair_rounds": 3}).status_code == 422
        assert client.get(path, headers=HEADERS).json()["status"] == "queued"
        done = client.post(path + "/execute", headers=HEADERS, json={"expected_revision": 1})
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "completed", done.text
        result = done.json()["result"]
        assert result["real"] is False and result["origin"] == "mock"
        assert result["evaluation"] == {"passed": 22, "failed": 3, "indeterminate": 0, "total": 25}
        assert result["usage"]["estimated_cost_usd"] == result["usage"]["uncertain_cost_usd"] == 0
        verified = client.get(path + "/verification", headers=HEADERS).json()
        assert verified["evaluation"] == result["evaluation"] and verified["real"] is False
        assert verified["repair_history_availability"] == "available"
        assert verified["repair"]["selected_version"] == "initial"
        assert verified["repair"]["verdict"] == "no_change"
        assert len(verified["repair"]["versions"]) == 2
        events = client.get(path + "/events", headers=HEADERS).json()["items"]
        assert [event["event_type"] for event in events if event["event_type"].startswith("repair_")] == ["repair_started", "repair_completed"]
        assert client.get(path + "/verification", headers={"Authorization": "Bearer " + OTHER}).status_code == 404
        calls = len(transport.calls)
        assert client.post(path + "/execute", headers=HEADERS, json={"expected_revision": 1}).json() == done.json()
        assert len(transport.calls) == calls
        proof = client.get(path + "/export.zip", headers=HEADERS)
        assert verify_bundle(proof.content)["valid"]
        assert b"PRIVATE_TITLE_SENTINEL" not in proof.content and str(tmp_path).encode() not in proof.content
        assert any(key[2] == "private:candidate.v1.json" for key in db.refs)
        for round_number in (1,):
            for prefix in ("candidate", "broker-artifact", "evaluation-receipt"):
                assert any(key[2] == f"private:{prefix}.r{round_number}.json" for key in db.refs)
        assert any(key[2] == "private:G3_repair_history.json" for key in db.refs)
        assert client.get(path + "/report", headers={"Authorization": "Bearer " + OTHER}).status_code == 404
        assert client.get(path + "/export.zip", headers={"Authorization": "Bearer " + OTHER}).status_code == 404
    restarted = build_cloud_app(config(False), store=LocalAcceptanceStore(tmp_path / "state.sqlite"),
                                transport=transport, identity=identity)
    with TestClient(restarted) as client:
        assert client.get(path, headers=HEADERS).json() == done.json()
        assert client.get(path + "/verification", headers=HEADERS).json() == verified
        assert client.get(path + "/export.zip", headers=HEADERS).content == proof.content
        assert client.get(path + "/export.zip", headers={"Authorization": "Bearer " + OTHER}).status_code == 404
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


@pytest.mark.parametrize("enabled", [False, True])
def test_target_discovery_reports_actual_execution_gate(tmp_path, enabled):
    app = build_cloud_app(config(enabled), store=LocalAcceptanceStore(tmp_path / "state.sqlite"),
                          transport=FakeStorage(), identity=identity)
    with TestClient(app) as client:
        target, = client.get("/v1/targets", headers=HEADERS).json()
        assert target["execution_enabled"] is enabled
        assert target["real"] is False and target["run_kind"] == "g3_mock"


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


@pytest.mark.parametrize(('reason', 'upload_fails', 'expected'), [
    ('CANCELLED', False, 'cancelled'),
    ('ENGINE_TIMEOUT', False, 'failed'),
    ('CANCELLED', True, 'needs_reconciliation'),
])
def test_partial_private_artifacts_survive_stop_or_quarantine(tmp_path, reason, upload_fails, expected):
    db, transport = LocalAcceptanceStore(tmp_path / 'state.sqlite'), FakeStorage()
    service = BackendService(store=db)
    artifacts = SupabaseArtifactStore(transport, authorize_run=service.get_run)
    executions = []

    class InterruptedEngine:
        def __init__(self, root, reports, **kwargs):
            self.root = root

        def execute(self, lease, stage, cancelled):
            executions.append(lease.run.run_id)
            stage(CodeStage.CAPTURE)
            directory = self.root / lease.run.run_id / 'engine'
            directory.mkdir(parents=True)
            (directory / 'candidate.v1.json').write_bytes(b'{"fixture":"NON_AI"}')
            (directory / 'sealed-suite.json').write_bytes(b'SEALED_SENTINEL')
            if reason == 'CANCELLED':
                current = service.get_run(Principal(owner_id=OWNER), lease.run.run_id)
                service.cancel_run(Principal(owner_id=OWNER), lease.run.run_id, current.revision)
            raise BackendError(reason, 'Synthetic interruption')

    executor = OnDemandMockExecutor(service, artifacts, record_artifact=db.record_artifact_ref,
                                    engine_factory=InterruptedEngine)
    app = build_cloud_app(config(), store=db, transport=transport, identity=identity, executor=executor)
    with TestClient(app) as client:
        _, run = prepare(client)
        path = f"/v1/runs/{run['run_id']}"
        if upload_fails:
            transport.overrides.append(OSError('PRIVATE_FAILURE_SENTINEL'))
        result = client.post(path + '/execute', headers=HEADERS, json={'expected_revision': 1})
        assert result.status_code == 200 and result.json()['status'] == expected
        assert result.json()['error_code'] == ('ARTIFACT_PUBLICATION_UNCERTAIN' if upload_fails else reason)
        assert b'SEALED_SENTINEL' not in b''.join(transport.objects.values())
        assert client.get(path + '/report', headers=HEADERS).status_code == 404
        if not upload_fails:
            ref = db.refs[(OWNER, run['run_id'], 'private:candidate.v1.json')]
            assert artifacts.for_worker(Principal(owner_id=OWNER)).read_private(run['run_id'], ref) == b'{"fixture":"NON_AI"}'
            with pytest.raises(BackendError):
                artifacts.for_worker(Principal(owner_id='194d8e1f-b8d2-4b59-a387-92698d47678c')).read_private(run['run_id'], ref)
        calls = len(transport.calls)
        assert client.post(path + '/execute', headers=HEADERS, json={'expected_revision': 1}).json() == result.json()
        assert len(executions) == 1 and len(transport.calls) == calls


def test_expired_worker_cannot_archive_partial_artifacts(tmp_path):
    db, transport = LocalAcceptanceStore(tmp_path / 'state.sqlite'), FakeStorage()
    service = BackendService(store=db)
    artifacts = SupabaseArtifactStore(transport, authorize_run=service.get_run)

    class ExpiringEngine:
        def __init__(self, root, reports, **kwargs):
            self.root = root

        def execute(self, lease, stage, cancelled):
            stage(CodeStage.CAPTURE)
            directory = self.root / lease.run.run_id / 'engine'
            directory.mkdir(parents=True)
            (directory / 'candidate.v1.json').write_bytes(b'{"fixture":"NON_AI"}')
            with db.transaction() as connection:
                connection.execute('UPDATE runs SET lease_expires=0 WHERE run_id=?', (lease.run.run_id,))
            raise BackendError('ENGINE_TIMEOUT', 'Synthetic expiry')

    executor = OnDemandMockExecutor(service, artifacts, record_artifact=db.record_artifact_ref,
                                    engine_factory=ExpiringEngine)
    app = build_cloud_app(config(), store=db, transport=transport, identity=identity, executor=executor)
    with TestClient(app) as client:
        _, run = prepare(client)
        path = f"/v1/runs/{run['run_id']}"
        response = client.post(path + '/execute', headers=HEADERS, json={'expected_revision': 1})
        assert response.json()['status'] == 'running'  # expired lease is not a success or a retry
        assert not transport.calls and not db.refs
        revision = response.json()['revision']
        assert client.post(path + '/reconcile', headers=HEADERS,
                           json={'expected_revision': revision}).json()['status'] == 'needs_reconciliation'


def test_cancellation_during_publication_preserves_remaining_artifacts_without_reposting(tmp_path):
    db, transport = LocalAcceptanceStore(tmp_path / 'state.sqlite'), FakeStorage()
    service = BackendService(store=db)
    artifacts = SupabaseArtifactStore(transport, authorize_run=service.get_run)
    principal = Principal(owner_id=OWNER)

    class FinishedEngine:
        def __init__(self, root, reports, **kwargs):
            self.root = root

        def execute(self, lease, stage, cancelled):
            for value in CodeStage:
                stage(value)
            directory = self.root / lease.run.run_id / 'engine'
            directory.mkdir(parents=True)
            for name in ('candidate.v1.json', 'broker-artifact.v1.json',
                         'generation-dispatch.v1.private.json', 'generation-result.v1.private.json',
                         'evaluation-receipt.v1.json', 'evaluation-manifest.v1.json'):
                (directory / name).write_bytes(b'{"fixture":"NON_AI"}')
            (directory / 'G3_report.json').write_bytes(b'{}')
            return EngineResult(stop_reason='completed_mock_run')

    def record_and_cancel(owner, run_id, reference, *, lease_token):
        db.record_artifact_ref(owner, run_id, reference, lease_token=lease_token)
        if len(db.refs) == 1:
            current = service.get_run(principal, run_id)
            service.cancel_run(principal, run_id, current.revision)

    executor = OnDemandMockExecutor(service, artifacts, record_artifact=record_and_cancel,
                                    engine_factory=FinishedEngine)
    app = build_cloud_app(config(), store=db, transport=transport, identity=identity, executor=executor)
    with TestClient(app) as client:
        _, run = prepare(client)
        path = f"/v1/runs/{run['run_id']}"
        result = client.post(path + '/execute', headers=HEADERS, json={'expected_revision': 1})
        assert result.json()['status'] == 'cancelled'
        assert len(db.refs) == 7
        posts = [url for method, url, _ in transport.calls if method == 'POST']
        assert len(posts) == len(set(posts)) == 7
        assert client.get(path + '/report', headers=HEADERS).status_code == 404


def test_partial_archive_rejects_hard_linked_secret(tmp_path):
    db, transport = LocalAcceptanceStore(tmp_path / 'state.sqlite'), FakeStorage()
    service = BackendService(store=db)
    artifacts = SupabaseArtifactStore(transport, authorize_run=service.get_run)
    secret = tmp_path / 'secret'
    secret.write_bytes(b'PRIVATE_SECRET_SENTINEL')

    class UnsafeEngine:
        def __init__(self, root, reports, **kwargs):
            self.root = root

        def execute(self, lease, stage, cancelled):
            directory = self.root / lease.run.run_id / 'engine'
            directory.mkdir(parents=True)
            try:
                (directory / 'candidate.v1.json').hardlink_to(secret)
            except OSError:
                pytest.skip('Local filesystem does not support hard links')
            raise BackendError('ENGINE_TIMEOUT', 'Synthetic interruption')

    executor = OnDemandMockExecutor(service, artifacts, record_artifact=db.record_artifact_ref,
                                    engine_factory=UnsafeEngine)
    app = build_cloud_app(config(), store=db, transport=transport, identity=identity, executor=executor)
    with TestClient(app) as client:
        _, run = prepare(client)
        result = client.post(f"/v1/runs/{run['run_id']}/execute", headers=HEADERS,
                             json={'expected_revision': 1})
        assert result.json()['status'] == 'needs_reconciliation'
        assert not transport.calls and not db.refs


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
