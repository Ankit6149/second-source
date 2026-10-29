"""Bounded candidate repair loop over the pinned G3 broker/evaluator seam.

Only previously issued broker artifacts and aggregate evaluator feedback are
used. Every (re)generation goes through ``PinnedEvaluatorRun.generate`` (strict
admission, attempt budget, provenance receipts intact) and every version is
scored by ``PinnedEvaluatorRun.evaluate`` on the SAME sealed suite. The loop
never invents feedback, never reuses a ticket, and never widens a budget.

Regeneration uses the frozen approved context: the current broker builds each
request from that context, so a repair round is an honestly labeled bounded
retry informed by the recorded aggregate feedback, NOT feedback-conditioned
synthesis. Feeding mismatch detail back into the model request would need a
reviewed broker-context amendment (documented blocker, not done here).

All providers here are test doubles or owner-configured gateways; this module
performs zero billable calls itself and reads no credentials.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from .g3_verification import EvaluationBlocked

RepairVerdict = Literal[
    "no_repair_needed",
    "improved",
    "regressed",
    "no_change",
    "unrepaired",
]


@dataclass
class RepairAttempt:
    """One admitted, independently scored candidate version."""

    round: int
    candidate_digest: str
    response_id: str
    origin: str
    evaluation: dict[str, Any]
    feedback: dict[str, Any]


@dataclass
class RepairReport:
    """Complete bounded repair history with a same-denominator verdict."""

    versions: list[RepairAttempt] = field(default_factory=list)
    verdict: RepairVerdict = "unrepaired"
    stop_reason: str = ""
    rounds_used: int = 0
    broker_diagnostic: dict[str, Any] | None = None


def _counts(evaluation: Mapping[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(evaluation["passed"]),
        int(evaluation["failed"]),
        int(evaluation["indeterminate"]),
        int(evaluation["total"]),
    )


def run_bounded_repair(
    run: Any,
    *,
    provider: Any,
    budget: Any,
    max_rounds: int = 2,
    claim: str = "TRUSTED_CONTROL",
) -> RepairReport:
    """Generate, score, and boundedly retry a candidate through the real seam.

    ``max_rounds`` counts generation attempts including the initial one and
    must be >= 1. The broker's own attempt limit (scope repair budget) stays
    authoritative: hitting it stops the loop with the broker diagnostic
    preserved. Every version keeps its digest, receipt origin, aggregate
    feedback, and exact counts; the verdict compares first vs last on the
    identical denominator.
    """
    if type(max_rounds) is not int or max_rounds < 1:
        raise ValueError("max_rounds must be a positive integer")
    report = RepairReport()
    baseline_total: int | None = None
    while report.rounds_used < max_rounds:
        try:
            ticket = run.prepare()
            artifact = run.generate(ticket, provider, budget)
            result = run.evaluate(artifact, claim=claim)
            feedback = run.repair_feedback(artifact)
        except EvaluationBlocked as blocked:
            report.stop_reason = "broker_blocked"
            diagnostic = getattr(blocked, "broker_diagnostic", None)
            report.broker_diagnostic = dict(diagnostic) if isinstance(diagnostic, dict) else None
            break
        receipt = result.get("origin", {})
        evaluation = dict(result.get("evaluation", {}))
        try:
            _, failed, _, total = _counts(evaluation)
        except (KeyError, TypeError, ValueError):
            report.stop_reason = "invalid_evaluation_shape"
            break
        if baseline_total is None:
            baseline_total = total
        elif total != baseline_total:
            report.stop_reason = "denominator_changed"
            break
        report.rounds_used += 1
        report.versions.append(
            RepairAttempt(
                round=report.rounds_used,
                candidate_digest=str(receipt.get("candidate_digest", "")),
                response_id=str(receipt.get("response_id", "")),
                origin=str(receipt.get("origin", "")),
                evaluation=evaluation,
                feedback=dict(feedback) if isinstance(feedback, dict) else {},
            )
        )
        if failed == 0:
            report.stop_reason = "perfect_score" if report.rounds_used == 1 else "repaired_to_perfect"
            break
        report.stop_reason = "rounds_exhausted"
    if not report.versions:
        report.verdict = "unrepaired"
        if not report.stop_reason:
            report.stop_reason = "no_attempt_made"
        return report
    if len(report.versions) == 1 and report.versions[0].evaluation["failed"] == 0:
        report.verdict = "no_repair_needed"
        return report
    first_failed = int(report.versions[0].evaluation["failed"])
    last_failed = int(report.versions[-1].evaluation["failed"])
    if len(report.versions) == 1:
        report.verdict = "unrepaired"
    elif last_failed < first_failed:
        report.verdict = "improved"
    elif last_failed > first_failed:
        report.verdict = "regressed"
    else:
        report.verdict = "no_change"
    return report
