"""G2 planner tests: schemas, guard routing, ranking."""

import json

import pytest

from second_source.budgets import RunBudget
from second_source.hypotheses import HypothesisStore
from second_source.model_gateway import MockProvider, ModelGateway
from second_source.planner import ExperimentPlanner, score_utility
from second_source.scope_guard import ScopeGuard


def responder(hyp_ids=("hyp-1", "hyp-2"), command="add", params=None,
              requirement_id="REQ-LEDGER", side_effect="read_only"):
    def respond(request):
        user = [m for m in request.messages if m["role"] == "user"][0]["content"]
        doc = json.loads(user)
        if request.stage == "hypothesize":
            digests = [e["digest"] for e in doc["evidence"]]
            return {"content": {
                "schema_version": "1.0",
                "hypotheses": [
                    {"id": h, "statement": f"candidate rule {h}",
                     "evidence_ids": [digests[0]],
                     "alternatives": ["alt"], "unresolved_questions": ["q?"]}
                    for h in hyp_ids
                ],
            }}
        ids = [h["id"] for h in doc.get("extra", {}).get("hypotheses", [])] or list(hyp_ids)
        return {"content": {"proposals": [{
            "proposal_id": "exp-001",
            "requirement_id": requirement_id,
            "hypothesis_ids": ids,
            "question": "discriminator?",
            "command": command,
            "params": params if params is not None else {"label": "Probe", "amount": 5},
            "predictions": {h: f"prediction under {h}" for h in ids},
            "side_effect": side_effect,
        }]}}
    return respond


def planner(cli_scope, mock):
    budget = RunBudget(cli_scope.budgets)
    gateway = ModelGateway(MockProvider(responder=mock), budget)
    store = HypothesisStore()
    return ExperimentPlanner(gateway, ScopeGuard(cli_scope), store, budget, cli_scope), store


def test_score_weights():
    assert score_utility(discrimination=1.0, scope_relevance=1.0, novelty=1.0,
                         coverage_gain=1.0, normalized_cost=0.0, risk_penalty=0.0) == pytest.approx(1.0)
    assert score_utility(discrimination=1.0, scope_relevance=1.0, novelty=1.0,
                         coverage_gain=1.0, normalized_cost=0.5, risk_penalty=0.5) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        score_utility(discrimination=2.0, scope_relevance=1.0, novelty=1.0,
                      coverage_gain=1.0, normalized_cost=0.0, risk_penalty=0.0)


def test_hypothesize_registers_batch(cli_scope):
    plan, store = planner(cli_scope, responder())
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    assert len(batch.hypotheses) == 2
    store.add_batch(batch)
    assert store.ids() == frozenset({"hyp-1", "hyp-2"})


def test_hypothesize_rejects_unknown_evidence(cli_scope):
    plan, _ = planner(cli_scope, responder())
    with pytest.raises(Exception):
        plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"other"}))


def test_propose_returns_ranked_allowed(cli_scope):
    plan, store = planner(cli_scope, responder())
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    store.add_batch(batch)
    result = plan.propose([{"digest": "d1", "observation": {}}], store.competing(),
                          "REQ-LEDGER", reference_remaining=10, model_remaining=5)
    assert len(result.ranked) == 1
    top = result.ranked[0]
    assert top.proposal_id == "exp-001"
    assert top.decision_code == "ALLOWED"
    assert top.action.target == "add"
    assert top.action.kind == "cli"
    assert top.utility >= 0.0


def test_propose_routes_guard_denial_to_rejected(cli_scope):
    plan, store = planner(cli_scope, responder(command="rm -rf /"))
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    store.add_batch(batch)
    result = plan.propose([{"digest": "d1", "observation": {}}], store.competing(),
                          "REQ-LEDGER", reference_remaining=10, model_remaining=5)
    assert result.ranked == ()
    assert len(result.rejected) == 1
    assert "COMMAND_NOT_ALLOWED" in result.rejected[0][1]


def test_propose_rejects_malformed(cli_scope):
    def bad(request):
        if request.stage == "hypothesize":
            return responder()(request)
        return {"content": {"proposals": [{"proposal_id": "x"}]}}
    plan, store = planner(cli_scope, bad)
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    store.add_batch(batch)
    result = plan.propose([{"digest": "d1", "observation": {}}], store.competing(),
                          "REQ-LEDGER", reference_remaining=10, model_remaining=5)
    assert result.ranked == ()
    assert "schema" in result.rejected[0][1]


def test_novelty_scores_repeat_lower(cli_scope):
    plan, store = planner(cli_scope, responder())
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    store.add_batch(batch)
    kwargs = dict(requirement_id="REQ-LEDGER", reference_remaining=10, model_remaining=5)
    first = plan.propose([{"digest": "d1", "observation": {}}], store.competing(), **kwargs)
    plan.mark_executed(first.ranked[0].action)
    second = plan.propose([{"digest": "d1", "observation": {}}], store.competing(), **kwargs)
    assert second.ranked[0].utility < first.ranked[0].utility
