"""Native PG + HTTP + real NON_AI fixture; Auth/Storage remain test substitutes."""
from fastapi.testclient import TestClient

from second_source.backend.asgi import build_cloud_app
from second_source.backend.artifacts import verify_bundle
from test_backend_cloud_app import config, prepare, TOKEN, OTHER as OTHER_TOKEN, HEADERS
from test_backend_cloud_artifacts import FakeStorage
from test_backend_postgres_native import native, OWNER, OTHER


def test_native_authenticated_http_actual_fixture_durable_export_and_restart(native):
    transport = FakeStorage()

    def identity(token):
        return OWNER if token == TOKEN else OTHER if token == OTHER_TOKEN else None

    app = build_cloud_app(config(), store=native.store, transport=transport, identity=identity)
    with TestClient(app) as client:
        assert client.get("/health/ready").json() == {"status": "ok"}
        _, run = prepare(client)
        path = f"/v1/runs/{run['run_id']}"
        completed = client.post(path + "/execute", headers=HEADERS, json={"expected_revision": 1})
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "completed", completed.text
        result = completed.json()["result"]
        assert result["real"] is False and result["origin"] == "mock"
        assert result["evaluation"] == {"passed": 22, "failed": 3, "indeterminate": 0, "total": 25}
        assert len(native.store.artifact_refs(OWNER, run["run_id"])) >= 6
        calls = len(transport.calls)
        assert client.post(path + "/execute", headers=HEADERS, json={"expected_revision": 1}).json() == completed.json()
        assert len(transport.calls) == calls
        proof = client.get(path + "/export.zip", headers=HEADERS).content
        assert verify_bundle(proof)["valid"]
        assert client.get(path + "/report", headers={"Authorization": "Bearer " + OTHER_TOKEN}).status_code == 404
    restarted = build_cloud_app(config(False), store=native.store, transport=transport, identity=identity)
    with TestClient(restarted) as client:
        assert client.get(path, headers=HEADERS).json() == completed.json()
        assert client.get(path + "/export.zip", headers=HEADERS).content == proof
