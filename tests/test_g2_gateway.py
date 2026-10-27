"""G2 gateway tests: mock labeling, budgets, isolation."""

import pytest

from second_source.budgets import RunBudget
from second_source.contracts import Budgets
from second_source.model_gateway import (
    GatewayError,
    MetaProvider,
    MockProvider,
    ModelGateway,
    ModelRequest,
)
from second_source.runner import BudgetExhausted


def request(content="hello", schema=None):
    return ModelRequest(
        stage="hypothesize",
        messages=({"role": "user", "content": content},),
        json_schema=schema,
        max_output_tokens=64,
        prompt_version="test-v1",
    )


def test_mock_labeled_not_real():
    gateway = ModelGateway(MockProvider([{"content": {"ok": True}}]), RunBudget(Budgets()))
    response = gateway.generate(request("hi", schema={"type": "object"}))
    assert response.real is False
    assert response.provider == "mock"
    assert response.parsed == {"ok": True}
    assert response.estimated_cost_usd == 0.0
    assert len(gateway.receipts) == 1
    assert gateway.receipts[0].real is False


def test_mock_script_exhaustion_errors():
    gateway = ModelGateway(MockProvider([]), RunBudget(Budgets()))
    with pytest.raises(GatewayError):
        gateway.generate(request("hi"))


def test_call_cap_blocks_mock():
    gateway = ModelGateway(
        MockProvider([{"content": {}}]), RunBudget(Budgets(max_model_calls=0))
    )
    with pytest.raises(BudgetExhausted):
        gateway.generate(request("hi"))


def test_mock_ignores_spend_budget():
    gateway = ModelGateway(
        MockProvider([{"content": {}}]),
        RunBudget(Budgets(max_estimated_model_spend_usd=0)),
    )
    assert gateway.generate(request("hi")).real is False


def test_forbidden_marker_refused():
    gateway = ModelGateway(MockProvider([{"content": {}}]), RunBudget(Budgets()))
    with pytest.raises(GatewayError, match="forbidden marker"):
        gateway.generate(request("use MODEL_API_KEY=xyz"))


def test_real_call_blocked_at_zero_spend_before_http():
    provider = MetaProvider("key-unused", base_url="http://127.0.0.1:1")
    gateway = ModelGateway(provider, RunBudget(Budgets(max_estimated_model_spend_usd=0)))
    with pytest.raises(GatewayError, match="spend budget"):
        gateway.generate(request("hi"))


def test_meta_provider_requires_key():
    with pytest.raises(GatewayError):
        MetaProvider("")


def test_meta_error_never_echoes_key():
    provider = MetaProvider("live-secret-key-123", base_url="http://127.0.0.1:1")
    gateway = ModelGateway(provider, RunBudget(Budgets()))
    with pytest.raises(GatewayError) as excinfo:
        gateway.generate(request("hi"))
    assert "live-secret-key-123" not in str(excinfo.value)


def test_mock_ping():
    gateway = ModelGateway(MockProvider([{"content": "ready"}]), RunBudget(Budgets()))
    response = gateway.ping()
    assert response.content_text == "ready"
    assert response.real is False
