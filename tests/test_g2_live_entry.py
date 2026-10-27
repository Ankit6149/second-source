"""Non-billable tests for the operator-controlled real experiment entry point."""

import json

from second_source.budgets import RunBudget
from second_source.contracts import Budgets
from second_source.live_experiment import ROOT, create_scope, main, fixture_verifier_summary
from second_source.model_gateway import MockProvider, ModelGateway, ModelRequest


def test_live_runner_refuses_missing_key_and_budget(monkeypatch, capsys):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("SECOND_SOURCE_MAX_RUN_USD", raising=False)
    assert main(["--max-usd", "0.10"]) == 2
    assert "BLOCKED_REAL_MODEL" in capsys.readouterr().err


def test_live_runner_refuses_over_budget_before_network(monkeypatch, capsys):
    monkeypatch.setenv("MODEL_API_KEY", "only-a-test-value")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.10")
    assert main(["--max-usd", "0.20"]) == 2
    assert "BLOCKED_BUDGET" in capsys.readouterr().err
    assert main(["--max-usd", "0.26"]) == 2


def test_live_scope_and_public_manifest_are_aligned():
    scope = create_scope(0.25, max_rounds=1)
    public = json.loads(
        (ROOT / "fixtures/owned_ledger/public_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(public["commands"]) == set(scope.observation.allowed_commands)
    assert scope.budgets.max_model_calls == 2
    assert scope.budgets.max_estimated_model_spend_usd == 0.25
    assert "private_dashboard" not in scope.implementation.allowed_subsystems


def test_model_gateway_instructs_json_schema_before_mock_call():
    observed = []

    def responder(request):
        observed.append(request)
        return {"content": {"ok": True}}

    schema = {
        "type": "object",
        "required": ["ok"],
        "additionalProperties": False,
        "properties": {"ok": {"type": "boolean"}},
    }
    gateway = ModelGateway(MockProvider(responder=responder), RunBudget(Budgets()))
    response = gateway.generate(
        ModelRequest(
            stage="hypothesize",
            messages=({"role": "user", "content": "A public test only"},),
            json_schema=schema,
            max_output_tokens=32,
        )
    )
    assert response.parsed == {"ok": True}
    assert len(observed) == 1
    assert observed[0].messages[0]["role"] == "system"
    assert "JSON Schema:" in observed[0].messages[0]["content"]
    assert '"required":["ok"]' in observed[0].messages[0]["content"]
    assert observed[0].messages[1]["content"] == "A public test only"


def test_independent_harness_negative_control(reference):
    result = fixture_verifier_summary(reference)
    assert result["kind"] == "trusted_harness_negative_control_not_generated_candidate"
    feedback = result["model_feedback"]
    assert feedback["total"] == 2
    assert feedback["passed"] >= 1
    assert feedback["failed"] >= 1
    assert "case_id" not in json.dumps(feedback)
