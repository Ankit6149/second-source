import pytest
from second_source.contracts import ProposedAction
from second_source.runner import SafeCLIExperimentRunner, PolicyViolation, BudgetExhausted
from second_source.evidence import EvidenceLedger


def proposed(target, **payload):
    return ProposedAction(kind="cli", target=target, requirement_id="REQ-LEDGER", payload=payload)


def test_end_to_end_allowed_and_evidence(cli_scope, reference, tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence")
    runner = SafeCLIExperimentRunner(cli_scope, reference, ledger)
    result = runner.run([proposed("add", label="Alpha", amount=10), proposed("total")])
    assert result.status == "ok"
    assert result.observations[1].output == {"ok": True, "count": 1, "amount": 10}
    assert len(list(ledger.root.glob("*.json"))) == 2


def test_no_out_of_scope_command_executes(cli_scope, reference, tmp_path):
    runner = SafeCLIExperimentRunner(cli_scope, reference, EvidenceLedger(tmp_path))
    with pytest.raises(PolicyViolation, match="COMMAND_NOT_ALLOWED"):
        runner.run([proposed("rm -rf /")])
    assert runner.count == 0


def test_no_action_payload_override(cli_scope, reference, tmp_path):
    runner = SafeCLIExperimentRunner(cli_scope, reference, EvidenceLedger(tmp_path))
    with pytest.raises(PolicyViolation, match="cannot override"):
        runner.run([proposed("total", command="remove")])
    assert runner.count == 0


def test_all_action_gate_before_any_execution(cli_scope, reference, tmp_path):
    runner = SafeCLIExperimentRunner(cli_scope, reference, EvidenceLedger(tmp_path))
    with pytest.raises(PolicyViolation):
        runner.run([proposed("add", label="x", amount=3), proposed("nonsense")])
    assert runner.count == 0
    assert list(tmp_path.glob("*.json")) == []


def test_explicit_experiment_budget(cli_scope, reference, tmp_path):
    scope = cli_scope.model_copy(update={"budgets": cli_scope.budgets.model_copy(update={"max_reference_experiments": 1})})
    runner = SafeCLIExperimentRunner(scope, reference, EvidenceLedger(tmp_path))
    runner.run([proposed("total")])
    with pytest.raises(BudgetExhausted):
        runner.run([proposed("total")])
