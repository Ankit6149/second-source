"""G2 model-side budget tests. Reference/wall budgets stay with the runner."""

import pytest

from second_source.budgets import RunBudget, TokenCaps, estimate_cost_usd
from second_source.contracts import Budgets
from second_source.runner import BudgetExhausted


def test_call_cap():
    budget = RunBudget(Budgets(max_model_calls=1))
    budget.check_model_call(10, 10)
    budget.record_model_call(10, 10, 0.0001)
    with pytest.raises(BudgetExhausted):
        budget.check_model_call(10, 10)


def test_spend_cap_blocks_prefetch():
    budget = RunBudget(Budgets(max_estimated_model_spend_usd=0.000001))
    with pytest.raises(BudgetExhausted):
        budget.check_model_call(10_000, 10_000)


def test_token_caps():
    budget = RunBudget(Budgets(), TokenCaps(max_input_tokens=50, max_output_tokens=50))
    with pytest.raises(BudgetExhausted):
        budget.check_model_call(51, 0)
    with pytest.raises(BudgetExhausted):
        budget.check_model_call(0, 51)


def test_zero_call_budget_blocks_even_mock_estimate():
    budget = RunBudget(Budgets(max_model_calls=0))
    with pytest.raises(BudgetExhausted):
        budget.check_model_call(0, 0)


def test_summary_shape():
    summary = RunBudget(Budgets()).summary()
    assert summary["model_calls"] == 0
    assert summary["limits"]["max_estimated_model_spend_usd"] == 2.0


def test_cost_estimator_scales():
    assert estimate_cost_usd(0, 0) == 0.0
    assert estimate_cost_usd(1_000_000, 0) == 1.25
    assert estimate_cost_usd(0, 1_000_000) == 4.25
