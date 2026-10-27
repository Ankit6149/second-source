"""G2 gateway tests: labeling, reservation, pricing, endpoints, schema checks."""

import json

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

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean"}},
}


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
    response = gateway.generate(request("hi", schema=SCHEMA))
    assert response.real is False
    assert response.provider == "mock"
    assert response.parsed == {"ok": True}
    assert response.outcome == "ok"
    assert response.estimated_cost_usd == 0.0
    assert len(gateway.receipts) == 1
    assert gateway.receipts[0].real is False


def test_mock_schema_violation_rejected_and_booked():
    gateway = ModelGateway(
        MockProvider([{"content": {"bogus": 1}}]), RunBudget(Budgets())
    )
    with pytest.raises(GatewayError, match="violated JSON schema"):
        gateway.generate(request("hi", schema=SCHEMA))
    receipt = gateway.receipts[0]
    assert receipt.outcome == "failed"
    assert gateway._budget.attempts == 1
    assert gateway._budget.model_calls == 0


def test_mock_script_exhaustion_books_failure():
    gateway = ModelGateway(MockProvider([]), RunBudget(Budgets()))
    with pytest.raises(GatewayError, match="uncertain"):
        gateway.generate(request("hi"))
    assert gateway.receipts[0].outcome == "failed"


def test_call_cap_blocks_mock():
    gateway = ModelGateway(
        MockProvider([{"content": {}}]), RunBudget(Budgets(max_model_calls=0))
    )
    with pytest.raises(BudgetExhausted):
        gateway.generate(request("hi"))
    assert gateway.receipts == ()


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
    provider = MetaProvider("key-unused", base_url="http://127.0.0.1:1", test_mode=True)
    gateway = ModelGateway(provider, RunBudget(Budgets(max_estimated_model_spend_usd=0)))
    with pytest.raises(GatewayError, match="spend budget"):
        gateway.generate(request("hi"))


def test_meta_provider_requires_key():
    with pytest.raises(GatewayError):
        MetaProvider("")


def test_http_endpoint_rejected():
    with pytest.raises(GatewayError, match="non-HTTPS"):
        MetaProvider("k", base_url="http://api.meta.ai/v1")


def test_unexpected_host_rejected():
    with pytest.raises(GatewayError, match="unexpected model host"):
        MetaProvider("k", base_url="https://evil.example/v1")


def test_loopback_requires_test_mode():
    with pytest.raises(GatewayError):
        MetaProvider("k", base_url="http://127.0.0.1:1")
    provider = MetaProvider("k", base_url="http://127.0.0.1:1", test_mode=True)
    assert provider.model == "muse-spark-1.3"


def test_unknown_model_pricing_fail_closed():
    with pytest.raises(GatewayError, match="unknown pricing"):
        MetaProvider("k", model="muse-future-9")
    provider = MetaProvider("k", model="muse-future-9", rates=(9.0, 9.0))
    assert provider.rates == (9.0, 9.0)


def test_meta_error_never_echoes_key():
    provider = MetaProvider("live-secret-key-123", base_url="http://127.0.0.1:1", test_mode=True)
    gateway = ModelGateway(provider, RunBudget(Budgets()))
    with pytest.raises(GatewayError) as excinfo:
        gateway.generate(request("hi"))
    assert "live-secret-key-123" not in str(excinfo.value)
    assert gateway.receipts[0].outcome == "failed"


def test_wire_format_and_usage_reconciled(monkeypatch):
    seen = {}

    class FakeResp:
        def read(self):
            return json.dumps({
                "id": "resp-1",
                "choices": [{"message": {"content": json.dumps({"ok": True})}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["payload"] = json.loads(req.data.decode())
        seen["auth"] = req.get_header("Authorization")
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = MetaProvider("k", test_mode=True, base_url="https://api.meta.ai/v1")
    gateway = ModelGateway(provider, RunBudget(Budgets()))
    response = gateway.generate(request("hi", schema=SCHEMA))
    assert seen["url"] == "https://api.meta.ai/v1/chat/completions"
    assert seen["payload"]["response_format"]["type"] == "json_schema"
    assert seen["payload"]["response_format"]["json_schema"]["strict"] is False
    assert seen["payload"]["response_format"]["json_schema"]["schema"] == SCHEMA
    assert seen["payload"]["model"] == "muse-spark-1.3"
    assert seen["payload"]["reasoning_effort"] == "low"
    assert seen["auth"] == "Bearer k"
    assert response.real is True
    assert response.parsed == {"ok": True}
    assert response.input_tokens == 100
    assert gateway._budget.input_tokens == 100
    assert gateway._budget.output_tokens == 20
    assert gateway._budget.model_calls == 1


def test_mock_ping():
    gateway = ModelGateway(MockProvider([{"content": "ready"}]), RunBudget(Budgets()))
    response = gateway.ping()
    assert response.content_text == "ready"
    assert response.real is False


def test_real_provider_non_json_preserves_safe_finish_reason_and_actual_usage(monkeypatch):
    """Failed structured response must not lose observed provider token usage."""
    text = "Not JSON: unexpected truncated response"

    class FakeResponse:
        def read(self):
            return json.dumps({
                "id": "resp-diagnostic-1",
                "choices": [{
                    "finish_reason": "length",
                    "message": {"content": text},
                }],
                "usage": {
                    "prompt_tokens": 150,
                    "completion_tokens": 64,
                    "completion_tokens_details": {"reasoning_tokens": 56},
                },
            }).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: FakeResponse())
    budget = RunBudget(Budgets(max_estimated_model_spend_usd=0.25))
    gateway = ModelGateway(MetaProvider("local-fixture-key"), budget)
    with pytest.raises(GatewayError, match="MODEL_JSON_INVALID.*finish_reason=length"):
        gateway.generate(request("hi", schema=SCHEMA))
    receipt = gateway.receipts[0]
    assert receipt.real and receipt.outcome == "failed"
    assert receipt.failure_code == "MODEL_JSON_INVALID"
    assert receipt.finish_reason == "length"
    assert receipt.response_id == "resp-diagnostic-1"
    assert receipt.input_tokens == 150
    assert receipt.output_tokens == 64
    assert receipt.reasoning_tokens == 56
    assert receipt.content_chars == len(text)
    assert len(receipt.content_sha256) == 64
    assert receipt.estimated_cost_usd > 0
    assert receipt.uncertain_cost_usd == 0.0
    assert budget.summary()["uncertain_cost_usd"] == 0.0
    assert budget.summary()["estimated_cost_usd"] > 0
    assert text not in receipt.model_dump_json()


def test_model_request_defaults_to_low_reasoning_for_bounded_json():
    assert request(schema=SCHEMA).reasoning_effort == "low"
