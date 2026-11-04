"""No-billing acceptance for the opt-in live Muse repair integration.

All model and reference calls are injected fakes. These tests do NOT
establish real Meta provider success or held-out conformance.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import muse_pipeline_repair as repair  # noqa: E402


def fixture():
    spec = {"users": {"alice": "bench_alice"}, "auth": {},
            "routes": [{"method": "GET", "path": "/projects",
                        "kind": "compiled_list", "collection": "projects",
                        "status": 200, "access": "owner", "auth": True,
                        "validate": [], "template": [{"id": "<new_id>"}]}]}
    baseline = {"public_passed": 5, "public_total": 6,
                "divergences": [{"action": "GET /projects",
                                 "reference": [200, [{"id": "1"}]],
                                 "candidate": [403, {"error": "forbidden"}]}]}
    return spec, baseline


def proposal(**values):
    route = {"method": "GET", "path": "/projects", "template_unchanged": True}
    route.update(values)
    return json.dumps({"route": route})


def test_valid_model_edit_only_keeps_if_public_replay_improves():
    spec, baseline = fixture()
    events, calls = [], []
    def call(prompt, audit):
        assert "PUBLIC DIFFERENTIAL DATA" in prompt
        calls.append(prompt)
        audit("model_dispatch", {"provider": "meta-direct"})
        return proposal(access="shared_read"), {"response_id": "synthetic-test"}
    def measure(candidate):
        access = candidate["routes"][0]["access"]
        return {"public_passed": 6 if access == "shared_read" else 5,
                "public_total": 6, "divergences": []}
    final, scores, model = repair.attempt_muse_public_repair(
        compiled=spec, observations=[], baseline=baseline, measure=measure,
        api_key="", model_call=call,
        record_audit=lambda kind, payload: events.append((kind, payload)))
    assert len(calls) == 1
    assert model["called"] and model["accepted"]
    assert model["outcome"] == "accepted_public_improvement"
    assert scores["public_passed"] == 6
    assert final["routes"][0]["access"] == "shared_read"
    assert final["routes"][0]["template"] == spec["routes"][0]["template"]
    assert spec["routes"][0]["access"] == "owner"  # source unchanged
    assert events[0][0] == "model_dispatch"


def test_valid_model_edit_rejected_when_public_gate_does_not_improve():
    spec, baseline = fixture()
    def call(prompt, audit):
        return proposal(status=201), {"response_id": "synthetic-test"}
    def measure(candidate):
        return {"public_passed": 5, "public_total": 6, "divergences": []}
    selected, score, model = repair.attempt_muse_public_repair(
        compiled=spec, observations=[], baseline=baseline,
        measure=measure, api_key="", model_call=call,
        record_audit=lambda *a: None)
    assert model["called"] and not model["accepted"]
    assert model["outcome"] == "rejected_no_public_improvement"
    assert selected == spec and score["public_passed"] == 5


@pytest.mark.parametrize("response", [
    proposal(template={"stolen": True}),
    proposal(method="POST"),
    proposal(status=True),
    proposal(admin_override=True),
    json.dumps({"routes": []}),
    "not JSON",
])
def test_unsafe_or_invalid_candidate_fails_closed(response):
    spec, baseline = fixture()
    with pytest.raises(ValueError):
        repair.admit_route_patch(spec, spec["routes"][0], response)


def test_failed_provider_is_unscored_and_compiler_is_preserved():
    spec, baseline = fixture()
    def fail(prompt, audit):
        raise RuntimeError("simulated provider disconnect")
    selected, score, model = repair.attempt_muse_public_repair(
        compiled=spec, observations=[], baseline=baseline,
        measure=lambda x: pytest.fail("must not measure a failed model output"),
        api_key="", model_call=fail, record_audit=lambda *a: None)
    assert model["called"] and not model["accepted"]
    assert model["outcome"] == "provider_or_admission_failed"
    assert "simulated provider disconnect" not in json.dumps(model)
    assert selected == spec and score == baseline


def test_no_divergence_does_not_spend():
    spec, _ = fixture()
    baseline = {"public_passed": 6, "public_total": 6, "divergences": []}
    selected, _, model = repair.attempt_muse_public_repair(
        compiled=spec, observations=[], baseline=baseline,
        measure=lambda x: pytest.fail("no replay necessary"),
        api_key="unused", record_audit=lambda *a: None,
        model_call=lambda *a: pytest.fail("no model call necessary"))
    assert selected == spec and model["called"] is False
    assert model["outcome"] == "no_editable_divergence"


def test_paid_mode_requires_explicit_server_opt_in(monkeypatch):
    from fastapi.testclient import TestClient
    import investigation_engine as engine
    monkeypatch.delenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", raising=False)
    monkeypatch.setenv("MODEL_API_KEY", "synthetic-do-not-use")
    monkeypatch.setattr(engine, "run_investigation", lambda _id: None)
    client = TestClient(engine.app)
    blocked = client.post("/engine/v1/investigations",
                          json={"target": "vikunja-v1", "model_mode": "muse-repair"})
    assert blocked.status_code == 409
    monkeypatch.setenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", "true")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    blocked = client.post("/engine/v1/investigations",
                          json={"target": "vikunja-v1", "model_mode": "muse-repair"})
    assert blocked.status_code == 503
    monkeypatch.setenv("MODEL_API_KEY", "synthetic-do-not-use")
    blocked = client.post("/engine/v1/investigations",
                          json={"target": "filebrowser-v1", "model_mode": "muse-repair"})
    assert blocked.status_code == 422
    admitted = client.post("/engine/v1/investigations",
                          json={"target": "vikunja-v1", "model_mode": "muse-repair"})
    assert admitted.status_code == 200
    assert admitted.json()["model_mode"] == "muse-repair"


def test_local_candidate_remains_downloadable_after_restart(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import investigation_engine as engine
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    inv_id = "inv-a1b2c3d4e5f6"
    spec = {"users": {}, "routes": [{"method": "GET", "path": "/projects"}]}
    rec = {"id": inv_id, "target": "vikunja-v1", "status": "completed",
           "compiled": {"provenance": "EVIDENCE_COMPILED"}, "_spec": spec}
    engine._persist_completed_record(rec)
    assert (tmp_path / f"{inv_id}-candidate.json").is_file()
    assert not (tmp_path / f"{inv_id}.json").read_text().count('"_spec"')
    client = TestClient(engine.app)
    saved = client.get(f"/engine/v1/investigations/{inv_id}")
    assert saved.status_code == 200
    assert saved.json()["candidate_artifact"]["size_bytes"] > 0
    candidate = client.get(f"/engine/v1/investigations/{inv_id}/candidate")
    assert candidate.status_code == 200 and candidate.json() == spec
    report = client.get(f"/engine/v1/investigations/{inv_id}/report")
    assert report.status_code == 200
    assert "Candidate SHA-256" in report.text
    assert "NOT held-out" in report.text
    assert "content-disposition" in report.headers
