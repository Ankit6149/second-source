"""Admission and schema-validation tests for the model experiment (NON_AI)."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "vikunja_model_experiment", ROOT / "scripts" / "vikunja_model_experiment.py")
mx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mx)


def oracle():
    return json.loads((ROOT / "scripts" / "vikunja_oracle_spec.json").read_text())


def test_oracle_spec_is_schema_valid():
    assert mx.validate_spec(oracle()) == []


def test_bad_kind_rejected():
    spec = oracle()
    spec["routes"][0]["kind"] = "teleport_project"
    assert any("kind" in e for e in mx.validate_spec(spec))


def test_bad_status_rejected():
    spec = oracle()
    spec["routes"][0]["status"] = "two hundred"
    assert any("status" in e for e in mx.validate_spec(spec))


def test_missing_users_rejected():
    spec = oracle()
    del spec["users"]
    assert mx.validate_spec(spec)


def test_schema_rejected_spec_is_not_admitted():
    spec = oracle()
    spec["routes"] = []
    record = mx.evaluate_spec("bad", spec, "http://127.0.0.1:9", 3599)
    assert record["admitted"] is False
    assert record["failure_class"] == "SCHEMA_REJECTED"
    assert "passed" not in record


def test_arms_are_prompt_conditions_not_active_except_d():
    # Guard the honesty delimiter: A/B/C prompts differ, D has a menu.
    assert "A_prior" in mx.ARMS and "D_active" not in mx.ARMS
    assert len(mx.PROBE_MENU) >= 5


def test_menu_execution_against_live_reference():
    # Arm D execution (D3 labels + D7 unshare exercise typed id
    # substitution in bodies AND paths). Skips without a reference.
    import urllib.request
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:3456/api/v1/info", timeout=5) as resp:
            assert resp.status == 200
    except Exception:
        import pytest
        pytest.skip("no Vikunja reference on 127.0.0.1:3456")
    obs = mx.execute_menu_probes(["D3_labels", "D7_unshare"],
                                 "http://127.0.0.1:3456")
    by_probe = {}
    for o in obs:
        by_probe.setdefault(o["probe"], []).append(o["status"])
    assert by_probe["D3_labels"][0] == 201
    assert by_probe["D7_unshare"][-1] == 403  # revoked: bob can no longer read


def test_validate_rule_status_must_be_http_status():
    spec = oracle()
    spec["routes"][0]["validate"] = [{"field": "title", "rule": "nonempty", "status": 0, "error_body": {"code": 0, "message": "x"}}]
    assert any("validate status" in e for e in mx.validate_spec(spec))


def test_validate_rule_error_body_shape_checked():
    spec = oracle()
    spec["routes"][0]["validate"] = [{"field": "title", "rule": "nonempty", "status": 400, "error_body": {"code": "400", "message": "x"}}]
    assert any("error_body" in e for e in mx.validate_spec(spec))


def test_selection_schema_enumerates_exactly_the_menu():
    enum = mx.SELECTION_SCHEMA["properties"]["probes"]["items"]["enum"]
    assert set(enum) == set(mx.PROBE_MENU)
    assert mx.SELECTION_SCHEMA["required"] == ["probes"]
