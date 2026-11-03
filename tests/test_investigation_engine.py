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
