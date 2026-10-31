"""Bounded candidate repair loop over the pinned G3 broker/evaluator seam.

Only previously issued broker artifacts and aggregate evaluator feedback are
used. Every (re)generation goes through ``PinnedEvaluatorRun.generate``
(strict admission, attempt budget, provenance receipts intact) and every
version is scored by ``PinnedEvaluatorRun.evaluate`` on the SAME sealed suite.
The loop never invents feedback, never reuses a ticket, and never widens a
budget.

The FIRST version is the caller's already-evaluated initial candidate
(``seed``): verdicts compare the true original against the final retry, never
retry-vs-retry alone. Regeneration uses the frozen approved context: the
current broker builds each request from that context, so a repair round is an
honestly labeled bounded retry informed by the recorded aggregate feedback.
Rounds after the first generation use feedback-conditioned synthesis
(``synthesize-v2-repair1``): the broker re-issues the request with the
run's own aggregate evaluation (counts plus mismatch-category names only)
attached as repair guidance. No case ids, inputs, or expected outputs ever
reach the model; the sanitizer rejects any other feedback shape.
Caller-supplied seeds that carry no broker artifact start with one frozen
retry; conditioned rounds begin once a broker-issued artifact exists.

Perfect means exactly ``passed == total`` with zero failures AND zero
indeterminate results; counts are strictly validated (nonnegative integers,
each share summing to the denominator). Selection is explicit: the best
version is the minimum of ``(failed, indeterminate)`` with ties broken toward
the earliest version, so a later regression is never silently promoted.

All providers here are test doubles or owner-configured gateways; this module
performs zero billable calls itself and reads no credentials.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping

from .g3_verification import EvaluationBlocked

RepairVerdict = Literal[
    "no_repair_needed",
    "improved",
    "regressed",
    "no_change",
    "unrepaired",
]

# Explicit selection policy, surfaced in reports so readers can audit which
# candidate a primary score belongs to. Earliest wins ties: the initial
# candidate is never displaced by an equal-or-worse retry.
SELECTION_POLICY = "best_failed_then_indeterminate_then_earliest"


@dataclass
class RepairAttempt:
    """One admitted, independently scored candidate version.

    ``round`` 0 is the seed: the original evaluated candidate supplied by the
    caller. Rounds >= 1 are driver-generated retries in order.
    """

    round: int
    candidate_digest: str
    response_id: str
    origin: str
    evaluation: dict[str, Any]
    feedback: dict[str, Any]
    # Broker artifact this version was generated from (rounds >= 1); None
    # for caller-supplied seeds reconstructed without one, whose first retry
    # therefore reuses the frozen context instead of conditioned guidance.
    artifact: Any = None


@dataclass
class RepairReport:
    """Complete bounded repair history with a same-denominator verdict."""

    versions: list[RepairAttempt] = field(default_factory=list)
    verdict: RepairVerdict = "unrepaired"
    stop_reason: str = ""
    rounds_used: int = 0
    broker_diagnostic: dict[str, Any] | None = None


def checked_counts(evaluation: Mapping[str, Any]) -> tuple[int, int, int, int]:
    """Strictly validate an evaluation count mapping.

    Every count must be a genuine nonnegative integer (bools rejected), each
    outcome share must fit the denominator, and the shares must sum to it.
    Returns ``(passed, failed, indeterminate, total)``.
    """
    try:
        values = {key: evaluation[key] for key in ("passed", "failed", "indeterminate", "total")}
    except (KeyError, TypeError) as exc:
        raise ValueError("evaluation counts are incomplete") from exc
    for key, value in values.items():
        if type(value) is not int or value < 0:
            raise ValueError(f"evaluation count {key!r} is not a nonnegative integer")
    passed, failed, indeterminate, total = (
        values["passed"], values["failed"], values["indeterminate"], values["total"])
    if passed > total or failed > total or indeterminate > total:
        raise ValueError("evaluation outcome exceeds its denominator")
    if passed + failed + indeterminate != total:
        raise ValueError("evaluation outcomes do not sum to the denominator")
    return passed, failed, indeterminate, total


def is_perfect(evaluation: Mapping[str, Any]) -> bool:
    """A perfect verified result: every case passed, none failed or open."""
    passed, failed, indeterminate, total = checked_counts(evaluation)
    return passed == total and failed == 0 and indeterminate == 0


def _score_key(evaluation: Mapping[str, Any]) -> tuple[int, int]:
    _, failed, indeterminate, _ = checked_counts(evaluation)
    return (failed, indeterminate)


def select_best(versions: list[RepairAttempt]) -> int:
    """Index of the selected version under SELECTION_POLICY.

    Minimum ``(failed, indeterminate)``; ties resolve to the earliest version,
    so the report can never silently promote a later regression over the
    baseline. Requires a nonempty lineage.
    """
    if not versions:
        raise ValueError("no versions to select from")
    best = 0
    for index in range(1, len(versions)):
        if _score_key(versions[index].evaluation) < _score_key(versions[best].evaluation):
            best = index
    return best


def run_bounded_repair(
    run: Any,
    *,
    provider: Any,
    budget: Any,
    max_rounds: int = 2,
    claim: str = "TRUSTED_CONTROL",
    seed: RepairAttempt | None = None,
    on_version: Callable[[RepairAttempt, Any], None] | None = None,
) -> RepairReport:
    """Generate, score, and boundedly retry a candidate through the real seam.

    ``seed`` is the already-evaluated initial candidate (round 0) and becomes
    ``versions[0]``; the verdict compares it against the final retry.
    ``max_rounds`` counts NEW generation attempts (>= 1) and is additionally
    bounded by the broker's own attempt limit, which stays authoritative.
    ``on_version`` fires per admitted version (seed included when supplied by
    the caller after its own persistence, so callbacks usually only observe
    retries) so the operator can persist immutable bytes immediately, before
    a later interruption can lose them.
    """
    if type(max_rounds) is not int or max_rounds < 1:
        raise ValueError("max_rounds must be a positive integer")
    if seed is not None and (type(seed) is not RepairAttempt or seed.round != 0):
        raise ValueError("seed must be a round-0 RepairAttempt")
    report = RepairReport()
    pending_artifact = seed.artifact if seed is not None else None
    baseline_total: int | None = None
    if seed is not None:
        checked_counts(seed.evaluation)
        baseline_total = int(seed.evaluation["total"])
        report.versions.append(seed)
        if on_version is not None:
            on_version(seed, None)
        if is_perfect(seed.evaluation):
            report.verdict = "no_repair_needed"
            report.stop_reason = "baseline_perfect"
            return report
    while report.rounds_used < max_rounds:
        try:
            if (pending_artifact is not None
                    and getattr(run, "synthesis", None) == "guided"
                    and hasattr(run, "prepare_repair")):
                ticket = run.prepare_repair(pending_artifact)
            else:
                ticket = run.prepare()
            artifact = run.generate(ticket, provider, budget)
            pending_artifact = artifact
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
            _, _, _, total = checked_counts(evaluation)
        except ValueError:
            report.stop_reason = "invalid_evaluation_shape"
            break
        if baseline_total is None:
            baseline_total = total
        elif total != baseline_total:
            report.stop_reason = "denominator_changed"
            break
        report.rounds_used += 1
        attempt = RepairAttempt(
            round=len(report.versions),
            candidate_digest=str(receipt.get("candidate_digest", "")),
            response_id=str(receipt.get("response_id", "")),
            origin=str(receipt.get("origin", "")),
            evaluation=evaluation,
            feedback=dict(feedback) if isinstance(feedback, dict) else {},
            artifact=artifact,
        )
        report.versions.append(attempt)
        if on_version is not None:
            on_version(attempt, artifact)
        if is_perfect(attempt.evaluation):
            report.stop_reason = "repaired_to_perfect"
            break
        report.stop_reason = "rounds_exhausted"
    if not report.versions:
        report.verdict = "unrepaired"
        if not report.stop_reason:
            report.stop_reason = "no_attempt_made"
        return report
    if len(report.versions) == 1 and is_perfect(report.versions[0].evaluation):
        report.verdict = "no_repair_needed"
        report.stop_reason = "perfect_score"
        return report
    first = _score_key(report.versions[0].evaluation)
    last = _score_key(report.versions[-1].evaluation)
    if len(report.versions) == 1:
        report.verdict = "unrepaired"
    elif last < first:
        report.verdict = "improved"
    elif last > first:
        report.verdict = "regressed"
    else:
        report.verdict = "no_change"
    return report
