"""Prompt wiring tests for the generic field inventory (NON_AI).

The extractor itself is scripts/field_inventory.py (tested in
tests/test_field_inventory.py). These tests only verify that the
model experiment delegates to it, appends its block to observation
arms, and enforces the JSON-first contract — using an invented
non-Vikunja target so nothing here is target-specific.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "vikunja_model_experiment", ROOT / "scripts" / "vikunja_model_experiment.py")
mx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mx)

OBS = [
    {"action": "POST /v9/widgets", "status": 201,
     "body": {"wid": 3, "gadget_state": "idle", "charged_at": None}},
    {"action": "GET /v9/widgets", "status": 200,
     "body": [{"wid": 3, "charged_at": "0001-01-01T00:00:00Z"}]},
    {"action": "POST /v9/widgets", "status": 422,
     "body": {"problem": "bad gadget"}},
]


def test_inventory_text_delegates_to_generic_extractor():
    text = mx.field_inventory_text(OBS)
    assert "FIELD INVENTORY" in text
    assert "POST /v9/widgets" in text
    assert "charged_at: null" in text
    assert "zero_time" in text
    assert "[error] problem" in text


def test_inventory_text_accepts_json_text_and_rejects_bad_input():
    assert mx.field_inventory_text(json.dumps(OBS)) == \
        mx.field_inventory_text(OBS)
    assert mx.field_inventory_text("not json") == ""
    assert mx.field_inventory_text([]) == ""


def test_build_prompt_appends_inventory_and_json_first():
    prompt = mx.build_prompt("C_grounded", json.dumps(OBS))
    assert "FIELD INVENTORY" in prompt
    assert "gadget_state" in prompt
    assert prompt.rstrip().endswith(mx.JSON_FIRST)
    assert "FIRST character" in prompt and "'{'" in prompt


def test_prior_arm_gets_json_first_but_no_inventory_or_observations():
    prompt = mx.build_prompt("A_prior", json.dumps(OBS))
    assert "FIELD INVENTORY" not in prompt
    assert "gadget_state" not in prompt
    assert prompt.rstrip().endswith(mx.JSON_FIRST)


def test_extra_observations_get_their_own_inventory():
    prompt = mx.build_prompt("C_grounded", json.dumps(OBS),
                             json.dumps(OBS[:1]))
    assert prompt.count("FIELD INVENTORY") == 2


def test_selection_prompt_is_json_first():
    prompt = mx.build_selection_prompt(json.dumps(OBS))
    assert "FIRST character" in prompt
    assert '{"probes":' in prompt


def test_prompt_works_unchanged_for_a_swapped_target():
    other = [{"action": "GET /healthz", "status": 200,
              "body": {"ok": True}}]
    prompt = mx.build_prompt("B_observations", json.dumps(other))
    assert "GET /healthz" in prompt and "ok: bool" in prompt


def test_call_budgets_unchanged():
    assert mx.ALL_ARMS == ["A_prior", "B_observations",
                           "C_grounded", "D_active"]
