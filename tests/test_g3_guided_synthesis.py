"""Constraint-guided synthesis: skeleton determinism, strict merge, honest scores."""

import copy
import json
from pathlib import Path

import pytest

from second_source.budgets import RunBudget
from second_source.candidate_generation import (
    FILL_JSON_SCHEMA,
    GenerationReceipt,
    _validate_context_shape,
    build_guided_request,
    build_spec_skeleton,
    merge_skeleton_fill,
    request_guided_spec,
    validate_generated_spec,
)
from second_source.candidate_spec import CandidateError
from second_source.candidate_runtime import CandidateInterpreter
from second_source.contracts import Budgets
from second_source.model_gateway import (
    GatewayError,
    MockProvider,
    ModelGateway,
    _estimate_tokens,
)
from second_source.verifier import DifferentialVerifier, SealedCase

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = json.loads(
    (ROOT / "fixtures/owned_ledger/public_contract.json").read_text(
        encoding="utf-8")
)


def correct_fill():
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


def amount_unique_fill():
    """A fill that makes a DIFFERENT but valid behavioral choice: the amount
    parameter carries uniqueness instead of the label. Must load and must
    decide duplicate cases differently than correct_fill()."""
    fill = correct_fill()
    fill["add"]["unique_field"] = "amount"
    fill["add"]["duplicate_error"] = "duplicate_amount"
    return fill


def loose_fill():
    fill = correct_fill()
    fill["add"]["label"]["max_length"] = 200
    fill["add"]["amount"]["minimum"] = 0
    fill["add"]["amount"]["maximum"] = 1000
    return fill


def mock_receipt():
    return GenerationReceipt(
        origin="mock", provider="mock", real=False,
        model="mock-muse-0", response_id="mock-1-synthesize")


def valid_context():
    return {
        "scope": {
            "goal": "reconstruct ledger behavior",
            "requirement_ids": ["REQ-LEDGER"],
            "allowed_commands": ["add", "list", "total", "remove"],
            "excluded_subsystems": [],
        },
        "public_commands": PUBLIC,
        "evidence": [{
            "digest": "d" * 64,
            "observation": {
                "observation_id": "o",
                "sequence_id": "s",
                "action_index": 0,
                "input_action": {"command": "list"},
                "output": {"ok": True},
                "exit_code": 0,
                "duration_ms": 1,
                "status": "ok",
            },
        }],
        "hypotheses": [{
            "id": "h",
            "statement": "list works",
            "evidence_ids": ["d" * 64],
            "status": "hypothesized",
        }],
    }


def test_skeleton_derives_only_public_structure():
    first = build_spec_skeleton(PUBLIC)
    second = build_spec_skeleton(json.loads(json.dumps(PUBLIC)))
    assert first == second
    leaves = []

    def collect(value):
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        else:
            leaves.append(value)

    collect(first)
    assert not [leaf for leaf in leaves
                if isinstance(leaf, (int, float)) and not isinstance(leaf, bool)]
    assert [leaf for leaf in leaves if leaf is None]
    for secret in ("invalid_label", "invalid_amount", "duplicate_label",
                   "not_found"):
        assert secret not in leaves
    assert set(first["commands"]) == {"add", "list", "total", "remove"}
    # Unspecified behavioral choices stay model-controlled: the skeleton
    # carries NO uniqueness selection and NO response key bindings. Any
    # future hard-coding here fails this test by design.
    assert first["commands"]["add"]["unique_field"] is None
    for name in ("add", "list", "total", "remove"):
        assert first["commands"][name]["respond"] == {}


def test_skeleton_rejects_unapproved_contract():
    tampered = copy.deepcopy(PUBLIC)
    tampered["commands"]["add"]["params"]["label"] = "integer"
    with pytest.raises(GatewayError):
        build_spec_skeleton(tampered)
    with pytest.raises(GatewayError):
        build_spec_skeleton({"commands": {}})


def test_merge_correct_fill_loads_strict(cli_scope):
    merged = merge_skeleton_fill(build_spec_skeleton(PUBLIC), correct_fill())
    loaded, stamped = validate_generated_spec(merged, cli_scope, mock_receipt())
    assert stamped.spec_digest == loaded.digest


def test_merge_rejects_shape_violations():
    skeleton = build_spec_skeleton(PUBLIC)
    bad = correct_fill()
    bad["add"]["extra"] = 1
    with pytest.raises(GatewayError):
        merge_skeleton_fill(skeleton, bad)
    bad = correct_fill()
    del bad["remove"]
    with pytest.raises(GatewayError):
        merge_skeleton_fill(skeleton, bad)
    bad = correct_fill()
    bad["add"]["label_error"] = "x" * 65
    with pytest.raises(GatewayError):
        merge_skeleton_fill(skeleton, bad)
    bad = correct_fill()
    bad["add"]["amount"]["minimum"] = 10 ** 10
    with pytest.raises(GatewayError):
        merge_skeleton_fill(skeleton, bad)
    with pytest.raises(GatewayError):
        merge_skeleton_fill(skeleton, [1, 2, 3])


def test_merge_rejects_foreign_or_missing_uniqueness():
    skeleton = build_spec_skeleton(PUBLIC)
    bad = correct_fill()
    bad["add"]["unique_field"] = "nope"
    with pytest.raises(GatewayError):
        merge_skeleton_fill(skeleton, bad)
    bad = correct_fill()
    del bad["add"]["unique_field"]
    with pytest.raises(GatewayError):
        merge_skeleton_fill(skeleton, bad)


def test_merge_rejects_bad_respond_bindings():
    skeleton = build_spec_skeleton(PUBLIC)
    for respond in ({}, {"ok": "id"}, {"Bad Key!": "id"}, {"id": ""}):
        bad = correct_fill()
        bad["add"]["respond"] = respond
        with pytest.raises(GatewayError):
            merge_skeleton_fill(skeleton, bad)
    bad = correct_fill()
    bad["list"]["respond"] = {}
    with pytest.raises(GatewayError):
        merge_skeleton_fill(skeleton, bad)


def test_loader_rejects_unresolvable_respond_source(cli_scope):
    # Shape-valid at the merge (a non-empty string), but no command produces
    # a "bogus" value: the strict loader must fail admission closed.
    skeleton = build_spec_skeleton(PUBLIC)
    fill = correct_fill()
    fill["total"]["respond"] = {"count": "bogus"}
    merged = merge_skeleton_fill(skeleton, fill)
    with pytest.raises(CandidateError):
        validate_generated_spec(merged, cli_scope, mock_receipt())


def test_differing_unique_field_changes_decisions(cli_scope):
    # amount-unique is a valid but different choice: it must load, and the
    # real interpreter must decide duplicate cases differently.
    skeleton = build_spec_skeleton(PUBLIC)
    label_raw = merge_skeleton_fill(skeleton, correct_fill())
    amount_raw = merge_skeleton_fill(skeleton, amount_unique_fill())
    label_loaded, _ = validate_generated_spec(label_raw, cli_scope,
                                              mock_receipt())
    amount_loaded, _ = validate_generated_spec(amount_raw, cli_scope,
                                               mock_receipt())
    label_candidate = CandidateInterpreter(label_loaded.spec)
    amount_candidate = CandidateInterpreter(amount_loaded.spec)
    repeat_label = [
        {"command": "add", "label": "K", "amount": 5},
        {"command": "add", "label": "K", "amount": 6},
    ]
    label_out = label_candidate.execute_sequence(repeat_label).observations
    amount_out = amount_candidate.execute_sequence(repeat_label).observations
    assert label_out[1].output["ok"] is False
    assert label_out[1].output["error"] == "duplicate_label"
    assert all(entry.output["ok"] is True for entry in amount_out)
    repeat_amount = [
        {"command": "add", "label": "A", "amount": 5},
        {"command": "add", "label": "B", "amount": 5},
    ]
    amount_candidate.reset()
    clash = amount_candidate.execute_sequence(repeat_amount).observations
    assert clash[1].output["ok"] is False
    assert clash[1].output["error"] == "duplicate_amount"


def test_merge_defers_semantics_to_loader(cli_scope):
    skeleton = build_spec_skeleton(PUBLIC)
    bad = correct_fill()
    bad["add"]["amount"]["minimum"] = 3
    bad["add"]["amount"]["maximum"] = 2
    merged = merge_skeleton_fill(skeleton, bad)
    with pytest.raises(CandidateError):
        validate_generated_spec(merged, cli_scope, mock_receipt())


def test_fill_costs_fraction_of_full_spec():
    # The fill now also carries the model-controlled uniqueness selection
    # and response bindings, so it is ~half a full spec, not a third. It is
    # still strictly smaller, and every added token is a model decision the
    # full-spec path would also have to emit.
    full = (ROOT / "tests/g3_fixtures/valid_candidate.json").read_text()
    fill = json.dumps(correct_fill())
    assert _estimate_tokens(fill) * 3 < _estimate_tokens(full) * 2


def test_guided_request_uses_fill_schema_and_small_cap():
    skeleton = build_spec_skeleton(PUBLIC)
    safe = _validate_context_shape(valid_context())
    request = build_guided_request(safe, skeleton)
    assert request.json_schema == FILL_JSON_SCHEMA
    assert request.max_output_tokens == 800
    assert request.prompt_version == "synthesize-v2"


def test_guided_mock_round_trip(cli_scope):
    gateway = ModelGateway(
        MockProvider(responder=lambda request: {"content": correct_fill()}),
        RunBudget(Budgets()),
    )
    merged, receipt = request_guided_spec(valid_context(), gateway)
    assert receipt.prompt_version == "synthesize-v2" and receipt.real is False
    loaded, stamped = validate_generated_spec(merged, cli_scope, receipt)
    assert stamped.spec_digest == loaded.digest


def guided_probe_cases():
    from second_source.verifier import SealedCase

    return [
        SealedCase(case_id=f"guided-{i}", actions=(dict(action),))
        for i, action in enumerate([
            {"command": "add", "label": "K", "amount": 5},
            {"command": "add", "label": "", "amount": 5},
            {"command": "add", "label": "K", "amount": 0},
            {"command": "add", "label": "x" * 25, "amount": 5},
            {"command": "frobnicate"},
        ])
    ]


# Helper-level boundary test: exercises skeleton/fill/merge through a mock
# provider. The operator ticket path (synthesis='full'|'guided' binding in
# the broker/verifier) stays Codex-owned and v1-unchanged.
def test_guided_wire_end_to_end_mock(cli_scope, reference):
    from second_source.candidate_adapter import CandidateReferenceAdapter
    from second_source.candidate_generation import _validate_context_shape
    from second_source.verifier import DifferentialVerifier

    captured = {}

    def responder(request):
        captured["request"] = request.model_dump(mode="json")
        return {"content": correct_fill()}

    gateway = ModelGateway(
        MockProvider(responder=responder), RunBudget(Budgets()))
    skeleton = build_spec_skeleton(PUBLIC)
    expected = build_guided_request(
        _validate_context_shape(valid_context()), skeleton,
    ).model_dump(mode="json")
    merged, receipt = request_guided_spec(valid_context(), gateway)
    wire = captured["request"]
    assert wire["messages"][1:] == expected["messages"]
    assert wire["json_schema"] == expected["json_schema"] == FILL_JSON_SCHEMA
    assert wire["stage"] == expected["stage"] == "synthesize"
    assert wire["prompt_version"] == "synthesize-v2"
    loaded, stamped = validate_generated_spec(merged, cli_scope, receipt)
    assert stamped.spec_digest == loaded.digest
    cases = guided_probe_cases()
    report = DifferentialVerifier(
        reference,
        CandidateReferenceAdapter(json.dumps(merged).encode(), cli_scope),
    ).verify(cases)
    assert report.passed == report.total == len(cases)


def test_materially_different_fills_score_differently(cli_scope, reference):
    from second_source.candidate_adapter import CandidateReferenceAdapter

    skeleton = build_spec_skeleton(PUBLIC)
    good_raw = merge_skeleton_fill(skeleton, correct_fill())
    bad_raw = merge_skeleton_fill(skeleton, loose_fill())
    assert good_raw != bad_raw
    cases = [
        SealedCase(case_id=f"guided-{i}", actions=(dict(action),))
        for i, action in enumerate([
            {"command": "add", "label": "K", "amount": 5},
            {"command": "add", "label": "", "amount": 5},
            {"command": "add", "label": "K", "amount": 0},
            {"command": "add", "label": "x" * 25, "amount": 5},
            {"command": "frobnicate"},
        ])
    ]
    good = DifferentialVerifier(
        reference,
        CandidateReferenceAdapter(json.dumps(good_raw).encode(), cli_scope),
    ).verify(cases)
    bad = DifferentialVerifier(
        reference,
        CandidateReferenceAdapter(json.dumps(bad_raw).encode(), cli_scope),
    ).verify(cases)
    assert good.passed == good.total == len(cases)
    assert bad.passed < good.passed
