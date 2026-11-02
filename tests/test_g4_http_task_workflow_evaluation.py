"""Differential evaluation, candidate admission, scope guard, and isolation tests for G4."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from fixtures.owned_http_task_workflow import (
    HTTPCandidateError,
    HTTPCandidateInterpreter,
    HTTPDifferentialEvaluator,
    HTTPEvaluationBlocked,
    HTTPReferenceAdapter,
    SafeHTTPExperimentRunner,
    build_heldout_http_cases,
    build_http_guided_fill_control,
    build_http_naive_direct_fill,
    build_http_spec_skeleton,
    create_http_scope,
    extract_state_transitions,
    load_http_candidate,
    load_public_contract,
    load_sealed_http_suite,
    merge_http_skeleton_fill,
    prepare_http_generation_request,
    seal_http_task_workflow_suite,
    start_reference_server,
)
from second_source.evidence import EvidenceLedger
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.verifier import DifferentialVerifier


def test_safe_http_experiment_runner_enforces_scope_guard(tmp_path: Path) -> None:
    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url, max_reference_experiments=3)
        ref = HTTPReferenceAdapter(srv)
        ledger = EvidenceLedger(tmp_path / "ledger")
        runner = SafeHTTPExperimentRunner(contract, ref, ledger)

        # 1. Allowed request succeeds and records into EvidenceLedger
        res = runner.run_actions(
            [{"operation": "create_task", "actor": "alice", "body": {"title": "Scoped task", "priority": 3}}]
        )
        assert res.status == "ok"
        assert res.observations[0].output["http_status"] == 201

        # 2. Disallowed path (/v1/admin or /__admin/reset) raises PermissionError from ScopeGuard
        with pytest.raises(PermissionError, match="EXCLUDED_ROUTE|OUT_OF_OBSERVATION_SCOPE"):
            runner.run_actions(
                [{"method": "POST", "path": "/__admin/reset", "actor": "admin", "body": {}}]
            )

        # 3. Disallowed HTTP method (PUT) raises PermissionError from ScopeGuard
        with pytest.raises(PermissionError, match="ACTION_NOT_ALLOWED"):
            runner.run_actions(
                [{"method": "PUT", "path": "/v1/tasks/tsk-1", "actor": "alice", "body": {"title": "Nope"}}]
            )


def test_http_candidate_spec_admission_rejects_unsafe_or_malformed_specs() -> None:
    contract = create_http_scope("http://127.0.0.1:8000")
    public_contract = load_public_contract()
    skeleton = build_http_spec_skeleton(public_contract)
    valid_doc = merge_http_skeleton_fill(skeleton, build_http_guided_fill_control())

    loaded = load_http_candidate(valid_doc, contract)
    assert loaded.spec.subsystem == "http_task_workflow"
    assert loaded.digest.startswith("sha256:")

    # Reject extra/code-bearing fields (StrictModel forbids extra fields)
    with_code = dict(valid_doc)
    with_code["python_code"] = "import os; os.system('whoami')"
    with pytest.raises(HTTPCandidateError):
        load_http_candidate(with_code, contract)

    # Reject wrong subsystem outside ScopeContract
    wrong_subsystem = dict(valid_doc)
    wrong_subsystem["subsystem"] = "cli_ledger"
    with pytest.raises(HTTPCandidateError, match="Subsystem"):
        load_http_candidate(wrong_subsystem, contract)

    # Reject inverted priority bounds
    bad_bounds = merge_http_skeleton_fill(skeleton, build_http_guided_fill_control())
    bad_bounds["priority_rules"] = {
        "minimum": 5,
        "maximum": 1,
        "invalid_error": "invalid_priority",
    }
    with pytest.raises(HTTPCandidateError, match="priority minimum exceeds maximum"):
        load_http_candidate(bad_bounds, contract)


def test_positive_control_scores_30_of_30_and_works_with_core_verifier() -> None:
    public_contract = load_public_contract()
    skeleton = build_http_spec_skeleton(public_contract)
    cases = build_heldout_http_cases()
    assert len(cases) == 30

    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url)
        loaded = load_http_candidate(
            merge_http_skeleton_fill(skeleton, build_http_guided_fill_control()),
            contract,
        )
        ref = HTTPReferenceAdapter(srv)
        cand = HTTPCandidateInterpreter(loaded.spec)

        evaluator = HTTPDifferentialEvaluator(ref, cand)
        report = evaluator.evaluate(cases)
        assert report.total == 30
        assert report.passed == 30
        assert report.failed == 0
        assert report.indeterminate == 0
        assert report.http_dimension_counts == {}

        # Also verify direct compatibility with core DifferentialVerifier
        core_verifier = DifferentialVerifier(ref, cand)
        core_report = core_verifier.verify(cases[:6])
        assert core_report.total == 6
        assert core_report.passed == 6
        assert core_report.failed == 0


def test_negative_controls_distinguish_error_headers_state_and_value_mismatches() -> None:
    public_contract = load_public_contract()
    skeleton = build_http_spec_skeleton(public_contract)
    cases = build_heldout_http_cases()

    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url)
        ref = HTTPReferenceAdapter(srv)

        # 1. Naive direct fill has permissive transitions, wrong bounds, and no delete lock -> fails with error/state mismatches
        naive_doc = merge_http_skeleton_fill(skeleton, build_http_naive_direct_fill())
        naive_cand = HTTPCandidateInterpreter(load_http_candidate(naive_doc, contract).spec)
        rep_naive = HTTPDifferentialEvaluator(ref, naive_cand).evaluate(cases)
        assert rep_naive.passed < 25
        assert rep_naive.failed >= 5
        assert rep_naive.http_dimension_counts.get("error", 0) >= 4

        # 2. Missing protocol headers (Location, X-Task-Revision) -> fails with 'headers' (mapped to 'schema' in engine)
        header_fill = build_http_guided_fill_control()
        header_fill["emit_location_header"] = False
        header_fill["emit_revision_header"] = False
        header_doc = merge_http_skeleton_fill(skeleton, header_fill)
        header_cand = HTTPCandidateInterpreter(load_http_candidate(header_doc, contract).spec)
        rep_header = HTTPDifferentialEvaluator(ref, header_cand).evaluate(cases)
        assert rep_header.http_dimension_counts.get("headers", 0) >= 15
        assert rep_header.engine_EvaluationReport.diagnostic_class_counts.get("schema", 0) >= 15

        # 3. Default pagination limit defect (5 instead of 10) -> value mismatch on list queries
        value_fill = build_http_guided_fill_control()
        value_fill["query_rules"]["default_limit"] = 5
        value_doc = merge_http_skeleton_fill(skeleton, value_fill)
        value_cand = HTTPCandidateInterpreter(load_http_candidate(value_doc, contract).spec)
        rep_value = HTTPDifferentialEvaluator(ref, value_cand).evaluate(cases)
        assert rep_value.http_dimension_counts.get("value", 0) >= 1


def test_state_transition_extraction_records_lifecycle() -> None:
    public_contract = load_public_contract()
    skeleton = build_http_spec_skeleton(public_contract)
    contract = create_http_scope("http://127.0.0.1:8000")
    loaded = load_http_candidate(
        merge_http_skeleton_fill(skeleton, build_http_guided_fill_control()),
        contract,
    )
    interp = HTTPCandidateInterpreter(loaded.spec)
    seq_res = interp.execute_sequence(
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "Lifecycle", "priority": 3}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "done"}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress"}},
            {"operation": "get_task", "task_id": "tsk-1", "actor": "viewer"},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "done"}},
            {"operation": "delete_task", "task_id": "tsk-1", "actor": "alice"},
        ]
    )
    transitions = extract_state_transitions(seq_res.observations)
    assert [t.outcome for t in transitions] == [
        "mutated",
        "rejected",
        "mutated",
        "read_only",
        "mutated",
        "mutated",
    ]
    assert transitions[0].post_status == "todo"
    assert transitions[1].http_status == 409
    assert transitions[2].prior_status == "todo" and transitions[2].post_status == "in_progress"
    assert transitions[4].prior_status == "in_progress" and transitions[4].post_status == "done"
    assert transitions[5].prior_status == "done" and transitions[5].post_status == "deleted"


def test_sealed_suite_and_generation_wire_isolation(tmp_path: Path) -> None:
    contract = create_http_scope("http://127.0.0.1:8000")
    public_contract = load_public_contract()

    # 1. Sealing inside repository root must be rejected
    in_repo_dir = Path(__file__).resolve().parent / "_illegal_sealed"
    with pytest.raises(HTTPEvaluationBlocked, match="outside Git checkouts"):
        seal_http_task_workflow_suite(in_repo_dir, contract)

    # 2. Sealing in an external temporary directory outside any git repo succeeds
    with tempfile.TemporaryDirectory() as ext_tmp:
        sealed_dir = Path(ext_tmp) / "sealed_g4_suite"
        suite_path, suite_digest = seal_http_task_workflow_suite(sealed_dir, contract)
        loaded_suite = load_sealed_http_suite(suite_path, suite_digest, contract)
        assert len(loaded_suite.cases()) == 30

    # 3. Wire preparation succeeds on clean observations and fails on oracle/sealed leakage
    with start_reference_server() as srv:
        live_contract = create_http_scope(srv.base_url)
        ref = HTTPReferenceAdapter(srv)
        ledger = EvidenceLedger(tmp_path / "wire_ledger")
        runner = SafeHTTPExperimentRunner(live_contract, ref, ledger)
        res = runner.run_actions(
            [{"operation": "create_task", "actor": "alice", "body": {"title": "CleanProbe", "priority": 3}}]
        )
        digest = ledger.store(res.observations[0])["sha256"]

        hyps = HypothesisStore()
        hyps.add_batch(
            validate_batch(
                {
                    "hypotheses": [
                        {
                            "id": "h1",
                            "statement": "POST /v1/tasks creates todo task with revision 1",
                            "evidence_ids": [digest],
                            "status": "supported",
                        }
                    ]
                },
                frozenset([digest]),
            )
        )

        clean_req = prepare_http_generation_request(
            contract=live_contract,
            public_contract=public_contract,
            ledger=ledger,
            observation_digests=[digest],
            hypotheses=hyps,
            forbidden_markers=["SECRET_CANARY_TOKEN"],
        )
        assert clean_req.prompt_version == "http-synthesize-v1"

        # If a forbidden marker or reference class name appears in hypotheses, wire builder blocks it
        leaked_hyps = HypothesisStore()
        leaked_hyps.add_batch(
            validate_batch(
                {
                    "hypotheses": [
                        {
                            "id": "h_leak",
                            "statement": "Saw TaskWorkflowReferenceState in source",
                            "evidence_ids": [digest],
                            "status": "hypothesized",
                        }
                    ]
                },
                frozenset([digest]),
            )
        )
        with pytest.raises(HTTPEvaluationBlocked, match="Protected material detected"):
            prepare_http_generation_request(
                contract=live_contract,
                public_contract=public_contract,
                ledger=ledger,
                observation_digests=[digest],
                hypotheses=leaked_hyps,
            )
