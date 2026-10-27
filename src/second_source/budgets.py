"""Model-side run budgets (G2).

Reference-experiment and wall-clock budgets stay enforced by
`SafeCLIExperimentRunner`; this ledger governs billable model usage
(call count, token caps, spend estimate) and shares the runner's
`BudgetExhausted` signal so loops stop cleanly.
"""
from __future__ import annotations

from pydantic import Field

from .contracts import Budgets, StrictModel
from .runner import BudgetExhausted

# Snapshot of Meta standard Spark pricing at PRD issue (S06). Estimates only;
# provider billing is authoritative.
SPARK_INPUT_USD_PER_MTOK = 1.25
SPARK_OUTPUT_USD_PER_MTOK = 4.25


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * SPARK_INPUT_USD_PER_MTOK / 1_000_000
        + output_tokens * SPARK_OUTPUT_USD_PER_MTOK / 1_000_000
    )


class TokenCaps(StrictModel):
    """H0 defaults; tighten per investigation. No silent overage."""

    max_input_tokens: int = Field(default=200_000, ge=0)
    max_output_tokens: int = Field(default=60_000, ge=0)


class RunBudget:
    """Mutable model-usage ledger bound to contract Budgets + TokenCaps."""

    def __init__(self, budgets: Budgets, caps: TokenCaps | None = None) -> None:
        self.limits = budgets
        self.caps = caps or TokenCaps()
        self.model_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.estimated_cost_usd = 0.0

    def check_model_call(self, est_input_tokens: int = 0, est_output_tokens: int = 0) -> None:
        if self.model_calls + 1 > self.limits.max_model_calls:
            raise BudgetExhausted(
                f"model call budget exhausted ({self.model_calls}/{self.limits.max_model_calls})"
            )
        if (
            self.input_tokens + est_input_tokens > self.caps.max_input_tokens
            or self.output_tokens + est_output_tokens > self.caps.max_output_tokens
        ):
            raise BudgetExhausted("token budget exhausted")
        if (
            self.estimated_cost_usd + estimate_cost_usd(est_input_tokens, est_output_tokens)
            > self.limits.max_estimated_model_spend_usd
        ):
            raise BudgetExhausted(
                f"spend budget exhausted (${self.estimated_cost_usd:.4f}/"
                f"${self.limits.max_estimated_model_spend_usd:.4f})"
            )

    def record_model_call(self, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        self.model_calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.estimated_cost_usd += cost_usd

    @property
    def model_calls_remaining(self) -> int:
        return max(0, self.limits.max_model_calls - self.model_calls)

    def summary(self) -> dict:
        return {
            "model_calls": self.model_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "limits": {
                "max_model_calls": self.limits.max_model_calls,
                "max_input_tokens": self.caps.max_input_tokens,
                "max_output_tokens": self.caps.max_output_tokens,
                "max_estimated_model_spend_usd": self.limits.max_estimated_model_spend_usd,
            },
        }
