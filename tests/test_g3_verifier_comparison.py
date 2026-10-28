"""Public synthetic comparator probes; these are not sealed score cases."""
from copy import deepcopy

import pytest

from second_source.contracts import Observation, SequenceResult
from second_source.verifier import DifferentialVerifier, SealedCase


class ResultAdapter:
    def __init__(self, output=None, change=None):
        self.output = {"ok": True, "count": 1} if output is None else output
        self.change = change
        self.called = 0

    def execute_sequence(self, actions, *, sequence_id=None):
        self.called += 1
        result = SequenceResult(
            sequence_id=sequence_id,
            observations=tuple(Observation(
                observation_id=f"{sequence_id}:{i}", sequence_id=sequence_id,
                action_index=i, input_action=deepcopy(action),
                output=deepcopy(self.output), exit_code=0, duration_ms=0,
                status="ok" if self.output.get("ok") is True else "target_error",
            ) for i, action in enumerate(actions)), status="ok",
        )
        return self.change(result, actions) if self.change else result


def suite():
    return [SealedCase(case_id="public-synthetic", actions=({"command": "total"},))]


def patch_observation(**changes):
    def change(result, actions):
        obs = result.observations[0].model_copy(update=changes)
        return result.model_copy(update={"observations": (obs,)})
    return change


@pytest.mark.parametrize("reference,candidate", [
    ({"ok": True, "count": 1}, {"ok": True, "count": True}),
    ({"ok": True, "count": 1}, {"ok": True, "count": 1.0}),
    ({"ok": True, "items": [{"amount": 1}]}, {"ok": True, "items": [{"amount": True}]}),
])
def test_json_types_cannot_false_pass(reference, candidate):
    report = DifferentialVerifier(ResultAdapter(reference), ResultAdapter(candidate)).verify(suite())
    assert report.failed == 1


@pytest.mark.parametrize("changes", [
    {"exit_code": 7}, {"status": "timeout"}, {"status": "protocol_error"},
    {"status": "target_error"}, {"action_index": 3},
    {"sequence_id": "wrong"}, {"observation_id": "wrong"},
    {"input_action": {"command": "list"}}, {"duration_ms": -1},
])
def test_inconsistent_candidate_envelope_fails(changes):
    report = DifferentialVerifier(ResultAdapter(), ResultAdapter(change=patch_observation(**changes))).verify(suite())
    assert report.failed == 1 and report.cases[0].mismatch_category == "candidate_protocol_error"


@pytest.mark.parametrize("output", [{}, {"ok": 1}, {"ok": False}, {"ok": True, "x": float("nan")}])
def test_malformed_reference_is_indeterminate_even_when_candidate_matches(output):
    report = DifferentialVerifier(ResultAdapter(output), ResultAdapter(output)).verify(suite())
    assert report.indeterminate == 1 and report.passed == 0


def test_business_errors_are_comparable():
    report = DifferentialVerifier(ResultAdapter({"ok": False, "error": "invalid_amount"}),
                                  ResultAdapter({"ok": False, "error": "invalid_amount"})).verify(suite())
    assert report.passed == 1


def test_reference_and_candidate_cannot_mutate_suite_or_each_other():
    cases = suite()
    seen = []

    def mutate(result, actions):
        actions[0]["poison"] = {"private": "synthetic"}
        return result

    def inspect(result, actions):
        seen.append(deepcopy(actions))
        return result

    report = DifferentialVerifier(ResultAdapter(change=mutate), ResultAdapter(change=inspect)).verify(cases)
    assert report.passed == 1
    assert "poison" not in seen[0][0] and "poison" not in cases[0].actions[0]


def test_exceptions_are_sanitized_and_every_case_is_counted():
    def broken(result, actions):
        raise RuntimeError("PRIVATE_SYNTHETIC_CANARY")

    cases = suite() + [SealedCase(case_id="another-public", actions=({"command": "list"},))]
    report = DifferentialVerifier(ResultAdapter(), ResultAdapter(change=broken)).verify(cases)
    assert report.failed == report.total == 2
    assert "CANARY" not in report.model_dump_json()


def test_unavailable_reference_does_not_execute_candidate():
    ref = ResultAdapter(change=lambda result, actions: result.model_copy(update={"status": "timeout"}))
    candidate = ResultAdapter()
    report = DifferentialVerifier(ref, candidate).verify(suite())
    assert report.indeterminate == 1 and candidate.called == 0


def test_feedback_is_detached_and_contains_only_fixed_categories():
    report = DifferentialVerifier(ResultAdapter(), ResultAdapter({"ok": True, "count": 2})).verify(suite())
    feedback = report.model_feedback()
    feedback["failure_categories"]["PRIVATE_CANARY"] = 1
    assert "PRIVATE_CANARY" not in report.model_feedback()["failure_categories"]
    assert set(report.model_feedback()) == {"passed", "failed", "indeterminate", "total", "failure_categories"}


@pytest.mark.parametrize("field,value", [("sequence_id", "wrong"), ("observations", ()), ("stderr", "private")])
def test_invalid_sequence_envelopes_cannot_pass(field, value):
    change = lambda result, actions: result.model_copy(update={field: value})
    report = DifferentialVerifier(ResultAdapter(), ResultAdapter(change=change)).verify(suite())
    assert report.failed == 1
    report = DifferentialVerifier(ResultAdapter(change=change), ResultAdapter()).verify(suite())
    assert report.indeterminate == 1


def test_ordering_missing_and_extra_keys_are_not_normalized_away():
    for output in ({"ok": True, "count": 1, "extra": 0}, {"ok": True},
                   {"ok": True, "items": [2, 1]}):
        expected = {"ok": True, "items": [1, 2]} if "items" in output else {"ok": True, "count": 1}
        assert DifferentialVerifier(ResultAdapter(expected), ResultAdapter(output)).verify(suite()).failed == 1


def test_no_case_identifier_is_sent_to_executors():
    seen = []
    def inspect(result, actions):
        seen.append(result.sequence_id)
        return result
    DifferentialVerifier(ResultAdapter(change=inspect), ResultAdapter(change=inspect)).verify(suite())
    assert all("public-synthetic" not in value for value in seen)
