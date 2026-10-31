"""G4 scaffolding: second distinct owned target (variant ledger).

Proves the reconstruction machinery discriminates targets by evidence: the
variant fixture shares the ledger-DSL command surface but hides different
validation rules, and the same pipeline admits a measurably different
candidate for it. All fixtures here are owned and synthetic; the variant
checks below are NON-SEALED scaffolding assertions, never sealed evidence.

Not claimed: control-plane target selection, per-target sealed suites, or
joint verifier integration (pending coordinated contract work).
"""

import json
import sys
from pathlib import Path

import pytest

from second_source.candidate_generation import (
    GenerationReceipt,
    build_spec_skeleton,
    merge_skeleton_fill,
    validate_generated_spec,
)
from second_source.candidate_runtime import CandidateInterpreter
from second_source.reference import CLIReferenceAdapter
from second_source.verifier import DifferentialVerifier, SealedCase

ROOT = Path(__file__).resolve().parents[1]
VARIANT = ROOT / "fixtures/owned_ledger_variant"
VARIANT_PUBLIC = json.loads(
    (VARIANT / "public_contract.json").read_text(encoding="utf-8"))


def variant_reference():
    return CLIReferenceAdapter(
        [sys.executable, str(VARIANT / "reference.py")], cwd=str(ROOT))


def run_actions(adapter, actions):
    return [obs.output for obs in
            adapter.execute_sequence(actions).observations]


def variant_fill():
    return {
        "error_codes": {
            "unknown_command": "unknown_command",
            "invalid_input": "invalid_input",
        },
        "add": {
            "label": {"min_length": 1, "max_length": 48, "trim": True},
            "amount": {"minimum": 1, "maximum": 500},
            "unique_field": "label",
            "unique_casefold": False,
            "label_error": "invalid_title",
            "amount_error": "invalid_qty",
            "duplicate_error": "duplicate_title",
            "respond": {"id": "id"},
        },
        "list": {"respond": {"items": "items"}},
        "total": {"respond": {"count": "count", "amount": "amount"}},
        "remove": {
            "not_found_error": "missing_id",
            "respond": {"removed": "id"},
        },
    }


def main_fill():
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


def mock_receipt():
    return GenerationReceipt(
        origin="mock", provider="mock", real=False,
        model="mock-muse-0", response_id="mock-g4-scaffold")


def test_variant_fixture_honors_documented_rules():
    ref = variant_reference()
    assert run_actions(ref, [
        {"command": "add", "label": "x" * 48, "amount": 500},
    ])[0] == {"ok": True, "id": "1"}
    assert run_actions(ref, [
        {"command": "add", "label": "x" * 49, "amount": 5},
    ])[0] == {"ok": False, "error": "invalid_title"}
    assert run_actions(ref, [
        {"command": "add", "label": "Q", "amount": 501},
    ])[0] == {"ok": False, "error": "invalid_qty"}
    assert run_actions(ref, [
        {"command": "add", "label": "K", "amount": 1},
        {"command": "add", "label": "k", "amount": 2},
    ])[1] == {"ok": True, "id": "2"}
    assert run_actions(ref, [
        {"command": "add", "label": "K", "amount": 1},
        {"command": "add", "label": "K", "amount": 2},
    ])[1] == {"ok": False, "error": "duplicate_title"}
    assert run_actions(ref, [
        {"command": "remove", "id": "nope"},
    ])[0] == {"ok": False, "error": "missing_id"}


def test_variant_fill_admits_and_matches_fixture(cli_scope):
    merged = merge_skeleton_fill(
        build_spec_skeleton(VARIANT_PUBLIC), variant_fill())
    loaded, stamped = validate_generated_spec(
        merged, cli_scope, mock_receipt())
    assert stamped.spec_digest == loaded.digest
    candidate = CandidateInterpreter(loaded.spec)
    assert run_actions(candidate, [
        {"command": "add", "label": "Alpha", "amount": 3},
        {"command": "list"},
        {"command": "total"},
        {"command": "remove", "id": "1"},
    ])[3] == {"ok": True, "removed": "1"}
    assert run_actions(candidate, [
        {"command": "add", "label": "K", "amount": 1},
        {"command": "add", "label": "k", "amount": 2},
    ])[1]["ok"] is True
    assert run_actions(candidate, [
        {"command": "add", "label": "K", "amount": 1},
        {"command": "add", "label": "K", "amount": 2},
    ])[1] == {"ok": False, "error": "duplicate_title"}


def test_pipeline_discriminates_targets_by_evidence(cli_scope):
    main_public = json.loads(
        (ROOT / "fixtures/owned_ledger/public_contract.json").read_text(
            encoding="utf-8"))
    main_raw = merge_skeleton_fill(
        build_spec_skeleton(main_public), main_fill())
    variant_raw = merge_skeleton_fill(
        build_spec_skeleton(VARIANT_PUBLIC), variant_fill())
    main_loaded, _ = validate_generated_spec(
        main_raw, cli_scope, mock_receipt())
    variant_loaded, _ = validate_generated_spec(
        variant_raw, cli_scope, mock_receipt())
    assert main_loaded.digest != variant_loaded.digest
    main_add = main_raw["commands"]["add"]
    variant_add = variant_raw["commands"]["add"]
    assert (main_add["params"]["label"]["max_length"]
            != variant_add["params"]["label"]["max_length"])
    assert (main_add["unique_casefold"]
            != variant_add["unique_casefold"])
    assert (main_add["unique_error"]
            != variant_add["unique_error"])
    assert (main_raw["commands"]["remove"]["not_found_error"]
            != variant_raw["commands"]["remove"]["not_found_error"])


def test_variant_candidate_scores_on_variant_reference():
    # NON-SEALED scaffolding check: hand-built cases, variant reference on
    # both sides of the comparison harness. The variant candidate passes;
    # the main-ledger candidate does not transfer. Neither number is sealed
    # evidence.
    from second_source.candidate_adapter import CandidateReferenceAdapter
    from second_source.reconstruct import create_scope
    scope = create_scope(0)
    variant_raw = merge_skeleton_fill(
        build_spec_skeleton(VARIANT_PUBLIC), variant_fill())
    variant_candidate = CandidateReferenceAdapter(
        json.dumps(variant_raw).encode(), scope)
    main_public = json.loads(
        (ROOT / "fixtures/owned_ledger/public_contract.json").read_text(
            encoding="utf-8"))
    main_raw = merge_skeleton_fill(
        build_spec_skeleton(main_public), main_fill())
    main_candidate = CandidateReferenceAdapter(
        json.dumps(main_raw).encode(), scope)
    reference = variant_reference()
    cases = [
        SealedCase(case_id="G4-SCAFFOLD-1", actions=(
            {"command": "add", "label": "K", "amount": 5},
            {"command": "add", "label": "k", "amount": 6},
            {"command": "total"},
        )),
        SealedCase(case_id="G4-SCAFFOLD-2", actions=(
            {"command": "add", "label": "y" * 48, "amount": 500},
            {"command": "list"},
        )),
    ]
    variant_report = DifferentialVerifier(reference, variant_candidate).verify(cases)
    assert (variant_report.passed, variant_report.failed) == (2, 0)
    main_report = DifferentialVerifier(reference, main_candidate).verify(cases)
    assert main_report.failed == 2
