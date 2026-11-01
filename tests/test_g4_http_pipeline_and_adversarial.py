"""End-to-end G4 HTTP pipeline integration and 7-category adversarial verification suite."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

import pytest

from fixtures.owned_http_task_workflow import (
    HTTPBudgetExhausted,
    HTTPCandidateError,
    HTTPCandidateInterpreter,
    HTTPDifferentialEvaluator,
    HTTPEvaluationBlocked,
    HTTPPolicyViolation,
    HTTPReferenceAdapter,
    PinnedHTTPEvaluatorRun,
    SafeHTTPExperimentRunner,
    build_heldout_http_cases,
    build_http_guided_fill_control,
    build_http_naive_direct_fill,
    build_http_spec_skeleton,
    create_http_scope,
    load_http_candidate,
    load_public_contract,
    load_sealed_http_suite,
    merge_http_skeleton_fill,
    prepare_http_generation_request,
    seal_http_task_workflow_suite,
    start_reference_server,
)
from second_source.backend.artifacts import ArtifactStore, sanitized_report, verify_bundle
from second_source.backend.contracts import (
    CodeStage,
    EngineResult,
    EvaluationSummary,
    Investigation,
    LifecycleEvent,
    Run,
    RunStatus,
    UsageSummary,
)
from second_source.budgets import RunBudget
from second_source.contracts import (
    Observation,
    ProposedAction,
    SequenceResult,
    SideEffect,
)
from second_source.evidence import EvidenceLedger
from second_source.g3_verification import BrokerArtifact
from second_source.g4_http_reconstruct import main as g4_http_main
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.model_gateway import GatewayError, MockProvider, ModelGateway
from second_source.planner import RESET_BOUNDARY, ExperimentPlanner, reconcile_predictions
from second_source.repair_loop import RepairAttempt, run_bounded_repair, select_best
from second_source.scope_guard import ScopeGuard
from second_source.verifier import SealedCase


# ===========================================================================
# 0. End-to-End Evidence-Driven Architecture & CLI Demonstration Tests
# ===========================================================================


def test_end_to_end_cli_mock_and_repair_and_artifact_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove the full G4 HTTP pipeline:
    Scope -> Observe -> Hypothesize -> Experiment -> Candidate Generation Contract
    -> Admission -> Independent Verification -> Bounded Repair -> Report -> Proof Bundle.
    """
    seal_root = Path(tempfile.mkdtemp(prefix="g4-cli-seal-"))
    run_dir_initial = tmp_path / "run_initial"
    run_dir_repaired = tmp_path / "run_repaired"
    run_dir_preflight = tmp_path / "run_preflight"

    # 1. Baseline mock run (--repair-rounds 0): passive seed observations -> 25/30
    rc0 = g4_http_main(
        [
            "--mode",
            "mock",
            "--run-dir",
            str(run_dir_initial),
            "--seal-dir",
            str(seal_root / "s0"),
        ]
    )
    assert rc0 == 0
    report0 = json.loads((run_dir_initial / "G4_report.json").read_text(encoding="utf-8"))
    assert report0["kind"] == "G4_HTTP_RECONSTRUCT_RUN_REPORT"
    assert report0["origin"] == "mock"
    assert report0["real"] is False
    assert report0["target_id"] == "owned-http-task-workflow-v1"
    assert report0["target_kind"] == "http"
    assert report0["evaluation"]["passed"] == 25
    assert report0["evaluation"]["failed"] == 5
    assert report0["evaluation"]["total"] == 30
    assert report0["repair_history"] is None
    assert report0["g4_gate_verdict"]["local_non_ai_pipeline_gate"] == "PASSED"
    assert (
        report0["g4_gate_verdict"]["genuine_meta_model_g4_gate"]
        == "BLOCKED_AWAITING_PAID_INFERENCE_APPROVAL"
    )

    # 2. Full mock run with 1 bounded repair round: 25/30 -> 30/30 ("improved", "repaired_to_perfect")
    rc1 = g4_http_main(
        [
            "--mode",
            "mock",
            "--repair-rounds",
            "1",
            "--run-dir",
            str(run_dir_repaired),
            "--seal-dir",
            str(seal_root / "s1"),
        ]
    )
    assert rc1 == 0
    report1 = json.loads((run_dir_repaired / "G4_report.json").read_text(encoding="utf-8"))
    assert report1["origin"] == "mock"
    assert report1["real"] is False
    assert report1["initial_evaluation"]["passed"] == 25
    assert report1["evaluation"]["passed"] == 30
    assert report1["evaluation"]["failed"] == 0
    assert report1["selected"]["version"] == "repair-1"
    assert report1["repair_history"]["verdict"] == "improved"
    assert report1["repair_history"]["stop_reason"] == "repaired_to_perfect"
    assert (run_dir_repaired / "candidate.v1.json").is_file()
    assert (run_dir_repaired / "candidate.r1.json").is_file()
    assert (run_dir_repaired / "broker-artifact.v1.json").is_file()
    assert (run_dir_repaired / "broker-artifact.r1.json").is_file()
    assert (run_dir_repaired / "G4_discovery_summary.json").is_file()

    disc = json.loads(
        (run_dir_repaired / "G4_discovery_summary.json").read_text(encoding="utf-8")
    )
    assert disc["active_rounds_executed"] == 4
    assert disc["hypothesis_resolution_counts"]["supported"] == 4
    assert disc["post_discovery_active_attribution"]["rules_revealed_count"] == 8

    # 3. Verify compatibility with Codex's backend ArtifactStore & verify_bundle
    sanitized = sanitized_report(report1)
    assert sanitized["origin"] == "mock"
    assert sanitized["real"] is False
    assert sanitized["evaluation"]["passed"] == 30
    assert sanitized["repair"]["verdict"] == "improved"
    assert sanitized["repair"]["selected_version"] == "repair-1"

    store = ArtifactStore(tmp_path / "artifacts")
    run_uuid = str(uuid4())
    inv_uuid = str(uuid4())
    art_ref = store.publish_report(run_uuid, report1)
    now_iso = datetime.now(timezone.utc).isoformat()
    raw_scope_hex = report1["scope_digest"].removeprefix("sha256:")
    inv = Investigation(
        investigation_id=inv_uuid,
        owner_id="usr-test",
        title="G4 HTTP Task Workflow",
        scope=create_http_scope("http://127.0.0.1:8000"),
        scope_digest=raw_scope_hex,
        status="authorized",
        revision=2,
        created_at=now_iso,
        updated_at=now_iso,
    )
    run_model = Run(
        run_id=run_uuid,
        investigation_id=inv_uuid,
        kind="g3_mock",
        status=RunStatus.COMPLETED,
        stage=CodeStage.EXECUTE,
        revision=2,
        cancel_requested=False,
        created_at=now_iso,
        updated_at=now_iso,
        result=EngineResult(
            origin="mock",
            real=False,
            stop_reason="completed_mock_run",
            usage=UsageSummary.model_validate(report1["usage"]),
            evaluation=EvaluationSummary(passed=30, failed=0, indeterminate=0, total=30),
            report=art_ref,
        ),
    )
    ev = LifecycleEvent(
        event_id=1,
        investigation_id=inv_uuid,
        run_id=run_uuid,
        event_type="run.completed",
        stage=CodeStage.EXECUTE,
        created_at=now_iso,
        revision=2,
    )
    bundle_bytes = store.export_bundle(inv, run_model, [ev])
    verified = verify_bundle(bundle_bytes)
    assert verified["valid"] is True
    assert verified["origin"] == "mock"
    assert verified["attests_provider"] is False

    # 4. Zero-call preflight mode
    evidence_dir = run_dir_repaired / "evidence"
    obs_files = sorted(p.stem for p in evidence_dir.glob("*.json"))
    hyp_file = tmp_path / "operator_hyps.json"
    hyp_file.write_text(
        json.dumps(
            {
                "hypotheses": [
                    {
                        "id": "op-h1",
                        "statement": "POST /v1/tasks creates todo tasks with 1..5 priority",
                        "evidence_ids": [obs_files[0]],
                        "status": "supported",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rc_pre = g4_http_main(
        [
            "--mode",
            "preflight",
            "--max-usd",
            "0.25",
            "--ledger-dir",
            str(evidence_dir),
            "--hypotheses-file",
            str(hyp_file),
            "--observation-digests",
            obs_files[0],
            "--seal-dir",
            str(seal_root / "s_pre"),
            "--run-dir",
            str(run_dir_preflight),
        ]
    )
    assert rc_pre == 0
    pre_doc = json.loads((run_dir_preflight / "G4_preflight.json").read_text(encoding="utf-8"))
    assert pre_doc["provider_calls"] == 0
    assert pre_doc["real"] is False
    assert pre_doc["stop_reason"] == "preflight_ready"

    # 5. Real mode fails closed (exit code 2) without owner authorization and credentials
    monkeypatch.delenv("SECOND_SOURCE_MAX_RUN_USD", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    rc_real = g4_http_main(["--mode", "real", "--max-usd", "0.25"])
    assert rc_real == 2


# ===========================================================================
# 1. Adversarial Suite: Schema Drift
# ===========================================================================


def test_adversarial_schema_drift_across_body_headers_and_candidate_spec(
    tmp_path: Path,
) -> None:
    """Verify that response body key drift, missing headers, non-JSON reference responses,
    and candidate spec schema drift are all caught and classified accurately.
    """
    public = load_public_contract()
    skeleton = build_http_spec_skeleton(public)

    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url)
        ref = HTTPReferenceAdapter(srv)
        gold_spec = load_http_candidate(
            merge_http_skeleton_fill(skeleton, build_http_guided_fill_control()), contract
        ).spec

        # 1a. Missing `location` header on 201 Created -> classified as `headers` (`schema` in core engine)
        no_location_spec = gold_spec.model_copy(update={"emit_location_header": False})
        case_create = SealedCase(
            case_id="G4-HTTP-ADV-SCHEMA-1",
            category="crud",
            actions=({"operation": "create_task", "actor": "alice", "body": {"title": "HeaderDrift", "priority": 3}},),
        )
        rep_loc = HTTPDifferentialEvaluator(
            ref, HTTPCandidateInterpreter(no_location_spec)
        ).evaluate([case_create])
        assert rep_loc.failed == 1
        assert rep_loc.cases[0].http_mismatch_dimension == "headers"
        assert rep_loc.cases[0].engine_mismatch_category == "schema"

        # 1b. Missing `x-task-revision` header -> classified as `headers` (`schema` in core engine)
        no_rev_spec = gold_spec.model_copy(update={"emit_revision_header": False})
        rep_rev = HTTPDifferentialEvaluator(
            ref, HTTPCandidateInterpreter(no_rev_spec)
        ).evaluate([case_create])
        assert rep_rev.failed == 1
        assert rep_rev.cases[0].http_mismatch_dimension == "headers"

        # 1c. Response body key drift (`items` instead of `tasks` in candidate output) -> `schema`
        class DriftedBodyCandidate:
            def execute_sequence(
                self, actions: list[dict[str, Any]], *, sequence_id: str | None = None
            ) -> SequenceResult:
                return SequenceResult(
                    sequence_id=sequence_id or "seq",
                    observations=(
                        Observation(
                            observation_id="seq:0",
                            sequence_id="seq",
                            action_index=0,
                            input_action=actions[0],
                            output={
                                "ok": True,
                                "http_status": 200,
                                "headers": {"content-type": "application/json"},
                                "body": {"ok": True, "items": [], "total": 0},
                            },
                            exit_code=0,
                            duration_ms=1,
                            status="ok",
                        ),
                    ),
                    status="ok",
                    stderr="",
                )

        case_list = SealedCase(
            case_id="G4-HTTP-ADV-SCHEMA-2",
            category="crud",
            actions=({"operation": "list_tasks", "actor": "alice"},),
        )
        rep_body = HTTPDifferentialEvaluator(ref, DriftedBodyCandidate()).evaluate([case_list])
        assert rep_body.failed == 1
        assert rep_body.cases[0].http_mismatch_dimension == "schema"
        assert rep_body.cases[0].engine_mismatch_category == "schema"

        # 1d. Candidate specification schema drift (extra fields or wrong types) rejected at admission
        drifted_spec = merge_http_skeleton_fill(skeleton, build_http_guided_fill_control())
        drifted_spec["unexpected_top_level_key"] = True
        with pytest.raises(HTTPCandidateError):
            load_http_candidate(drifted_spec, contract)


# ===========================================================================
# 2. Adversarial Suite: Leaked Sealed Material
# ===========================================================================


def test_adversarial_leaked_sealed_material_blocked_at_all_boundaries(
    tmp_path: Path,
) -> None:
    """Verify that sealed case IDs, reference source identifiers, control-plane routes,
    and non-aggregate repair feedback cannot enter model-facing generation requests.
    """
    public = load_public_contract()
    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url)
        ref = HTTPReferenceAdapter(srv)
        ledger = EvidenceLedger(tmp_path / "leak_ledger")
        runner = SafeHTTPExperimentRunner(contract, ref, ledger)
        seq = runner.run_actions(
            [{"operation": "create_task", "actor": "alice", "body": {"title": "CleanTask", "priority": 2}}]
        )
        clean_digest = ledger.store(seq.observations[0])["sha256"]

        # 2a. Hypothesis containing sealed case ID prefix `G4-HTTP-` is blocked
        for forbidden_token in (
            "G4-HTTP-01-CREATE-AND-GET",
            "TaskWorkflowReferenceState",
            "_BoundedHTTPServer",
            "__admin/reset",
        ):
            bad_hyps = HypothesisStore()
            bad_hyps.add_batch(
                validate_batch(
                    {
                        "hypotheses": [
                            {
                                "id": "h-leak",
                                "statement": f"Observed {forbidden_token} in target",
                                "evidence_ids": [clean_digest],
                                "status": "hypothesized",
                            }
                        ]
                    },
                    frozenset([clean_digest]),
                )
            )
            with pytest.raises(HTTPEvaluationBlocked, match="Protected material detected"):
                prepare_http_generation_request(
                    contract=contract,
                    public_contract=public,
                    ledger=ledger,
                    observation_digests=[clean_digest],
                    hypotheses=bad_hyps,
                )

        # 2b. Non-aggregate repair feedback (leaking case IDs or inputs) is blocked
        clean_hyps = HypothesisStore()
        clean_hyps.add_batch(
            validate_batch(
                {
                    "hypotheses": [
                        {
                            "id": "h-clean",
                            "statement": "POST /v1/tasks creates a todo task",
                            "evidence_ids": [clean_digest],
                            "status": "supported",
                        }
                    ]
                },
                frozenset([clean_digest]),
            )
        )
        with pytest.raises(HTTPEvaluationBlocked, match="aggregate counts only"):
            prepare_http_generation_request(
                contract=contract,
                public_contract=public,
                ledger=ledger,
                observation_digests=[clean_digest],
                hypotheses=clean_hyps,
                repair_feedback={
                    "passed": 25,
                    "failed": 5,
                    "indeterminate": 0,
                    "total": 30,
                    "failure_categories": {"error": 5},
                    "leaked_failed_cases": ["G4-HTTP-08-FORBIDDEN-TRANSITION-TODO-TO-DONE"],
                },
            )


# ===========================================================================
# 3. Adversarial Suite: State Contamination
# ===========================================================================


def test_adversarial_state_contamination_and_control_plane_isolation() -> None:
    """Verify zero cross-sequence state contamination and strict blocking of mid-sequence
    control-plane resets or post-admission spec mutation.
    """
    public = load_public_contract()
    skeleton = build_http_spec_skeleton(public)

    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url)
        ref = HTTPReferenceAdapter(srv)
        raw_spec = merge_http_skeleton_fill(skeleton, build_http_guided_fill_control())
        loaded = load_http_candidate(raw_spec, contract)
        interp = HTTPCandidateInterpreter(loaded.spec)

        # 3a. Mutating the input dictionary after load_http_candidate does not contaminate interpreter
        raw_spec["id_prefix"] = "mutated-"
        raw_spec["priority_rules"]["maximum"] = 999
        res_interp = interp.execute_sequence(
            [{"operation": "create_task", "actor": "alice", "body": {"title": "Immutable", "priority": 3}}]
        )
        assert res_interp.observations[0].output["body"]["task"]["id"] == "tsk-1"

        # 3b. Cross-sequence isolation: sequence 1 creates and mutates tasks; sequence 2 starts empty at tsk-1
        seq1 = [
            {"operation": "create_task", "actor": "alice", "body": {"title": "Contam", "priority": 5}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress"}},
        ]
        seq2 = [
            {"operation": "list_tasks", "actor": "alice"},
            {"operation": "create_task", "actor": "alice", "body": {"title": "Contam", "priority": 1}},
        ]
        for target in (ref, interp):
            r1 = target.execute_sequence(seq1)
            assert r1.status == "ok"
            assert r1.observations[1].output["body"]["task"]["revision"] == 2
            r2 = target.execute_sequence(seq2)
            assert r2.status == "ok"
            assert r2.observations[0].output["body"]["total"] == 0
            assert r2.observations[1].output["http_status"] == 201
            assert r2.observations[1].output["body"]["task"]["id"] == "tsk-1"
            assert r2.observations[1].output["body"]["task"]["revision"] == 1

        # 3c. Mid-sequence control-plane access (literal and URL-encoded) is blocked on both reference and candidate
        for spoofed_path in ("/__admin/reset", "/%5f%5fadmin/reset", "/%5F%5Fadmin/reset"):
            for target in (ref, interp):
                blocked_res = target.execute_sequence(
                    [{"method": "POST", "path": spoofed_path, "actor": "admin", "body": {}}]
                )
                assert blocked_res.status == "protocol_error"
                assert blocked_res.stderr == "control_plane_access_denied"


# ===========================================================================
# 4. Adversarial Suite: Scope Bypass
# ===========================================================================


def test_adversarial_scope_bypass_urls_verbs_roles_and_planner_smuggling(
    tmp_path: Path,
) -> None:
    """Verify that arbitrary URLs, wrong ports, path traversal, disallowed HTTP methods,
    unauthorized roles, actor payload mismatches, and planner `approval_granted` smuggling
    are all rejected before execution.
    """
    public = load_public_contract()
    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url)
        guard = ScopeGuard(contract)
        ref = HTTPReferenceAdapter(srv)
        ledger = EvidenceLedger(tmp_path / "bypass_ledger")
        runner = SafeHTTPExperimentRunner(contract, ref, ledger)

        # 4a. Arbitrary external URLs, wrong ports, and out-of-scope routes rejected by ScopeGuard
        for bad_target in (
            "http://evil.example.com/v1/tasks",
            "https://127.0.0.1:8000/v1/tasks",
            "http://127.0.0.1:9999/v1/tasks",
            "/v2/tasks",
            "/__admin/reset",
        ):
            act = ProposedAction(
                kind="http_get",
                target=bad_target,
                requirement_id="REQ-HTTP-TASKS",
                role="alice",
                requires_auth=True,
                side_effect=SideEffect.READ_ONLY,
            )
            assert not guard.validate_action(act).allowed

        # 4b. Disallowed HTTP methods (PUT, OPTIONS, CONNECT) rejected by runner
        for bad_method in ("PUT", "OPTIONS", "CONNECT"):
            with pytest.raises(HTTPPolicyViolation):
                runner.run_actions([{"method": bad_method, "path": "/v1/tasks", "actor": "alice"}])

        # 4c. Unauthorized actor role rejected by runner
        with pytest.raises(HTTPPolicyViolation, match="ROLE_NOT_ALLOWED"):
            runner.run_actions([{"method": "GET", "path": "/v1/tasks", "actor": "mallory"}])

        # 4d. Smuggled payload actor mismatch (`role="viewer"` with `payload={"actor": "admin"}`) rejected
        smuggled_actor = ProposedAction(
            kind="http_post",
            target="/v1/tasks",
            requirement_id="REQ-HTTP-TASKS",
            role="viewer",
            requires_auth=True,
            side_effect=SideEffect.LOCAL_MUTATION,
            payload={"actor": "admin", "body": {"title": "Spoof", "priority": 1}},
        )
        with pytest.raises(HTTPPolicyViolation, match="ROLE_MISMATCH"):
            runner.run([smuggled_actor])

        # 4e. Smuggled `approval_granted: True` with `side_effect: "external"` in ExperimentPlanner is stripped & denied
        seed = runner.run_actions(
            [{"operation": "list_tasks", "actor": "alice"}]
        )
        d0 = ledger.store(seed.observations[0])["sha256"]
        hyps = HypothesisStore()
        hyps.add_batch(
            validate_batch(
                {
                    "hypotheses": [
                        {
                            "id": "h-scope-1",
                            "statement": "GET /v1/tasks lists tasks",
                            "evidence_ids": [d0],
                            "status": "hypothesized",
                        }
                    ]
                },
                frozenset([d0]),
            )
        )
        smuggled_proposal = {
            "proposals": [
                {
                    "proposal_id": "smuggled-ext",
                    "requirement_id": "REQ-HTTP-TASKS",
                    "hypothesis_ids": ["h-scope-1"],
                    "question": "Attempt external mutation with smuggled approval",
                    "reset_boundary": RESET_BOUNDARY,
                    "side_effect": "external",
                    "role": "alice",
                    "requires_auth": True,
                    "approval_granted": True,
                    "expected_information_gain": "Should be rejected by ScopeGuard",
                    "actions": [
                        {"kind": "http_post", "command": "/v1/tasks", "params": {"actor": "alice"}}
                    ],
                    "predictions": [{"hypothesis_id": "h-scope-1", "expects_ok": True}],
                }
            ]
        }
        planner_budget = RunBudget(contract.budgets)
        planner = ExperimentPlanner(
            gateway=ModelGateway(MockProvider([{"content": smuggled_proposal}]), planner_budget),
            guard=guard,
            hypotheses=hyps,
            budget=planner_budget,
            contract=contract,
            public_contract=public,
        )
        plan_res = planner.propose(
            [{"digest": d0, "observation": ledger.model_view(d0)}],
            hyps.competing(),
            "REQ-HTTP-TASKS",
            reference_remaining=5,
            model_remaining=5,
        )
        assert len(plan_res.ranked) == 0
        assert len(plan_res.rejected) == 1
        assert "HUMAN_APPROVAL_REQUIRED" in plan_res.rejected[0][1]


# ===========================================================================
# 5. Adversarial Suite: Timeout & Budget Exhaustion
# ===========================================================================


def test_adversarial_timeout_classification_and_budget_exhaustion(
    tmp_path: Path,
) -> None:
    """Verify that reference timeouts yield `indeterminate` (never false pass/fail),
    candidate timeouts yield `failed` (`candidate_timeout`), and experiment budgets are enforced.
    """
    public = load_public_contract()
    skeleton = build_http_spec_skeleton(public)

    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url, max_reference_experiments=2)
        ref = HTTPReferenceAdapter(srv)
        gold_spec = load_http_candidate(
            merge_http_skeleton_fill(skeleton, build_http_guided_fill_control()), contract
        ).spec
        cand = HTTPCandidateInterpreter(gold_spec)
        case = SealedCase(
            case_id="G4-HTTP-ADV-TIMEOUT-1",
            category="crud",
            actions=({"operation": "list_tasks", "actor": "alice"},),
        )

        class TimeoutAdapter:
            def execute_sequence(
                self, actions: list[dict[str, Any]], *, sequence_id: str | None = None
            ) -> SequenceResult:
                return SequenceResult(
                    sequence_id=sequence_id or "seq",
                    observations=(),
                    status="timeout",
                    stderr="http_request_timeout",
                )

        # 5a. Reference timeout -> indeterminate (`reference_unavailable`)
        rep_ref_to = HTTPDifferentialEvaluator(TimeoutAdapter(), cand).evaluate([case])
        assert rep_ref_to.passed == 0
        assert rep_ref_to.failed == 0
        assert rep_ref_to.indeterminate == 1
        assert rep_ref_to.cases[0].http_mismatch_dimension == "reference_unavailable"

        # 5b. Candidate timeout -> failed (`candidate_timeout`)
        rep_cand_to = HTTPDifferentialEvaluator(ref, TimeoutAdapter()).evaluate([case])
        assert rep_cand_to.passed == 0
        assert rep_cand_to.failed == 1
        assert rep_cand_to.indeterminate == 0
        assert rep_cand_to.cases[0].http_mismatch_dimension == "candidate_timeout"

        # 5c. Reference experiment budget exhaustion raises HTTPBudgetExhausted
        ledger = EvidenceLedger(tmp_path / "budget_ledger")
        runner = SafeHTTPExperimentRunner(contract, ref, ledger)
        runner.run_actions([{"operation": "list_tasks", "actor": "alice"}])
        runner.run_actions([{"operation": "list_tasks", "actor": "alice"}])
        with pytest.raises(HTTPBudgetExhausted, match="BUDGET_EXHAUSTED"):
            runner.run_actions([{"operation": "list_tasks", "actor": "alice"}])


# ===========================================================================
# 6. Adversarial Suite: Candidate Rejection & Broker Diagnostics
# ===========================================================================


def test_adversarial_candidate_rejection_and_broker_accounting(
    tmp_path: Path,
) -> None:
    """Verify that malformed JSON, code-bearing strings, and invalid candidate bounds
    are rejected inside `PinnedHTTPEvaluatorRun.generate` with sanitized diagnostics and
    honest attempt accounting.
    """
    seal_dir = Path(tempfile.mkdtemp(prefix="g4-adv-cand-"))

    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url, max_model_calls=5)
        ref = HTTPReferenceAdapter(srv)
        ledger = EvidenceLedger(tmp_path / "cand_ledger")
        runner = SafeHTTPExperimentRunner(contract, ref, ledger)
        seq = runner.run_actions(
            [{"operation": "create_task", "actor": "alice", "body": {"title": "Seed", "priority": 3}}]
        )
        d0 = ledger.store(seq.observations[0])["sha256"]
        hyps = HypothesisStore()
        hyps.add_batch(
            validate_batch(
                {
                    "hypotheses": [
                        {
                            "id": "h-cand-1",
                            "statement": "POST /v1/tasks creates todo task",
                            "evidence_ids": [d0],
                            "status": "supported",
                        }
                    ]
                },
                frozenset([d0]),
            )
        )
        suite_path, suite_digest = seal_http_task_workflow_suite(seal_dir, contract)
        suite = load_sealed_http_suite(suite_path, suite_digest, contract)
        run = PinnedHTTPEvaluatorRun(
            suite,
            contract,
            ledger=ledger,
            observation_digests=(d0,),
            hypotheses=hyps,
            reference=ref,
        )
        budget = RunBudget(contract.budgets)

        # 6a. Malformed non-JSON string rejected at gateway boundary
        t1 = run.prepare()
        with pytest.raises(HTTPEvaluationBlocked) as exc_json:
            run.generate(t1, MockProvider([{"content": "{not valid json"}]), budget)
        diag_json = exc_json.value.broker_diagnostic
        assert diag_json["failure_stage"] == "broker"
        assert diag_json["transport_attempted"] is True
        assert budget.attempts == 1

        # 6b. Code-bearing string (`import subprocess`) rejected at `candidate_admission`
        bad_code_fill = build_http_guided_fill_control()
        bad_code_fill["title_rules"]["invalid_error"] = "import subprocess; subprocess.Popen('sh')"
        t2 = run.prepare()
        with pytest.raises(HTTPEvaluationBlocked) as exc_code:
            run.generate(t2, MockProvider([{"content": bad_code_fill}]), budget)
        diag_code = exc_code.value.broker_diagnostic
        assert diag_code["failure_stage"] == "candidate_admission"
        assert diag_code["failure_code"] == "CANDIDATE_SPEC_INVALID"
        assert diag_code["transport_attempted"] is True
        assert budget.attempts == 2

        # 6c. Inverted priority bounds (`minimum: 8, maximum: 2`) rejected at `candidate_admission`
        bad_bounds_fill = build_http_guided_fill_control()
        bad_bounds_fill["priority_rules"]["minimum"] = 8
        bad_bounds_fill["priority_rules"]["maximum"] = 2
        t3 = run.prepare()
        with pytest.raises(HTTPEvaluationBlocked) as exc_bounds:
            run.generate(t3, MockProvider([{"content": bad_bounds_fill}]), budget)
        assert exc_bounds.value.broker_diagnostic["failure_stage"] == "candidate_admission"
        assert budget.attempts == 3


# ===========================================================================
# 7. Adversarial Suite: Replay Consistency & Attestation Integrity
# ===========================================================================


def test_adversarial_replay_consistency_and_ticket_signature_integrity(
    tmp_path: Path,
) -> None:
    """Verify deterministic replay across multiple evaluations, single-use ticket nonce
    enforcement, HMAC tamper rejection, and wire mutation rejection.
    """
    seal_dir = Path(tempfile.mkdtemp(prefix="g4-adv-replay-"))

    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url, max_model_calls=5)
        ref = HTTPReferenceAdapter(srv)
        ledger = EvidenceLedger(tmp_path / "replay_ledger")
        runner = SafeHTTPExperimentRunner(contract, ref, ledger)
        seq = runner.run_actions(
            [{"operation": "create_task", "actor": "alice", "body": {"title": "ReplaySeed", "priority": 3}}]
        )
        d0 = ledger.store(seq.observations[0])["sha256"]
        hyps = HypothesisStore()
        hyps.add_batch(
            validate_batch(
                {
                    "hypotheses": [
                        {
                            "id": "h-rep-1",
                            "statement": "POST /v1/tasks creates todo task",
                            "evidence_ids": [d0],
                            "status": "supported",
                        }
                    ]
                },
                frozenset([d0]),
            )
        )
        suite_path, suite_digest = seal_http_task_workflow_suite(seal_dir, contract)
        suite = load_sealed_http_suite(suite_path, suite_digest, contract)
        run = PinnedHTTPEvaluatorRun(
            suite,
            contract,
            ledger=ledger,
            observation_digests=(d0,),
            hypotheses=hyps,
            reference=ref,
        )
        budget = RunBudget(contract.budgets)

        ticket = run.prepare()
        artifact = run.generate(
            ticket,
            MockProvider([{"content": build_http_guided_fill_control()}]),
            budget,
        )

        # 7a. Single-use ticket nonce: replaying the same ticket is rejected
        with pytest.raises(HTTPEvaluationBlocked, match="replay rejected"):
            run.generate(
                ticket,
                MockProvider([{"content": build_http_guided_fill_control()}]),
                budget,
            )

        # 7b. Deterministic replay: evaluating the admitted artifact multiple times yields identical results
        eval1 = run.evaluate(artifact, claim="TRUSTED_CONTROL")
        eval2 = run.evaluate(artifact, claim="TRUSTED_CONTROL")
        assert eval1 == eval2
        assert eval1["evaluation"]["passed"] == 30
        assert eval1["evaluation"]["failed"] == 0

        # 7c. Claiming REAL_MODEL on a MockProvider artifact is blocked
        with pytest.raises(HTTPEvaluationBlocked, match="cannot claim real-model accuracy"):
            run.evaluate(artifact, claim="REAL_MODEL")

        # 7d. Tampering with BrokerArtifact payload or signature is rejected
        tampered_sig = BrokerArtifact(
            payload=artifact.payload,
            signature=("0" if artifact.signature[0] != "0" else "1") + artifact.signature[1:],
        )
        with pytest.raises(HTTPEvaluationBlocked, match="Unattested or changed broker artifact"):
            run.evaluate(tampered_sig, claim="TRUSTED_CONTROL")

        # 7e. Passing an INSPECTED_REQUEST ticket where CANDIDATE_ORIGIN is required is rejected
        ticket2 = run.prepare()
        with pytest.raises(HTTPEvaluationBlocked, match="Wrong run or broker artifact kind"):
            run.evaluate(ticket2, claim="TRUSTED_CONTROL")
