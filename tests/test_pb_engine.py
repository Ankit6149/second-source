"""PocketBase engine target: contract, Muse gate, and pipeline with stubs.

No PocketBase server, no model calls, no spend: references and the
model stage are monkeypatched. Live runs stay operator-side work.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import investigation_engine as engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_health_reports_muse_targets_and_vision(monkeypatch):
    monkeypatch.delenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("SECOND_SOURCE_VISION_ENDPOINT", raising=False)
    health = TestClient(engine.app).get("/engine/v1/health").json()
    assert health["ok"] is True
    assert health["model_calls"] is False
    assert health["muse_repair_targets"] == ["pocketbase-v1", "vikunja-v1"]
    assert health["vision"]["motion_physics"] == "local-non-ai"
    assert health["vision"]["regions"] == "unconfigured"


def test_targets_list_pocketbase_with_model_repair_flag():
    by_id = {t["id"]: t for t in TestClient(engine.app).get("/engine/v1/targets").json()}
    assert by_id["pocketbase-v1"]["label"].startswith("PocketBase v0.28.4")
    assert by_id["pocketbase-v1"]["pipeline"] == ["probe", "compile", "differential-cases"]
    assert by_id["pocketbase-v1"]["model_repair"] is True
    assert by_id["vikunja-v1"]["model_repair"] is True
    assert by_id["filebrowser-v1"]["model_repair"] is False
    assert by_id["gitea-v1"]["model_repair"] is False


def test_muse_repair_gate_per_target(monkeypatch):
    monkeypatch.setattr(engine, "run_investigation", lambda i: None)
    client = TestClient(engine.app, raise_server_exceptions=False)
    resp = client.post("/engine/v1/investigations",
                       json={"target": "filebrowser-v1", "model_mode": "muse-repair"})
    assert resp.status_code == 422
    monkeypatch.delenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", raising=False)
    resp = client.post("/engine/v1/investigations",
                       json={"target": "pocketbase-v1", "model_mode": "muse-repair"})
    assert resp.status_code == 409
    monkeypatch.setenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", "true")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    resp = client.post("/engine/v1/investigations",
                       json={"target": "pocketbase-v1", "model_mode": "muse-repair"})
    assert resp.status_code == 503


def test_pb_conformance_shape_with_stubs(monkeypatch):
    monkeypatch.setattr(engine, "_pb_start_candidate", lambda spec, procs, tag: "http://c:1")
    monkeypatch.setattr(engine.fb, "call", lambda *a, **k: (200, {}))
    monkeypatch.setattr(engine.fb, "token_of", lambda *a, **k: (200, "tok"))
    monkeypatch.setattr(engine.pb, "_cases_ref", lambda: {"a": (200,), "b": (200,)})
    monkeypatch.setattr(engine.pb, "_cases_cand", lambda c, t: {"a": (200,), "b": (500,)})
    conf = engine._pb_conformance({"routes": []}, [], "t")
    assert conf["public_passed"] == 1 and conf["public_total"] == 2
    assert conf["divergences"][0]["action"] == "b"


def _rec(**over):
    base = {"id": "inv-abcdef123456", "target": "pocketbase-v1",
            "status": "running", "stage": "queued",
            "provenance": "NON_AI", "model_mode": "none",
            "_cancel": threading.Event()}
    base.update(over)
    return base


def test_run_pocketbase_deterministic_path(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    monkeypatch.setattr(engine, "_pb_available", lambda: True)
    monkeypatch.setattr(engine.pb, "public_probes", lambda: [{"action": "GET /x"}])
    monkeypatch.setattr(engine.fb, "compile_spec",
                        lambda obs, digest: {"routes": [{"method": "GET", "path": "/x"}]})
    monkeypatch.setattr(engine, "_pb_conformance",
                        lambda spec, procs, tag: {"public_passed": 2, "public_total": 2,
                                                  "divergences": []})
    rec = _rec()
    engine._run_pocketbase(rec)
    assert rec["status"] == "completed"
    assert rec["public_conformance"] == {"passed": 2, "total": 2, "divergences": []}
    assert rec["model"] == {"called": False, "mode": "none",
                            "reason": "Deterministic NON_AI compiler only."}
    assert rec["compiled"]["provenance"] == "EVIDENCE_COMPILED"
    assert (tmp_path / "inv-abcdef123456.json").is_file()


def test_run_pocketbase_muse_accepted_path(monkeypatch, tmp_path):
    import muse_pipeline_repair as repair
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    monkeypatch.setattr(engine, "_pb_available", lambda: True)
    monkeypatch.setattr(engine.pb, "public_probes", lambda: [{"action": "GET /x"}])
    monkeypatch.setattr(engine.fb, "compile_spec",
                        lambda obs, digest: {"routes": [{"method": "GET", "path": "/x"}]})
    monkeypatch.setattr(engine, "_pb_conformance",
                        lambda spec, procs, tag: {"public_passed": 1, "public_total": 2,
                                                  "divergences": []})
    patched = {"routes": [{"method": "GET", "path": "/x", "kind": "list"}]}
    improved = {"public_passed": 2, "public_total": 2, "divergences": []}
    summary = {"called": True, "mode": "muse-public-repair", "accepted": True,
               "outcome": "accepted_public_improvement",
               "receipt": {"response_id": "r1", "input_tokens": 10,
                           "output_tokens": 5, "estimated_cost_usd": 0.01}}
    monkeypatch.setattr(repair, "attempt_muse_public_repair",
                        lambda **kw: (patched, improved, summary))
    monkeypatch.setenv("MODEL_API_KEY", "test-only-fake-key")
    monkeypatch.setenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", "true")
    rec = _rec(model_mode="muse-repair")
    engine._run_pocketbase(rec)
    assert rec["status"] == "completed"
    assert rec["compiled"]["provenance"] == "REAL_MODEL_ASSISTED"
    assert rec["model"]["receipt"]["estimated_cost_usd"] == 0.01
    assert (tmp_path / "inv-abcdef123456-muse-private-receipts.jsonl").is_file() is False


def test_pb_report_includes_model_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    (tmp_path / "inv-abcdef123456.json").write_text(
        '{"status": "completed", "target": "pocketbase-v1", '
        '"candidate_artifact": {"provenance": "REAL_MODEL_ASSISTED", "sha256": "s"}, '
        '"observations": {"count": 14, "sha256": "sha256:o"}, '
        '"public_conformance": {"passed": 12, "total": 12, "divergences": []}, '
        '"model": {"called": true, "mode": "muse-public-repair", '
        '"outcome": "accepted_public_improvement", "accepted": true, '
        '"receipt": {"response_id": "resp_9", "input_tokens": 1200, '
        '"output_tokens": 300, "estimated_cost_usd": 0.02}}}', encoding="utf-8")
    resp = TestClient(engine.app).get("/engine/v1/investigations/inv-abcdef123456/report")
    assert resp.status_code == 200
    assert "resp_9" in resp.text
    assert "in=1200" in resp.text and "out=300" in resp.text
    assert "~$0.02" in resp.text


def test_spend_cap_blocks_muse_repair_at_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "run_investigation", lambda i: None)
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    monkeypatch.setenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", "true")
    monkeypatch.setenv("MODEL_API_KEY", "test-only-fake-key")
    (tmp_path / "spend.json").write_text('{"total_estimated_usd": 15.0}',
                                         encoding="utf-8")
    client = TestClient(engine.app, raise_server_exceptions=False)
    resp = client.post("/engine/v1/investigations",
                       json={"target": "pocketbase-v1", "model_mode": "muse-repair"})
    assert resp.status_code == 402
    (tmp_path / "spend.json").write_text('{"total_estimated_usd": 14.0}',
                                         encoding="utf-8")
    resp = client.post("/engine/v1/investigations",
                       json={"target": "pocketbase-v1", "model_mode": "muse-repair"})
    assert resp.status_code == 200


def test_spend_ledger_accumulates_and_health_reports(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    monkeypatch.delenv("SECOND_SOURCE_MAX_SPEND_USD", raising=False)
    assert engine._record_spend_usd(0.5, "inv-1") == 0.5
    assert engine._record_spend_usd(0.25, "inv-2") == 0.75
    assert engine._record_spend_usd(0.0, "inv-3") == 0.75
    health = TestClient(engine.app).get("/engine/v1/health").json()
    assert health["spend"] == {"used_usd": 0.75, "cap_usd": 15.0}


def test_dispatch_routes_pocketbase(monkeypatch):
    seen = []
    monkeypatch.setattr(engine, "_run_pocketbase", lambda rec: seen.append(rec["id"]))
    engine.INVESTIGATIONS["inv-abcdef123456"] = _rec()
    try:
        engine.run_investigation("inv-abcdef123456")
    finally:
        engine.INVESTIGATIONS.pop("inv-abcdef123456", None)
    assert seen == ["inv-abcdef123456"]
