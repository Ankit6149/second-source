"""Evaluator tests. Private sequence values are generated only in external tmp storage."""
import json
from pathlib import Path
import sys

import pytest

from second_source.candidate_adapter import CandidateReferenceAdapter, CandidateExecutionLimits, ExecutionUnavailable
from second_source.g3_verification import (
    EvaluationBlocked, _admit_suite, _digest, _encode, _scope_digest,
    OwnedLedgerReferenceAdapter, evaluate_sealed_suite, evidence_manifest, load_sealed_suite, seal_owned_ledger_suite,
)
from second_source.reference import CLIReferenceAdapter

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "tests/g3_fixtures/valid_candidate.json"


def public_suite(scope, actions=None):
    raw = _encode({"suite_version": "1", "scope_digest": _scope_digest(scope), "cases": [
        {"case_id": "public-probe", "category": "public", "actions": actions or [{"command": "list"}]},
    ]})
    return _admit_suite(raw, _digest(raw), scope)


def test_private_sealed_positive_and_deliberately_bad_controls(cli_scope, reference, tmp_path):
    path, digest = seal_owned_ledger_suite(tmp_path / "evaluator", cli_scope)
    suite = load_sealed_suite(path, digest, cli_scope)
    positive = CandidateReferenceAdapter(CONTROL.read_bytes(), cli_scope)
    good = evaluate_sealed_suite(suite, cli_scope, reference, positive)
    assert good.total == 25 and good.indeterminate == 0
    counts = []
    for rule, value in (("unique_casefold", False), ("trim", False), ("maximum", 99)):
        doc = json.loads(CONTROL.read_bytes())
        # Each is explicitly a deliberately buggy TRUSTED_CONTROL, never model output.
        if rule == "trim":
            doc["commands"]["add"]["params"]["label"][rule] = value
        elif rule == "maximum":
            doc["commands"]["add"]["params"]["amount"][rule] = value
        else:
            doc["commands"]["add"][rule] = value
        negative = CandidateReferenceAdapter(_encode(doc), cli_scope)
        bad = evaluate_sealed_suite(suite, cli_scope, reference, negative)
        assert bad.failed > 0 and bad.indeterminate == 0
        assert bad.passed + bad.failed == bad.total == good.total
        counts.append(bad.failed)
    # Check genuine additional sensitivity even while a shared Muse semantic
    # regression blocks the positive control. Never hide the positive failure.
    assert counts == [good.failed + 2, good.failed + 2, good.failed + 1]
    assert good.passed == good.total
    replay = evaluate_sealed_suite(suite, cli_scope, reference, positive)
    assert replay == good
    assert suite.digest == digest
    report = evidence_manifest(suite, positive, good)
    wire = json.dumps(report)
    assert all(case.case_id not in wire for case in suite.cases())
    assert "cases" not in wire and "actions" not in report["evaluation"]
    assert report["arbitrary_code_sandbox"] is False


def test_bounded_reference_matches_existing_g0_adapter(cli_scope, reference):
    from second_source.verifier import DifferentialVerifier, SealedCase
    cases = [SealedCase(case_id="public-state", actions=(
        {"command": "add", "label": "public-probe", "amount": 4},
        {"command": "list"}, {"command": "total"},
        {"command": "remove", "id": "1"}, {"command": "total"},
    )), SealedCase(case_id="public-errors", actions=(
        {"command": "add"}, {"command": "remove", "id": 7},
    ))]
    bounded = OwnedLedgerReferenceAdapter(cli_scope)
    report = DifferentialVerifier(reference, bounded).verify(cases)
    assert report.passed == report.total == 2
    assert bounded.execute_sequence([{"command": "list"}] * 65).status == "protocol_error"


def test_suite_is_create_once_digest_pinned_and_detached(cli_scope, tmp_path):
    path, digest = seal_owned_ledger_suite(tmp_path / "evaluator", cli_scope)
    with pytest.raises(EvaluationBlocked, match="never overwrite"):
        seal_owned_ledger_suite(path.parent, cli_scope)
    with pytest.raises(EvaluationBlocked, match="digest mismatch"):
        load_sealed_suite(path, "sha256:" + "0" * 64, cli_scope)
    suite = load_sealed_suite(path, digest, cli_scope)
    cases = suite.cases()
    cases[0].actions[0]["command"] = "poison"
    assert suite.cases()[0].actions[0]["command"] != "poison"
    changed = cli_scope.model_copy(update={"goal": "A different scope contract"})
    with pytest.raises(EvaluationBlocked, match="wrong-scope"):
        load_sealed_suite(path, digest, changed)


def test_suite_cannot_be_created_inside_a_git_checkout(cli_scope):
    with pytest.raises(EvaluationBlocked, match="outside Git"):
        seal_owned_ledger_suite(ROOT / "private-gold-must-not-be-created", cli_scope)
    assert not (ROOT / "private-gold-must-not-be-created").exists()


@pytest.mark.parametrize("change", ["command", "analysis", "budget", "subsystem"])
def test_scope_denial_happens_before_either_executor(cli_scope, monkeypatch, change):
    scope = cli_scope
    actions = [{"command": "list"}]
    if change == "command":
        actions = [{"command": "admin_reset"}]
    elif change == "analysis":
        from second_source.contracts import ScopeMode
        scope = scope.model_copy(update={"mode": ScopeMode.ANALYSIS_ONLY})
    elif change == "subsystem":
        scope = scope.model_copy(update={"implementation": scope.implementation.model_copy(update={"allowed_subsystems": frozenset({"other"})})})
    suite = public_suite(scope, actions)
    if change == "budget":
        doc = json.loads(suite._raw)
        doc["cases"] *= 31
        for i, case in enumerate(doc["cases"]):
            # JSON multiplication shares dicts: detach via serialization before assigning IDs.
            doc["cases"][i] = {**case, "case_id": f"public-{i}"}
        raw = _encode(doc)
        suite = _admit_suite(raw, _digest(raw), scope)

    class Never:
        limits = CandidateExecutionLimits()
        def execute_sequence(self, *args, **kwargs):
            pytest.fail("Denied suite invoked an executor")
        def check_containment(self):
            pytest.fail("Denied suite invoked a worker")
    with pytest.raises(EvaluationBlocked):
        evaluate_sealed_suite(suite, scope, Never(), Never())


def test_missing_backend_blocks_evaluation_before_reference(cli_scope, monkeypatch):
    candidate = CandidateReferenceAdapter(CONTROL.read_bytes(), cli_scope)
    monkeypatch.setattr(candidate, "check_containment", lambda: (_ for _ in ()).throw(ExecutionUnavailable()))
    class Never:
        def execute_sequence(self, *args, **kwargs):
            pytest.fail("Uncontained evaluation reached reference")
    with pytest.raises(ExecutionUnavailable):
        evaluate_sealed_suite(public_suite(cli_scope), cli_scope, Never(), candidate)


def test_timeout_and_protocol_controls_have_exact_accounting(cli_scope, reference):
    from second_source.verifier import DifferentialVerifier
    cases = public_suite(cli_scope).cases()
    for name, expected in (("protocol_broken.py", "candidate_protocol_error"), ("timeout.py", "candidate_timeout")):
        candidate = CLIReferenceAdapter([sys.executable, str(ROOT / "fixtures/candidates" / name)], cwd=ROOT, timeout_seconds=0.2)
        report = DifferentialVerifier(reference, candidate).verify(cases)
        assert report.failed == report.total == 1 and report.cases[0].mismatch_category == expected
    unavailable = CLIReferenceAdapter([sys.executable, str(ROOT / "fixtures/candidates/protocol_broken.py")], cwd=ROOT)
    report = DifferentialVerifier(unavailable, reference).verify(cases)
    assert report.indeterminate == report.total == 1 and report.failed == 0


@pytest.mark.parametrize("action", [{"command": "add"}, {"command": "add", "label": "", "amount": 0}])
def test_parameter_precedence_matches_original_for_both_representations(cli_scope, reference, action):
    from second_source.verifier import DifferentialVerifier, SealedCase
    raw = CONTROL.read_bytes()
    canonical_dict = json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")).encode()
    case = SealedCase(case_id="public-validation-order", actions=(action,))
    observed = reference.execute_sequence([action])
    assert observed.observations[0].output == {"ok": False, "error": "invalid_label"}
    text_report = DifferentialVerifier(reference, CandidateReferenceAdapter(raw, cli_scope)).verify([case])
    dict_report = DifferentialVerifier(reference, CandidateReferenceAdapter(canonical_dict, cli_scope)).verify([case])
    assert text_report == dict_report
    assert text_report.passed == dict_report.passed == 1
    # The evaluator never repairs candidate semantics to make this pass.


def test_persistent_state_negative_control_is_detected(cli_scope, reference):
    from second_source.candidate_spec import load_candidate
    from second_source.candidate_runtime import CandidateInterpreter
    from second_source.verifier import DifferentialVerifier, SealedCase
    interpreter = CandidateInterpreter(load_candidate(CONTROL.read_bytes(), cli_scope).spec)
    class StickyTrustedControl:
        def __init__(self):
            self.history = []
        def execute_sequence(self, actions, *, sequence_id=None):
            offset = len(self.history)
            self.history.extend(actions)
            result = interpreter.execute_sequence(self.history, sequence_id=sequence_id)
            return result.model_copy(update={"observations": tuple(
                obs.model_copy(update={"observation_id": f"{sequence_id}:{i}", "action_index": i})
                for i, obs in enumerate(result.observations[offset:])
            )})
    cases = [SealedCase(case_id="public-state-one", actions=({"command": "add", "label": "public", "amount": 1},)),
             SealedCase(case_id="public-state-two", actions=({"command": "total"},))]
    report = DifferentialVerifier(reference, StickyTrustedControl()).verify(cases)
    assert report.passed == 1 and report.failed == 1
