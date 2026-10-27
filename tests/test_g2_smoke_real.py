"""Real Meta provider smoke test (G2 gate EXEC-006).

Runs ONLY when the owner explicitly configures BOTH:
  MODEL_API_KEY (server-side secret, never logged)
  SECOND_SOURCE_MAX_RUN_USD (positive number, explicit spend authorization)

Otherwise the module skips with a named reason. A skip is reported as SKIPPED,
never as green proof. No billable request is sent without both.
"""

import json
import os
import unittest

API_KEY = os.environ.get("MODEL_API_KEY", "")
try:
    RUN_BUDGET = float(os.environ.get("SECOND_SOURCE_MAX_RUN_USD", "0") or "0")
except ValueError:
    RUN_BUDGET = 0.0

REAL_ENABLED = bool(API_KEY) and RUN_BUDGET > 0


@unittest.skipUnless(
    REAL_ENABLED,
    "BLOCKED_REAL_MODEL: set MODEL_API_KEY and SECOND_SOURCE_MAX_RUN_USD>0",
)
class TestRealMetaSmoke(unittest.TestCase):
    def test_ping_returns_real_receipt(self):
        from second_source.budgets import RunBudget
        from second_source.contracts import Budgets
        from second_source.model_gateway import MetaProvider, ModelGateway

        budget = RunBudget(Budgets(max_estimated_model_spend_usd=min(RUN_BUDGET, 0.25)))
        gateway = ModelGateway(MetaProvider(API_KEY), budget)
        assert gateway.is_real
        response = gateway.ping()
        assert response.real is True
        assert response.provider == "meta-direct"
        assert response.response_id
        assert gateway.receipts[-1].real is True
        print("\nREAL_META_PING " + json.dumps({
            "model": response.model,
            "response_id": response.response_id,
            "latency_ms": response.latency_ms,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "estimated_cost_usd": response.estimated_cost_usd,
        }))

    def test_structured_hypothesis_parses(self):
        from second_source.budgets import RunBudget
        from second_source.contracts import Budgets
        from second_source.model_gateway import MetaProvider, ModelGateway, ModelRequest
        from second_source.planner import HYPOTHESIZE_JSON_SCHEMA

        budget = RunBudget(Budgets(max_estimated_model_spend_usd=min(RUN_BUDGET, 0.25)))
        gateway = ModelGateway(MetaProvider(API_KEY), budget)
        response = gateway.generate(ModelRequest(
            stage="hypothesize",
            messages=({"role": "user", "content": (
                "Observations: ledger add ok; duplicate add rejected. "
                "Return a hypothesis batch citing digest d1.")},),
            json_schema=HYPOTHESIZE_JSON_SCHEMA,
            max_output_tokens=600,
            prompt_version="smoke-hypothesize-v1",
        ))
        assert response.real is True
        assert isinstance(response.parsed, dict)
        assert "hypotheses" in response.parsed
