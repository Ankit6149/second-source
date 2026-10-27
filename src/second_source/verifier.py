"""Independent, sealed behavioral comparison. No model self-grading."""
from __future__ import annotations

from collections import Counter
from typing import Any, Literal, Protocol

from pydantic import Field

from .contracts import SequenceResult, StrictModel


class ReferenceProtocol(Protocol):
    def execute_sequence(self, actions: list[dict], *, sequence_id: str | None = None) -> SequenceResult: ...


class SealedCase(StrictModel):
    """Trusted harness input; never hand cases or expected output to inference agent."""
    case_id: str = Field(min_length=1)
    actions: tuple[dict[str, Any], ...] = Field(min_length=1)
    category: str = "stateful"


class CaseResult(StrictModel):
    case_id: str
    outcome: Literal["passed", "failed", "indeterminate"]
    mismatch_category: str | None = None
    # Intentionally no case input or expected output: even trusted reports stay minimal.


class EvaluationReport(StrictModel):
    passed: int
    failed: int
    indeterminate: int
    total: int
    cases: tuple[CaseResult, ...]
    diagnostic_class_counts: dict[str, int]

    def model_feedback(self) -> dict[str, Any]:
        """No hidden inputs, expected values, or case IDs exposed to model."""
        return {
            "passed": self.passed,
            "failed": self.failed,
            "indeterminate": self.indeterminate,
            "total": self.total,
            "failure_categories": self.diagnostic_class_counts,
        }


def _difference_type(reference: Any, candidate: Any, *, action_count: int) -> str | None:
    if not isinstance(reference, list) or not isinstance(candidate, list):
        return "schema"
    if len(reference) != len(candidate) or len(reference) != action_count:
        return "state"
    for r, c in zip(reference, candidate):
        if not isinstance(r, dict) or not isinstance(c, dict):
            return "schema"
        if r.get("ok") != c.get("ok") or r.get("error") != c.get("error"):
            return "error"
        if set(r) != set(c):
            return "schema"
        if r != c:
            return "value"
    return None


class DifferentialVerifier:
    def __init__(self, reference: ReferenceProtocol, candidate: ReferenceProtocol):
        self._reference = reference
        self._candidate = candidate

    def verify(self, cases: list[SealedCase]) -> EvaluationReport:
        if not cases or len({c.case_id for c in cases}) != len(cases):
            raise ValueError("Need a nonempty suite with unique sealed case IDs")
        results: list[CaseResult] = []
        for case in cases:
            actions = list(case.actions)
            ref = self._reference.execute_sequence(actions, sequence_id="ref-" + case.case_id)
            cand = self._candidate.execute_sequence(actions, sequence_id="candidate-" + case.case_id)
            if ref.status != "ok":
                results.append(CaseResult(case_id=case.case_id, outcome="indeterminate", mismatch_category="reference_unavailable"))
                continue
            if cand.status != "ok":
                category = "candidate_timeout" if cand.status == "timeout" else "candidate_protocol_error"
                results.append(CaseResult(case_id=case.case_id, outcome="failed", mismatch_category=category))
                continue
            expected = [o.output for o in ref.observations]
            actual = [o.output for o in cand.observations]
            category = _difference_type(expected, actual, action_count=len(actions))
            results.append(CaseResult(case_id=case.case_id, outcome="passed" if category is None else "failed", mismatch_category=category))
        counts = Counter(c.outcome for c in results)
        categories = Counter(c.mismatch_category for c in results if c.mismatch_category and c.outcome == "failed")
        return EvaluationReport(
            passed=counts["passed"], failed=counts["failed"], indeterminate=counts["indeterminate"],
            total=len(results), cases=tuple(results), diagnostic_class_counts=dict(categories)
        )
