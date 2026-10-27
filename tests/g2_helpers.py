"""Shared G2 test builders (responder mocks read evidence from requests)."""

import json

from second_source.budgets import RunBudget
from second_source.evidence import EvidenceLedger
from second_source.hypotheses import HypothesisStore
from second_source.loop import DiscoveryLoop
from second_source.model_gateway import MockProvider, ModelGateway
from second_source.planner import ExperimentPlanner
from second_source.runner import SafeCLIExperimentRunner
from second_source.scope_guard import ScopeGuard

RESET = "fresh_process_per_sequence"


def hyp_doc(hyp_ids, digest):
    return {
        "schema_version": "1.0",
        "hypotheses": [
            {
                "id": h,
                "statement": f"candidate rule {h}",
                "evidence_ids": [digest],
                "status": "hypothesized",
                "alternatives": ["alt"],
                "unresolved_questions": ["q?"],
            }
            for h in hyp_ids
        ],
    }


def propose_doc(pid, hyp_ids, actions, predictions, requirement_id="REQ-LEDGER",
                side_effect="read_only", **kw):
    doc = {
        "proposal_id": pid,
        "requirement_id": requirement_id,
        "hypothesis_ids": list(hyp_ids),
        "question": "does the probe separate the hypotheses?",
        "reset_boundary": RESET,
        "actions": actions,
        "predictions": predictions,
        "expected_information_gain": "discriminator",
        "side_effect": side_effect,
        "role": "guest",
        "requires_auth": False,
    }
    doc.update(kw)
    return doc


def add_action(label="Probe", amount=5, kind="cli"):
    return {"command": "add", "kind": kind, "params": {"label": label, "amount": amount}}


def pred(hyp_id, expects_ok, contains=None):
    item = {"hypothesis_id": hyp_id, "expects_ok": expects_ok}
    if contains is not None:
        item["expects_contains"] = contains
    return item


def responder(hyp_ids=("hyp-1", "hyp-2"), actions=None, predictions=None, **kw):
    """Evidence-grounded mock: cites digests/hypothesis ids from the request."""
    def respond(request):
        user = [m for m in request.messages if m["role"] == "user"][0]["content"]
        doc = json.loads(user)
        if request.stage == "hypothesize":
            digest = doc["evidence"][0]["digest"]
            return {"content": hyp_doc(list(hyp_ids), digest)}
        ids = [h["id"] for h in doc.get("extra", {}).get("hypotheses", [])] or list(hyp_ids)
        steps = actions if actions is not None else [add_action()]
        preds = (
            predictions
            if predictions is not None
            else [pred(h, True) for h in ids]
        )
        return {"content": {"proposals": [propose_doc("exp-001", ids, steps, preds, **kw)]}}
    return respond


def wiring(cli_scope, reference, tmp_path, mock, budgets=None, max_rounds=2, public_contract=None):
    ledger = EvidenceLedger(tmp_path / "ev")
    budget = RunBudget(budgets or cli_scope.budgets)
    gateway = ModelGateway(MockProvider(responder=mock), budget)
    store = HypothesisStore()
    plan = ExperimentPlanner(gateway, ScopeGuard(cli_scope), store, budget, cli_scope,
                             public_contract=public_contract)
    runner = SafeCLIExperimentRunner(cli_scope, reference, ledger)
    loop = DiscoveryLoop(
        run_id="run_t", requirement_id="REQ-LEDGER", contract=cli_scope,
        runner=runner, ledger=ledger, hypotheses=store,
        planner=plan, budget=budget, max_rounds=max_rounds,
    )
    return loop, ledger, budget, plan, store
