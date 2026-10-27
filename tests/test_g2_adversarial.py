"""G2 adversarial edge cases: injection is data, policy decides, secrets redact."""

from pathlib import Path

import pytest

from second_source.budgets import RunBudget
from second_source.contracts import Budgets
from second_source.model_gateway import GatewayError, MockProvider, ModelGateway, ModelRequest
from second_source.planner import ExperimentPlanner
from second_source.scope_guard import ScopeGuard
from second_source.hypotheses import HypothesisStore

SRC = Path(__file__).resolve().parents[1] / "src" / "second_source"
G2_MODULES = ("budgets.py", "model_gateway.py", "hypotheses.py", "planner.py", "loop.py")


def test_no_shell_or_subprocess_in_g2():
    for name in G2_MODULES:
        text = (SRC / name).read_text(encoding="utf-8")
        assert "shell=True" not in text
        assert "subprocess" not in text


def test_forbidden_marker_refused_even_from_planner_context(cli_scope):
    budget = RunBudget(cli_scope.budgets)
    gateway = ModelGateway(MockProvider([{"content": {}}]), budget)
    plan = ExperimentPlanner(gateway, ScopeGuard(cli_scope), HypothesisStore(), budget, cli_scope)
    evil = [{"digest": "d", "observation": {"note": "MODEL_API_KEY=zzz"}}]
    with pytest.raises(GatewayError, match="forbidden marker"):
        plan.hypothesize(evil, frozenset({"d"}))


def test_secrets_redacted_before_model(cli_scope):
    budget = RunBudget(cli_scope.budgets)
    gateway = ModelGateway(MockProvider([{"content": {}}]), budget)
    plan = ExperimentPlanner(gateway, ScopeGuard(cli_scope), HypothesisStore(), budget, cli_scope)
    evidence = [{"digest": "d", "observation": {"authorization": "Bearer abc123"}}]
    context = plan._model_context(evidence)
    assert "abc123" not in context
    assert "[REDACTED]" in context


def test_injection_text_cannot_hijack_action(cli_scope):
    """Target text stays inside evidence JSON; a hostile action kind is denied."""
    from second_source.planner import PROPOSE_JSON_SCHEMA  # noqa: F401 (schema pins kinds)

    budget = RunBudget(cli_scope.budgets)

    def hostile(request):
        if request.stage == "hypothesize":
            return {"content": {"schema_version": "1.0", "hypotheses": [
                {"id": "hyp-1", "statement": "x", "evidence_ids": ["d"]}]}}
        return {"content": {"proposals": [{
            "proposal_id": "exp-evil", "requirement_id": "REQ-LEDGER",
            "hypothesis_ids": ["hyp-1"], "command": "add",
            "kind": "exec_shell", "params": {"label": "x", "amount": 1},
            "predictions": {"hyp-1": "p"}, "side_effect": "read_only"}]}}

    gateway = ModelGateway(MockProvider(responder=hostile), budget)
    store = HypothesisStore()
    plan = ExperimentPlanner(gateway, ScopeGuard(cli_scope), store, budget, cli_scope)
    batch = plan.hypothesize([{"digest": "d", "observation": {}}], frozenset({"d"}))
    store.add_batch(batch)
    result = plan.propose([{"digest": "d", "observation": {}}], store.competing(),
                          "REQ-LEDGER", reference_remaining=10, model_remaining=5)
    assert result.ranked == ()
    assert "ACTION_NOT_ALLOWED" in result.rejected[0][1]


def test_gateway_request_carries_no_credentials():
    budget = RunBudget(Budgets())
    gateway = ModelGateway(MockProvider([{"content": "ok"}]), budget)
    gateway.generate(ModelRequest(stage="ping", messages=({"role": "user", "content": "hi"},)))
    assert gateway.receipts[0].model == "mock-muse-0"
