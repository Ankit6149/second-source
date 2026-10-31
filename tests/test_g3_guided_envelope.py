"""Guided envelope-key fix: the runtime envelope owns ok/error.

Regression source: genuine Meta response
`chatcmpl-01a191e3-4640-76d9-9a66-faea2027635c` (2026-10-31, receipt
`.runs/real-g3-guided-20261031T121200Z-authorized1/`) returned a
shape-valid fill that echoed the envelope key `ok` as a respond binding.
Observations show outputs like {"id": "1", "ok": true}, so the model could
not tell envelope keys from payload keys. The contract now declares the
envelope in the request, forbids ok/error in the fill schema, names them in
the prompt, and keeps the merger rejection as the backstop. Admission rules
are unchanged: invalid output still fails closed, never repaired.
"""

import json
from pathlib import Path

import pytest

from second_source.budgets import RunBudget
from second_source.candidate_generation import (
    FILL_JSON_SCHEMA,
    SYNTHESIZE_SYSTEM_V2,
    build_guided_request,
    build_spec_skeleton,
    merge_skeleton_fill,
    request_guided_spec,
    validate_generated_spec,
)
from second_source.candidate_runtime import CandidateInterpreter
from second_source.contracts import Budgets
from second_source.model_gateway import (
    GatewayError,
    MockProvider,
    ModelGateway,
)
from second_source.schema_validate import validate_json_schema

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = json.loads(
    (ROOT / "fixtures/owned_ledger/public_contract.json").read_text(
        encoding="utf-8")
)

# Exact bytes the genuine model returned (574 chars, sha256
# 68ff7f95598748976beb6cadddf17d8ca22f360d024e268cce3ea11ca31423ec).
GENUINE_FILL_TEXT = (
    '{"add": {"amount": {"maximum": 1000000, "minimum": 1}, '
    '"amount_error": "invalid_input", "duplicate_error": "duplicate_error", '
    '"label": {"max_length": 100, "min_length": 1, "trim": true}, '
    '"label_error": "invalid_input", '
    '"respond": {"id": "id", "ok": "ok"}, '
    '"unique_casefold": false, "unique_field": "label"}, '
    '"error_codes": {"invalid_input": "invalid_input", '
    '"unknown_command": "unknown_command"}, '
    '"list": {"respond": {"ok": "ok"}}, '
    '"remove": {"not_found_error": "not_found", "respond": {"ok": "ok"}}, '
    '"total": {"respond": {"amount": "amount", "count": "count", '
    '"ok": "ok"}}}'
)


def genuine_fill():
    fill = json.loads(GENUINE_FILL_TEXT)
    assert len(GENUINE_FILL_TEXT) == 574
    return fill


def test_genuine_envelope_echo_rejected_at_merge():
    skeleton = build_spec_skeleton(PUBLIC)
    with pytest.raises(GatewayError, match="reserved"):
        merge_skeleton_fill(skeleton, genuine_fill())


def test_gateway_schema_layer_rejects_envelope_keys():
    gateway = ModelGateway(
        MockProvider(responder=lambda request: {"content": genuine_fill()}),
        RunBudget(Budgets()),
    )
    with pytest.raises(GatewayError, match="[Ss]chema"):
        request_guided_spec(_context(), gateway)


def test_valid_fill_passes_new_schema_layer():
    assert validate_json_schema(_correct_fill(), FILL_JSON_SCHEMA) == []
    gateway = ModelGateway(
        MockProvider(responder=lambda request: {"content": _correct_fill()}),
        RunBudget(Budgets()),
    )
    merged, receipt = request_guided_spec(_context(), gateway)
    assert receipt.prompt_version == "synthesize-v2"
    assert merged["commands"]["add"]["respond"] == {"id": "id"}


def test_envelope_declared_in_request_and_prompt():
    request = build_guided_request(
        {"scope": {}, "public_commands": PUBLIC, "evidence": [],
         "hypotheses": []},
        build_spec_skeleton(PUBLIC),
    )
    user = json.loads(
        next(m["content"] for m in request.messages if m["role"] == "user"))
    assert user["response_envelope"] == {
        "success_key": "ok",
        "failure_key": "error",
        "owned_by": "runtime",
    }
    assert "'ok' and 'error'" in SYNTHESIZE_SYSTEM_V2
    assert "must never appear as respond keys" in SYNTHESIZE_SYSTEM_V2


def test_validator_supports_boolean_false_schema():
    schema = {"type": "object",
              "properties": {"ok": False, "error": False}}
    assert validate_json_schema({"ok": "x"}, schema) != []
    assert validate_json_schema({"error": "x"}, schema) != []
    assert validate_json_schema({"id": "x"}, schema) == []
    assert validate_json_schema({"anything": 1}, True) == []


def test_corrected_genuine_fill_admits_and_executes(cli_scope):
    # The genuine decisions minus the echoed envelope keys: this is the
    # output the clarified contract asks for, and it must admit, execute,
    # and answer the observed behaviors (add/list/total/remove).
    fill = genuine_fill()
    fill["add"]["respond"] = {"id": "id"}
    fill["list"]["respond"] = {"items": "items"}
    fill["total"]["respond"] = {"count": "count", "amount": "amount"}
    fill["remove"]["respond"] = {"removed": "id"}
    merged = merge_skeleton_fill(build_spec_skeleton(PUBLIC), fill)
    loaded, stamped = validate_generated_spec(
        merged, cli_scope,
        _receipt(origin="mock", provider="mock", real=False,
                 model="mock-muse-0", response_id="envelope-fix"),
    )
    assert stamped.spec_digest == loaded.digest
    candidate = CandidateInterpreter(loaded.spec)
    observations = candidate.execute_sequence([
        {"command": "add", "label": "Alpha", "amount": 3},
        {"command": "list"},
        {"command": "total"},
        {"command": "remove", "id": "1"},
    ]).observations
    assert observations[0].output["ok"] is True
    assert observations[1].output["ok"] is True
    assert observations[2].output["ok"] is True
    assert observations[3].output["ok"] is True


def _context():
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


def _correct_fill():
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


def _receipt(**fields):
    from second_source.candidate_generation import GenerationReceipt
    return GenerationReceipt(**fields)
