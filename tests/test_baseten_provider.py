"""Hermetic Baseten transport tests. These MUST NOT make paid API calls."""
import json
import urllib.error
import pytest

from second_source.baseten_provider import (
    BASETEN_ENDPOINT, BASETEN_MODEL, BasetenMuseOpenProvider,
)
from second_source.budgets import RunBudget
from second_source.contracts import Budgets
from second_source.model_gateway import GatewayError, ModelGateway, ModelRequest

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"], "additionalProperties": False}


def request(schema=SCHEMA):
    return ModelRequest(stage="hypothesize",
        messages=({"role": "user", "content": "Authorized observation only"},),
        json_schema=schema, max_output_tokens=128, prompt_version="baseten-test-v1")


class FakeResponse:
    status = 200

    def __init__(self, data, *, url=BASETEN_ENDPOINT):
        self.data = json.dumps(data).encode() if not isinstance(data, bytes) else data
        self.url = url

    def read(self, size=-1):
        return self.data[:size]

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def stub(monkeypatch, data):
    seen = {}
    class Opener:
        def open(self, req, timeout):
            seen["url"] = req.full_url
            seen["headers"] = dict(req.header_items())
            seen["payload"] = json.loads(req.data)
            seen["timeout"] = timeout
            return FakeResponse(data)
    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: Opener())
    return seen


def test_baseten_is_real_and_gateway_budgets_and_provenance(monkeypatch):
    seen = stub(monkeypatch, {
        "id": "bt-response-1",
        "choices": [{"message": {"content": '{"ok":true}'},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 24},
    })
    provider = BasetenMuseOpenProvider("server-only-test-key")
    budget = RunBudget(Budgets(max_estimated_model_spend_usd=0.02))
    gateway = ModelGateway(provider, budget)
    response = gateway.generate(request())
    assert response.real is True and gateway.is_real
    assert response.provider == gateway.provider_name == "baseten-muse-open"
    assert response.model == BASETEN_MODEL
    assert response.parsed == {"ok": True}
    assert response.response_id == "bt-response-1"
    assert (response.input_tokens, response.output_tokens) == (120, 24)
    assert seen["url"] == BASETEN_ENDPOINT and seen["timeout"] == 60.0
    assert seen["payload"]["model"] == BASETEN_MODEL
    assert seen["payload"]["max_tokens"] == 128
    assert "response_format" not in seen["payload"]
    assert seen["payload"]["messages"][0]["role"] == "system"
    assert seen["headers"]["Authorization"] == "Bearer server-only-test-key"
    assert gateway.receipts[0].outcome == "ok"
    assert gateway.receipts[0].real is True
    assert gateway.receipts[0].provider == "baseten-muse-open"
    assert budget.model_calls == 1


def test_no_budget_means_no_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No HTTP permitted")
    monkeypatch.setattr("urllib.request.build_opener", forbidden)
    gateway = ModelGateway(BasetenMuseOpenProvider("server-only-test-key"),
                           RunBudget(Budgets(max_estimated_model_spend_usd=0)))
    with pytest.raises(GatewayError, match="spend budget"):
        gateway.generate(request())
    assert gateway.receipts == ()


@pytest.mark.parametrize("key,timeout,rates", [
    ("", 60, (1.25, 4.25)),
    ("key", 0, (1.25, 4.25)),
    ("key", 999, (1.25, 4.25)),
    ("key", 60, (0, 4.25)),
    ("key", 60, (1.25, -1)),
    ("key", 60, (float("nan"), 4.25)),
])
def test_invalid_config_refused(key, timeout, rates):
    with pytest.raises(GatewayError):
        BasetenMuseOpenProvider(key, timeout_s=timeout, rates=rates)


def test_nonjson_output_retains_failure_receipt_without_raw_content(monkeypatch):
    stub(monkeypatch, {
        "id": "bt-failed-1",
        "choices": [{"message": {"content": "private output not JSON"},
                     "finish_reason": "length"}],
        "usage": {"prompt_tokens": 90, "completion_tokens": 50},
    })
    gateway = ModelGateway(BasetenMuseOpenProvider("server-only-test-key"),
                           RunBudget(Budgets(max_estimated_model_spend_usd=0.02)))
    with pytest.raises(GatewayError, match="MODEL_JSON_INVALID"):
        gateway.generate(request())
    receipt = gateway.receipts[0]
    assert receipt.failure_code == "MODEL_JSON_INVALID"
    assert receipt.finish_reason == "length"
    assert (receipt.input_tokens, receipt.output_tokens) == (90, 50)
    assert receipt.uncertain_cost_usd == 0
    assert "private output not JSON" not in receipt.model_dump_json()


def test_missing_usage_fails_closed_and_books_uncertainty(monkeypatch):
    stub(monkeypatch, {
        "id": "bt-unknown",
        "choices": [{"message": {"content": '{"ok":true}'}}],
    })
    gateway = ModelGateway(BasetenMuseOpenProvider("server-only-test-key"),
                           RunBudget(Budgets(max_estimated_model_spend_usd=0.02)))
    with pytest.raises(GatewayError):
        gateway.generate(request())
    assert gateway.receipts[0].outcome == "failed"
    assert gateway.receipts[0].uncertain_cost_usd > 0


def test_http_error_never_echoes_key_or_response_body(monkeypatch):
    class Opener:
        def open(self, req, timeout):
            raise urllib.error.HTTPError(BASETEN_ENDPOINT, 401,
                "server-only-test-key", {}, None)
    monkeypatch.setattr("urllib.request.build_opener", lambda *a: Opener())
    gateway = ModelGateway(BasetenMuseOpenProvider("server-only-test-key"),
                           RunBudget(Budgets(max_estimated_model_spend_usd=0.02)))
    with pytest.raises(GatewayError) as caught:
        gateway.generate(request())
    assert "server-only-test-key" not in str(caught.value)
    assert gateway.receipts[0].outcome == "failed"


def test_bad_schema_is_not_a_real_success(monkeypatch):
    stub(monkeypatch, {
        "id": "bt-invalid-1",
        "choices": [{"message": {"content": '{"unexpected":true}'}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10},
    })
    gateway = ModelGateway(BasetenMuseOpenProvider("server-only-test-key"),
                           RunBudget(Budgets(max_estimated_model_spend_usd=0.02)))
    with pytest.raises(GatewayError, match="MODEL_SCHEMA_INVALID"):
        gateway.generate(request())
    assert gateway.receipts[0].failure_code == "MODEL_SCHEMA_INVALID"
