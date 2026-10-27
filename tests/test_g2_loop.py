"""G2 end-to-end mock discovery loop on the owned fixture."""

import json

import pytest

from second_source.budgets import RunBudget
from second_source.evidence import EvidenceLedger
from second_source.hypotheses import HypothesisStore
from second_source.loop import STOP_REASONS, DiscoveryLoop
from second_source.model_gateway import MockProvider, ModelGateway
from second_source.planner import ExperimentPlanner
from second_source.runner import SafeCLIExperimentRunner
from second_source.scope_guard import ScopeGuard


def loop_responder(command="add", requirement_id="REQ-LEDGER"):
    def respond(request):
        user = [m for m in request.messages if m["role"] == "user"][0]["content"]
        doc = json.loads(user)
        if request.stage == "hypothesize":
            digest = doc["evidence"][0]["digest"]
            return {"content": {
                "schema_version": "1.0",
                "hypotheses": [
                    {"id": "hyp-a", "statement": "duplicate labels are rejected",
                     "evidence_ids": [digest]},
                    {"id": "hyp-b", "statement": "amounts must be within bounds",
                     "evidence_ids": [digest]},
                ],
            }}
        ids = [h["id"] for h in doc.get("extra", {}).get("hypotheses", [])]
        return {"content": {"proposals": [{
            "proposal_id": "exp-loop-1",
            "requirement_id": requirement_id,
            "hypothesis_ids": ids,
            "question": "does the probe separate the hypotheses?",
            "command": command,
            "params": {"label": "Probe", "amount": 5},
            "predictions": {h: f"prediction under {h}" for h in ids},
            "side_effect": "read_only",
        }]}}
    return respond


def wiring(cli_scope, reference, tmp_path, mock, budgets=None):
    cli = cli_scope
    ledger = EvidenceLedger(tmp_path / "ev")
    budget = RunBudget(budgets or cli.budgets)
    gateway = ModelGateway(MockProvider(responder=mock), budget)
    store = HypothesisStore()
    plan = ExperimentPlanner(gateway, ScopeGuard(cli), store, budget, cli)
    runner = SafeCLIExperimentRunner(cli, reference, ledger)
    loop = DiscoveryLoop(
        run_id="run_t", requirement_id="REQ-LEDGER", contract=cli,
        runner=runner, ledger=ledger, hypotheses=store,
        planner=plan, budget=budget, max_rounds=2,
    )
    return loop, ledger, budget


SEED = ({"command": "add", "label": "Seed", "amount": 7}, {"command": "total"})


def test_mock_loop_runs_two_rounds(cli_scope, reference, tmp_path):
    loop, ledger, budget = wiring(cli_scope, reference, tmp_path, loop_responder())
    report = loop.run(list(SEED))
    assert len(report.rounds) == 2
    assert report.stop_reason in STOP_REASONS
    assert report.real_model_calls == 0
    assert report.mock_model_calls > 0
    assert report.budget_summary["model_calls"] == report.mock_model_calls
    assert len(list(ledger.root.glob("*.json"))) >= 4  # seed + rounds
    assert all(r.proposal_id for r in report.rounds)


def test_model_budget_stop_is_clean(cli_scope, reference, tmp_path):
    tight = cli_scope.budgets.model_copy(update={"max_model_calls": 0})
    loop, _, _ = wiring(cli_scope, reference, tmp_path, loop_responder(), budgets=tight)
    report = loop.run(list(SEED))
    assert report.stop_reason == "budget"
    assert report.real_model_calls == 0


def test_guard_blocked_when_nothing_allowed(cli_scope, reference, tmp_path):
    loop, ledger, _ = wiring(
        cli_scope, reference, tmp_path, loop_responder(command="nope")
    )
    report = loop.run(list(SEED))
    assert report.stop_reason == "guard_blocked"
    assert len(list(ledger.root.glob("*.json"))) == 2  # seed only
