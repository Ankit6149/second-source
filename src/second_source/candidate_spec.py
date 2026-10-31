"""Versioned candidate specification, manifest, and trusted loader (G3-A).

A `CandidateSpec` is a purely declarative JSON document: parameter shapes,
trimming, uniqueness, storage, lookup, aggregation, and response shaping for
the ledger command set. It contains NO code, NO imports, NO shell, NO eval,
NO subprocess, NO file paths, and NO network operations — the trusted
interpreter (`candidate_runtime`) implements a fixed operation allowlist.

Scope is pinned at load time: subsystem must be `cli_ledger` and every
requirement id must belong to the run's `ScopeContract`. The file manifest
is validated through G0 `ScopeGuard.validate_candidate_files`.

The v1 DSL also pins command effects to the operator-owned public contract:
`add` may store, `remove` may delete by id, and `list`/`total` are
read-only. A generated spec cannot smuggle state mutation behind a nominally
read-only command.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, ValidationError

from .contracts import ProposedFile, ScopeContract, StrictModel
from .scope_guard import ScopeGuard

SPEC_VERSION = "1"
CANDIDATE_SUBSYSTEM = "cli_ledger"
MANIFEST_PATH = "candidate.json"
MANIFEST_VERSION = "1"
ALLOWED_COMMANDS = ("add", "list", "total", "remove")
# Resolvable respond sources per command: the payload field names each
# command's execution can emit. This is observable public behavior (every
# evidence output shows these keys), shared here as the single source of
# truth for both strict admission and the guided skeleton's model-visible
# vocabulary. Changing this table changes the DSL contract.
RESPOND_SOURCES: dict[str, frozenset[str]] = {
    "add": frozenset({"id", "label", "amount"}),
    "list": frozenset({"items"}),
    "total": frozenset({"count", "amount"}),
    "remove": frozenset({"id"}),
}

MAX_SPEC_BYTES = 65_536
ERROR_CODE_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
PARAM_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


class CandidateError(ValueError):
    """Malformed, over-scoped, or unsafe candidate specification."""


class ParamSpec(StrictModel):
    type: Literal["string", "integer"]
    required: StrictBool = True
    trim: StrictBool = False
    min_length: StrictInt | None = None
    max_length: StrictInt | None = None
    minimum: StrictInt | None = None
    maximum: StrictInt | None = None
    error: StrictStr = Field(min_length=1, max_length=64)


class CommandSpec(StrictModel):
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    unique_field: StrictStr | None = None
    unique_casefold: StrictBool = False
    unique_error: StrictStr | None = None
    store_record: StrictBool = False
    lookup_by: StrictStr | None = None
    lookup_param: StrictStr | None = None
    not_found_error: StrictStr | None = None
    delete_after_lookup: StrictBool = False
    aggregate_count: StrictBool = False
    aggregate_sum_field: StrictStr | None = None
    respond: dict[str, StrictStr] = Field(default_factory=dict)


class CandidateSpec(StrictModel):
    spec_version: Literal["1"] = "1"
    subsystem: StrictStr = Field(min_length=1, max_length=64)
    requirement_ids: frozenset[StrictStr] = Field(min_length=1)
    unknown_command_error: StrictStr = Field(min_length=1, max_length=64)
    invalid_input_error: StrictStr = Field(min_length=1, max_length=64)
    commands: dict[str, CommandSpec] = Field(min_length=1)


class ManifestFile(StrictModel):
    path: str = Field(min_length=1)
    subsystem: str = Field(min_length=1)
    requirement_ids: frozenset[str] = Field(min_length=1)


class CandidateManifest(StrictModel):
    manifest_version: Literal["1"] = "1"
    spec_digest: str = Field(min_length=1)
    files: tuple[ManifestFile, ...] = Field(min_length=1, max_length=1)


class LoadedCandidate(StrictModel):
    model_config = {"arbitrary_types_allowed": True}

    spec: CandidateSpec
    manifest: CandidateManifest
    digest: str


def _check_error_code(value: str, where: str) -> None:
    if not ERROR_CODE_RE.fullmatch(value):
        raise CandidateError(
            f"{where}: error code {value!r} must match [a-z][a-z0-9_]*"
        )


def _has_uniqueness(cmd: CommandSpec) -> bool:
    return (
        cmd.unique_field is not None
        or cmd.unique_error is not None
        or cmd.unique_casefold
    )


def _has_lookup(cmd: CommandSpec) -> bool:
    return (
        cmd.lookup_by is not None
        or cmd.lookup_param is not None
        or cmd.not_found_error is not None
        or cmd.delete_after_lookup
    )


def _has_aggregate(cmd: CommandSpec) -> bool:
    return cmd.aggregate_count or cmd.aggregate_sum_field is not None


def _check_command(name: str, cmd: CommandSpec) -> None:
    if name not in ALLOWED_COMMANDS:
        raise CandidateError(
            f"command {name!r} is not in the authorized set {ALLOWED_COMMANDS}"
        )

    # Sorted so identical content validates identically regardless of
    # JSON/dict key order.
    for param_name in sorted(cmd.params):
        param = cmd.params[param_name]
        if not PARAM_NAME_RE.fullmatch(param_name):
            raise CandidateError(f"command {name!r}: bad param name {param_name!r}")
        _check_error_code(param.error, f"command {name!r} param {param_name!r}")
        if param.type == "string":
            if param.minimum is not None or param.maximum is not None:
                raise CandidateError(
                    f"command {name!r} param {param_name!r}: numeric bounds on a string"
                )
            if (
                param.min_length is not None
                and param.max_length is not None
                and param.min_length > param.max_length
            ):
                raise CandidateError(
                    f"command {name!r} param {param_name!r}: min_length exceeds max_length"
                )
        else:
            if param.min_length is not None or param.max_length is not None:
                raise CandidateError(
                    f"command {name!r} param {param_name!r}: length bounds on an integer"
                )
            if (
                param.minimum is not None
                and param.maximum is not None
                and param.minimum > param.maximum
            ):
                raise CandidateError(
                    f"command {name!r} param {param_name!r}: minimum exceeds maximum"
                )

    if cmd.unique_field is not None:
        if cmd.unique_field not in cmd.params:
            raise CandidateError(
                f"command {name!r}: unique_field {cmd.unique_field!r} not a declared param"
            )
        if cmd.unique_error is None:
            raise CandidateError(f"command {name!r}: unique_field needs unique_error")
        _check_error_code(cmd.unique_error, f"command {name!r}")
    elif cmd.unique_error is not None or cmd.unique_casefold:
        raise CandidateError(f"command {name!r}: uniqueness options need unique_field")

    if (cmd.lookup_by is None) != (cmd.lookup_param is None):
        raise CandidateError(
            f"command {name!r}: lookup_by and lookup_param go together"
        )
    if cmd.lookup_by is not None:
        if cmd.lookup_by != "id":
            raise CandidateError(
                f"command {name!r}: v1 lookup_by supports only 'id'"
            )
        if cmd.lookup_param not in cmd.params:
            raise CandidateError(
                f"command {name!r}: lookup_param not a declared param"
            )
        if cmd.not_found_error is None:
            raise CandidateError(f"command {name!r}: lookup needs not_found_error")
        _check_error_code(cmd.not_found_error, f"command {name!r}")
    elif cmd.not_found_error is not None or cmd.delete_after_lookup:
        raise CandidateError(f"command {name!r}: lookup options need lookup_by")

    if cmd.aggregate_sum_field is not None and not cmd.aggregate_count:
        raise CandidateError(
            f"command {name!r}: aggregate_sum_field needs aggregate_count"
        )

    allowed_sources = RESPOND_SOURCES[name]
    for key in sorted(cmd.respond):
        source = cmd.respond[key]
        if not PARAM_NAME_RE.fullmatch(key):
            raise CandidateError(f"command {name!r}: bad respond key {key!r}")
        if key in {"ok", "error"}:
            raise CandidateError(
                f"command {name!r}: respond key {key!r} is protocol-reserved"
            )
        if source not in allowed_sources:
            raise CandidateError(
                f"command {name!r}: respond source {source!r} unresolvable"
            )

    # Command effects are pinned to the trusted public command manifest.
    if name == "add":
        if set(cmd.params) != {"label", "amount"}:
            raise CandidateError(
                "command 'add' params must be exactly {'label', 'amount'}"
            )
        if not cmd.store_record or cmd.unique_field is None:
            raise CandidateError(
                "command 'add' must store records with a uniqueness rule"
            )
        if _has_lookup(cmd) or _has_aggregate(cmd):
            raise CandidateError(
                "command 'add' cannot lookup/delete or aggregate in v1"
            )
        if "id" not in cmd.respond.values():
            raise CandidateError(
                "command 'add' must respond with the generated record id"
            )

    elif name == "list":
        if (
            cmd.params
            or _has_uniqueness(cmd)
            or cmd.store_record
            or _has_lookup(cmd)
            or _has_aggregate(cmd)
        ):
            raise CandidateError("command 'list' must be read-only in v1")

    elif name == "total":
        if cmd.params or _has_uniqueness(cmd) or cmd.store_record or _has_lookup(cmd):
            raise CandidateError("command 'total' must be read-only in v1")
        if not cmd.aggregate_count:
            raise CandidateError("command 'total' must aggregate a count")

    elif name == "remove":
        if set(cmd.params) != {"id"}:
            raise CandidateError("command 'remove' params must be exactly {'id'}")
        if _has_uniqueness(cmd) or cmd.store_record or _has_aggregate(cmd):
            raise CandidateError(
                "command 'remove' may only lookup and delete in v1"
            )
        if cmd.lookup_by != "id" or not cmd.delete_after_lookup:
            raise CandidateError("command 'remove' must lookup and delete by id")


def _check_spec_semantics(spec: CandidateSpec) -> None:
    if spec.subsystem != CANDIDATE_SUBSYSTEM:
        raise CandidateError(
            f"subsystem {spec.subsystem!r} is not the authorized {CANDIDATE_SUBSYSTEM!r}"
        )
    _check_error_code(spec.unknown_command_error, "spec")
    _check_error_code(spec.invalid_input_error, "spec")

    missing = [c for c in ALLOWED_COMMANDS if c not in spec.commands]
    if missing:
        raise CandidateError(
            f"spec omits authorized commands {missing}: declare all four"
        )
    for name in sorted(spec.commands):
        _check_command(name, spec.commands[name])

    add_params = spec.commands["add"].params
    sum_field = spec.commands["total"].aggregate_sum_field
    if sum_field is not None:
        declared = add_params.get(sum_field)
        if declared is None or declared.type != "integer":
            raise CandidateError(
                "command 'total': aggregate_sum_field must name an integer add parameter"
            )


def spec_digest_of(canonical: bytes) -> str:
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def parse_spec(raw: str | bytes | dict[str, Any]) -> tuple[CandidateSpec, str]:
    """Parse and semantically validate a candidate spec. Returns (spec, digest).

    The digest is over the exact canonicalized generated object (dict inputs
    are key-sorted; textual inputs retain their exact bytes). G3 reports use
    this loader-owned digest rather than recomputing it inside the runtime.
    """
    if isinstance(raw, dict):
        canonical = json.dumps(
            raw, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    elif isinstance(raw, str):
        canonical = raw.encode("utf-8")
    else:
        canonical = bytes(raw)

    if len(canonical) > MAX_SPEC_BYTES:
        raise CandidateError(f"spec exceeds {MAX_SPEC_BYTES} bytes")
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise CandidateError(f"spec contains duplicate JSON key {key!r}")
            out[key] = value
        return out

    try:
        doc = json.loads(
            canonical.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except CandidateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateError(f"spec is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise CandidateError("spec must be a JSON object")
    try:
        spec = CandidateSpec.model_validate(doc)
    except ValidationError as exc:
        raise CandidateError(
            f"spec schema violation: {exc.errors()[0]['msg']}"
        ) from exc

    _check_spec_semantics(spec)
    return spec, spec_digest_of(canonical)


def load_candidate(
    raw: str | bytes | dict[str, Any], contract: ScopeContract
) -> LoadedCandidate:
    """Validate a spec against a run's ScopeContract and build its manifest."""
    spec, digest = parse_spec(raw)
    if spec.subsystem not in contract.implementation.allowed_subsystems:
        raise CandidateError(
            f"subsystem {spec.subsystem!r} not in scope subsystems "
            f"{sorted(contract.implementation.allowed_subsystems)}"
        )
    unknown = sorted(
        set(spec.requirement_ids) - set(contract.implementation.requirements)
    )
    if unknown:
        raise CandidateError(
            f"requirement ids {unknown} not in scope requirements"
        )

    manifest = CandidateManifest(
        manifest_version=MANIFEST_VERSION,
        spec_digest=digest,
        files=(
            ManifestFile(
                path=MANIFEST_PATH,
                subsystem=spec.subsystem,
                requirement_ids=spec.requirement_ids,
            ),
        ),
    )
    decision = ScopeGuard(contract).validate_candidate_files(
        [
            ProposedFile(
                path=item.path,
                subsystem=item.subsystem,
                requirement_ids=item.requirement_ids,
            )
            for item in manifest.files
        ]
    )
    if not decision.allowed:
        raise CandidateError(
            f"manifest rejected: {decision.code}: {decision.reason}"
        )
    return LoadedCandidate(spec=spec, manifest=manifest, digest=digest)
