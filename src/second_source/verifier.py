"""Independent, sealed behavioral comparison. No model self-grading."""
from __future__ import annotations

from collections import Counter
import json
import math
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import Field

from .contracts import SequenceResult, StrictModel

_FAILURE_CATEGORIES = frozenset({
    "schema", "state", "error", "value", "candidate_timeout", "candidate_protocol_error",
})


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
            "failure_categories": {
                key: value for key, value in self.diagnostic_class_counts.items()
                if key in _FAILURE_CATEGORIES and type(value) is int and value > 0
            },
        }


def _valid_json(value: Any, depth: int = 0) -> bool:
    """Only finite JSON primitives, with bounded nesting; no Python equality tricks."""
    if depth > 64:
        return False
    if value is None or type(value) in (bool, int, str):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_valid_json(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _valid_json(item, depth + 1)
                   for key, item in value.items())
    return False


def _json_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_json_equal(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right))
    return left == right


def _valid_envelope(result: SequenceResult, actions: list[dict], sequence_id: str) -> bool:
    if (not isinstance(result, SequenceResult) or result.status != "ok"
            or result.sequence_id != sequence_id or result.stderr != ""
            or type(result.observations) is not tuple or len(result.observations) != len(actions)):
        return False
    for i, observation in enumerate(result.observations):
        output = observation.output
        if (observation.sequence_id != sequence_id or observation.observation_id != f"{sequence_id}:{i}"
                or type(observation.action_index) is not int or observation.action_index != i
                or type(observation.exit_code) is not int or observation.exit_code != 0
                or type(observation.duration_ms) is not int or observation.duration_ms < 0
                or not _valid_json(observation.input_action)
                or not _json_equal(observation.input_action, actions[i])
                or type(output) is not dict or not _valid_json(output)
                or type(output.get("ok")) is not bool):
            return False
        if output["ok"]:
            if observation.status != "ok" or "error" in output:
                return False
        elif (observation.status != "target_error" or type(output.get("error")) is not str
              or not output["error"]):
            return False
    return True


def _execute(adapter: ReferenceProtocol, snapshot: str, sequence_id: str) -> SequenceResult | None:
    try:
        result = adapter.execute_sequence(json.loads(snapshot), sequence_id=sequence_id)
        # Validate against a separate copy: adapters cannot rewrite their own input receipt.
        if _valid_envelope(result, json.loads(snapshot), sequence_id):
            return result
        if isinstance(result, SequenceResult) and result.status == "timeout":
            return SequenceResult(sequence_id=sequence_id, observations=(), status="timeout")
    except Exception:
        # Never return exception messages/tracebacks containing protected inputs or paths.
        pass
    return None


def _difference_type(reference: Any, candidate: Any, *, action_count: int) -> str | None:
    if not isinstance(reference, list) or not isinstance(candidate, list):
        return "schema"
    if len(reference) != len(candidate) or len(reference) != action_count:
        return "state"
    for r, c in zip(reference, candidate):
        if not isinstance(r, dict) or not isinstance(c, dict):
            return "schema"
        if not _json_equal(r.get("ok"), c.get("ok")) or not _json_equal(r.get("error"), c.get("error")):
            return "error"
        if set(r) != set(c):
            return "schema"
        if not _json_equal(r, c):
            return "value"
    return None


class DifferentialVerifier:
    def __init__(self, reference: ReferenceProtocol, candidate: ReferenceProtocol):
        self._reference = reference
        self._candidate = candidate

    def verify(self, cases: list[SealedCase]) -> EvaluationReport:
        if not cases or len({c.case_id for c in cases}) != len(cases):
            raise ValueError("Need a nonempty suite with unique sealed case IDs")
        snapshots: list[str] = []
        for case in cases:
            actions = list(case.actions)
            if not _valid_json(actions):
                raise ValueError("Sealed actions must be finite JSON with bounded nesting")
            snapshots.append(json.dumps(actions, allow_nan=False, separators=(",", ":")))
        results: list[CaseResult] = []
        for case, snapshot in zip(cases, snapshots):
            # Opaque transport IDs prevent hidden case identifiers reaching candidate workers.
            ref = _execute(self._reference, snapshot, "ref-" + uuid4().hex)
            if ref is None or ref.status != "ok":
                results.append(CaseResult(case_id=case.case_id, outcome="indeterminate", mismatch_category="reference_unavailable"))
                continue
            cand = _execute(self._candidate, snapshot, "candidate-" + uuid4().hex)
            if cand is None or cand.status != "ok":
                category = "candidate_timeout" if cand is not None and cand.status == "timeout" else "candidate_protocol_error"
                results.append(CaseResult(case_id=case.case_id, outcome="failed", mismatch_category=category))
                continue
            expected = [o.output for o in ref.observations]
            actual = [o.output for o in cand.observations]
            category = _difference_type(expected, actual, action_count=len(case.actions))
            results.append(CaseResult(case_id=case.case_id, outcome="passed" if category is None else "failed", mismatch_category=category))
        counts = Counter(c.outcome for c in results)
        categories = Counter(c.mismatch_category for c in results if c.mismatch_category and c.outcome == "failed")
        return EvaluationReport(
            passed=counts["passed"], failed=counts["failed"], indeterminate=counts["indeterminate"],
            total=len(results), cases=tuple(results), diagnostic_class_counts=dict(categories)
        )
