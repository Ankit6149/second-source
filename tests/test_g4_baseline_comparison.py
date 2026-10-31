"""Controlled comparison: direct synthesis vs evidence-driven mock generation.

Protocol A (direct): the author-written CONTROL candidate
(tests/g3_fixtures/valid_candidate.json, zero inference) admitted and
evaluated on a fixed 2-case synthetic suite.
Protocol B (evidence-driven): a guided mock fill merged into the trusted
skeleton from approved evidence, admitted, and evaluated on the SAME suite.

Both protocols are deterministic and nonbillable; the comparison measures
agreement counts, wall latency, estimated tokens, and cost under one
denominator. It proves measurement mechanics — NEVER model quality.
"""

import json
import time
from pathlib import Path

from second_source.candidate_adapter import CandidateReferenceAdapter
from second_source.candidate_generation import (
    build_spec_skeleton,
    merge_skeleton_fill,
)
from second_source.model_gateway import _estimate_tokens
from second_source.reference import CLIReferenceAdapter
from second_source.verifier import DifferentialVerifier

import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = json.loads(
    (ROOT / "fixtures/owned_ledger/public_contract.json").read_text(
        encoding="utf-8"))
CONTROL = json.loads(
    (ROOT / "tests/g3_fixtures/valid_candidate.json").read_text(
        encoding="utf-8"))


def evidence_fill():
    return {
        "error_codes": {
            "unknown_command": "unknown_command",
            "invalid_input": "invalid_input",
        },
        "add": {
            "label": {"min_length": 1, "max_length": 24, "trim": True},
            "amount": {"minimum": 1, "maximum": 100},
            "unique_field": "label",
            "unique_casefold": True,
            "label_error": "invalid_label",
            "amount_error": "invalid_amount",
            "duplicate_error": "duplicate_label",
            "respond": {"id": "id"},
        },
        "list": {"respond": {"items": "items"}},
        "total": {"respond": {"count": "count", "amount": "amount"}},
        "remove": {
            "not_found_error": "not_found",
            "respond": {"removed": "id"},
        },
    }


def two_cases():
    return [
        {"case_id": "G4-BASELINE-LIST", "category": "empty",
         "actions": [{"command": "list"}]},
        {"case_id": "G4-BASELINE-TOTAL", "category": "empty",
         "actions": [{"command": "total"}]},
    ]


def test_direct_vs_evidence_driven_same_denominator(cli_scope):
    from second_source.verifier import SealedCase
    reference = CLIReferenceAdapter(
        [sys.executable, str(ROOT / "fixtures/owned_ledger/reference.py")],
        cwd=str(ROOT))
    cases = [SealedCase(case_id=c["case_id"], actions=tuple(c["actions"]))
             for c in two_cases()]

    started = time.perf_counter()
    direct = CandidateReferenceAdapter(
        json.dumps(CONTROL).encode(), cli_scope)
    direct_report = DifferentialVerifier(reference, direct).verify(cases)
    direct_latency = time.perf_counter() - started

    from second_source.candidate_generation import build_guided_request
    skeleton = build_spec_skeleton(PUBLIC)
    request = build_guided_request(
        {"scope": {}, "public_commands": PUBLIC, "evidence": [],
         "hypotheses": []},
        skeleton)
    captured = {"request": request}

    started = time.perf_counter()
    merged = merge_skeleton_fill(skeleton, evidence_fill())
    driven = CandidateReferenceAdapter(
        json.dumps(merged).encode(), cli_scope)
    driven_report = DifferentialVerifier(reference, driven).verify(cases)
    driven_latency = time.perf_counter() - started

    request = captured["request"]
    in_tokens = _estimate_tokens(" ".join(
        m.get("content", "") for m in request.messages))
    out_tokens = _estimate_tokens(json.dumps(evidence_fill()))

    assert direct_report.total == driven_report.total == 2
    assert (direct_report.passed, direct_report.failed) == (2, 0)
    assert (driven_report.passed, driven_report.failed) == (2, 0)
    assert direct_latency >= 0 and driven_latency >= 0
    assert in_tokens > 0 and out_tokens > 0
    # Mock transport is $0 by design; the token estimate is what a priced
    # provider would meter, kept visible for cost comparisons.
    print(f"direct: {direct_report.passed}/2 in {direct_latency:.2f}s, "
          f"0 model tokens")
    print(f"evidence-driven mock: {driven_report.passed}/2 in "
          f"{driven_latency:.2f}s, ~{in_tokens + out_tokens} tokens, $0.00")
