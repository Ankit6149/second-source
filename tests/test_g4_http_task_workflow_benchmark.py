"""Competitive benchmark, matched-budget attribution, and zero-call authorization packet tests for G4 HTTP target."""

from __future__ import annotations

from pathlib import Path

from fixtures.owned_http_task_workflow import (
    HISTORICAL_V1_SCAFFOLDING_SUMMARY,
    HTTPReferenceAdapter,
    SafeHTTPExperimentRunner,
    active_discriminating_sequences,
    build_authorization_packet_proposal,
    build_uninformed_prior_fill,
    create_http_scope,
    derive_fill_from_observations,
    load_public_contract,
    passive_matched_probe_sequences,
    prepare_http_generation_request,
    run_competitive_benchmark,
    start_reference_server,
)
from second_source.evidence import EvidenceLedger
from second_source.hypotheses import HypothesisStore, validate_batch


def test_competitive_benchmark_controls_budgets_and_attributes_probe_evidence(
    tmp_path: Path,
) -> None:
    report = run_competitive_benchmark(work_dir=tmp_path / "bench")

    assert report["kind"] == "G4_HTTP_COMPETITIVE_BENCHMARK_SCAFFOLDING"
    assert report["benchmark_version"] == "2.0-matched-budget-observation-derived"
    assert report["claim"] == "NON_AI_DETERMINISTIC_SCAFFOLDING_NOT_MODEL_QUALITY"
    assert "BLOCKED" in report["scientific_limitation"]
    assert report["target_id"] == "owned-http-task-workflow-v1"
    assert report["suite_case_count"] == 30

    # Budget parity controls explicitly recorded
    controls = report["budget_controls"]
    assert controls["passive_vs_active_experiments_matched"] == 5
    assert controls["passive_vs_active_actions_matched"] == 15
    assert controls["max_output_tokens_matched"] == 4096
    assert controls["held_out_cases_matched"] == 30
    assert controls["shared_prior_and_extractor"] is True

    arms = report["arms"]
    assert set(arms) == {
        "A_direct_synthesis",
        "B_passive_fixed_probes",
        "C_active_evidence_driven",
        "D_bounded_repair",
    }

    direct = arms["A_direct_synthesis"]
    passive = arms["B_passive_fixed_probes"]
    active = arms["C_active_evidence_driven"]
    repair = arms["D_bounded_repair"]

    # Every arm is scored on the exact same 30-case denominator and marked NON_AI (origin="mock", real=False)
    for arm in arms.values():
        assert arm["total"] == 30
        assert arm["origin"] == "mock"
        assert arm["real"] is False
        assert arm["estimated_cost_usd"] == 0.0
        assert arm["estimated_input_tokens"] > 0
        assert arm["estimated_output_tokens"] > 0
        assert "evidence_attribution" in arm

    # Exact budget parity between Condition B (passive) and Condition C (active):
    # both use 5 experiments and 15 HTTP actions (3 actions per experiment)
    assert direct["experiments_used"] == 1
    assert direct["actions_executed"] == 3
    assert passive["experiments_used"] == 5
    assert passive["actions_executed"] == 15
    assert active["experiments_used"] == 5
    assert active["actions_executed"] == 15
    assert passive["experiments_used"] == active["experiments_used"]
    assert passive["actions_executed"] == active["actions_executed"]

    # Evidence attribution distinguishes what probes empirically revealed vs. uninformed prior assumptions
    direct_attr = direct["evidence_attribution"]
    passive_attr = passive["evidence_attribution"]
    active_attr = active["evidence_attribution"]
    repair_attr = repair["evidence_attribution"]

    assert direct_attr["rules_revealed_count"] == 0
    assert len(direct_attr["prior_assumptions_retained"]) == 8

    # Passive happy-path probes reveal 4 input/duplicate/pagination rules but miss 4 workflow/deletion/cancellation rules
    assert passive_attr["rules_revealed_count"] == 4
    assert set(passive_attr["rules_revealed_by_probes"]) == {
        "title_max_length_64",
        "priority_maximum_5",
        "duplicate_title_casefold_per_owner",
        "pagination_max_limit_50",
    }
    assert set(passive_attr["prior_assumptions_retained"]) == {
        "cancelled_frees_title",
        "forbid_shortcut_transitions_to_done",
        "terminal_statuses_locked",
        "delete_in_progress_blocked",
    }

    # Active boundary-discriminating probes with the EXACT same 5-exp / 15-action budget reveal all 8 hidden rules
    assert active_attr["rules_revealed_count"] == 8
    assert active_attr["prior_assumptions_retained"] == []
    for obs_list in active_attr["rules_revealed_by_probes"].values():
        assert len(obs_list) >= 1

    # Scientific ordering on 30-case suite: Direct (19/30) < Passive (25/30) < Active (30/30)
    assert direct["passed"] == 19
    assert passive["passed"] == 25
    assert active["passed"] == 30
    assert direct["passed"] < passive["passed"] < active["passed"]
    assert active["failed"] == 0

    # Bounded repair (Arm D) repairs Arm B's 25/30 candidate to 30/30 using aggregate feedback + targeted follow-up probes
    assert repair["passed"] == 30
    assert repair["failed"] == 0
    assert repair_attr["rules_revealed_count"] == 8
    assert repair_attr["repair_feedback_received"] == {
        "passed": 25,
        "failed": 5,
        "indeterminate": 0,
        "total": 30,
        "failure_categories": {"error": 5},
    }

    # Historical v1 scaffolding results are preserved with explicit limitation disclosure
    hist = report["historical_v1_scaffolding"]
    assert hist == HISTORICAL_V1_SCAFFOLDING_SUMMARY
    assert hist["status"] == "RETAINED_HISTORICAL_CONTROL_EVIDENCE"
    assert hist["arms"]["A_direct_synthesis"]["passed"] == 19
    assert hist["arms"]["B_passive_fixed_probes"]["passed"] == 26
    assert hist["arms"]["B_passive_fixed_probes"]["actions"] == 12
    assert hist["arms"]["C_active_evidence_driven"]["passed"] == 30
    assert hist["arms"]["C_active_evidence_driven"]["actions"] == 15


def test_derive_fill_from_observations_only_updates_empirically_witnessed_rules() -> None:
    prior = build_uninformed_prior_fill()
    empty_fill, empty_attr = derive_fill_from_observations([])
    assert empty_fill == prior
    assert empty_attr["rules_revealed_count"] == 0
    assert len(empty_attr["prior_assumptions_retained"]) == 8

    assert sum(len(s) for s in passive_matched_probe_sequences()) == 15
    assert sum(len(s) for s in active_discriminating_sequences()) == 15


def test_authorization_packet_proposal_is_zero_call_and_bounded(tmp_path: Path) -> None:
    public_contract = load_public_contract()
    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url)
        ref = HTTPReferenceAdapter(srv)
        ledger = EvidenceLedger(tmp_path / "auth_ledger")
        runner = SafeHTTPExperimentRunner(contract, ref, ledger)
        seq = runner.run_actions(
            [{"operation": "create_task", "actor": "alice", "body": {"title": "AuthCheck", "priority": 3}}]
        )
        digest = ledger.store(seq.observations[0])["sha256"]

        hyps = HypothesisStore()
        hyps.add_batch(
            validate_batch(
                {
                    "hypotheses": [
                        {
                            "id": "h-auth-1",
                            "statement": "POST /v1/tasks creates a todo task",
                            "evidence_ids": [digest],
                            "status": "supported",
                        }
                    ]
                },
                frozenset([digest]),
            )
        )

        wire = prepare_http_generation_request(
            contract=contract,
            public_contract=public_contract,
            ledger=ledger,
            observation_digests=[digest],
            hypotheses=hyps,
        )

        proposal = build_authorization_packet_proposal(
            contract=contract,
            suite_digest="sha256:" + ("a" * 64),
            inspected_direct_wire=wire,
            inspected_active_wire=wire,
        )
        assert proposal["status"] == "PREPARED_UNAUTHORIZED_ZERO_CALLS"
        assert proposal["provider_calls_made"] == 0
        assert proposal["target_id"] == "owned-http-task-workflow-v1"
        assert proposal["isolation_verified"] is True
        assert proposal["max_output_tokens"] == 4096
