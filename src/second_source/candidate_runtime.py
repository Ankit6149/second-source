"""Trusted declarative candidate interpreter (G3-A).

Executes a validated `CandidateSpec` WITHOUT evaluating any model-supplied
code: the interpreter implements a fixed operation allowlist (parse, validate,
trim, uniqueness, store, lookup, delete, aggregate, respond). Unknown
operations cannot be expressed — the spec schema rejects them at load.

The interpreter satisfies G0 `ReferenceProtocol`: it accepts the SAME flat
action dictionaries as the owned reference fixture, returns
`SequenceResult`/`Observation`, and honors the SAME reset boundary (fresh
state per sequence). It runs in-process with isolated in-memory state: no
subprocess, no filesystem, no network. Resource caps fail closed.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .candidate_spec import CandidateError, CandidateSpec, CommandSpec
from .contracts import Observation, SequenceResult

MAX_SEQUENCE_ACTIONS = 64
MAX_RECORDS = 10_000
MAX_OUTPUT_BYTES = 131_072
RESOURCE_EXHAUSTED = "resource_exhausted"

_ERROR_STATUS = "target_error"


class CandidateInterpreter:
    """In-memory ledger implementing exactly the validated spec."""

    def __init__(
        self,
        spec: CandidateSpec,
        *,
        max_actions: int = MAX_SEQUENCE_ACTIONS,
        max_records: int = MAX_RECORDS,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
    ) -> None:
        if max_actions < 1 or max_records < 1 or max_output_bytes < 512:
            raise ValueError("invalid candidate runtime resource limits")
        # Detach execution semantics from caller-owned mutable nested mappings.
        # CandidateSpec is frozen at the model level, but Python dict values are
        # otherwise still mutable aliases.
        self._spec = CandidateSpec.model_validate(spec.model_dump(mode="json"))
        self._max_actions = max_actions
        self._max_records = max_records
        self._max_output_bytes = max_output_bytes
        self._records: dict[str, dict[str, Any]] = {}
        self._next_id = 1

    def reset(self) -> None:
        """Fresh isolated state (mirrors the reference fresh-process boundary)."""
        self._records = {}
        self._next_id = 1

    def execute_sequence(
        self, actions: list[dict[str, Any]], *, sequence_id: str | None = None
    ) -> SequenceResult:
        # SAME boundary as the reference: every sequence starts empty.
        self.reset()
        if not isinstance(actions, list):
            return SequenceResult(
                sequence_id=sequence_id or uuid.uuid4().hex,
                observations=(),
                status="protocol_error",
                stderr="actions must be a list",
            )
        if len(actions) > self._max_actions:
            return SequenceResult(
                sequence_id=sequence_id or uuid.uuid4().hex,
                observations=(),
                status="protocol_error",
                stderr=f"sequence exceeds {self._max_actions} actions",
            )
        # ReferenceProtocol and SealedCase define actions as JSON objects.
        # Reject an out-of-contract sequence before executing any step so the
        # behavior matches CLIReferenceAdapter, which cannot construct a
        # trusted Observation with a non-dict input_action.
        if any(not isinstance(action, dict) for action in actions):
            return SequenceResult(
                sequence_id=sequence_id or uuid.uuid4().hex,
                observations=(),
                status="protocol_error",
                stderr="actions must contain JSON objects",
            )
        seq_id = sequence_id or uuid.uuid4().hex
        observations: list[Observation] = []
        for index, action in enumerate(actions):
            started = time.monotonic()
            try:
                output = self._apply(action)
            except CandidateError as exc:
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=tuple(observations),
                    status="protocol_error",
                    stderr=str(exc),
                )
            duration_ms = max(0, round((time.monotonic() - started) * 1000))
            ok = isinstance(output, dict) and output.get("ok") is True
            blob = json.dumps(output, sort_keys=True, ensure_ascii=False).encode("utf-8")
            if len(blob) > self._max_output_bytes:
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=tuple(observations),
                    status="protocol_error",
                    stderr="output exceeded byte cap",
                )
            observations.append(
                Observation(
                    observation_id=f"{seq_id}:{index}",
                    sequence_id=seq_id,
                    action_index=index,
                    input_action=dict(action) if isinstance(action, dict) else {},
                    output=output,
                    exit_code=0,
                    duration_ms=duration_ms,
                    status="ok" if ok else _ERROR_STATUS,
                )
            )
        return SequenceResult(
            sequence_id=seq_id, observations=tuple(observations), status="ok", stderr=""
        )

    # -- operation allowlist ------------------------------------------------

    def _apply(self, action: Any) -> dict[str, Any]:
        if not isinstance(action, dict):
            raise CandidateError("each action must be a JSON object")
        # Within the dict-only ReferenceProtocol, missing/non-string commands
        # mirror the owned fixture's unknown_command behavior.
        command = action.get("command")
        if not isinstance(command, str):
            return {"ok": False, "error": self._spec.unknown_command_error}
        cmd = self._spec.commands.get(command)
        if cmd is None:
            return {"ok": False, "error": self._spec.unknown_command_error}

        # ReferenceProtocol actions are flat JSON objects:
        # {"command":"add","label":"A","amount":1}.  The exact same action
        # object is handed to reference and candidate by DifferentialVerifier.
        params = {key: value for key, value in action.items() if key != "command"}
        values, error = self._validate_params(cmd, params)
        if error is not None:
            return {"ok": False, "error": error}
        if cmd.unique_field is not None and self._is_duplicate(cmd, values):
            err = cmd.unique_error or self._spec.invalid_input_error
            return {"ok": False, "error": err}

        record: dict[str, Any] | None = None
        if cmd.lookup_by is not None:
            record = self._lookup(cmd, values)
            if record is None:
                err = cmd.not_found_error or self._spec.invalid_input_error
                return {"ok": False, "error": err}
            if cmd.delete_after_lookup:
                del self._records[record["id"]]

        if cmd.store_record:
            if len(self._records) >= self._max_records:
                return {"ok": False, "error": RESOURCE_EXHAUSTED}
            record_id = str(self._next_id)
            self._next_id += 1
            record = {"id": record_id}
            for key in values:
                record[key] = values[key]
            self._records[record_id] = record

        aggregate: dict[str, Any] = {}
        if cmd.aggregate_count:
            aggregate["count"] = len(self._records)
            if cmd.aggregate_sum_field is not None:
                aggregate["amount"] = sum(
                    int(item.get(cmd.aggregate_sum_field, 0))
                    for item in self._records.values()
                )

        return {"ok": True, **self._respond(cmd, values, record, aggregate)}

    def _validate_params(
        self, cmd: CommandSpec, params: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        # Deterministic precedence: identical spec content yields the same
        # first param error regardless of JSON/dict key order. Spec mapping
        # order is a transport representation detail, never semantics.
        values: dict[str, Any] = {}
        for name in sorted(cmd.params):
            decl = cmd.params[name]
            if name not in params:
                if decl.required:
                    return {}, decl.error
                continue
            value = params[name]
            if decl.type == "string":
                if not isinstance(value, str):
                    return {}, decl.error
                if decl.trim:
                    value = value.strip()
                if decl.min_length is not None and len(value) < decl.min_length:
                    return {}, decl.error
                if decl.max_length is not None and len(value) > decl.max_length:
                    return {}, decl.error
            else:
                if not isinstance(value, int) or isinstance(value, bool):
                    return {}, decl.error
                if decl.minimum is not None and value < decl.minimum:
                    return {}, decl.error
                if decl.maximum is not None and value > decl.maximum:
                    return {}, decl.error
            values[name] = value
        # The owned reference ignores unrecognized extra fields; match that
        # observable wire behavior rather than inventing a stricter candidate.
        return values, None

    def _fold(self, value: Any) -> Any:
        return value.casefold() if isinstance(value, str) else value

    def _is_duplicate(self, cmd: CommandSpec, values: dict[str, Any]) -> bool:
        field = cmd.unique_field or ""
        candidate = values.get(field)
        probe = self._fold(candidate) if cmd.unique_casefold else candidate
        for item in self._records.values():
            existing = (
                self._fold(item.get(field)) if cmd.unique_casefold else item.get(field)
            )
            if existing == probe:
                return True
        return False

    def _lookup(self, cmd: CommandSpec, values: dict[str, Any]) -> dict[str, Any] | None:
        # G3-A v1 intentionally supports only trusted in-memory id lookup.
        if cmd.lookup_by != "id":
            raise CandidateError(f"unsupported lookup field {cmd.lookup_by!r}")
        want = values.get(cmd.lookup_param or "")
        if not isinstance(want, str):
            return None
        return self._records.get(want)

    def _respond(
        self,
        cmd: CommandSpec,
        values: dict[str, Any],
        record: dict[str, Any] | None,
        aggregate: dict[str, Any],
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        items = list(self._records.values())
        for key, source in cmd.respond.items():
            if source == "items":
                out[key] = [dict(item) for item in items]
            elif source in aggregate:
                out[key] = aggregate[source]
            elif record is not None and source in record:
                out[key] = record[source]
            elif source in values:
                out[key] = values[source]
            else:
                raise CandidateError(f"respond source {source!r} unresolvable")
        return out
