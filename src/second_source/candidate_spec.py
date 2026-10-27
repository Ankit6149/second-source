"""Versioned candidate specification, manifest, and trusted loader (G3-A).

A `CandidateSpec` is a purely declarative JSON document: parameter shapes,
normalization, uniqueness, storage, lookup, aggregation, and response shaping
for the ledger command set. It contains NO code, NO imports, NO shell, NO
eval, NO subprocess, NO file paths, and NO network operations — the trusted
interpreter (`candidate_runtime`) implements a fixed operation allowlist.

Scope is pinned at load time: subsystem must be `cli_ledger` and every
requirement id must belong to the run's `ScopeContract`. The file manifest is
validated through G0 `ScopeGuard.validate_candidate_files`.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import Field, ValidationError

from .contracts import StrictModel
from .scope_guard import ScopeGuard
from .contracts import ProposedFile, ScopeContract

SPEC_VERSION = "1"
CANDIDATE_SUBSYSTEM = "cli_ledger"
MANIFEST_PATH = "candidate.json"
MANIFEST_VERSION = "1"
ALLOWED_COMMANDS = ("add", "list", "total", "remove")

MAX_SPEC_BYTES = 65_536
ERROR_CODE_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
PARAM_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


class CandidateError(ValueError):
    """Malformed, over-scoped, or unsafe candidate specification."""


class ParamSpec(StrictModel):
    type: Literal["string", "integer"]
    required: bool = True
    trim: bool = False
    min_length: int | None = None
    max_length: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    error: str = Field(min_length=1, max_length=64)


class CommandSpec(StrictModel):
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    normalize_casefold: tuple[str, ...] = ()
    unique_field: str | None = None
    unique_casefold: bool = False
    unique_error: str | None = None
    store_record: bool = False
    lookup_by: str | None = None
    lookup_param: str | None = None
    not_found_error: str | None = None
    delete_after_lookup: bool = False
    aggregate_count: bool = False
    aggregate_sum_field: str | None = None
    respond: dict[str, str] = Field(default_factory=dict)


class CandidateSpec(StrictModel):
    spec_version: Literal["1"] = "1"
    subsystem: str = Field(min_length=1, max_length=64)
    requirement_ids: frozenset[str] = Field(min_length=1)
    unknown_command_error: str = Field(min_length=1, max_length=64)
    invalid_input_error: str = Field(min_length=1, max_length=64)
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
        raise CandidateError(f"{where}: error code {value!r} must match [a-z][a-z0-9_]*")


def _check_command(name: str, cmd: CommandSpec) -> None:
    if name not in ALLOWED_COMMANDS:
        raise CandidateError(f"command {name!r} is not in the authorized set {ALLOWED_COMMANDS}")
    for param_name, param in cmd.params.items():
        if not PARAM_NAME_RE.fullmatch(param_name):
            raise CandidateError(f"command {name!r}: bad param name {param_name!r}")
        _check_error_code(param.error, f"command {name!r} param {param_name!r}")
        if param.type == "string":
            if param.minimum is not None or param.maximum is not None:
                raise CandidateError(f"command {name!r} param {param_name!r}: numeric bounds on a string")
        else:
            if param.min_length is not None or param.max_length is not None:
                raise CandidateError(f"command {name!r} param {param_name!r}: length bounds on an integer")
    if cmd.unique_field is not None:
        if cmd.unique_field not in cmd.params:
            raise CandidateError(f"command {name!r}: unique_field {cmd.unique_field!r} not a declared param")
        if cmd.unique_error is None:
            raise CandidateError(f"command {name!r}: unique_field needs unique_error")
        _check_error_code(cmd.unique_error, f"command {name!r}")
    elif cmd.unique_error is not None or cmd.unique_casefold:
        raise CandidateError(f"command {name!r}: uniqueness options need unique_field")
    for field in cmd.normalize_casefold:
        if field not in cmd.params:
            raise CandidateError(f"command {name!r}: normalize_casefold {field!r} not a declared param")
    if (cmd.lookup_by is None) != (cmd.lookup_param is None):
        raise CandidateError(f"command {name!r}: lookup_by and lookup_param go together")
    if cmd.lookup_by is not None:
        if cmd.lookup_param not in cmd.params:
            raise CandidateError(f"command {name!r}: lookup_param not a declared param")
        if cmd.not_found_error is None:
            raise CandidateError(f"command {name!r}: lookup needs not_found_error")
        _check_error_code(cmd.not_found_error, f"command {name!r}")
    elif cmd.not_found_error is not None or cmd.delete_after_lookup:
        raise CandidateError(f"command {name!r}: lookup options need lookup_by")
    if cmd.aggregate_sum_field is not None and not cmd.aggregate_count:
        raise CandidateError(f"command {name!r}: aggregate_sum_field needs aggregate_count")
    allowed_sources = {
        "add": {"id", "label", "amount"},
        "list": {"items"},
        "total": {"count", "amount"},
        "remove": {"id"},
    }[name]
    for key, source in cmd.respond.items():
        if not PARAM_NAME_RE.fullmatch(key):
            raise CandidateError(f"command {name!r}: bad respond key {key!r}")
        if source not in allowed_sources:
            raise CandidateError(
                f"command {name!r}: respond source {source!r} unresolvable"
            )
    if name == "add":
        for required in ("label", "amount"):
            if required not in cmd.params:
                raise CandidateError(f"command 'add' requires param {required!r}")
        if not cmd.store_record or cmd.unique_field is None:
            raise CandidateError("command 'add' must store records with a uniqueness rule")
        if "id" not in cmd.respond:
            raise CandidateError("command 'add' must respond with the record id")
    if name == "remove":
        if cmd.lookup_by is None or not cmd.delete_after_lookup:
            raise CandidateError("command 'remove' must lookup and delete by id")
    if name == "total" and not cmd.aggregate_count:
        raise CandidateError("command 'total' must aggregate a count")


def _check_spec_semantics(spec: CandidateSpec) -> None:
    if spec.subsystem != CANDIDATE_SUBSYSTEM:
        raise CandidateError(
            f"subsystem {spec.subsystem!r} is not the authorized {CANDIDATE_SUBSYSTEM!r}"
        )
    _check_error_code(spec.unknown_command_error, "spec")
    _check_error_code(spec.invalid_input_error, "spec")
    missing = [c for c in ALLOWED_COMMANDS if c not in spec.commands]
    if missing:
        raise CandidateError(f"spec omits authorized commands {missing}: declare all four")
    for name, cmd in spec.commands.items():
        _check_command(name, cmd)


def spec_digest_of(canonical: bytes) -> str:
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def parse_spec(raw: str | bytes | dict[str, Any]) -> tuple[CandidateSpec, str]:
    """Parse and semantically validate a candidate spec. Returns (spec, digest)."""
    if isinstance(raw, dict):
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(raw, str):
        canonical = raw.encode("utf-8")
    else:
        canonical = bytes(raw)
    if len(canonical) > MAX_SPEC_BYTES:
        raise CandidateError(f"spec exceeds {MAX_SPEC_BYTES} bytes")
    try:
        doc = json.loads(canonical.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateError(f"spec is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise CandidateError("spec must be a JSON object")
    try:
        spec = CandidateSpec.model_validate(doc)
    except ValidationError as exc:
        raise CandidateError(f"spec schema violation: {exc.errors()[0]['msg']}") from exc
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
    unknown = sorted(set(spec.requirement_ids) - set(contract.implementation.requirements))
    if unknown:
        raise CandidateError(f"requirement ids {unknown} not in scope requirements")
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
    decision = ScopeGuard(contract).validate_candidate_files([
        ProposedFile(
            path=item.path,
            subsystem=item.subsystem,
            requirement_ids=item.requirement_ids,
        )
        for item in manifest.files
    ])
    if not decision.allowed:
        raise CandidateError(f"manifest rejected: {decision.code}: {decision.reason}")
    return LoadedCandidate(spec=spec, manifest=manifest, digest=digest)
