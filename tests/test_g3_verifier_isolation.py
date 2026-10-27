"""Model-request boundary probes use synthetic canaries and MockProvider only."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from second_source.candidate_adapter import CandidateExecutionLimits, _run_worker
from second_source.candidate_generation import build_generation_context
from second_source.g3_verification import EvaluationBlocked, load_sealed_suite, prepare_generation_request, seal_owned_ledger_suite

ROOT = Path(__file__).resolve().parents[1]


def approved_context():
    observation = {
        "observation_id": "public:0", "sequence_id": "public", "action_index": 0,
        "input_action": {"command": "list"}, "output": {"ok": True, "items": []},
        "exit_code": 0, "duration_ms": 0, "status": "ok",
    }
    digest = hashlib.sha256(json.dumps(observation, sort_keys=True).encode()).hexdigest()
    context = build_generation_context(
        scope_goal="Reconstruct authorized public ledger behavior", requirement_ids=["REQ-LEDGER"],
        allowed_commands=["add", "list", "total", "remove"], excluded_subsystems=["payments"],
        public_command_manifest=json.loads((ROOT / "fixtures/owned_ledger/public_contract.json").read_bytes()),
        redacted_views=[{"digest": digest, "observation": observation}],
        hypotheses=[{"id": "public-hypothesis", "statement": "List returns record items", "evidence_ids": [digest]}],
    )
    return context, {digest: deepcopy(observation)}


def test_isolated_generation_request_contains_no_tools_gold_or_environment(monkeypatch):
    context, registry = approved_context()
    monkeypatch.setenv("SYNTHETIC_SECRET", "ENV_SYNTHETIC_CANARY")
    request = prepare_generation_request(context, approved_evidence=registry,
        forbidden_markers=("ENV_SYNTHETIC_CANARY", "SEALED_SYNTHETIC_CANARY", "fixtures/owned_ledger/reference.py"))
    assert request["stage"] == "synthesize" and "tools" not in request
    assert "JSON Schema:" in request["messages"][0]["content"]
    assert len(request["messages"]) == 3
    assert "hypothesis" in json.dumps(request)


@pytest.mark.parametrize("kind", ["unknown_evidence", "changed_observation", "injected_root", "forged_hypothesis"])
def test_generation_context_contamination_is_rejected(kind):
    context, registry = approved_context()
    if kind == "unknown_evidence":
        context["evidence"][0]["digest"] = "0" * 64
    elif kind == "changed_observation":
        context["evidence"][0]["observation"]["output"]["source"] = "SOURCE_SYNTHETIC_CANARY"
    elif kind == "injected_root":
        context["reference_source"] = "SOURCE_SYNTHETIC_CANARY"
    else:
        context["hypotheses"][0]["evidence_ids"] = ["0" * 64]
    with pytest.raises(EvaluationBlocked):
        prepare_generation_request(context, approved_evidence=registry)


def test_canary_scan_covers_approved_fields_and_final_gateway_schema():
    context, registry = approved_context()
    context["scope"]["goal"] = "Reconstruct behavior GOLD_SYNTHETIC_CANARY"
    with pytest.raises(EvaluationBlocked, match="Protected material"):
        prepare_generation_request(context, approved_evidence=registry, forbidden_markers=("GOLD_SYNTHETIC_CANARY",))
    context, registry = approved_context()
    with pytest.raises(EvaluationBlocked, match="Protected material"):
        prepare_generation_request(context, approved_evidence=registry, forbidden_markers=("JSON Schema:",))


def test_private_suite_identifiers_do_not_enter_model_request(cli_scope, tmp_path):
    path, digest = seal_owned_ledger_suite(tmp_path / "evaluator", cli_scope)
    suite = load_sealed_suite(path, digest, cli_scope)
    context, registry = approved_context()
    request = prepare_generation_request(context, approved_evidence=registry,
        forbidden_markers=tuple(case.case_id for case in suite.cases()))
    assert str(path) not in json.dumps(request)


@pytest.mark.parametrize("mode", ["probe", "generation_probe"])
def test_both_workers_are_denied_actual_reference_source_and_external_gold(mode, tmp_path):
    gold = tmp_path / "gold-canary"
    gold.write_text("SYNTHETIC_GOLD_CANARY")
    for path in (ROOT / "fixtures/owned_ledger/reference.py", gold):
        response = _run_worker(mode, {"path": str(path)}, CandidateExecutionLimits())
        assert all(response["checks"].values()), response


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction probe")
def test_windows_junction_cannot_expose_evaluator_storage(cli_scope, tmp_path):
    target = tmp_path / "evaluator"
    path, digest = seal_owned_ledger_suite(target, cli_scope)
    alias = tmp_path / "alias"
    command = str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe")
    result = subprocess.run([command, "/d", "/c", "mklink", "/J", str(alias), str(target)], capture_output=True)
    assert result.returncode == 0
    with pytest.raises(EvaluationBlocked, match="links or junctions"):
        load_sealed_suite(alias / "suite.json", digest, cli_scope)
    response = _run_worker("probe", {"path": str(alias / "suite.json")}, CandidateExecutionLimits())
    assert response["checks"]["file"] is True
