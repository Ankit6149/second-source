"""Local investigation engine: contract + honesty-boundary tests.

Uses FastAPI TestClient with the pipeline monkeypatched (no Vikunja
binary, no network). The live end-to-end run is exercised separately
against the real reference.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import investigation_engine as engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_engine_never_imports_held_out():
    src = Path(engine.__file__).read_text(encoding="utf-8")
    assert "vikunja_held_out" not in src
    assert "HELD_OUT" not in src


def test_health_and_targets_contract():
    client = TestClient(engine.app)
    health = client.get("/engine/v1/health").json()
    assert health["ok"] is True and health["model_calls"] is False
    targets = client.get("/engine/v1/targets").json()
    assert targets[0]["id"] == "vikunja-v1"
    assert targets[0]["provenance"] == "NON_AI"


def test_unknown_target_rejected():
    client = TestClient(engine.app)
    resp = client.post("/engine/v1/investigations", json={"target": "nope"})
    assert resp.status_code == 400


def test_investigation_lifecycle_and_candidate(monkeypatch):
    def fake_run(inv_id):
        rec = engine.INVESTIGATIONS[inv_id]
        rec.update(status="completed", stage="completed",
                   observations={"count": 20, "sha256": "sha256:x"},
                   compiled={"routes": ["GET /projects"],
                             "provenance": "EVIDENCE_COMPILED",
                             "label": "NON_AI"},
                   public_conformance={"passed": 19, "total": 19,
                                       "divergences": []},
                   held_out={"status": "not_run_by_engine"},
                   model={"called": False},
                   _spec={"users": {}, "routes": []})
    monkeypatch.setattr(engine, "run_investigation", fake_run)
    client = TestClient(engine.app)
    created = client.post("/engine/v1/investigations",
                          json={"target": "vikunja-v1"})
    # Thread runs the fake synchronously enough for test client polling;
    # call it directly to be deterministic.
    inv_id = created.json()["id"]
    fake_run(inv_id)
    got = client.get(f"/engine/v1/investigations/{inv_id}").json()
    assert got["status"] == "completed"
    assert got["public_conformance"]["passed"] == 19
    assert "_spec" not in got  # private spec never leaks into the view
    cand = client.get(f"/engine/v1/investigations/{inv_id}/candidate")
    assert cand.status_code == 200
    assert cand.json() == {"users": {}, "routes": []}
    missing = client.get("/engine/v1/investigations/inv-nope")
    assert missing.status_code == 404


import threading as _threading  # noqa: E402


def _client(monkeypatch, run=None):
    monkeypatch.setattr(engine, "run_investigation", run or (lambda i: None))
    return TestClient(engine.app, raise_server_exceptions=False)


def test_cors_allows_local_and_rejects_remote_origin(monkeypatch):
    client = _client(monkeypatch)
    local = client.get("/engine/v1/health",
                       headers={"Origin": "http://127.0.0.1:5173"})
    assert local.status_code == 200
    assert local.headers.get("access-control-allow-origin") == \
        "http://127.0.0.1:5173"
    evil = client.get("/engine/v1/health",
                      headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert "access-control-allow-origin" not in evil.headers
    preflight = client.options(
        "/engine/v1/investigations",
        headers={"Origin": "https://evil.example",
                 "Access-Control-Request-Method": "POST"})
    assert preflight.status_code in (400, 403)
    assert preflight.headers.get("access-control-allow-origin") != "*"


def test_remote_origin_cannot_create_investigation(monkeypatch):
    calls = []
    client = _client(monkeypatch, lambda i: calls.append(i))
    resp = client.post("/engine/v1/investigations",
                       json={"target": "vikunja-v1"},
                       headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403 and calls == []


def test_request_validation_rejects_bad_bodies(monkeypatch):
    client = _client(monkeypatch)
    for payload in ({}, {"target": 7}, {"target": ""},
                    {"target": "vikunja-v1", "extra": 1},
                    {"target": "x" * 65}):
        assert client.post("/engine/v1/investigations",
                           json=payload).status_code == 422, payload
    assert client.post("/engine/v1/investigations",
                       content="not-json",
                       headers={"Content-Type": "application/json"}
                       ).status_code == 422


def test_oversized_body_rejected(monkeypatch):
    client = _client(monkeypatch)
    big = {"target": "vikunja-v1", "pad": "x" * engine.MAX_BODY_BYTES}
    assert client.post("/engine/v1/investigations",
                       json=big).status_code in (413, 422)


def test_idempotency_key_reuses_investigation(monkeypatch):
    calls = []
    client = _client(monkeypatch, lambda i: calls.append(i))
    h = {"Idempotency-Key": "req-1"}
    a = client.post("/engine/v1/investigations",
                    json={"target": "vikunja-v1"}, headers=h)
    b = client.post("/engine/v1/investigations",
                    json={"target": "vikunja-v1"}, headers=h)
    assert a.status_code == b.status_code == 200
    assert a.json()["id"] == b.json()["id"]
    assert len(calls) == 1
    bad = client.post("/engine/v1/investigations",
                      json={"target": "vikunja-v1"},
                      headers={"Idempotency-Key": "x" * 129})
    assert bad.status_code == 400


def test_cancellation_is_idempotent_and_worker_cooperates(monkeypatch):
    real_run = engine.run_investigation
    client = _client(monkeypatch)
    inv_id = client.post("/engine/v1/investigations",
                         json={"target": "vikunja-v1"}).json()["id"]
    first = client.post(f"/engine/v1/investigations/{inv_id}/cancel")
    assert first.status_code == 200
    assert first.json()["cancel_requested"] is True
    second = client.post(f"/engine/v1/investigations/{inv_id}/cancel")
    assert second.status_code == 200
    assert client.post("/engine/v1/investigations/inv-000000000000/cancel"
                       ).status_code == 404
    started = []
    monkeypatch.setattr(engine.mx, "start_reference",
                        lambda p: started.append(p))
    real_run(inv_id)
    assert engine.INVESTIGATIONS[inv_id]["status"] == "cancelled"
    assert started == []


def test_concurrent_creates_are_unique_and_consistent(monkeypatch):
    client = _client(monkeypatch)
    ids, errors = [], []

    def make(n):
        try:
            r = client.post("/engine/v1/investigations",
                            json={"target": "vikunja-v1"},
                            headers={"Idempotency-Key": f"k-{n}"})
            ids.append(r.json()["id"])
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [_threading.Thread(target=make, args=(n,)) for n in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(set(ids)) == 16
    for inv_id in ids:
        assert client.get(
            f"/engine/v1/investigations/{inv_id}").status_code == 200


def test_invalid_id_and_pruning_bound_state(monkeypatch, tmp_path):
    client = _client(monkeypatch)
    assert client.get("/engine/v1/investigations/..%2fsecret"
                      ).status_code in (404, 405)
    assert client.get("/engine/v1/investigations/inv-nope"
                      ).status_code == 404
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    monkeypatch.setattr(engine, "MAX_INVESTIGATIONS", 3)
    with engine._STATE_LOCK:
        engine.INVESTIGATIONS.clear()
        engine._IDEMPOTENCY.clear()
        for n in range(5):
            engine.INVESTIGATIONS[f"inv-{n:012d}"] = {
                "id": f"inv-{n:012d}", "status": "completed",
                "created_at": n}
        engine._prune_locked()
    assert len(engine.INVESTIGATIONS) == 3
    assert "inv-000000000000" not in engine.INVESTIGATIONS
