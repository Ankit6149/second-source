"""Candidate generation boundary (G3-A).

Generation context is built EXPLICITLY from caller-supplied, already-authorized
inputs only: the scope public projection, the operator-owned public command
manifest, redacted observation views, and G2 hypotheses. This module NEVER
reads reference source, sealed cases, gold fixtures, local machine paths, or
secrets — there is no file access here at all.

Origin labels (never relabeled):
- `mock`: scripted/responder transport; exercises the typed boundary only.
- `trusted-test-fixture`: author-written spec (tests/g3_fixtures).
- `real`: a genuine Meta response received through `ModelGateway`.

`request_candidate_spec` revalidates the closed top-level context shape and
redacts it immediately before serialization. It still relies on the trusted
orchestrator to supply only approved evidence; sealed evaluator material must
remain physically outside the generation path.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal, Sequence

from .candidate_spec import LoadedCandidate, load_candidate
from .contracts import Observation, ScopeContract, StrictModel
from .evidence import redact
from .model_gateway import GatewayError, ModelGateway, ModelRequest, ModelResponse

SYNTHESIZE_STAGE = "synthesize"
SYNTHESIZE_PROMPT_VERSION = "synthesize-v1"

PARAM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "error"],
    "properties": {
        "type": {"type": "string", "enum": ["string", "integer"]},
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
        # The provider schema keeps parameter names open; the trusted Pydantic
        # loader validates every parameter object and all semantic relations.
        "params": {"type": "object"},
        "unique_field": {"type": "string"},
        "unique_casefold": {"type": "boolean"},
        "unique_error": {"type": "string"},
        "store_record": {"type": "boolean"},
        "lookup_by": {"type": "string", "enum": ["id"]},
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
        "spec_version",
        "subsystem",
        "requirement_ids",
        "unknown_command_error",
        "invalid_input_error",
        "commands",
    ],
    "properties": {
        "spec_version": {"const": "1"},
        "subsystem": {"type": "string"},
        "requirement_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string"},
        },
        "unknown_command_error": {"type": "string"},
        "invalid_input_error": {"type": "string"},
        "commands": {
            "type": "object",
            "additionalProperties": False,
            "required": ["add", "list", "total", "remove"],
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
    "typed params (string/integer with bounds), trimming, case-insensitive "
    "uniqueness rejection, sequential record storage, id lookup with not_found "
    "errors, deletion, count/sum aggregation, and ok/error response shaping. "
    "Declare all four commands (add, list, total, remove). add may store; remove "
    "may delete by id; list and total are read-only. Derive validation and "
    "response rules ONLY from the attached authorized observations. Do not "
    "invent hidden internals, approvals, file paths, imports, shell, network, "
    "or code of any kind. Output JSON only."
)

_CONTEXT_KEYS = {"scope", "public_commands", "evidence", "hypotheses"}
_SCOPE_KEYS = {
    "goal",
    "requirement_ids",
    "allowed_commands",
    "excluded_subsystems",
}


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


def _validate_context_shape(context: dict[str, Any]) -> dict[str, Any]:
    """Validate the complete nested model-visible projection, then redact it.

    This is an admission boundary, not merely a top-level key check: evidence
    must be a real Observation envelope keyed by a ledger digest; hypotheses
    may cite only admitted evidence digests; and the public command manifest
    must exactly match the scope command allowlist.
    """
    if not isinstance(context, dict) or set(context) != _CONTEXT_KEYS:
        raise GatewayError(
            "synthesize: generation context must contain only "
            + ", ".join(sorted(_CONTEXT_KEYS))
        )
    scope = context.get("scope")
    if not isinstance(scope, dict) or set(scope) != _SCOPE_KEYS:
        raise GatewayError(
            "synthesize: scope context must contain only "
            + ", ".join(sorted(_SCOPE_KEYS))
        )

    requirement_ids = scope.get("requirement_ids")
    allowed_commands = scope.get("allowed_commands")
    excluded_subsystems = scope.get("excluded_subsystems")
    if (
        not isinstance(scope.get("goal"), str)
        or not scope["goal"].strip()
        or not isinstance(requirement_ids, list)
        or not requirement_ids
        or not all(isinstance(x, str) and x for x in requirement_ids)
        or not isinstance(allowed_commands, list)
        or not allowed_commands
        or not all(isinstance(x, str) and x for x in allowed_commands)
        or not isinstance(excluded_subsystems, list)
        or not all(isinstance(x, str) for x in excluded_subsystems)
    ):
        raise GatewayError("synthesize: malformed scope projection")

    public = context.get("public_commands")
    if not isinstance(public, dict):
        raise GatewayError("synthesize: public_commands must be an object")
    if set(public) != {
        "version", "description", "transport", "reset_boundary", "commands"
    }:
        raise GatewayError("synthesize: malformed public command manifest")
    if public.get("transport") != "stdin_jsonl":
        raise GatewayError("synthesize: unexpected public transport")
    if public.get("reset_boundary") != "fresh_process_per_sequence":
        raise GatewayError("synthesize: unexpected reset boundary")
    commands = public.get("commands")
    if not isinstance(commands, dict) or set(commands) != set(allowed_commands):
        raise GatewayError(
            "synthesize: public commands must exactly match allowed_commands"
        )
    for name, definition in commands.items():
        if not isinstance(definition, dict):
            raise GatewayError(f"synthesize: malformed public command {name!r}")
        if set(definition) != {"params", "purpose", "side_effect"}:
            raise GatewayError(f"synthesize: malformed public command {name!r}")
        if not isinstance(definition.get("params"), dict):
            raise GatewayError(f"synthesize: malformed params for {name!r}")
        if definition.get("side_effect") not in {
            "read_only", "owned_mutation", "external", "prohibited"
        }:
            raise GatewayError(f"synthesize: malformed side_effect for {name!r}")

    evidence = context.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise GatewayError("synthesize: evidence must be a non-empty list")
    evidence_ids: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"digest", "observation"}:
            raise GatewayError("synthesize: malformed evidence view")
        digest = item.get("digest")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise GatewayError("synthesize: invalid evidence digest")
        try:
            Observation.model_validate(item.get("observation"))
        except Exception as exc:
            raise GatewayError("synthesize: invalid observation envelope") from exc
        evidence_ids.add(digest)

    hypotheses = context.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        raise GatewayError("synthesize: hypotheses must be a non-empty list")
    allowed_hypothesis_keys = {
        "id", "statement", "evidence_ids", "status",
        "alternatives", "unresolved_questions",
    }
    for hyp in hypotheses:
        if not isinstance(hyp, dict) or not set(hyp).issubset(allowed_hypothesis_keys):
            raise GatewayError("synthesize: malformed hypothesis view")
        if not isinstance(hyp.get("id"), str) or not hyp["id"]:
            raise GatewayError("synthesize: hypothesis id missing")
        if not isinstance(hyp.get("statement"), str) or not hyp["statement"]:
            raise GatewayError("synthesize: hypothesis statement missing")
        cited = hyp.get("evidence_ids")
        if not isinstance(cited, (list, tuple, set, frozenset)) or not cited:
            raise GatewayError("synthesize: hypothesis evidence_ids missing")
        if not all(isinstance(x, str) for x in cited):
            raise GatewayError("synthesize: malformed hypothesis evidence_ids")
        if not set(cited).issubset(evidence_ids):
            raise GatewayError("synthesize: hypothesis cites unavailable evidence")
        status = hyp.get("status", "hypothesized")
        if status not in {
            "hypothesized", "supported", "contradicted", "unresolved"
        }:
            raise GatewayError("synthesize: malformed hypothesis status")

    # Defense in depth: redact again at the final model boundary so later
    # caller mutation cannot bypass the context builder.
    return redact(context)


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
    """Ask the model for ONE CandidateSpec.

    Billable only when the gateway's own key + spend gates pass. Returns the
    parsed spec dict (STILL UNVALIDATED — caller must run load_candidate)
    plus a receipt whose origin derives from the response's real flag.
    """
    safe_context = _validate_context_shape(context)
    response = gateway.generate(
        ModelRequest(
            stage=SYNTHESIZE_STAGE,
            messages=(
                {"role": "system", "content": SYNTHESIZE_SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        safe_context, sort_keys=True, default=str
                    ),
                },
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
    spec_dict: dict[str, Any],
    contract: ScopeContract,
    receipt: GenerationReceipt,
) -> tuple[LoadedCandidate, GenerationReceipt]:
    """Load a generated spec and stamp the receipt digest. Origin untouched."""
    loaded = load_candidate(spec_dict, contract)
    return loaded, receipt.model_copy(update={"spec_digest": loaded.digest})
