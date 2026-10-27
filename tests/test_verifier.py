from pathlib import Path
import sys
import pytest
from second_source.reference import CLIReferenceAdapter
from second_source.verifier import DifferentialVerifier, SealedCase

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cases():
    return [
        SealedCase(case_id="empty", actions=({"command": "list"},)),
        SealedCase(case_id="stateful", actions=({"command": "add", "label": "A", "amount": 5}, {"command": "add", "label": "a", "amount": 6}, {"command": "total"})),
        SealedCase(case_id="removed", actions=({"command": "add", "label": "A", "amount": 5}, {"command": "remove", "id": "1"}, {"command": "total"})),
        SealedCase(case_id="invalid", actions=({"command": "add", "label": "A", "amount": -1},)),
    ]


def test_independent_verifier_detects_failures(reference, faulty, cases):
    report = DifferentialVerifier(reference, faulty).verify(cases)
    assert report.total == len(cases)
    assert report.passed == 1
    assert report.failed == 3
    assert report.indeterminate == 0
    assert sum([report.passed, report.failed, report.indeterminate]) == report.total
    assert report.diagnostic_class_counts


def test_identical_fixture_matches_on_gold(reference, cases):
    report = DifferentialVerifier(reference, reference).verify(cases)
    assert report.passed == len(cases) and report.failed == 0


def test_candidate_protocol_failure_is_failure(reference, cases):
    candidate = CLIReferenceAdapter([sys.executable, str(ROOT / "fixtures/candidates/protocol_broken.py")], cwd=ROOT)
    report = DifferentialVerifier(reference, candidate).verify(cases[:1])
    assert report.failed == 1
    assert report.cases[0].mismatch_category == "candidate_protocol_error"


def test_reference_unavailable_is_not_candidate_failure(reference, faulty, cases):
    unavailable = CLIReferenceAdapter([sys.executable, str(ROOT / "fixtures/candidates/protocol_broken.py")], cwd=ROOT)
    report = DifferentialVerifier(unavailable, faulty).verify(cases[:1])
    assert report.indeterminate == 1 and report.failed == 0


def test_no_gold_case_details_in_model_feedback(reference, faulty, cases):
    report = DifferentialVerifier(reference, faulty).verify(cases)
    feedback = str(report.model_feedback())
    assert "stateful" not in feedback
    assert "removed" not in feedback
    assert "command" not in feedback
    assert "actions" not in feedback


def test_invalid_suite_rejected(reference, cases):
    with pytest.raises(ValueError):
        DifferentialVerifier(reference, reference).verify([])
    with pytest.raises(ValueError):
        DifferentialVerifier(reference, reference).verify([cases[0], cases[0]])
