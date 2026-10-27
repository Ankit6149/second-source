"""Candidate generation boundary (G3-A).

Generation context is built EXPLICITLY from caller-supplied inputs only: the
scope public projection, the operator-owned public command manifest, redacted
observation views, and G2 hypotheses. This module NEVER reads reference
source, sealed cases, gold fixtures, local machine paths, or secrets — there
is no file access here at all, and a regression test pins that property.

Origin labels (never relabeled):
- `mock`: scripted/responder transport; exercises the typed boundary only.
- `trusted-test-fixture`: author-written spec (tests/g3_fixtures).
- `real`: a genuine Meta response received through `ModelGateway`.

`request_candidate_spec` prepares everything for a real call but performs NO
billable request itself beyond `gateway.generate`, which enforces its own
key + spend gates. Tests use `MockProvider` exclusively.
"""
from __future__ import annotations

import json
from typing import Any, Literal, Sequence

from .candidate_spec import (
    CandidateError,
    LoadedCandidate,
    load_candidate,
)
from .contracts import ScopeContract, StrictModel
from .evidence import redact
from .model_gateway import (
    GatewayError,
    ModelGateway,
    ModelRequest,
    ModelResponse,
)

SYNTHESIZE_STAGE = "synthesize"
SYNTHESIZE_PROMPT_VERSION = "synthesize-v1"

PARAM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "error"],
    "properties": {
        "type": {"type": "string"},
        "required": {"type": "boolean"},
        "trim": {"type": "boolean"},
        "min_length": {"type": "integer"},
        "max_length": {"type": "integer"},
        "minimum": {"type": "integer"},
        "maximum": {"type": "integer"},
        "error": {"type": "string"},
    },
}

COMMAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["respond"],
    "properties": {
        "params": {"type": "object"},
        "normalize_casefold": {"type": "array", "items": {"type": "string"}},
        "unique_field": {"type": "string"},
        "unique_casefold": {"type": "boolean"},
        "unique_error": {"type": "string"},
        "store_record": {"type": "boolean"},
        "lookup_by": {"type": "string"},
        "lookup_param": {"type": "string"},
        "not_found_error": {"type": "string"},
        "delete_after_lookup": {"type": "boolean"},
        "aggregate_count": {"type": "boolean"},
        "aggregate_sum_field": {"type": "string"},
        "respond": {"type": "object"},
    },
}

CANDIDATE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "spec_version", "subsystem", "requirement_ids",
        "unknown_command_error", "invalid_input_error", "commands",
    ],
    "properties": {
        "spec_version": {"const": "1"},
        "subsystem": {"type": "string"},
        "requirement_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "unknown_command_error": {"type": "string"},
        "invalid_input_error": {"type": "string"},
        "commands": {
            "type": "object",
            "minProperties": 4,
            "properties": {
                "add": COMMAND_SCHEMA,
                "list": COMMAND_SCHEMA,
                "total": COMMAND_SCHEMA,
                "remove": COMMAND_SCHEMA,
            },
        },
    },
}

SYNTHESIZE_SYSTEM = (
    "You are a behavioral specification author. Output ONE CandidateSpec JSON "
    "object for subsystem cli_ledger using ONLY these declarative operations: "
    "typed params (string/integer with bounds), trim/casefold normalization, "
    "case-insensitive uniqueness rejection, sequential record storage, id "
    "lookup with not_found errors, deletion, count/sum aggregation, and ok/error "
    "response shaping. Declare all four commands (add, list, total, remove). "
    "Derive validation rules ONLY from the attached authorized observations. "
    "Do not invent hidden internals, approvals, file paths, imports, shell, "
    "network, or code of any kind. Output JSON only."
)


class GenerationReceipt(StrictModel):
    origin: Literal["mock", "trusted-test-fixture", "real"]
    provider: str
    real: bool
    model: str
    response_id: str
    prompt_version: str = ""
    spec_digest: str = ""


def origin_of(response: ModelResponse) -> Literal["mock", "real"]:
    """Derive the origin label from the gateway response flag. No relabeling."""
    return "real" if response.real else "mock"


def build_generation_context(
    *,
    scope_goal: str,
    requirement_ids: Sequence[str],
    allowed_commands: Sequence[str],
    excluded_subsystems: Sequence[str],
    public_command_manifest: dict[str, Any],
    redacted_views: Sequence[dict[str, Any]],
    hypotheses: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the model-bound context from EXPLICIT inputs. No file reads."""
    return {
        "scope": {
            "goal": scope_goal,
            "requirement_ids": sorted(requirement_ids),
            "allowed_commands": sorted(allowed_commands),
            "excluded_subsystems": sorted(excluded_subsystems),
        },
        "public_commands": redact(public_command_manifest),
        "evidence": [redact(dict(view)) for view in redacted_views],
        "hypotheses": [redact(dict(hyp)) for hyp in hypotheses],
    }


def mock_propose_candidate(
    spec_dict: dict[str, Any],
    contract: ScopeContract,
    *,
    provider: str = "mock",
    model: str = "mock-muse-0",
) -> tuple[LoadedCandidate, GenerationReceipt]:
    """Validate an author-written spec through the real loading pipeline.

    Origin is ALWAYS `mock`: this exercises the typed boundary, never model
    provenance. The CONTENT provenance (e.g. trusted-test-fixture) is tracked
    separately by the caller and must never be upgraded to `real`.
    """
    loaded = load_candidate(spec_dict, contract)
    receipt = GenerationReceipt(
        origin="mock",
        provider=provider,
        real=False,
        model=model,
        response_id="mock-candidate-1",
        prompt_version=SYNTHESIZE_PROMPT_VERSION,
        spec_digest=loaded.digest,
    )
    return loaded, receipt


def request_candidate_spec(
    context: dict[str, Any],
    gateway: ModelGateway,
    *,
    max_output_tokens: int = 2000,
) -> tuple[dict[str, Any], GenerationReceipt]:
    """Ask the model for ONE CandidateSpec. Performs no key handling here.

    Billable only when the gateway's own key + spend gates pass. Returns the
    parsed spec dict (STILL UNVALIDATED — the caller must run load_candidate)
    plus a receipt whose origin derives from the response's real flag.
    """
    response = gateway.generate(
        ModelRequest(
            stage=SYNTHESIZE_STAGE,
            messages=(
                {"role": "system", "content": SYNTHESIZE_SYSTEM},
                {"role": "user", "content": json.dumps(context, sort_keys=True, default=str)},
            ),
            json_schema=CANDIDATE_JSON_SCHEMA,
            max_output_tokens=max_output_tokens,
            prompt_version=SYNTHESIZE_PROMPT_VERSION,
        )
    )
    if response.parsed is None:
        raise GatewayError("synthesize: model returned no parsed object")
    if not isinstance(response.parsed, dict):
        raise GatewayError("synthesize: model output is not an object")
    receipt = GenerationReceipt(
        origin=origin_of(response),
        provider=response.provider,
        real=response.real,
        model=response.model,
        response_id=response.response_id,
        prompt_version=response.prompt_version,
    )
    return dict(response.parsed), receipt


def validate_generated_spec(
    spec_dict: dict[str, Any], contract: ScopeContract, receipt: GenerationReceipt
) -> tuple[LoadedCandidate, GenerationReceipt]:
    """Load a generated spec and stamp the receipt digest. Origin untouched."""
    loaded = load_candidate(spec_dict, contract)
    return loaded, receipt.model_copy(update={"spec_digest": loaded.digest})
