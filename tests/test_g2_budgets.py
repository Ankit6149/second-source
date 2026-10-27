"""G2 model-side budget tests: reservation, commit, failure booking."""

import pytest

from second_source.budgets import (
    RunBudget,
    TokenCaps,
    estimate_cost_usd,
)
from second_source.contracts import Budgets
from second_source.runner import BudgetExhausted


def test_attempt_cap():
    budget = RunBudget(Budgets(max_model_calls=1))
    res = budget.reserve(10, 10)
    budget.commit(res, 10, 10, 0.0001)
    with pytest.raises(BudgetExhausted):
        budget.reserve(10, 10)


def test_spend_cap_blocks_reservation():
    budget = RunBudget(Budgets(max_estimated_model_spend_usd=0.000001))
    with pytest.raises(BudgetExhausted):
        budget.reserve(10_000, 10_000)


def test_token_caps():
    budget = RunBudget(Budgets(), TokenCaps(max_input_tokens=50, max_output_tokens=50))
    with pytest.raises(BudgetExhausted):
        budget.reserve(51, 0)
    with pytest.raises(BudgetExhausted):
        budget.reserve(0, 51)


def test_failure_books_uncertain_spend():
    budget = RunBudget(Budgets(max_estimated_model_spend_usd=10.0))
    res = budget.reserve(1_000, 500)
    assert res.est_cost_usd > 0
    budget.fail(res)
    assert budget.uncertain_cost_usd == pytest.approx(res.est_cost_usd)
    assert budget.model_calls == 0
    # Uncertain spend counts against the cap: a repeat is blocked.
    with pytest.raises(BudgetExhausted):
        budget.reserve(10_000_000, 10_000_000)


def test_commit_releases_reservation():
    budget = RunBudget(Budgets(max_estimated_model_spend_usd=0.01))
    res = budget.reserve(100, 100)
    budget.commit(res, 100, 100, 0.0005)
    assert budget.model_calls == 1
    assert budget.summary()["attempts"] == 1
    # Reservation released: only actuals count now.
    res2 = budget.reserve(100, 100)
    budget.commit(res2, 100, 100, 0.0005)
    assert budget.model_calls == 2


def test_model_specific_rates():
    spark = estimate_cost_usd(1_000_000, 0)
    wonder = estimate_cost_usd(1_000_000, 0, (4.0, 20.0))
    assert spark == pytest.approx(1.25)
    assert wonder == pytest.approx(4.0)
    assert wonder > spark


def test_zero_call_budget_blocks_reserve():
    with pytest.raises(BudgetExhausted):
        RunBudget(Budgets(max_model_calls=0)).reserve(0, 0)


def test_summary_shape():
    summary = RunBudget(Budgets()).summary()
    assert summary["attempts"] == 0
    assert summary["uncertain_cost_usd"] == 0.0
    assert summary["limits"]["max_estimated_model_spend_usd"] == 2.0
