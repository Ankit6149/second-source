"""Independent HTTP differential evaluation (G4 scaffolding).

Compares the owned HTTP reference fixture against an admitted HTTP
candidate on the same request sequences, resetting both per case.
Mismatch vocabulary mirrors the ledger verifier so cross-target reports
share categories:

- ``status``: HTTP status codes differ (includes error-code paths)
- ``schema``: response body key sets differ
- ``value``: same keys, different values

Only aggregate counts and categories leave this module toward any model
context; per-case detail stays in operator-side receipts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .http_candidate import HttpCandidateApp
from .http_target import HttpObservationAdapter, HttpRequest

HTTP_FAILURE_CATEGORIES = frozenset({"status", "schema", "value"})


@dataclass(frozen=True)
class HttpCase:
    case_id: str
    actions: tuple


@dataclass(frozen=True)
class HttpCaseResult:
    case_id: str
    outcome: str  # "passed" or a mismatch category
    mismatch_category: str | None = None


@dataclass(frozen=True)
class HttpVerificationReport:
    passed: int
    failed: int
    total: int
    failure_categories: dict
    cases: tuple

    def model_feedback(self) -> dict:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "indeterminate": 0,
            "total": self.total,
            "failure_categories": dict(self.failure_categories),
        }


def _difference(expected_status: int, expected_body: dict,
                actual_status: int, actual_body: dict) -> str | None:
    if expected_status != actual_status:
        return "status"
    if set(expected_body) != set(actual_body):
        return "schema"
    if expected_body != actual_body:
        return "value"
    return None


class HttpDifferentialVerifier:
    """Reference-vs-candidate comparison with per-case reset."""

    def __init__(self, reference: HttpObservationAdapter,
                 candidate: HttpCandidateApp) -> None:
        self._reference = reference
        self._candidate = candidate

    def verify(self, cases: list[HttpCase]) -> HttpVerificationReport:
        results: list[HttpCaseResult] = []
        categories: Counter = Counter()
        passed = 0
        for case in cases:
            self._reference.reset()
            self._candidate.reset()
            outcome: HttpCaseResult = HttpCaseResult(
                case_id=case.case_id, outcome="passed")
            for action in case.actions:
                assert isinstance(action, HttpRequest)
                observed = self._reference.exchange(action)
                reproduced = self._candidate.handle(action)
                mismatch = _difference(
                    observed.response.status, observed.response.body,
                    reproduced.status, reproduced.body)
                if mismatch is not None:
                    outcome = HttpCaseResult(
                        case_id=case.case_id, outcome=mismatch,
                        mismatch_category=mismatch)
                    categories[mismatch] += 1
                    break
            if outcome.outcome == "passed":
                passed += 1
            results.append(outcome)
        total = len(cases)
        return HttpVerificationReport(
            passed=passed, failed=total - passed, total=total,
            failure_categories=dict(categories), cases=tuple(results))
