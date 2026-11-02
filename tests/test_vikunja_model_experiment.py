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
