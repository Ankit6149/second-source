"""Model-side run budgets with reservation accounting (G2).

Reference-experiment and wall-clock budgets stay enforced by
`SafeCLIExperimentRunner`; this ledger governs billable model usage.

Hard-stop semantics: the maximum is RESERVED before the provider call. On
success the reservation commits to actuals; on transport/parse failure the
worst case is booked as uncertain spend (fail closed — a billed request that
errors on our side must never look free). We never claim a guaranteed billing
hard cap: this ledger bounds what WE attempt, provider billing is authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from .contracts import Budgets, StrictModel
from .runner import BudgetExhausted

# Per-model standard rates (USD per million tokens) snapshotted at PRD issue.
# Unknown models fail closed unless the caller supplies explicit rates.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "muse-spark-1.3": (1.25, 4.25),
    "muse-wonder-1.0": (4.0, 20.0),
}
DEFAULT_RATES = MODEL_PRICING["muse-spark-1.3"]


def estimate_cost_usd(
    input_tokens: int, output_tokens: int, rates: tuple[float, float] = DEFAULT_RATES
) -> float:
    return input_tokens * rates[0] / 1_000_000 + output_tokens * rates[1] / 1_000_000


class TokenCaps(StrictModel):
    """H0 defaults; tighten per investigation. No silent overage."""

    max_input_tokens: int = Field(default=200_000, ge=0)
    max_output_tokens: int = Field(default=60_000, ge=0)


@dataclass(frozen=True)
class Reservation:
    est_input_tokens: int
    est_output_tokens: int
    est_cost_usd: float


class RunBudget:
    """Mutable model-usage ledger bound to contract Budgets + TokenCaps."""

    def __init__(
        self,
        budgets: Budgets,
        caps: TokenCaps | None = None,
        rates: tuple[float, float] = DEFAULT_RATES,
    ) -> None:
        self.limits = budgets
        self.caps = caps or TokenCaps()
        self.rates = rates
        self.attempts = 0
        self.model_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.estimated_cost_usd = 0.0
        self.uncertain_cost_usd = 0.0
        self._outstanding = 0.0

    def reserve(
        self,
        est_input_tokens: int,
        est_output_tokens: int,
        rates: tuple[float, float] | None = None,
    ) -> Reservation:
        """Reserve the worst case BEFORE the provider call. Raises on breach."""
        if self.attempts + 1 > self.limits.max_model_calls:
            raise BudgetExhausted(
                f"model call budget exhausted ({self.attempts}/{self.limits.max_model_calls})"
            )
        if (
            self.input_tokens + est_input_tokens > self.caps.max_input_tokens
            or self.output_tokens + est_output_tokens > self.caps.max_output_tokens
        ):
            raise BudgetExhausted("token budget exhausted")
        est_cost = estimate_cost_usd(
            est_input_tokens, est_output_tokens, rates or self.rates
        )
        if (
            self.estimated_cost_usd + self.uncertain_cost_usd + self._outstanding + est_cost
            > self.limits.max_estimated_model_spend_usd
        ):
            raise BudgetExhausted(
                f"spend budget exhausted (${self.estimated_cost_usd:.4f} used + "
                f"${self.uncertain_cost_usd:.4f} uncertain/"
                f"${self.limits.max_estimated_model_spend_usd:.4f})"
            )
        self.attempts += 1
        self._outstanding += est_cost
        return Reservation(est_input_tokens, est_output_tokens, est_cost)

    def commit(
        self, reservation: Reservation, actual_in: int, actual_out: int, actual_cost: float
    ) -> None:
        """Replace the reservation with provider-reported actuals."""
        self._outstanding = max(0.0, self._outstanding - reservation.est_cost_usd)
        self.model_calls += 1
        self.input_tokens += actual_in
        self.output_tokens += actual_out
        self.estimated_cost_usd += actual_cost

    def fail(self, reservation: Reservation, uncertain_cost: float | None = None) -> None:
        """Book the attempt as uncertain spend. Fail closed: assume billed."""
        self._outstanding = max(0.0, self._outstanding - reservation.est_cost_usd)
        self.uncertain_cost_usd += (
            reservation.est_cost_usd if uncertain_cost is None else uncertain_cost
        )

    @property
    def model_calls_remaining(self) -> int:
        return max(0, self.limits.max_model_calls - self.attempts)

    def summary(self) -> dict:
        return {
            "attempts": self.attempts,
            "model_calls": self.model_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "uncertain_cost_usd": round(self.uncertain_cost_usd, 6),
            "limits": {
                "max_model_calls": self.limits.max_model_calls,
                "max_input_tokens": self.caps.max_input_tokens,
                "max_output_tokens": self.caps.max_output_tokens,
                "max_estimated_model_spend_usd": self.limits.max_estimated_model_spend_usd,
            },
        }
