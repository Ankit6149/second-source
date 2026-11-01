"""Competitive benchmark and zero-call authorization packet tests for G4 HTTP target."""

from __future__ import annotations

from pathlib import Path

from fixtures.owned_http_task_workflow import (
    HTTPReferenceAdapter,
    SafeHTTPExperimentRunner,
    build_authorization_packet_proposal,
    create_http_scope,
    load_public_contract,
    prepare_http_generation_request,
    run_competitive_benchmark,
    start_reference_server,
)
from second_source.evidence import EvidenceLedger
from second_source.hypotheses import HypothesisStore, validate_batch


def test_competitive_benchmark_compares_four_arms_fairly_on_30_held_out_cases(
    tmp_path: Path,
) -> None:
    report = run_competitive_benchmark(work_dir=tmp_path / "bench")

    assert report["kind"] == "G4_HTTP_COMPETITIVE_BENCHMARK_SCAFFOLDING"
    assert report["claim"] == "NON_AI_DETERMINISTIC_SCAFFOLDING_NOT_MODEL_QUALITY"
    assert report["target_id"] == "owned-http-task-workflow-v1"
    assert report["suite_case_count"] == 30

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

    # Equal 5-experiment budget between Condition B (passive) and Condition C (active)
    assert direct["experiments_used"] == 1
    assert passive["experiments_used"] == 5
    assert active["experiments_used"] == 5

    # Scientific ordering: Direct < Passive < Active == 30/30
    assert direct["passed"] < passive["passed"] < active["passed"]
    assert active["passed"] == 30
    assert active["failed"] == 0

    # Bounded repair (Arm D) repairs Arm B's failures using aggregate feedback only
    assert repair["passed"] == 30
    assert repair["failed"] == 0


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
