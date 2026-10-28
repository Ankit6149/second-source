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

import hashlib
import json
import re
from typing import Any, Literal, Mapping, Sequence

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

def _command_schema_with_params(
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    schema = {
        **COMMAND_SCHEMA,
        "properties": dict(COMMAND_SCHEMA["properties"]),
    }
    param_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }
    if required:
        param_schema["required"] = required
    schema["properties"]["params"] = param_schema
    return schema


ADD_COMMAND_SCHEMA = _command_schema_with_params(
    {"label": PARAM_SCHEMA, "amount": PARAM_SCHEMA},
    required=["label", "amount"],
)
LIST_COMMAND_SCHEMA = _command_schema_with_params({})
TOTAL_COMMAND_SCHEMA = _command_schema_with_params({})
REMOVE_COMMAND_SCHEMA = _command_schema_with_params(
    {"id": PARAM_SCHEMA},
    required=["id"],
)


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
                "add": ADD_COMMAND_SCHEMA,
                "list": LIST_COMMAND_SCHEMA,
                "total": TOTAL_COMMAND_SCHEMA,
                "remove": REMOVE_COMMAND_SCHEMA,
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
    contract: ScopeContract | None = None,
    public_manifest_digest: str | None = None,
    approved_evidence: Mapping[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], GenerationReceipt]:
    """Ask the model for ONE CandidateSpec.

    Billable only when the gateway's own key + spend gates pass. Returns the
    parsed spec dict (STILL UNVALIDATED — caller must run load_candidate)
    plus a receipt whose origin derives from the response's real flag.
    """
    if gateway.is_real and (
        contract is None
        or public_manifest_digest is None
        or approved_evidence is None
    ):
        raise GatewayError(
            "synthesize: real inference requires provenance pins "
            "(contract, manifest digest, approved registry); "
            "refusing provider transport"
        )
    pinned = (contract is not None, public_manifest_digest is not None,
              approved_evidence is not None)
    if any(pinned) and not all(pinned):
        raise GatewayError(
            "synthesize: provenance pins must be supplied together"
        )
    if contract is not None:
        safe_context = validate_context_against_pins(
            context,
            contract=contract,
            public_manifest_digest=public_manifest_digest,
            approved_evidence=approved_evidence,
        )
    else:
        safe_context = _validate_context_shape(context)
    request = build_synthesize_request(
        safe_context, max_output_tokens=max_output_tokens
    )
    response = gateway.generate(request)
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


"""G3-D provenance binding (Muse-owned generation side).

The model-bound context is only as trustworthy as its provenance. A
caller-supplied mapping is NOT authentic provenance by itself: the
trusted orchestrator must build the approved evidence registry from
`EvidenceLedger` redacted views (`model_view`), pin the exact authorized
public command manifest via `pin_public_manifest`, and pass the run's
`ScopeContract`. These helpers verify the presented context against those
pins and build the EXACT `ModelRequest` the credential-owning broker
(the `ModelGateway`) sends, so an inspector can capture and compare the
wire request before any billable call. This module still performs no file
or credential access of its own.
"""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def pin_public_manifest(manifest: dict[str, Any]) -> str:
    """Digest the exact authorized public command manifest (context form)."""
    if not isinstance(manifest, dict):
        raise GatewayError("synthesize: public manifest must be an object")
    return hashlib.sha256(_canonical_bytes(manifest)).hexdigest()


def expected_scope_projection(contract: ScopeContract) -> dict[str, Any]:
    """The one scope projection a context bound to this contract may carry."""
    return {
        "goal": contract.goal,
        "requirement_ids": sorted(contract.implementation.requirements),
        "allowed_commands": sorted(contract.observation.allowed_commands),
        "excluded_subsystems": sorted(contract.exclusions.subsystems),
    }


def build_synthesize_request(
    safe_context: dict[str, Any], *, max_output_tokens: int = 2000
) -> ModelRequest:
    """Build the exact provider-bound synthesize request for an admitted context.

    The returned object is the inspected message/schema payload handed to
    the credential-owning broker (`ModelGateway`), which delivers it with
    only its documented deterministic schema-preamble prepended. Inspectors
    (including the evaluator-owned generation gate) capture the wire value
    and prove the admitted messages/schema travel through unmodified.
    """
    return ModelRequest(
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


def validate_context_against_pins(
    context: dict[str, Any],
    *,
    contract: ScopeContract,
    public_manifest_digest: str,
    approved_evidence: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Admit a context only if it matches the pinned contract/manifest/registry.

    Returns the redacted model-safe context. Raises `GatewayError` when the
    scope projection differs from the contract, the public manifest digest
    mismatches, or any evidence view is absent from (or differs from) the
    ledger-backed approved registry. Digest syntax alone never passes: every
    view's observation bytes must equal the registry entry byte for byte.
    """
    safe = _validate_context_shape(context)
    if safe["scope"] != expected_scope_projection(contract):
        raise GatewayError(
            "synthesize: generation scope is not the pinned contract projection"
        )
    if (
        not isinstance(public_manifest_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", public_manifest_digest) is None
    ):
        raise GatewayError("synthesize: malformed pinned manifest digest")
    if pin_public_manifest(safe["public_commands"]) != public_manifest_digest:
        raise GatewayError(
            "synthesize: public manifest does not match the pinned manifest"
        )
    if not isinstance(approved_evidence, Mapping):
        raise GatewayError("synthesize: approved evidence must be a mapping")
    for view in safe["evidence"]:
        approved = approved_evidence.get(view["digest"])
        if not isinstance(approved, dict):
            raise GatewayError(
                "synthesize: generation evidence is not approved registry evidence"
            )
        if _canonical_bytes(view["observation"]) != _canonical_bytes(approved):
            raise GatewayError(
                "synthesize: generation evidence differs from the approved registry"
            )
    return safe


def build_generation_report(
    *,
    receipt: GenerationReceipt,
    scope_digest: str,
    public_manifest_digest: str,
    evidence_digests: Sequence[str],
    spec_digest: str = "",
) -> dict[str, Any]:
    """Sanitized generation report: digests and receipt metadata only.

    Carries no prompts, observations, credentials, hidden cases, or reference
    material. `kind` marks it as generation provenance, never an evaluation
    score. Raises `GatewayError` on malformed digests (fail closed).
    """
    if not isinstance(scope_digest, str) or not scope_digest:
        raise GatewayError("synthesize: malformed scope digest")
    if re.fullmatch(r"[0-9a-f]{64}", public_manifest_digest or "") is None:
        raise GatewayError("synthesize: malformed manifest digest")
    digests = list(evidence_digests or [])
    if not digests or any(
        not isinstance(d, str) or re.fullmatch(r"[0-9a-f]{64}", d) is None
        for d in digests
    ):
        raise GatewayError("synthesize: malformed evidence digests")
    stamped = spec_digest or receipt.spec_digest
    if stamped and not stamped.startswith("sha256:"):
        raise GatewayError("synthesize: malformed spec digest")
    return {
        "kind": "GENERATION_REPORT_NOT_EVALUATION",
        "origin": receipt.origin,
        "real": receipt.real,
        "provider": receipt.provider,
        "model": receipt.model,
        "response_id": receipt.response_id,
        "prompt_version": receipt.prompt_version or SYNTHESIZE_PROMPT_VERSION,
        "spec_digest": stamped,
        "scope_digest": scope_digest,
        "public_manifest_digest": public_manifest_digest,
        "evidence_digests": sorted(digests),
    }

"""Constraint-guided synthesis (v2, Muse-owned intelligence side).

The v1 path asks the model for an entire CandidateSpec: every structural
field plus every behavior choice. That maximizes the model's freedom to emit
schema-invalid or DSL-invalid output on a paid call. The guided path splits
the work along the trust boundary instead:

- The TRUSTED skeleton is built deterministically from the authorized public
  command contract alone: command/param names and types, read-only versus
  mutating wiring, store/lookup/aggregate mechanics, and response shapes.
  It contains no hidden business rules and no error-code values.
- The MODEL fill decides ONLY evidence-dependent behavior: validation
  bounds, trimming, uniqueness selection (which declared param is unique),
  response key bindings, case handling, and the error-code strings observed
  in evidence outputs. The fill schema is a small fraction of a full spec,
  so output tokens, cost, and schema-violation surface all shrink.
- `merge_skeleton_fill` is shape-strict (unknown keys rejected, sane caps)
  and value-permissive; the UNCHANGED strict loader performs all semantic
  validation afterwards. Admission is never weakened: a merged spec passes
  through `load_candidate` exactly like a v1 spec.
"""


SYNTHESIZE_PROMPT_VERSION_V2 = "synthesize-v2"

#: Model decisions per command. Everything else is trusted structure.
FILL_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["error_codes", "add", "list", "total", "remove"],
    "properties": {
        "error_codes": {
            "type": "object",
            "additionalProperties": False,
            "required": ["unknown_command", "invalid_input"],
            "properties": {
                "unknown_command": {"type": "string"},
                "invalid_input": {"type": "string"},
            },
        },
        "add": {
            "type": "object",
            "additionalProperties": False,
            "required": ["label", "amount", "unique_field", "unique_casefold",
                         "label_error", "amount_error", "duplicate_error",
                         "respond"],
            "properties": {
                "label": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["min_length", "max_length", "trim"],
                    "properties": {
                        "min_length": {"type": "integer"},
                        "max_length": {"type": "integer"},
                        "trim": {"type": "boolean"},
                    },
                },
                "amount": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["minimum", "maximum"],
                    "properties": {
                        "minimum": {"type": "integer"},
                        "maximum": {"type": "integer"},
                    },
                },
                "unique_field": {"type": "string"},
                "unique_casefold": {"type": "boolean"},
                "label_error": {"type": "string"},
                "amount_error": {"type": "string"},
                "duplicate_error": {"type": "string"},
                "respond": {
                    "type": "object",
                    "minProperties": 1,
                    "maxProperties": 4,
                    "additionalProperties": {"type": "string"},
                },
            },
        },
        "list": {
            "type": "object",
            "additionalProperties": False,
            "required": ["respond"],
            "properties": {
                "respond": {
                    "type": "object",
                    "minProperties": 1,
                    "maxProperties": 4,
                    "additionalProperties": {"type": "string"},
                },
            },
        },
        "total": {
            "type": "object",
            "additionalProperties": False,
            "required": ["respond"],
            "properties": {
                "respond": {
                    "type": "object",
                    "minProperties": 1,
                    "maxProperties": 4,
                    "additionalProperties": {"type": "string"},
                },
            },
        },
        "remove": {
            "type": "object",
            "additionalProperties": False,
            "required": ["not_found_error", "respond"],
            "properties": {
                "not_found_error": {"type": "string"},
                "respond": {
                    "type": "object",
                    "minProperties": 1,
                    "maxProperties": 4,
                    "additionalProperties": {"type": "string"},
                },
            },
        },
    },
}

SYNTHESIZE_SYSTEM_V2 = (
    "You are a behavioral specification author. You will receive a trusted "
    "specification skeleton plus authorized observations. Output ONE JSON "
    "object matching the fill schema: validation bounds, trimming, which "
    "declared parameter carries the uniqueness rule, response key bindings, "
    "case handling, and the exact error-code strings shown in the "
    "observations. Derive every value ONLY from the attached observations. "
    "Do not invent hidden internals, approvals, file paths, imports, shell, "
    "network, or code of any kind. Output JSON only."
)

_ERROR_CODE_LIMIT = 64
_FILL_INT_LIMIT = 10 ** 9


def _skeleton_param(typ: str) -> dict[str, Any]:
    return {"type": typ, "required": True}


def build_spec_skeleton(public_commands: dict[str, Any]) -> dict[str, Any]:
    """Deterministic trusted skeleton from the authorized public contract.

    Fixes names, types, side-effect wiring, and response shapes. Carries no
    bounds, flags, or error-code values: those are model decisions from
    evidence. Raises `GatewayError` when the public contract lacks the four
    approved commands or the expected signatures.
    """
    if not isinstance(public_commands, dict):
        raise GatewayError("guided: public commands must be an object")
    try:
        commands = public_commands["commands"]
        add_params = commands["add"]["params"]
        remove_params = commands["remove"]["params"]
    except (KeyError, TypeError) as exc:
        raise GatewayError("guided: public contract misses approved commands") from exc
    if (set(commands) != {"add", "list", "total", "remove"}
            or add_params != {"label": "string", "amount": "integer"}
            or commands["list"]["params"] != {}
            or commands["total"]["params"] != {}
            or remove_params != {"id": "string"}
            or commands["add"].get("side_effect") != "owned_mutation"
            or commands["remove"].get("side_effect") != "owned_mutation"
            or commands["list"].get("side_effect") != "read_only"
            or commands["total"].get("side_effect") != "read_only"):
        raise GatewayError("guided: public contract signatures not approved")
    # Fixed slots below are justified ONLY by the authorized public contract
    # (command/param names and types, stated purposes, side-effect classes) or
    # by the normative DSL loader rules (which the strict loader itself
    # enforces at admission). Every None is an open model decision:
    # uniqueness selection, response key bindings, bounds, flags, error codes.
    return {
        "spec_version": "1",
        "subsystem": "cli_ledger",
        "requirement_ids": ["REQ-LEDGER"],
        "unknown_command_error": None,
        "invalid_input_error": None,
        "commands": {
            # "create a record" + owned_mutation -> store; DSL mandates SOME
            # uniqueness rule on add, but NOT which param: open.
            "add": {
                "params": {
                    "label": _skeleton_param("string"),
                    "amount": _skeleton_param("integer"),
                },
                "unique_field": None,
                "unique_casefold": None,
                "unique_error": None,
                "store_record": True,
                "respond": {},
            },
            "list": {"respond": {}},
            # "return count and aggregate amount": the only declared integer
            # param is amount, so the sum field follows from signatures.
            "total": {
                "aggregate_count": True,
                "aggregate_sum_field": "amount",
                "respond": {},
            },
            # "remove record by identifier": id is the only declared param,
            # so lookup wiring follows from signatures (v1 DSL: lookup_by id).
            "remove": {
                "params": {"id": _skeleton_param("string")},
                "lookup_by": "id",
                "lookup_param": "id",
                "not_found_error": None,
                "delete_after_lookup": True,
                "respond": {},
            },
        },
    }


def _fill_error(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _ERROR_CODE_LIMIT:
        raise GatewayError(f"guided: fill field {field!r} must be a short error code")
    return value


_RESPOND_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")
# Protocol-reserved response keys live in the runtime envelope ("ok" wraps
# every success, "error" every failure); a command output key may not claim
# either. The strict loader remains authoritative on source resolvability.
_RESERVED_RESPOND_KEYS = frozenset({"ok", "error"})


def _check_respond(command: str, respond: Any) -> dict[str, str]:
    if not isinstance(respond, dict) or not respond or len(respond) > 4:
        raise GatewayError(
            f"guided: fill {command!r} respond needs 1-4 key bindings")
    bindings: dict[str, str] = {}
    for key in sorted(respond):
        source = respond[key]
        if not isinstance(key, str) or not _RESPOND_KEY_RE.fullmatch(key):
            raise GatewayError(
                f"guided: fill {command!r} has bad respond key {key!r}")
        if key in _RESERVED_RESPOND_KEYS:
            raise GatewayError(
                f"guided: fill {command!r} respond key {key!r} is reserved")
        if not isinstance(source, str) or not source or len(source) > 32:
            raise GatewayError(
                f"guided: fill {command!r} has bad respond source")
        bindings[key] = source
    return bindings


def _fill_int(value: Any, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or abs(value) > _FILL_INT_LIMIT:
        raise GatewayError(f"guided: fill field {field!r} must be a bounded integer")
    return value


def merge_skeleton_fill(skeleton: dict[str, Any], fill: dict[str, Any]) -> dict[str, Any]:
    """Strictly merge model decisions into the trusted skeleton.

    Shape-strict (exact keys, sane caps) and value-permissive: semantic rules
    such as min<=max stay the strict loader's job, so admission is unchanged.
    The skeleton's `None` slots are the ONLY positions the fill may occupy;
    anything else raises. Returns a plain spec dict, still UNVALIDATED.
    """
    import copy as _copy

    if not isinstance(fill, dict):
        raise GatewayError("guided: fill must be an object")
    try:
        codes = fill["error_codes"]
        add = fill["add"]
        remove = fill["remove"]
        label = add["label"]
        amount = add["amount"]
    except (KeyError, TypeError) as exc:
        raise GatewayError("guided: fill misses required decisions") from exc
    allowed_top = {"error_codes", "add", "list", "total", "remove"}
    if set(fill) != allowed_top:
        raise GatewayError("guided: fill carries unknown top-level keys")
    if set(codes) != {"unknown_command", "invalid_input"}:
        raise GatewayError("guided: fill error_codes shape rejected")
    if set(add) != {"label", "amount", "unique_field", "unique_casefold",
                    "label_error", "amount_error", "duplicate_error",
                    "respond"}:
        raise GatewayError("guided: fill add shape rejected")
    if set(label) != {"min_length", "max_length", "trim"}:
        raise GatewayError("guided: fill label shape rejected")
    if set(amount) != {"minimum", "maximum"}:
        raise GatewayError("guided: fill amount shape rejected")
    if set(remove) != {"not_found_error", "respond"}:
        raise GatewayError("guided: fill remove shape rejected")
    for _name in ("list", "total"):
        _section = fill.get(_name)
        if not isinstance(_section, dict) or set(_section) != {"respond"}:
            raise GatewayError(f"guided: fill {_name} shape rejected")
    if not isinstance(add["unique_casefold"], bool) or not isinstance(label["trim"], bool):
        raise GatewayError("guided: fill flags must be booleans")
    spec = _copy.deepcopy(skeleton)
    try:
        spec["unknown_command_error"] = _fill_error(codes["unknown_command"], field="unknown_command")
        spec["invalid_input_error"] = _fill_error(codes["invalid_input"], field="invalid_input")
        add_spec = spec["commands"]["add"]
        add_spec["params"]["label"].update({
            "trim": label["trim"],
            "min_length": _fill_int(label["min_length"], field="min_length"),
            "max_length": _fill_int(label["max_length"], field="max_length"),
        })
        add_spec["params"]["amount"].update({
            "minimum": _fill_int(amount["minimum"], field="minimum"),
            "maximum": _fill_int(amount["maximum"], field="maximum"),
        })
        # Uniqueness selection is model-controlled but bounded: the field
        # must be a param the trusted skeleton declares for that command.
        # Presence of a rule on add is DSL-mandated, so a missing or foreign
        # selection fails closed instead of silently defaulting to "label".
        if add["unique_field"] not in set(add_spec["params"]):
            raise GatewayError(
                "guided: fill 'add' unique_field is not a declared add param")
        add_spec["unique_field"] = add["unique_field"]
        add_spec["respond"] = _check_respond("add", add["respond"])
        spec["commands"]["list"]["respond"] = _check_respond(
            "list", fill["list"]["respond"])
        spec["commands"]["total"]["respond"] = _check_respond(
            "total", fill["total"]["respond"])
        spec["commands"]["remove"]["respond"] = _check_respond(
            "remove", remove["respond"])
        add_spec["unique_casefold"] = add["unique_casefold"]
        add_spec["unique_error"] = _fill_error(add["duplicate_error"], field="duplicate_error")
        add_spec["params"]["label"]["error"] = _fill_error(add["label_error"], field="label_error")
        add_spec["params"]["amount"]["error"] = _fill_error(add["amount_error"], field="amount_error")
        spec["commands"]["remove"]["not_found_error"] = _fill_error(
            remove["not_found_error"], field="not_found_error")
        spec["commands"]["remove"]["params"]["id"]["error"] = spec[
            "commands"]["remove"]["not_found_error"]
    except (KeyError, TypeError) as exc:
        raise GatewayError("guided: skeleton slots missing") from exc
    if any(value is None for value in (
            spec["unknown_command_error"], spec["invalid_input_error"],
            add_spec["unique_casefold"], add_spec["unique_error"],
            add_spec["unique_field"],
            spec["commands"]["remove"]["not_found_error"])):
        raise GatewayError("guided: unfilled skeleton slots remain")
    if any(not spec["commands"][_name]["respond"]
           for _name in ("add", "list", "total", "remove")):
        raise GatewayError("guided: unfilled respond bindings remain")
    return spec


def build_guided_request(safe_context: dict[str, Any], skeleton: dict[str, Any],
                         *, max_output_tokens: int = 800) -> ModelRequest:
    """Provider-bound v2 request: skeleton plus admitted context, fill schema.

    The model returns ONLY the small fill object. Default output cap is 800
    tokens (a fill is an order of magnitude smaller than a full spec).
    """
    user_content = {
        "context": safe_context,
        "skeleton": skeleton,
    }
    return ModelRequest(
        stage=SYNTHESIZE_STAGE,
        messages=(
            {"role": "system", "content": SYNTHESIZE_SYSTEM_V2},
            {
                "role": "user",
                "content": json.dumps(user_content, sort_keys=True, default=str),
            },
        ),
        json_schema=FILL_JSON_SCHEMA,
        max_output_tokens=max_output_tokens,
        prompt_version=SYNTHESIZE_PROMPT_VERSION_V2,
    )


def request_guided_spec(context: dict[str, Any], gateway: ModelGateway, *,
                        max_output_tokens: int = 800,
                        contract: ScopeContract | None = None,
                        public_manifest_digest: str | None = None,
                        approved_evidence: Mapping[str, dict[str, Any]] | None = None,
                        ) -> tuple[dict[str, Any], GenerationReceipt]:
    """Ask the model for fill decisions only; merge into the trusted skeleton.

    Same provenance pins and fail-closed gates as v1. Returns the merged spec
    dict (STILL UNVALIDATED) plus a v2 receipt. Admission unchanged.
    """
    if gateway.is_real and (
        contract is None
        or public_manifest_digest is None
        or approved_evidence is None
    ):
        raise GatewayError(
            "synthesize: real inference requires provenance pins "
            "(contract, manifest digest, approved registry); "
            "refusing provider transport"
        )
    pinned = (contract is not None, public_manifest_digest is not None,
              approved_evidence is not None)
    if any(pinned) and not all(pinned):
        raise GatewayError(
            "synthesize: provenance pins must be supplied together"
        )
    if contract is not None:
        safe_context = validate_context_against_pins(
            context,
            contract=contract,
            public_manifest_digest=public_manifest_digest,
            approved_evidence=approved_evidence,
        )
    else:
        safe_context = _validate_context_shape(context)
    skeleton = build_spec_skeleton(safe_context["public_commands"])
    request = build_guided_request(
        safe_context, skeleton, max_output_tokens=max_output_tokens
    )
    response = gateway.generate(request)
    if response.parsed is None:
        raise GatewayError("synthesize: model returned no parsed object")
    if not isinstance(response.parsed, dict):
        raise GatewayError("synthesize: model output is not an object")
    merged = merge_skeleton_fill(skeleton, response.parsed)
    receipt = GenerationReceipt(
        origin=origin_of(response),
        provider=response.provider,
        real=response.real,
        model=response.model,
        response_id=response.response_id,
        prompt_version=response.prompt_version,
    )
    return merged, receipt
