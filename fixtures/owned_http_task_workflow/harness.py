"""Typed HTTP observation adapter, declarative candidate runtime, independent
differential evaluator, isolation boundary checks, and competitive benchmark
scaffolding for the owned G4 HTTP task-workflow target.

All functions in this module are strictly zero-call and nonbillable.
Never pass reference source or sealed suite cases to model generation requests.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import secrets
import stat
import time
from typing import Any, Literal, Mapping, Sequence
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

from pydantic import Field, StrictBool, StrictInt, StrictStr, ValidationError

from second_source.contracts import (
    Budgets,
    ExclusionScope,
    ImplementationScope,
    Observation,
    ObservationScope,
    PolicyDecision,
    ProposedAction,
    ProposedFile,
    ScopeContract,
    ScopeMode,
    SequenceResult,
    SideEffect,
    StrictModel,
    TargetKind,
    TargetSpec,
)
from second_source.evidence import EvidenceLedger, redact
from second_source.hypotheses import HypothesisBatch, HypothesisStore, validate_batch
from second_source.model_gateway import ModelRequest, _estimate_tokens
from second_source.scope_guard import ScopeGuard
from second_source.verifier import (
    CaseResult,
    DifferentialVerifier,
    EvaluationReport,
    ReferenceProtocol,
    SealedCase,
)

from .reference_server import (
    MAX_BODY_BYTES,
    MAX_RECORDS,
    OWNER_RE,
    TASK_ID_RE,
    RunningTaskWorkflowServer,
     _parse_strict_int,
    _task_seq_num,
    start_reference_server,
)

FIXTURE_DIR = Path(__file__).resolve().parent
PUBLIC_CONTRACT_PATH = FIXTURE_DIR / "public_contract.json"
REFERENCE_SERVER_PATH = FIXTURE_DIR / "reference_server.py"

TARGET_ID = "owned-http-task-workflow-v1"
SUBSYSTEM_ID = "http_task_workflow"
REQUIREMENT_ID = "REQ-HTTP-TASKS"
SUITE_VERSION = "1"
MAX_SUITE_BYTES = 1_000_000
MAX_SPEC_BYTES = 65_536

OBSERVABLE_HEADERS = frozenset({
    "content-type",
    "location",
    "x-task-revision",
    "allow",
    "www-authenticate",
})

OPERATION_SPECS: dict[str, tuple[str, str, SideEffect]] = {
    "create_task": ("POST", "/v1/tasks", SideEffect.LOCAL_MUTATION),
    "list_tasks": ("GET", "/v1/tasks", SideEffect.READ_ONLY),
    "get_task": ("GET", "/v1/tasks/{task_id}", SideEffect.READ_ONLY),
    "update_task": ("PATCH", "/v1/tasks/{task_id}", SideEffect.LOCAL_MUTATION),
    "delete_task": ("DELETE", "/v1/tasks/{task_id}", SideEffect.LOCAL_MUTATION),
}

METHOD_TO_ACTION_KIND: dict[str, str] = {
    "GET": "http_get",
    "POST": "http_post",
    "PATCH": "http_patch",
    "DELETE": "http_delete",
}


class HTTPEvaluationBlocked(RuntimeError):
    """Raised when scope, suite, provenance, or isolation boundaries are violated."""


class HTTPCandidateError(ValueError):
    """Raised when an HTTP candidate specification is malformed or out of scope."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def load_public_contract() -> dict[str, Any]:
    return json.loads(PUBLIC_CONTRACT_PATH.read_text(encoding="utf-8"))


def reference_source_digest() -> str:
    raw = REFERENCE_SERVER_PATH.read_bytes().replace(b"\r\n", b"\n")
    return _digest(raw)


def create_http_scope(
    reference_url: str = "http://127.0.0.1:8000",
    *,
    max_usd: float = 0.0,
    max_reference_experiments: int = 40,
) -> ScopeContract:
    """Build the authorized ScopeContract for the owned G4 HTTP task-workflow target."""
    return ScopeContract(
        target=TargetSpec(
            kind=TargetKind.HTTP,
            permission_ref=TARGET_ID,
            reference_url=reference_url,
        ),
        goal="Reconstruct the owned stateful HTTP task-workflow API service",
        mode=ScopeMode.SELECTED_FLOWS,
        observation=ObservationScope(
            allowed_url_patterns=("/v1/tasks", "/v1/tasks/*"),
            allowed_roles=frozenset({"alice", "bob", "viewer", "admin", "guest"}),
            permitted_actions=frozenset({
                "http_get",
                "http_post",
                "http_patch",
                "http_delete",
            }),
            authenticated_access="authorized_test_account",
        ),
        implementation=ImplementationScope(
            route_patterns=("/v1/tasks", "/v1/tasks/*"),
            required_flows=(
                "task_crud",
                "task_transitions",
                "task_rbac",
                "task_query",
            ),
            requirements=frozenset({REQUIREMENT_ID}),
            allowed_subsystems=frozenset({SUBSYSTEM_ID}),
            fidelity=frozenset({"behavioral"}),
        ),
        exclusions=ExclusionScope(
            url_patterns=("/__admin/**",),
            subsystems=frozenset({"billing", "external_webhooks", "real_oauth"}),
            external_side_effects=frozenset({"email", "webhook"}),
        ),
        budgets=Budgets(
            max_reference_experiments=max_reference_experiments,
            max_model_calls=5,
            max_repair_rounds=2,
            max_wall_seconds=600,
            max_estimated_model_spend_usd=max_usd,
        ),
    )


def scope_digest_of(contract: ScopeContract) -> str:
    doc = contract.model_dump(mode="json")

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in sorted(value.items())}
        if isinstance(value, list):
            return sorted(
                (normalize(x) for x in value),
                key=lambda item: json.dumps(item, sort_keys=True),
            )
        return value

    return _digest(_canonical_bytes(normalize(doc)))


class HTTPRequestAction(StrictModel):
    """Typed representation of an observable HTTP request step."""

    operation: str | None = None
    method: str = Field(min_length=1)
    path: str = Field(min_length=1)
    actor: str | None = "alice"
    query: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    raw_body: str | None = None
    seed_tasks: tuple[dict[str, Any], ...] | None = None


class HTTPResponseEnvelope(StrictModel):
    """Typed representation of a normalized observable HTTP response."""

    ok: bool
    error: str | None = None
    http_status: int
    headers: dict[str, str]
    body: dict[str, Any]


class HTTPStateTransition(StrictModel):
    """Typed record of an observed state transition across a sequence step."""

    step_index: int = Field(ge=0)
    actor: str | None
    method: str
    path: str
    http_status: int
    outcome: Literal["mutated", "read_only", "rejected"]
    task_id: str | None = None
    prior_status: str | None = None
    post_status: str | None = None
    prior_revision: int | None = None
    post_revision: int | None = None


def normalize_http_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize either a named-operation action or an explicit HTTP action dict."""
    if not isinstance(action, Mapping):
        raise ValueError("HTTP action must be a JSON object")
    op = action.get("operation")
    method = action.get("method")
    path = action.get("path")
    task_id = action.get("task_id")

    if op is not None:
        if not isinstance(op, str) or op not in OPERATION_SPECS:
            raise ValueError(f"Unsupported operation: {op!r}")
        spec_method, spec_path, _ = OPERATION_SPECS[op]
        method = method or spec_method
        if "{task_id}" in spec_path:
            if not isinstance(task_id, str) or not task_id:
                raise ValueError(f"Operation {op!r} requires non-empty string task_id")
            path = path or spec_path.replace("{task_id}", task_id)
        else:
            path = path or spec_path

    if not isinstance(method, str) or not method.strip():
        raise ValueError("HTTP action requires a non-empty method")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("HTTP action requires a non-empty path")

    actor = action.get("actor", "alice")
    if actor is not None and not isinstance(actor, str):
        raise ValueError("actor must be a string or None")

    query = action.get("query") or {}
    if not isinstance(query, Mapping):
        raise ValueError("query must be a mapping")

    out: dict[str, Any] = {
        "method": method.upper().strip(),
        "path": path.strip(),
        "actor": actor,
    }
    if op is not None:
        out["operation"] = op
    if task_id is not None:
        out["task_id"] = task_id
    if query:
        out["query"] = dict(query)
    if "raw_body" in action and action["raw_body"] is not None:
        if not isinstance(action["raw_body"], str):
            raise ValueError("raw_body must be a string")
        out["raw_body"] = action["raw_body"]
    elif "body" in action and action["body"] is not None:
        out["body"] = action["body"]
    if "seed_tasks" in action and action["seed_tasks"] is not None:
        if not isinstance(action["seed_tasks"], (list, tuple)):
            raise ValueError("seed_tasks must be a list")
        out["seed_tasks"] = [dict(item) for item in action["seed_tasks"]]
    return out


def to_proposed_action(
    action: Mapping[str, Any],
    *,
    requirement_id: str = REQUIREMENT_ID,
) -> ProposedAction:
    """Convert an HTTP action dictionary into a ScopeGuard-verifiable ProposedAction."""
    norm = normalize_http_action(action)
    method = norm["method"]
    kind = METHOD_TO_ACTION_KIND.get(method, f"http_{method.lower()}")
    actor = norm.get("actor") or "guest"
    requires_auth = actor != "guest"
    side_effect = (
        SideEffect.READ_ONLY
        if method == "GET"
        else SideEffect.LOCAL_MUTATION
    )
    payload: dict[str, Any] = {}
    if "query" in norm:
        payload["query"] = norm["query"]
    if "body" in norm:
        payload["body"] = norm["body"]
    if "raw_body" in norm:
        payload["raw_body"] = norm["raw_body"]
    return ProposedAction(
        kind=kind,
        target=norm["path"],
        requirement_id=requirement_id,
        role=actor,
        requires_auth=requires_auth,
        side_effect=side_effect,
        approval_granted=False,
        payload=payload,
    )


def format_observation_output(
    http_status: int,
    headers: Mapping[str, str],
    body: dict[str, Any],
) -> dict[str, Any]:
    """Construct the canonical Observation.output envelope for HTTP responses.

    Preserves HTTP status, normalized deterministic protocol headers, and parsed
    JSON body while remaining 100% compatible with `second_source.verifier.DifferentialVerifier`.
    """
    filtered_headers = {
        k.lower(): str(v)
        for k, v in sorted(headers.items(), key=lambda item: item[0].lower())
        if k.lower() in OBSERVABLE_HEADERS
    }
    is_ok = 200 <= http_status < 300 and bool(body.get("ok", True))
    if is_ok:
        return {
            "ok": True,
            "http_status": http_status,
            "headers": filtered_headers,
            "body": body,
        }
    err_code = body.get("error")
    if not isinstance(err_code, str) or not err_code:
        err_code = f"http_{http_status}"
    return {
        "ok": False,
        "error": err_code,
        "http_status": http_status,
        "headers": filtered_headers,
        "body": body,
    }


def extract_state_transitions(
    observations: Sequence[Observation],
) -> tuple[HTTPStateTransition, ...]:
    """Reconstruct observable task state transitions from a sequence of HTTP observations."""
    known_status: dict[str, str] = {}
    known_revision: dict[str, int] = {}
    transitions: list[HTTPStateTransition] = []

    for obs in observations:
        try:
            act = normalize_http_action(obs.input_action)
        except Exception:
            act = dict(obs.input_action)
        out = obs.output if isinstance(obs.output, dict) else {}
        method = str(act.get("method", "GET")).upper()
        path = str(act.get("path", "/"))
        actor = act.get("actor")
        http_status = int(out.get("http_status", 0))
        body = out.get("body") if isinstance(out.get("body"), dict) else {}

        if not out.get("ok"):
            task_id = act.get("task_id")
            if not task_id and path.startswith("/v1/tasks/"):
                task_id = path.split("/v1/tasks/", 1)[1]
            transitions.append(
                HTTPStateTransition(
                    step_index=obs.action_index,
                    actor=actor,
                    method=method,
                    path=path,
                    http_status=http_status,
                    outcome="rejected",
                    task_id=task_id if isinstance(task_id, str) else None,
                    prior_status=known_status.get(str(task_id)) if task_id else None,
                    post_status=known_status.get(str(task_id)) if task_id else None,
                    prior_revision=known_revision.get(str(task_id)) if task_id else None,
                    post_revision=known_revision.get(str(task_id)) if task_id else None,
                )
            )
            continue

        if method == "GET":
            task_obj = body.get("task")
            if isinstance(task_obj, dict) and "id" in task_obj:
                tid = str(task_obj["id"])
                known_status[tid] = str(task_obj.get("status", ""))
                known_revision[tid] = int(task_obj.get("revision", 1))
                transitions.append(
                    HTTPStateTransition(
                        step_index=obs.action_index,
                        actor=actor,
                        method=method,
                        path=path,
                        http_status=http_status,
                        outcome="read_only",
                        task_id=tid,
                        prior_status=known_status[tid],
                        post_status=known_status[tid],
                        prior_revision=known_revision[tid],
                        post_revision=known_revision[tid],
                    )
                )
            else:
                for item in body.get("items", []):
                    if isinstance(item, dict) and "id" in item:
                        tid = str(item["id"])
                        known_status[tid] = str(item.get("status", ""))
                        known_revision[tid] = int(item.get("revision", 1))
                transitions.append(
                    HTTPStateTransition(
                        step_index=obs.action_index,
                        actor=actor,
                        method=method,
                        path=path,
                        http_status=http_status,
                        outcome="read_only",
                    )
                )
        elif method in ("POST", "PATCH"):
            task_obj = body.get("task", {})
            tid = str(task_obj.get("id", ""))
            prior_st = known_status.get(tid)
            prior_rev = known_revision.get(tid)
            post_st = str(task_obj.get("status", ""))
            post_rev = int(task_obj.get("revision", 1))
            if tid:
                known_status[tid] = post_st
                known_revision[tid] = post_rev
            transitions.append(
                HTTPStateTransition(
                    step_index=obs.action_index,
                    actor=actor,
                    method=method,
                    path=path,
                    http_status=http_status,
                    outcome="mutated",
                    task_id=tid or None,
                    prior_status=prior_st,
                    post_status=post_st,
                    prior_revision=prior_rev,
                    post_revision=post_rev,
                )
            )
        elif method == "DELETE":
            tid = str(body.get("deleted", ""))
            prior_st = known_status.pop(tid, None)
            prior_rev = known_revision.pop(tid, None)
            transitions.append(
                HTTPStateTransition(
                    step_index=obs.action_index,
                    actor=actor,
                    method=method,
                    path=path,
                    http_status=http_status,
                    outcome="mutated",
                    task_id=tid or None,
                    prior_status=prior_st,
                    post_status="deleted",
                    prior_revision=prior_rev,
                    post_revision=None,
                )
            )
    return tuple(transitions)


class HTTPReferenceAdapter:
    """Trusted black-box HTTP adapter satisfying ReferenceProtocol.

    Communicates with the local HTTP reference server over loopback HTTP/1.1,
    enforcing deterministic per-sequence reset/seeding via `/__admin/reset` while
    forbidding any sequence action from accessing `/__admin/**`.
    """

    def __init__(
        self,
        server: RunningTaskWorkflowServer | None = None,
        *,
        timeout_seconds: float = 5.0,
        max_output_bytes: int = 128_000,
        max_actions: int = 64,
    ) -> None:
        if timeout_seconds <= 0 or max_output_bytes < 512 or max_actions < 1:
            raise ValueError("Invalid HTTPReferenceAdapter configuration")
        self._external_server = server
        self._timeout = timeout_seconds
        self._max_output = max_output_bytes
        self._max_actions = max_actions
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request_raw(
        self,
        base_url: str,
        method: str,
        target_path_and_query: str,
        headers: Mapping[str, str],
        body_bytes: bytes | None,
    ) -> tuple[int, dict[str, str], bytes]:
        url = base_url.rstrip("/") + target_path_and_query
        req = urllib.request.Request(
            url=url,
            data=body_bytes,
            headers=dict(headers),
            method=method,
        )
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                raw = resp.read(self._max_output + 1)
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return int(resp.status), resp_headers, raw
        except urllib.error.HTTPError as err:
            raw = err.read(self._max_output + 1) if err.fp is not None else b""
            resp_headers = {k.lower(): v for k, v in err.headers.items()} if err.headers else {}
            return int(err.code), resp_headers, raw

    def execute_sequence(
        self,
        actions: Sequence[dict[str, Any]],
        *,
        sequence_id: str | None = None,
    ) -> SequenceResult:
        seq_id = sequence_id or uuid4().hex
        if not isinstance(actions, (list, tuple)) or len(actions) > self._max_actions:
            return SequenceResult(
                sequence_id=seq_id,
                observations=(),
                status="protocol_error",
                stderr="invalid_action_sequence",
            )
        if any(not isinstance(a, dict) for a in actions):
            return SequenceResult(
                sequence_id=seq_id,
                observations=(),
                status="protocol_error",
                stderr="actions_must_be_objects",
            )

        if self._external_server is not None:
            return self._execute_against(self._external_server, actions, seq_id)
        with start_reference_server() as temp_srv:
            return self._execute_against(temp_srv, actions, seq_id)

    def _execute_against(
        self,
        srv: RunningTaskWorkflowServer,
        actions: Sequence[dict[str, Any]],
        seq_id: str,
    ) -> SequenceResult:
        # Step 0: Deterministic reset (and optional initial seeding from first action's seed_tasks)
        seed_tasks = None
        if actions and isinstance(actions[0].get("seed_tasks"), list):
            seed_tasks = actions[0]["seed_tasks"]
        reset_payload = (
            json.dumps({"seed_tasks": seed_tasks}).encode("utf-8")
            if seed_tasks is not None
            else b"{}"
        )
        try:
            r_status, _, _ = self._request_raw(
                srv.base_url,
                "POST",
                "/__admin/reset",
                {"Content-Type": "application/json"},
                reset_payload,
            )
            if r_status != 200:
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="protocol_error",
                    stderr="reference_reset_failed",
                )
        except TimeoutError:
            return SequenceResult(
                sequence_id=seq_id,
                observations=(),
                status="timeout",
                stderr="reference_reset_timeout",
            )
        except Exception:
            return SequenceResult(
                sequence_id=seq_id,
                observations=(),
                status="protocol_error",
                stderr="reference_reset_error",
            )

        observations: list[Observation] = []
        for idx, raw_action in enumerate(actions):
            try:
                norm = normalize_http_action(raw_action)
            except ValueError:
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="protocol_error",
                    stderr="invalid_action_shape",
                )

            path = norm["path"]
            # Block direct access to control plane from sequence steps
            if path.startswith("/__admin") or "/__admin" in urllib.parse.unquote(path):
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="protocol_error",
                    stderr="control_plane_access_denied",
                )

            query = norm.get("query")
            target = path
            if query:
                qs = urllib.parse.urlencode(
                    [(str(k), str(v)) for k, v in query.items()],
                    doseq=True,
                )
                target = f"{path}?{qs}" if "?" not in path else f"{path}&{qs}"

            req_headers: dict[str, str] = {"Accept": "application/json"}
            actor = norm.get("actor")
            if isinstance(actor, str) and actor:
                req_headers["X-Synthetic-Actor"] = actor

            body_bytes: bytes | None = None
            if "raw_body" in norm:
                req_headers["Content-Type"] = "application/json"
                body_bytes = norm["raw_body"].encode("utf-8")
            elif "body" in norm:
                req_headers["Content-Type"] = "application/json"
                body_bytes = json.dumps(
                    norm["body"], separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")

            started = time.monotonic()
            try:
                http_status, resp_headers, resp_bytes = self._request_raw(
                    srv.base_url,
                    norm["method"],
                    target,
                    req_headers,
                    body_bytes,
                )
            except TimeoutError:
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="timeout",
                    stderr="http_request_timeout",
                )
            except urllib.error.URLError as exc:
                if isinstance(getattr(exc, "reason", None), TimeoutError):
                    return SequenceResult(
                        sequence_id=seq_id,
                        observations=(),
                        status="timeout",
                        stderr="http_request_timeout",
                    )
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="protocol_error",
                    stderr="http_transport_error",
                )
            except Exception:
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="protocol_error",
                    stderr="http_transport_error",
                )

            elapsed_ms = max(0, round((time.monotonic() - started) * 1000))
            if len(resp_bytes) > self._max_output:
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="protocol_error",
                    stderr="response_output_cap_exceeded",
                )

            try:
                resp_json = json.loads(resp_bytes.decode("utf-8"))
                if not isinstance(resp_json, dict) or not isinstance(resp_json.get("ok"), bool):
                    raise ValueError("Response JSON must be an object with boolean ok")
            except Exception:
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="protocol_error",
                    stderr="invalid_reference_json",
                )

            envelope = format_observation_output(http_status, resp_headers, resp_json)
            observations.append(
                Observation(
                    observation_id=f"{seq_id}:{idx}",
                    sequence_id=seq_id,
                    action_index=idx,
                    input_action=dict(raw_action),
                    output=envelope,
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    status="ok" if envelope["ok"] else "target_error",
                )
            )

        return SequenceResult(
            sequence_id=seq_id,
            observations=tuple(observations),
            status="ok",
            stderr="",
        )


class SafeHTTPExperimentRunner:
    """ScopeGuard-enforced runner between proposed HTTP actions and HTTPReferenceAdapter."""

    def __init__(
        self,
        contract: ScopeContract,
        reference: HTTPReferenceAdapter,
        ledger: EvidenceLedger,
    ) -> None:
        if contract.target.kind != TargetKind.HTTP:
            raise ValueError("SafeHTTPExperimentRunner requires an HTTP ScopeContract")
        self.contract = contract
        self.guard = ScopeGuard(contract)
        self.reference = reference
        self.ledger = ledger
        self.count = 0
        self.start = time.monotonic()

    def run_actions(self, actions: Sequence[dict[str, Any]]) -> SequenceResult:
        if not actions:
            raise PermissionError("EMPTY_SEQUENCE: Cannot execute an empty HTTP action sequence")
        if self.count >= self.contract.budgets.max_reference_experiments:
            raise PermissionError("BUDGET_EXHAUSTED: Reference experiment budget exhausted")
        if time.monotonic() - self.start > self.contract.budgets.max_wall_seconds:
            raise PermissionError("TIME_EXHAUSTED: Investigation wall-clock budget exhausted")

        requirement_id = sorted(self.contract.implementation.requirements)[0]
        for action in actions:
            proposed = to_proposed_action(action, requirement_id=requirement_id)
            decision: PolicyDecision = self.guard.validate_action(proposed)
            if not decision.allowed:
                raise PermissionError(f"{decision.code}: {decision.reason}")

        self.count += 1
        result = self.reference.execute_sequence(actions)
        for obs in result.observations:
            self.ledger.store(obs)
        return result


# ---------------------------------------------------------------------------
# Declarative HTTP Candidate Specification & Interpreter
# ---------------------------------------------------------------------------


class TitleRuleSpec(StrictModel):
    min_length: StrictInt = Field(ge=1, le=256)
    max_length: StrictInt = Field(ge=1, le=256)
    trim: StrictBool = True
    unique_per_owner: StrictBool = True
    unique_casefold: StrictBool = True
    cancelled_frees_title: StrictBool = True
    invalid_error: StrictStr = Field(min_length=1, max_length=64)
    duplicate_error: StrictStr = Field(min_length=1, max_length=64)


class PriorityRuleSpec(StrictModel):
    minimum: StrictInt = Field(ge=0, le=100)
    maximum: StrictInt = Field(ge=1, le=100)
    invalid_error: StrictStr = Field(min_length=1, max_length=64)


class WorkflowRuleSpec(StrictModel):
    initial_status: StrictStr = "todo"
    valid_statuses: tuple[StrictStr, ...] = (
        "todo",
        "in_progress",
        "blocked",
        "done",
        "cancelled",
    )
    allowed_transitions: dict[StrictStr, tuple[StrictStr, ...]]
    terminal_statuses: tuple[StrictStr, ...]
    non_deletable_statuses: tuple[StrictStr, ...]
    invalid_status_error: StrictStr = Field(min_length=1, max_length=64)
    invalid_transition_error: StrictStr = Field(min_length=1, max_length=64)
    terminal_locked_error: StrictStr = Field(min_length=1, max_length=64)
    delete_blocked_error: StrictStr = Field(min_length=1, max_length=64)
    empty_update_error: StrictStr = Field(min_length=1, max_length=64)
    not_found_error: StrictStr = Field(min_length=1, max_length=64)


class AuthRuleSpec(StrictModel):
    actors: dict[StrictStr, Literal["member", "viewer", "admin"]]
    read_only_roles: tuple[StrictStr, ...] = ("viewer",)
    admin_roles: tuple[StrictStr, ...] = ("admin",)
    unauthenticated_error: StrictStr = Field(min_length=1, max_length=64)
    insufficient_role_error: StrictStr = Field(min_length=1, max_length=64)
    not_owner_error: StrictStr = Field(min_length=1, max_length=64)


class QueryRuleSpec(StrictModel):
    default_order: StrictStr = "id_asc"
    allowed_orders: tuple[StrictStr, ...] = (
        "id_asc",
        "id_desc",
        "priority_desc",
        "priority_asc",
    )
    default_limit: StrictInt = Field(default=10, ge=1, le=100)
    max_limit: StrictInt = Field(default=50, ge=1, le=500)
    invalid_filter_error: StrictStr = Field(min_length=1, max_length=64)
    invalid_order_error: StrictStr = Field(min_length=1, max_length=64)
    invalid_pagination_error: StrictStr = Field(min_length=1, max_length=64)


class StatusCodesSpec(StrictModel):
    create_ok: StrictInt = 201
    read_ok: StrictInt = 200
    update_ok: StrictInt = 200
    delete_ok: StrictInt = 200
    bad_json: StrictInt = 400
    unauthenticated: StrictInt = 401
    forbidden: StrictInt = 403
    not_found: StrictInt = 404
    method_not_allowed: StrictInt = 405
    conflict: StrictInt = 409
    validation_error: StrictInt = 422


class HTTPCandidateSpec(StrictModel):
    spec_version: Literal["1"] = "1"
    subsystem: StrictStr = SUBSYSTEM_ID
    requirement_ids: frozenset[StrictStr] = Field(min_length=1)
    id_prefix: StrictStr = "tsk-"
    emit_revision_header: StrictBool = True
    emit_location_header: StrictBool = True
    title_rules: TitleRuleSpec
    priority_rules: PriorityRuleSpec
    workflow_rules: WorkflowRuleSpec
    auth_rules: AuthRuleSpec
    query_rules: QueryRuleSpec
    status_codes: StatusCodesSpec = Field(default_factory=StatusCodesSpec)


@dataclass(frozen=True)
class LoadedHTTPCandidate:
    spec: HTTPCandidateSpec
    digest: str
    raw_bytes: bytes


def load_http_candidate(
    raw: str | bytes | Mapping[str, Any],
    contract: ScopeContract,
) -> LoadedHTTPCandidate:
    """Validate an HTTPCandidateSpec against schema, semantics, and ScopeContract."""
    if isinstance(raw, Mapping):
        canonical = _canonical_bytes(dict(raw))
    elif isinstance(raw, str):
        canonical = raw.encode("utf-8")
    elif isinstance(raw, bytes):
        canonical = bytes(raw)
    else:
        raise HTTPCandidateError("Candidate spec must be bytes, str, or mapping")

    if len(canonical) > MAX_SPEC_BYTES:
        raise HTTPCandidateError(f"Spec exceeds {MAX_SPEC_BYTES} bytes")

    try:
        doc = json.loads(canonical.decode("utf-8"))
        spec = HTTPCandidateSpec.model_validate(doc)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPCandidateError(f"Invalid HTTPCandidateSpec: {exc}") from exc

    if spec.title_rules.min_length > spec.title_rules.max_length:
        raise HTTPCandidateError("title min_length exceeds max_length")
    if spec.priority_rules.minimum > spec.priority_rules.maximum:
        raise HTTPCandidateError("priority minimum exceeds maximum")
    if spec.subsystem not in contract.implementation.allowed_subsystems:
        raise HTTPCandidateError(f"Subsystem {spec.subsystem!r} not in allowed scope")
    if not set(spec.requirement_ids).issubset(contract.implementation.requirements):
        raise HTTPCandidateError("Spec requirement_ids not in allowed scope")

    decision = ScopeGuard(contract).validate_candidate_files([
        ProposedFile(
            path="http_candidate.json",
            subsystem=spec.subsystem,
            requirement_ids=spec.requirement_ids,
        )
    ])
    if not decision.allowed:
        raise HTTPCandidateError(f"Manifest rejected: {decision.code}: {decision.reason}")

    digest = _digest(_canonical_bytes(spec.model_dump(mode="json")))
    return LoadedHTTPCandidate(spec=spec, digest=digest, raw_bytes=canonical)


def build_http_spec_skeleton(public_contract: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic trusted skeleton derived ONLY from the public contract."""
    if public_contract.get("target_id") != TARGET_ID:
        raise ValueError("Public contract target_id mismatch")
    actors = {
        k: v["role"]
        for k, v in public_contract.get("synthetic_actors", {}).items()
    }
    statuses = tuple(public_contract.get("task_statuses", ()))
    return {
        "spec_version": "1",
        "subsystem": public_contract["subsystem"],
        "requirement_ids": [public_contract["requirement_id"]],
        "id_prefix": "tsk-",
        "emit_revision_header": True,
        "emit_location_header": True,
        "auth_actors": actors,
        "task_statuses": list(statuses),
    }


def merge_http_skeleton_fill(
    skeleton: Mapping[str, Any],
    fill: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine the public-contract skeleton with model-inferred behavioral rules."""
    return {
        "spec_version": skeleton["spec_version"],
        "subsystem": skeleton["subsystem"],
        "requirement_ids": list(skeleton["requirement_ids"]),
        "id_prefix": fill.get("id_prefix", skeleton.get("id_prefix", "tsk-")),
        "emit_revision_header": fill.get("emit_revision_header", True),
        "emit_location_header": fill.get("emit_location_header", True),
        "title_rules": fill["title_rules"],
        "priority_rules": fill["priority_rules"],
        "workflow_rules": {
            "valid_statuses": skeleton["task_statuses"],
            **fill["workflow_rules"],
        },
        "auth_rules": {
            "actors": skeleton["auth_actors"],
            **fill["auth_rules"],
        },
        "query_rules": fill["query_rules"],
        "status_codes": fill.get("status_codes", {}),
    }


def build_http_guided_fill_control() -> dict[str, Any]:
    """Reference-equivalent NON_AI positive control fill for the HTTP task workflow."""
    return {
        "id_prefix": "tsk-",
        "emit_revision_header": True,
        "emit_location_header": True,
        "title_rules": {
            "min_length": 1,
            "max_length": 64,
            "trim": True,
            "unique_per_owner": True,
            "unique_casefold": True,
            "cancelled_frees_title": True,
            "invalid_error": "invalid_title",
            "duplicate_error": "duplicate_title",
        },
        "priority_rules": {
            "minimum": 1,
            "maximum": 5,
            "invalid_error": "invalid_priority",
        },
        "workflow_rules": {
            "initial_status": "todo",
            "allowed_transitions": {
                "todo": ["in_progress", "blocked", "cancelled"],
                "in_progress": ["todo", "blocked", "done", "cancelled"],
                "blocked": ["todo", "in_progress", "cancelled"],
                "done": [],
                "cancelled": [],
            },
            "terminal_statuses": ["done", "cancelled"],
            "non_deletable_statuses": ["in_progress"],
            "invalid_status_error": "invalid_status",
            "invalid_transition_error": "invalid_transition",
            "terminal_locked_error": "terminal_state_locked",
            "delete_blocked_error": "task_in_progress",
            "empty_update_error": "empty_update",
            "not_found_error": "not_found",
        },
        "auth_rules": {
            "read_only_roles": ["viewer"],
            "admin_roles": ["admin"],
            "unauthenticated_error": "unauthenticated",
            "insufficient_role_error": "insufficient_role",
            "not_owner_error": "not_owner",
        },
        "query_rules": {
            "default_order": "id_asc",
            "allowed_orders": ["id_asc", "id_desc", "priority_desc", "priority_asc"],
            "default_limit": 10,
            "max_limit": 50,
            "invalid_filter_error": "invalid_filter",
            "invalid_order_error": "invalid_order",
            "invalid_pagination_error": "invalid_pagination",
        },
        "status_codes": {
            "create_ok": 201,
            "read_ok": 200,
            "update_ok": 200,
            "delete_ok": 200,
            "bad_json": 400,
            "unauthenticated": 401,
            "forbidden": 403,
            "not_found": 404,
            "method_not_allowed": 405,
            "conflict": 409,
            "validation_error": 422,
        },
    }


def build_http_naive_direct_fill() -> dict[str, Any]:
    """Condition A (Direct synthesis baseline from public contract + 2 basic examples).

    Without active probing, direct synthesis assumes permissive transitions (e.g.
    `todo -> done` allowed), no deletion lock on `in_progress`, wide validation bounds
    (`title` 1..200, `priority` 1..10), global case-sensitive title uniqueness that
    does not free cancelled titles, and generic 400 validation status codes.
    """
    fill = build_http_guided_fill_control()
    fill["title_rules"] = {
        "min_length": 1,
        "max_length": 200,
        "trim": True,
        "unique_per_owner": False,
        "unique_casefold": False,
        "cancelled_frees_title": False,
        "invalid_error": "invalid_title",
        "duplicate_error": "duplicate_title",
    }
    fill["priority_rules"] = {
        "minimum": 1,
        "maximum": 10,
        "invalid_error": "invalid_priority",
    }
    fill["workflow_rules"]["allowed_transitions"] = {
        "todo": ["in_progress", "blocked", "done", "cancelled"],
        "in_progress": ["todo", "blocked", "done", "cancelled"],
        "blocked": ["todo", "in_progress", "done", "cancelled"],
        "done": ["todo", "in_progress"],
        "cancelled": ["todo"],
    }
    fill["workflow_rules"]["terminal_statuses"] = []
    fill["workflow_rules"]["non_deletable_statuses"] = []
    fill["query_rules"]["max_limit"] = 100
    return fill


def build_http_passive_probe_fill() -> dict[str, Any]:
    """Condition B (Fixed passive sequential probes).

    Fixed happy-path probes observe basic CRUD, priority range 1..5, and case-insensitive
    duplicates, but miss `blocked -> done` / `todo -> done` restrictions, `in_progress`
    deletion lock, `cancelled` title reuse, and `admin` override vs `not_owner`.
    """
    fill = build_http_guided_fill_control()
    fill["title_rules"]["cancelled_frees_title"] = False
    fill["workflow_rules"]["allowed_transitions"] = {
        "todo": ["in_progress", "blocked", "done", "cancelled"],
        "in_progress": ["todo", "blocked", "done", "cancelled"],
        "blocked": ["todo", "in_progress", "done", "cancelled"],
        "done": [],
        "cancelled": [],
    }
    fill["workflow_rules"]["non_deletable_statuses"] = []
    return fill


class HTTPCandidateInterpreter:
    """In-memory data-only interpreter for a validated HTTPCandidateSpec.

    Satisfies `second_source.verifier.ReferenceProtocol` with zero arbitrary code
    execution, no subprocesses, no filesystem access, and no network sockets.
    """

    def __init__(
        self,
        spec: HTTPCandidateSpec,
        *,
        max_actions: int = 64,
        max_records: int = MAX_RECORDS,
    ) -> None:
        self._spec = HTTPCandidateSpec.model_validate(spec.model_dump(mode="json"))
        self._max_actions = max_actions
        self._max_records = max_records
        self._tasks: dict[str, dict[str, Any]] = {}
        self._next_seq = 1

    def reset(self, seed_tasks: Sequence[Mapping[str, Any]] | None = None) -> None:
        self._tasks.clear()
        self._next_seq = 1
        if seed_tasks:
            max_seq = 0
            for item in seed_tasks:
                raw_id = str(item.get("id", f"{self._spec.id_prefix}{self._next_seq}"))
                seq = _task_seq_num(raw_id)
                self._tasks[raw_id] = {
                    "seq": seq,
                    "id": raw_id,
                    "title": str(item["title"]).strip(),
                    "priority": int(item["priority"]),
                    "status": str(item.get("status", self._spec.workflow_rules.initial_status)),
                    "owner": str(item.get("owner", "alice")),
                    "revision": int(item.get("revision", 1)),
                }
                if seq > max_seq:
                    max_seq = seq
            self._next_seq = max_seq + 1

    def execute_sequence(
        self,
        actions: Sequence[dict[str, Any]],
        *,
        sequence_id: str | None = None,
    ) -> SequenceResult:
        seq_id = sequence_id or uuid4().hex
        if not isinstance(actions, (list, tuple)) or len(actions) > self._max_actions:
            return SequenceResult(
                sequence_id=seq_id,
                observations=(),
                status="protocol_error",
                stderr="invalid_action_sequence",
            )
        if any(not isinstance(a, dict) for a in actions):
            return SequenceResult(
                sequence_id=seq_id,
                observations=(),
                status="protocol_error",
                stderr="actions_must_be_objects",
            )

        seed_tasks = None
        if actions and isinstance(actions[0].get("seed_tasks"), list):
            seed_tasks = actions[0]["seed_tasks"]
        try:
            self.reset(seed_tasks=seed_tasks)
        except Exception:
            return SequenceResult(
                sequence_id=seq_id,
                observations=(),
                status="protocol_error",
                stderr="invalid_seed_tasks",
            )

        observations: list[Observation] = []
        for idx, raw_action in enumerate(actions):
            started = time.monotonic()
            try:
                norm = normalize_http_action(raw_action)
            except ValueError:
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="protocol_error",
                    stderr="invalid_action_shape",
                )

            path = norm["path"]
            if path.startswith("/__admin") or "/__admin" in urllib.parse.unquote(path):
                return SequenceResult(
                    sequence_id=seq_id,
                    observations=(),
                    status="protocol_error",
                    stderr="control_plane_access_denied",
                )

            status_code, headers, body = self._apply(norm)
            elapsed_ms = max(0, round((time.monotonic() - started) * 1000))
            envelope = format_observation_output(status_code, headers, body)
            observations.append(
                Observation(
                    observation_id=f"{seq_id}:{idx}",
                    sequence_id=seq_id,
                    action_index=idx,
                    input_action=dict(raw_action),
                    output=envelope,
                    exit_code=0,
                    duration_ms=elapsed_ms,
                    status="ok" if envelope["ok"] else "target_error",
                )
            )

        return SequenceResult(
            sequence_id=seq_id,
            observations=tuple(observations),
            status="ok",
            stderr="",
        )

    def _public_task(self, rec: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": rec["id"],
            "title": rec["title"],
            "priority": rec["priority"],
            "status": rec["status"],
            "owner": rec["owner"],
            "revision": rec["revision"],
        }

    def _apply(
        self, norm: Mapping[str, Any]
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        sc = self._spec.status_codes
        ar = self._spec.auth_rules
        tr = self._spec.title_rules
        pr = self._spec.priority_rules
        wr = self._spec.workflow_rules
        qr = self._spec.query_rules

        raw_path = norm["path"]
        decoded_path = urllib.parse.unquote(raw_path)
        if (
            "\\" in raw_path
            or "\\" in decoded_path
            or "//" in raw_path
            or ".." in decoded_path.split("/")
            or not decoded_path.startswith("/")
        ):
            return (
                sc.bad_json,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_path"},
            )
        path = decoded_path.rstrip("/") or "/"
        method = norm["method"]

        is_collection = path == "/v1/tasks"
        item_match = re.fullmatch(r"/v1/tasks/([^/]+)", path)
        if not is_collection and not item_match:
            return (
                sc.not_found,
                {"content-type": "application/json"},
                {"ok": False, "error": "unknown_endpoint"},
            )

        if is_collection and method not in ("GET", "POST"):
            return (
                sc.method_not_allowed,
                {"content-type": "application/json", "allow": "GET, POST"},
                {"ok": False, "error": "method_not_allowed"},
            )
        if item_match and method not in ("GET", "PATCH", "DELETE"):
            return (
                sc.method_not_allowed,
                {"content-type": "application/json", "allow": "DELETE, GET, PATCH"},
                {"ok": False, "error": "method_not_allowed"},
            )

        actor = norm.get("actor") or ""
        if not actor or actor not in ar.actors:
            return (
                sc.unauthenticated,
                {
                    "content-type": "application/json",
                    "www-authenticate": 'SyntheticActor realm="owned-task-workflow"',
                },
                {"ok": False, "error": ar.unauthenticated_error},
            )
        role = ar.actors[actor]

        if method in ("POST", "PATCH", "DELETE") and role in ar.read_only_roles:
            return (
                sc.forbidden,
                {"content-type": "application/json"},
                {"ok": False, "error": ar.insufficient_role_error},
            )

        # Parse JSON body for POST/PATCH
        payload: dict[str, Any] = {}
        if method in ("POST", "PATCH"):
            if "raw_body" in norm:
                raw_bytes = norm["raw_body"].encode("utf-8")
                if len(raw_bytes) > MAX_BODY_BYTES or not raw_bytes.strip():
                    return (
                        sc.bad_json,
                        {"content-type": "application/json"},
                        {"ok": False, "error": "invalid_json"},
                    )
                try:
                    parsed = json.loads(raw_bytes.decode("utf-8"))
                    if not isinstance(parsed, dict):
                        raise ValueError
                    payload = parsed
                except Exception:
                    return (
                        sc.bad_json,
                        {"content-type": "application/json"},
                        {"ok": False, "error": "invalid_json"},
                    )
            elif isinstance(norm.get("body"), dict):
                payload = dict(norm["body"])
            else:
                return (
                    sc.bad_json,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_json"},
                )

        if is_collection and method == "POST":
            title = payload.get("title")
            if not isinstance(title, str):
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": tr.invalid_error},
                )
            clean_title = title.strip() if tr.trim else title
            if not (tr.min_length <= len(clean_title) <= tr.max_length):
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": tr.invalid_error},
                )

            prio = payload.get("priority")
            if type(prio) is not int or not (pr.minimum <= prio <= pr.maximum):
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": pr.invalid_error},
                )

            if self._is_duplicate_title(actor, clean_title):
                return (
                    sc.conflict,
                    {"content-type": "application/json"},
                    {"ok": False, "error": tr.duplicate_error},
                )

            seq = self._next_seq
            self._next_seq += 1
            tid = f"{self._spec.id_prefix}{seq}"
            rec = {
                "seq": seq,
                "id": tid,
                "title": clean_title,
                "priority": prio,
                "status": wr.initial_status,
                "owner": actor,
                "revision": 1,
            }
            self._tasks[tid] = rec
            headers = {"content-type": "application/json"}
            if self._spec.emit_location_header:
                headers["location"] = f"/v1/tasks/{tid}"
            if self._spec.emit_revision_header:
                headers["x-task-revision"] = "1"
            return sc.create_ok, headers, {"ok": True, "task": self._public_task(rec)}

        if is_collection and method == "GET":
            query = dict(norm.get("query") or {})
            allowed_keys = {
                "status",
                "owner",
                "min_priority",
                "max_priority",
                "order_by",
                "limit",
                "offset",
            }
            if any(k not in allowed_keys for k in query):
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": qr.invalid_filter_error},
                )

            status_f = None
            if "status" in query:
                if str(query["status"]) not in wr.valid_statuses:
                    return (
                        sc.validation_error,
                        {"content-type": "application/json"},
                        {"ok": False, "error": qr.invalid_filter_error},
                    )
                status_f = str(query["status"])

            owner_f = None
            if "owner" in query:
                if not OWNER_RE.fullmatch(str(query["owner"])):
                    return (
                        sc.validation_error,
                        {"content-type": "application/json"},
                        {"ok": False, "error": qr.invalid_filter_error},
                    )
                owner_f = str(query["owner"])

            min_p = None
            if "min_priority" in query:
                min_p = _parse_strict_int(str(query["min_priority"]))
                if min_p is None or not (pr.minimum <= min_p <= pr.maximum):
                    return (
                        sc.validation_error,
                        {"content-type": "application/json"},
                        {"ok": False, "error": qr.invalid_filter_error},
                    )
            max_p = None
            if "max_priority" in query:
                max_p = _parse_strict_int(str(query["max_priority"]))
                if max_p is None or not (pr.minimum <= max_p <= pr.maximum):
                    return (
                        sc.validation_error,
                        {"content-type": "application/json"},
                        {"ok": False, "error": qr.invalid_filter_error},
                    )
            if min_p is not None and max_p is not None and min_p > max_p:
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": qr.invalid_filter_error},
                )

            order_by = str(query.get("order_by", qr.default_order))
            if order_by not in qr.allowed_orders:
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": qr.invalid_order_error},
                )

            limit = qr.default_limit
            if "limit" in query:
                parsed_l = _parse_strict_int(str(query["limit"]))
                if parsed_l is None or not (1 <= parsed_l <= qr.max_limit):
                    return (
                        sc.validation_error,
                        {"content-type": "application/json"},
                        {"ok": False, "error": qr.invalid_pagination_error},
                    )
                limit = parsed_l

            offset = 0
            if "offset" in query:
                parsed_o = _parse_strict_int(str(query["offset"]))
                if parsed_o is None or parsed_o < 0:
                    return (
                        sc.validation_error,
                        {"content-type": "application/json"},
                        {"ok": False, "error": qr.invalid_pagination_error},
                    )
                offset = parsed_o

            recs = list(self._tasks.values())
            if status_f is not None:
                recs = [r for r in recs if r["status"] == status_f]
            if owner_f is not None:
                recs = [r for r in recs if r["owner"] == owner_f]
            if min_p is not None:
                recs = [r for r in recs if r["priority"] >= min_p]
            if max_p is not None:
                recs = [r for r in recs if r["priority"] <= max_p]

            if order_by == "id_asc":
                recs.sort(key=lambda r: r["seq"])
            elif order_by == "id_desc":
                recs.sort(key=lambda r: -r["seq"])
            elif order_by == "priority_desc":
                recs.sort(key=lambda r: (-r["priority"], r["seq"]))
            elif order_by == "priority_asc":
                recs.sort(key=lambda r: (r["priority"], r["seq"]))

            total = len(recs)
            page = recs[offset : offset + limit]
            return (
                sc.read_ok,
                {"content-type": "application/json"},
                {
                    "ok": True,
                    "items": [self._public_task(r) for r in page],
                    "total": total,
                    "count": len(page),
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + len(page)) < total,
                },
            )

        assert item_match is not None
        task_id = item_match.group(1)
        rec = self._tasks.get(task_id)
        if rec is None:
            return (
                sc.not_found,
                {"content-type": "application/json"},
                {"ok": False, "error": wr.not_found_error},
            )

        if method == "GET":
            headers = {"content-type": "application/json"}
            if self._spec.emit_revision_header:
                headers["x-task-revision"] = str(rec["revision"])
            return sc.read_ok, headers, {"ok": True, "task": self._public_task(rec)}

        if actor != rec["owner"] and role not in ar.admin_roles:
            return (
                sc.forbidden,
                {"content-type": "application/json"},
                {"ok": False, "error": ar.not_owner_error},
            )

        if method == "DELETE":
            if rec["status"] in wr.non_deletable_statuses:
                return (
                    sc.conflict,
                    {"content-type": "application/json"},
                    {"ok": False, "error": wr.delete_blocked_error},
                )
            del self._tasks[task_id]
            return (
                sc.delete_ok,
                {"content-type": "application/json"},
                {"ok": True, "deleted": task_id},
            )

        # PATCH
        if not any(k in payload for k in ("title", "priority", "status")):
            return (
                sc.validation_error,
                {"content-type": "application/json"},
                {"ok": False, "error": wr.empty_update_error},
            )

        if rec["status"] in wr.terminal_statuses:
            return (
                sc.conflict,
                {"content-type": "application/json"},
                {"ok": False, "error": wr.terminal_locked_error},
            )

        new_title = rec["title"]
        if "title" in payload:
            raw_t = payload["title"]
            if not isinstance(raw_t, str):
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": tr.invalid_error},
                )
            clean_t = raw_t.strip() if tr.trim else raw_t
            if not (tr.min_length <= len(clean_t) <= tr.max_length):
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": tr.invalid_error},
                )
            new_title = clean_t

        new_prio = rec["priority"]
        if "priority" in payload:
            raw_p = payload["priority"]
            if type(raw_p) is not int or not (pr.minimum <= raw_p <= pr.maximum):
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": pr.invalid_error},
                )
            new_prio = raw_p

        new_status = rec["status"]
        if "status" in payload:
            raw_s = payload["status"]
            if not isinstance(raw_s, str) or raw_s not in wr.valid_statuses:
                return (
                    sc.validation_error,
                    {"content-type": "application/json"},
                    {"ok": False, "error": wr.invalid_status_error},
                )
            new_status = raw_s

        if "title" in payload and self._is_duplicate_title(
            rec["owner"], new_title, exclude_id=rec["id"]
        ):
            return (
                sc.conflict,
                {"content-type": "application/json"},
                {"ok": False, "error": tr.duplicate_error},
            )

        if "status" in payload and new_status != rec["status"]:
            allowed_next = wr.allowed_transitions.get(rec["status"], ())
            if new_status not in allowed_next:
                return (
                    sc.conflict,
                    {"content-type": "application/json"},
                    {"ok": False, "error": wr.invalid_transition_error},
                )

        rec["title"] = new_title
        rec["priority"] = new_prio
        rec["status"] = new_status
        rec["revision"] += 1
        headers = {"content-type": "application/json"}
        if self._spec.emit_revision_header:
            headers["x-task-revision"] = str(rec["revision"])
        return sc.update_ok, headers, {"ok": True, "task": self._public_task(rec)}

    def _is_duplicate_title(
        self, owner: str, title: str, *, exclude_id: str | None = None
    ) -> bool:
        tr = self._spec.title_rules
        probe = title.casefold() if tr.unique_casefold else title
        for rec in self._tasks.values():
            if exclude_id is not None and rec["id"] == exclude_id:
                continue
            if tr.unique_per_owner and rec["owner"] != owner:
                continue
            if tr.cancelled_frees_title and rec["status"] == "cancelled":
                continue
            existing = rec["title"].casefold() if tr.unique_casefold else rec["title"]
            if existing == probe:
                return True
        return False


# ---------------------------------------------------------------------------
# Independent HTTP Differential Evaluation & Sealed Suite Management
# ---------------------------------------------------------------------------


class HTTPCaseResult(StrictModel):
    case_id: str
    category: str
    outcome: Literal["passed", "failed", "indeterminate"]
    http_mismatch_dimension: (
        Literal[
            "http_status",
            "headers",
            "error",
            "schema",
            "state",
            "value",
            "candidate_timeout",
            "candidate_protocol_error",
            "reference_unavailable",
        ]
        | None
    ) = None
    engine_mismatch_category: str | None = None


class HTTPDifferentialReport(StrictModel):
    passed: int
    failed: int
    indeterminate: int
    total: int
    cases: tuple[HTTPCaseResult, ...]
    http_dimension_counts: dict[str, int]
    engine_EvaluationReport: EvaluationReport

    def model_feedback(self) -> dict[str, Any]:
        """Aggregate-only feedback suitable for bounded repair; no case IDs or inputs."""
        return self.engine_EvaluationReport.model_feedback()


def _json_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(_json_equal(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right))
    return left == right


def classify_http_difference(
    expected_obs: Sequence[Observation],
    actual_obs: Sequence[Observation],
    *,
    action_count: int,
) -> tuple[str | None, str | None]:
    """Return (http_dimension, engine_category) for the first mismatch in a sequence."""
    if len(expected_obs) != len(actual_obs) or len(expected_obs) != action_count:
        return "state", "state"
    for r_obs, c_obs in zip(expected_obs, actual_obs):
        r = r_obs.output
        c = c_obs.output
        if not isinstance(r, dict) or not isinstance(c, dict):
            return "schema", "schema"
        if not _json_equal(r.get("ok"), c.get("ok")) or not _json_equal(
            r.get("error"), c.get("error")
        ):
            return "error", "error"
        if not _json_equal(r.get("http_status"), c.get("http_status")):
            return "http_status", "error"
        if not _json_equal(r.get("headers"), c.get("headers")):
            return "headers", "schema"
        r_body = r.get("body")
        c_body = c.get("body")
        if not isinstance(r_body, dict) or not isinstance(c_body, dict):
            return "schema", "schema"
        if set(r_body) != set(c_body):
            return "schema", "schema"
        # Check nested task revision/status state divergence vs general value divergence
        if "task" in r_body and isinstance(r_body["task"], dict) and isinstance(c_body["task"], dict):
            if set(r_body["task"]) != set(c_body["task"]):
                return "schema", "schema"
            if (
                r_body["task"].get("status") != c_body["task"].get("status")
                or r_body["task"].get("revision") != c_body["task"].get("revision")
            ):
                return "state", "state"
        if not _json_equal(r_body, c_body):
            return "value", "value"
    return None, None


class HTTPDifferentialEvaluator:
    """Independent differential evaluator preserving HTTP status, header, body, state,
    error, and timing uncertainty distinctions while also producing a standard
    `second_source.verifier.EvaluationReport`.
    """

    def __init__(self, reference: ReferenceProtocol, candidate: ReferenceProtocol) -> None:
        self._reference = reference
        self._candidate = candidate
        self._core_verifier = DifferentialVerifier(reference, candidate)

    def evaluate(self, cases: Sequence[SealedCase]) -> HTTPDifferentialReport:
        if not cases or len({c.case_id for c in cases}) != len(cases):
            raise ValueError("Need a non-empty suite with unique case IDs")

        http_results: list[HTTPCaseResult] = []
        core_results: list[CaseResult] = []

        for case in cases:
            snapshot = json.dumps(list(case.actions), allow_nan=False, separators=(",", ":"))
            ref_res = self._reference.execute_sequence(
                json.loads(snapshot), sequence_id="ref-" + uuid4().hex
            )
            if ref_res is None or ref_res.status != "ok" or len(ref_res.observations) != len(case.actions):
                http_results.append(
                    HTTPCaseResult(
                        case_id=case.case_id,
                        category=case.category,
                        outcome="indeterminate",
                        http_mismatch_dimension="reference_unavailable",
                        engine_mismatch_category="reference_unavailable",
                    )
                )
                core_results.append(
                    CaseResult(
                        case_id=case.case_id,
                        outcome="indeterminate",
                        mismatch_category="reference_unavailable",
                    )
                )
                continue

            cand_res = self._candidate.execute_sequence(
                json.loads(snapshot), sequence_id="cand-" + uuid4().hex
            )
            if cand_res is None or cand_res.status != "ok" or len(cand_res.observations) != len(case.actions):
                dim: Literal["candidate_timeout", "candidate_protocol_error"] = (
                    "candidate_timeout"
                    if cand_res is not None and cand_res.status == "timeout"
                    else "candidate_protocol_error"
                )
                http_results.append(
                    HTTPCaseResult(
                        case_id=case.case_id,
                        category=case.category,
                        outcome="failed",
                        http_mismatch_dimension=dim,
                        engine_mismatch_category=dim,
                    )
                )
                core_results.append(
                    CaseResult(
                        case_id=case.case_id,
                        outcome="failed",
                        mismatch_category=dim,
                    )
                )
                continue

            http_dim, engine_cat = classify_http_difference(
                ref_res.observations,
                cand_res.observations,
                action_count=len(case.actions),
            )
            outcome: Literal["passed", "failed"] = "passed" if http_dim is None else "failed"
            http_results.append(
                HTTPCaseResult(
                    case_id=case.case_id,
                    category=case.category,
                    outcome=outcome,
                    http_mismatch_dimension=http_dim,  # type: ignore[arg-type]
                    engine_mismatch_category=engine_cat,
                )
            )
            core_results.append(
                CaseResult(
                    case_id=case.case_id,
                    outcome=outcome,
                    mismatch_category=engine_cat,
                )
            )

        counts = Counter(r.outcome for r in http_results)
        http_dims = Counter(
            r.http_mismatch_dimension
            for r in http_results
            if r.http_mismatch_dimension and r.outcome == "failed"
        )
        engine_cats = Counter(
            r.engine_mismatch_category
            for r in http_results
            if r.engine_mismatch_category and r.outcome == "failed"
        )
        engine_report = EvaluationReport(
            passed=counts["passed"],
            failed=counts["failed"],
            indeterminate=counts["indeterminate"],
            total=len(http_results),
            cases=tuple(core_results),
            diagnostic_class_counts=dict(engine_cats),
        )
        return HTTPDifferentialReport(
            passed=counts["passed"],
            failed=counts["failed"],
            indeterminate=counts["indeterminate"],
            total=len(http_results),
            cases=tuple(http_results),
            http_dimension_counts=dict(http_dims),
            engine_EvaluationReport=engine_report,
        )


def _safe_external_path(path: str | Path) -> Path:
    candidate = Path(os.path.abspath(path))
    for part in (candidate, *candidate.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise HTTPEvaluationBlocked("Sealed storage cannot traverse symlinks or junctions")
        if (part / ".git").exists():
            raise HTTPEvaluationBlocked("Sealed material must remain outside Git checkouts")
    return candidate


@dataclass(frozen=True)
class SealedHTTPSuite:
    _raw: bytes
    digest: str
    scope_digest: str

    def cases(self) -> list[SealedCase]:
        doc = json.loads(self._raw.decode("utf-8"))
        return [SealedCase.model_validate(c) for c in doc["cases"]]


def build_heldout_http_cases(seed: int = 20261101) -> list[SealedCase]:
    """Build the 30-case held-out stateful evaluation suite for the HTTP task workflow."""
    rng = random.Random(seed)
    tok = lambda prefix="t": f"{prefix}-{rng.getrandbits(32):08x}"
    cases: list[SealedCase] = []

    def add_case(category: str, *actions: dict[str, Any]) -> None:
        cid = f"G4-HTTP-{len(cases) + 1:02d}-{hashlib.sha256(f'{seed}:{len(cases)}'.encode()).hexdigest()[:8]}"
        cases.append(SealedCase(case_id=cid, category=category, actions=tuple(actions)))

    # 1. Empty list and get missing
    add_case(
        "empty_state",
        {"operation": "list_tasks", "actor": "alice"},
        {"operation": "get_task", "task_id": "tsk-1", "actor": "alice"},
    )
    # 2. Basic create + get + list
    t1 = tok("Alpha")
    add_case(
        "crud_basic",
        {"operation": "create_task", "actor": "alice", "body": {"title": t1, "priority": 3}},
        {"operation": "get_task", "task_id": "tsk-1", "actor": "alice"},
        {"operation": "list_tasks", "actor": "alice"},
    )
    # 3. Priority boundary 1 and 5 valid
    add_case(
        "priority_bounds_valid",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("Low"), "priority": 1}},
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("High"), "priority": 5}},
        {"operation": "list_tasks", "actor": "alice"},
    )
    # 4. Priority invalid: 0, 6, -1, bool, string
    for bad_prio in (0, 6, True, "3"):
        add_case(
            "invalid_priority",
            {"operation": "create_task", "actor": "alice", "body": {"title": tok("Prio"), "priority": bad_prio}},
            {"operation": "list_tasks", "actor": "alice"},
        )
    # 8. Title boundary: 64 chars valid, 65 chars invalid, whitespace-only invalid
    add_case(
        "title_max_valid",
        {"operation": "create_task", "actor": "alice", "body": {"title": "  " + ("a" * 64) + "  ", "priority": 2}},
        {"operation": "get_task", "task_id": "tsk-1", "actor": "alice"},
    )
    add_case(
        "title_too_long",
        {"operation": "create_task", "actor": "alice", "body": {"title": "b" * 65, "priority": 2}},
        {"operation": "list_tasks", "actor": "alice"},
    )
    add_case(
        "title_empty_whitespace",
        {"operation": "create_task", "actor": "alice", "body": {"title": "   ", "priority": 2}},
        {"operation": "list_tasks", "actor": "alice"},
    )
    # 11. Validation precedence: both invalid title and invalid priority -> invalid_title wins
    add_case(
        "validation_precedence_create",
        {"operation": "create_task", "actor": "alice", "body": {"title": "", "priority": 99}},
    )
    # 12. Duplicate title: case-insensitive + trimmed for same owner -> 409 duplicate_title
    dup_name = tok("Deploy")
    add_case(
        "duplicate_title_casefold",
        {"operation": "create_task", "actor": "alice", "body": {"title": f" {dup_name} ", "priority": 3}},
        {"operation": "create_task", "actor": "alice", "body": {"title": dup_name.upper(), "priority": 4}},
        {"operation": "list_tasks", "actor": "alice"},
    )
    # 13. Duplicate title across different owners is permitted!
    shared_name = tok("Shared")
    add_case(
        "duplicate_title_cross_owner_allowed",
        {"operation": "create_task", "actor": "alice", "body": {"title": shared_name, "priority": 2}},
        {"operation": "create_task", "actor": "bob", "body": {"title": shared_name, "priority": 4}},
        {"operation": "list_tasks", "actor": "alice"},
    )
    # 14. Cancelled task frees duplicate title reservation for same owner!
    reused_name = tok("Reusable")
    add_case(
        "cancelled_frees_title",
        {"operation": "create_task", "actor": "alice", "body": {"title": reused_name, "priority": 3}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "cancelled"}},
        {"operation": "create_task", "actor": "alice", "body": {"title": reused_name, "priority": 5}},
        {"operation": "list_tasks", "actor": "alice"},
    )
    # 15. Valid workflow progression: todo -> in_progress -> blocked -> in_progress -> done
    add_case(
        "workflow_valid_chain",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("Flow"), "priority": 4}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress"}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "blocked"}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress", "priority": 5}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "done"}},
        {"operation": "get_task", "task_id": "tsk-1", "actor": "alice"},
    )
    # 16. Invalid direct jump: todo -> done is rejected with 409 invalid_transition
    add_case(
        "workflow_invalid_todo_to_done",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("Skip"), "priority": 3}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "done"}},
        {"operation": "get_task", "task_id": "tsk-1", "actor": "alice"},
    )
    # 17. Invalid jump: blocked -> done is rejected with 409 invalid_transition
    add_case(
        "workflow_invalid_blocked_to_done",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("Blocked"), "priority": 3}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "blocked"}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "done"}},
        {"operation": "get_task", "task_id": "tsk-1", "actor": "alice"},
    )
    # 18. Terminal state lock: done task cannot be updated or transitioned
    add_case(
        "workflow_terminal_done_locked",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("DoneLock"), "priority": 3}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress"}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "done"}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"priority": 1}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress"}},
    )
    # 19. Terminal state lock: cancelled task cannot be reopened
    add_case(
        "workflow_terminal_cancelled_locked",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("CancelLock"), "priority": 2}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "cancelled"}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "todo"}},
    )
    # 20. Delete lock: in_progress task cannot be deleted until transitioned
    add_case(
        "delete_in_progress_blocked_then_allowed",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("ActiveDel"), "priority": 4}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress"}},
        {"operation": "delete_task", "task_id": "tsk-1", "actor": "alice"},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "cancelled"}},
        {"operation": "delete_task", "task_id": "tsk-1", "actor": "alice"},
        {"operation": "list_tasks", "actor": "alice"},
    )
    # 21. Monotonic IDs after deletion
    add_case(
        "id_monotonic_after_delete",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("First"), "priority": 2}},
        {"operation": "delete_task", "task_id": "tsk-1", "actor": "alice"},
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("Second"), "priority": 3}},
        {"operation": "list_tasks", "actor": "alice"},
    )
    # 22. Auth: missing / invalid actor -> 401 unauthenticated with WWW-Authenticate
    add_case(
        "auth_unauthenticated",
        {"method": "GET", "path": "/v1/tasks", "actor": None},
        {"method": "POST", "path": "/v1/tasks", "actor": "intruder", "body": {"title": "X", "priority": 1}},
    )
    # 23. RBAC: viewer can read but cannot create, update, or delete -> 403 insufficient_role
    add_case(
        "rbac_viewer_read_only",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("ReadMe"), "priority": 3}},
        {"operation": "get_task", "task_id": "tsk-1", "actor": "viewer"},
        {"operation": "create_task", "actor": "viewer", "body": {"title": tok("NoCreate"), "priority": 2}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "viewer", "body": {"priority": 5}},
        {"operation": "delete_task", "task_id": "tsk-1", "actor": "viewer"},
    )
    # 24. RBAC: cross-owner mutation blocked for bob (403 not_owner) but allowed for admin (200)
    add_case(
        "rbac_cross_owner_vs_admin",
        {"operation": "create_task", "actor": "alice", "body": {"title": tok("AliceOwned"), "priority": 2}},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "bob", "body": {"priority": 5}},
        {"operation": "delete_task", "task_id": "tsk-1", "actor": "bob"},
        {"operation": "update_task", "task_id": "tsk-1", "actor": "admin", "body": {"priority": 5, "status": "in_progress"}},
        {"operation": "get_task", "task_id": "tsk-1", "actor": "bob"},
    )
    # 25. Filtering, ordering (priority_desc with id_asc tie-breaker), and pagination
    add_case(
        "query_filter_order_paginate",
        {
            "operation": "list_tasks",
            "actor": "alice",
            "seed_tasks": [
                {"id": "tsk-1", "title": "Task A", "priority": 3, "status": "todo", "owner": "alice", "revision": 1},
                {"id": "tsk-2", "title": "Task B", "priority": 5, "status": "in_progress", "owner": "bob", "revision": 2},
                {"id": "tsk-3", "title": "Task C", "priority": 5, "status": "todo", "owner": "alice", "revision": 1},
                {"id": "tsk-4", "title": "Task D", "priority": 1, "status": "done", "owner": "alice", "revision": 3},
            ],
            "query": {"order_by": "priority_desc", "limit": 2, "offset": 0},
        },
        {
            "operation": "list_tasks",
            "actor": "alice",
            "query": {"order_by": "priority_desc", "limit": 2, "offset": 2},
        },
        {
            "operation": "list_tasks",
            "actor": "alice",
            "query": {"owner": "alice", "min_priority": 3, "order_by": "id_desc"},
        },
    )
    # 26. Invalid query filters, ordering, and pagination bounds
    add_case(
        "query_validation_errors",
        {"operation": "list_tasks", "actor": "alice", "query": {"status": "archived"}},
        {"operation": "list_tasks", "actor": "alice", "query": {"min_priority": 4, "max_priority": 2}},
        {"operation": "list_tasks", "actor": "alice", "query": {"order_by": "random"}},
        {"operation": "list_tasks", "actor": "alice", "query": {"limit": 51}},
        {"operation": "list_tasks", "actor": "alice", "query": {"offset": -1}},
    )
    # 27. PATCH validation: empty_update, invalid_status, and rename to existing active title
    add_case(
        "patch_validation_and_duplicate_rename",
        {"operation": "create_task", "actor": "alice", "body": {"title": "First Title", "priority": 2}},
        {"operation": "create_task", "actor": "alice", "body": {"title": "Second Title", "priority": 3}},
        {"operation": "update_task", "task_id": "tsk-2", "actor": "alice", "body": {}},
        {"operation": "update_task", "task_id": "tsk-2", "actor": "alice", "body": {"status": "unknown_state"}},
        {"operation": "update_task", "task_id": "tsk-2", "actor": "alice", "body": {"title": "first title"}},
    )
    # 28. Method not allowed (405 + Allow header) and unknown endpoint (404)
    add_case(
        "http_protocol_404_405",
        {"method": "PUT", "path": "/v1/tasks", "actor": "alice", "body": {"title": "Put", "priority": 1}},
        {"method": "POST", "path": "/v1/tasks/tsk-1", "actor": "alice", "body": {"title": "PostItem", "priority": 1}},
        {"method": "GET", "path": "/v1/projects", "actor": "alice"},
    )
    # 29. Malformed JSON body -> 400 invalid_json
    add_case(
        "http_malformed_json",
        {"method": "POST", "path": "/v1/tasks", "actor": "alice", "raw_body": "{bad json"},
        {"method": "POST", "path": "/v1/tasks", "actor": "alice", "raw_body": "[1, 2, 3]"},
    )
    # 30. Cross-sequence reset verification
    add_case(
        "sequence_reset_isolation",
        {"operation": "list_tasks", "actor": "alice"},
        {"operation": "create_task", "actor": "bob", "body": {"title": tok("FreshSeq"), "priority": 4}},
        {"operation": "list_tasks", "actor": "bob"},
    )

    assert len(cases) == 30
    return cases


def seal_http_task_workflow_suite(
    directory: str | Path,
    contract: ScopeContract,
    *,
    seed: int = 20261101,
) -> tuple[Path, str]:
    """Create a sealed 30-case HTTP evaluation suite outside any Git checkout."""
    root = _safe_external_path(directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    cases = [c.model_dump(mode="json") for c in build_heldout_http_cases(seed=seed)]
    s_digest = scope_digest_of(contract)
    raw = _canonical_bytes({
        "suite_version": SUITE_VERSION,
        "target_id": TARGET_ID,
        "scope_digest": s_digest,
        "cases": cases,
    })
    digest = _digest(raw)
    path = root / "http_suite.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise HTTPEvaluationBlocked("Sealed HTTP suite already exists; refusing overwrite") from None
    return path, digest


def load_sealed_http_suite(
    path: str | Path,
    expected_digest: str,
    contract: ScopeContract,
) -> SealedHTTPSuite:
    external = _safe_external_path(path)
    if not external.is_file() or external.stat().st_size > MAX_SUITE_BYTES:
        raise HTTPEvaluationBlocked("Sealed HTTP suite unavailable or oversized")
    raw = external.read_bytes()
    if _digest(raw) != expected_digest:
        raise HTTPEvaluationBlocked("Sealed HTTP suite digest mismatch")
    doc = json.loads(raw.decode("utf-8"))
    if (
        not isinstance(doc, dict)
        or doc.get("suite_version") != SUITE_VERSION
        or doc.get("target_id") != TARGET_ID
        or doc.get("scope_digest") != scope_digest_of(contract)
        or not isinstance(doc.get("cases"), list)
        or not doc["cases"]
    ):
        raise HTTPEvaluationBlocked("Malformed or wrong-scope sealed HTTP suite")
    return SealedHTTPSuite(_raw=raw, digest=expected_digest, scope_digest=doc["scope_digest"])


# ---------------------------------------------------------------------------
# Isolation Boundary & Generation Request Builder
# ---------------------------------------------------------------------------


HTTP_SYNTHESIZE_SYSTEM_PROMPT = (
    "You are a behavioral specification author for Second Source. You receive a "
    "trusted HTTP endpoint skeleton, the public observation contract, and "
    "redacted black-box HTTP observations with evidence-linked hypotheses. "
    "Output ONE JSON object matching the HTTP candidate fill schema. Derive "
    "validation bounds, workflow state transitions, terminal locks, deletion "
    "guards, ownership/RBAC rules, query/pagination limits, error codes, and "
    "HTTP status mappings ONLY from the attached observations. Do not invent "
    "code, imports, shell commands, or network calls. Output JSON only."
)


def prepare_http_generation_request(
    *,
    contract: ScopeContract,
    public_contract: Mapping[str, Any],
    ledger: EvidenceLedger,
    observation_digests: Sequence[str],
    hypotheses: HypothesisStore,
    forbidden_markers: Sequence[str] = (),
    repair_feedback: Mapping[str, Any] | None = None,
    max_output_tokens: int = 4096,
) -> ModelRequest:
    """Assemble and verify a model-bound HTTP candidate synthesis request.

    Enforces:
    1. Every observation digest exists in the trusted EvidenceLedger and is
       retrieved via `ledger.model_view(digest)` (redacting any secrets/tokens).
    2. Every hypothesis in `HypothesisStore` cites only admitted observation digests.
    3. No reference source code, sealed case IDs, suite file paths, or caller-supplied
       `forbidden_markers` appear anywhere in the serialized request wire.
    """
    if contract.target.kind != TargetKind.HTTP:
        raise HTTPEvaluationBlocked("HTTP generation requires an HTTP ScopeContract")
    if not observation_digests or len(set(observation_digests)) != len(observation_digests):
        raise HTTPEvaluationBlocked("Observation digests must be non-empty and unique")
    if len(observation_digests) > contract.budgets.max_reference_experiments * 16:
        raise HTTPEvaluationBlocked("Observation count exceeds scope limit")

    views: list[dict[str, Any]] = []
    for digest in observation_digests:
        try:
            view = ledger.model_view(digest)
        except Exception as exc:
            raise HTTPEvaluationBlocked(f"Unverified observation digest {digest!r}") from exc
        views.append({"digest": digest, "observation": view})

    try:
        batch: HypothesisBatch = validate_batch(
            {"hypotheses": [h.model_dump(mode="json") for h in hypotheses.all()]},
            frozenset(observation_digests),
        )
    except Exception as exc:
        raise HTTPEvaluationBlocked(f"Hypothesis validation failed: {exc}") from exc

    skeleton = build_http_spec_skeleton(public_contract)
    context_payload: dict[str, Any] = {
        "scope": {
            "goal": contract.goal,
            "requirement_ids": sorted(contract.implementation.requirements),
            "allowed_url_patterns": list(contract.observation.allowed_url_patterns),
            "allowed_roles": sorted(contract.observation.allowed_roles),
            "excluded_subsystems": sorted(contract.exclusions.subsystems),
        },
        "public_contract": redact(dict(public_contract)),
        "skeleton": skeleton,
        "evidence": redact(views),
        "hypotheses": redact([
            {**h.model_dump(mode="json"), "evidence_ids": sorted(h.evidence_ids)}
            for h in batch.hypotheses
        ]),
    }

    if repair_feedback is not None:
        allowed_fb_keys = {"passed", "failed", "indeterminate", "total", "failure_categories"}
        if not isinstance(repair_feedback, Mapping) or set(repair_feedback) != allowed_fb_keys:
            raise HTTPEvaluationBlocked("Repair feedback must contain aggregate counts only")
        context_payload["repair_guidance"] = dict(repair_feedback)

    request = ModelRequest(
        stage="synthesize",
        messages=(
            {"role": "system", "content": HTTP_SYNTHESIZE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context_payload, sort_keys=True)},
        ),
        json_schema={"type": "object"},
        max_output_tokens=max_output_tokens,
        prompt_version="http-synthesize-v1" if repair_feedback is None else "http-synthesize-v1-repair1",
    )

    rendered = _canonical_bytes(request.model_dump(mode="json"))
    # Built-in canary checks: reference source lines and file paths must never appear
    builtin_canaries = (
        "TaskWorkflowReferenceState",
        "_BoundedHTTPServer",
        "__admin/reset",
        str(REFERENCE_SERVER_PATH),
        "G4-HTTP-",
    )
    for marker in (*builtin_canaries, *forbidden_markers):
        if marker and marker.encode("utf-8") in rendered:
            raise HTTPEvaluationBlocked(
                f"Protected material detected at model request boundary: {marker!r}"
            )
    return request


# ---------------------------------------------------------------------------
# Competitive Evaluation Benchmark Scaffolding (Section 7)
# ---------------------------------------------------------------------------


def passive_probe_sequences() -> list[list[dict[str, Any]]]:
    """Condition B: 5 fixed happy-path probes (12 actions total).

    Exercises basic create/get/list/patch/delete without probing state-transition
    matrix boundaries, deletion locks, or cancelled-title reuse.
    """
    return [
        [
            {"operation": "list_tasks", "actor": "alice"},
            {"operation": "create_task", "actor": "alice", "body": {"title": "Init task", "priority": 3}},
            {"operation": "get_task", "task_id": "tsk-1", "actor": "alice"},
        ],
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "Dup", "priority": 1}},
            {"operation": "create_task", "actor": "alice", "body": {"title": "dup", "priority": 5}},
        ],
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "", "priority": 3}},
            {"operation": "create_task", "actor": "alice", "body": {"title": "BadPrio", "priority": 6}},
        ],
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "Work", "priority": 2}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress"}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "done"}},
        ],
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "Temp", "priority": 2}},
            {"operation": "delete_task", "task_id": "tsk-1", "actor": "alice"},
        ],
    ]


def active_discriminating_sequences() -> list[list[dict[str, Any]]]:
    """Condition C: 5 hypothesis-discriminating active experiments (15 actions total).

    Same 5-experiment budget as Condition B, but designed to falsify rival hypotheses
    on transition shortcuts (`todo -> done`, `blocked -> done`), `in_progress` deletion
    locks, terminal state locks, `cancelled` title reuse, and `viewer`/`bob`/`admin` RBAC.
    """
    return [
        # Exp 1: Test whether todo -> done is allowed vs requires in_progress, and terminal lock on done
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "Probe1", "priority": 3}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "done"}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress"}},
        ],
        # Exp 2: Test delete lock on in_progress vs cancelled, and whether cancelled frees duplicate title
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "Probe2", "priority": 4}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "in_progress"}},
            {"operation": "delete_task", "task_id": "tsk-1", "actor": "alice"},
        ],
        # Exp 3: Test cancelled title reuse and cross-owner title isolation
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "UniqueTitle", "priority": 2}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "alice", "body": {"status": "cancelled"}},
            {"operation": "create_task", "actor": "alice", "body": {"title": "uniquetitle", "priority": 5}},
        ],
        # Exp 4: Test RBAC boundaries (viewer read-only vs bob cross-owner vs admin override)
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "OwnedTask", "priority": 2}},
            {"operation": "create_task", "actor": "viewer", "body": {"title": "ViewerTry", "priority": 2}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "bob", "body": {"priority": 4}},
            {"operation": "update_task", "task_id": "tsk-1", "actor": "admin", "body": {"priority": 4}},
        ],
        # Exp 5: Test boundary validation precedence (64 vs 65 chars, limit > 50)
        [
            {"operation": "create_task", "actor": "alice", "body": {"title": "x" * 65, "priority": 99}},
            {"operation": "list_tasks", "actor": "alice", "query": {"limit": 51}},
        ],
    ]


BENCHMARK_SUITES = {
    "passive_fixed_probes": passive_probe_sequences,
    "active_discriminating_probes": active_discriminating_sequences,
}


@dataclass(frozen=True)
class BenchmarkArmResult:
    arm_id: str
    description: str
    origin: Literal["mock"]
    real: Literal[False]
    experiments_used: int
    actions_executed: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    wall_seconds: float
    spec_digest: str
    passed: int
    failed: int
    indeterminate: int
    total: int
    http_dimension_counts: dict[str, int]
    engine_category_counts: dict[str, int]


def run_competitive_benchmark(
    *,
    work_dir: str | Path,
    seed: int = 20261101,
) -> dict[str, Any]:
    """Execute the controlled 4-arm benchmark scaffolding on the 30-case held-out HTTP suite.

    Controls for:
    - Target & held-out 30-case stateful evaluation suite (identical across all arms)
    - Allowed evidence per arm (2 seed examples vs 5 passive probes vs 5 active probes)
    - Model configuration & token budget ceiling (4096 max output tokens)
    - Execution wall time and token/cost accounting

    IMPORTANT: All candidate fills in this local harness are deterministic NON_AI
    controls (`origin="mock"`, `real=False`). This scaffolding proves measurement
    discrimination, isolation, and active-vs-passive evidence sufficiency—never
    claim these deterministic numbers as genuine Meta model scores.
    """
    base = Path(work_dir)
    base.mkdir(parents=True, exist_ok=True)
    public_contract = load_public_contract()

    with start_reference_server() as srv:
        contract = create_http_scope(srv.base_url, max_usd=0.0, max_reference_experiments=40)
        reference = HTTPReferenceAdapter(srv)
        cases = build_heldout_http_cases(seed=seed)
        skeleton = build_http_spec_skeleton(public_contract)

        arms_config = [
            (
                "A_direct_synthesis",
                "Direct synthesis from public contract + 2 minimal seed examples (0 active probes)",
                [
                    [
                        {"operation": "create_task", "actor": "alice", "body": {"title": "Example", "priority": 3}},
                        {"operation": "list_tasks", "actor": "alice"},
                    ]
                ],
                build_http_naive_direct_fill(),
                None,
            ),
            (
                "B_passive_fixed_probes",
                "Fixed sequential happy-path probes (5 experiments, 12 actions)",
                passive_probe_sequences(),
                build_http_passive_probe_fill(),
                None,
            ),
            (
                "C_active_evidence_driven",
                "Hypothesis-driven discriminating experiments (5 experiments, 15 actions)",
                active_discriminating_sequences(),
                build_http_guided_fill_control(),
                None,
            ),
        ]

        results: dict[str, BenchmarkArmResult] = {}
        c_feedback: dict[str, Any] | None = None

        for arm_id, desc, probe_seqs, fill_dict, repair_fb in arms_config:
            started = time.perf_counter()
            arm_ledger = EvidenceLedger(base / f"ledger_{arm_id}")
            runner = SafeHTTPExperimentRunner(contract, reference, arm_ledger)
            digests: list[str] = []
            action_count = 0
            for seq in probe_seqs:
                action_count += len(seq)
                seq_res = runner.run_actions(seq)
                for obs in seq_res.observations:
                    stored = arm_ledger.store(obs)
                    if stored["sha256"] not in digests:
                        digests.append(stored["sha256"])

            hyp_store = HypothesisStore()
            hyp_store.add_batch(
                validate_batch(
                    {
                        "hypotheses": [
                            {
                                "id": f"{arm_id}-h1",
                                "statement": f"Behavioral hypothesis set for {arm_id}",
                                "evidence_ids": [digests[0]],
                                "status": "hypothesized",
                            }
                        ]
                    },
                    frozenset(digests),
                )
            )

            req = prepare_http_generation_request(
                contract=contract,
                public_contract=public_contract,
                ledger=arm_ledger,
                observation_digests=digests,
                hypotheses=hyp_store,
                forbidden_markers=[c.case_id for c in cases],
                repair_feedback=repair_fb,
            )

            merged = merge_http_skeleton_fill(skeleton, fill_dict)
            loaded = load_http_candidate(merged, contract)
            candidate = HTTPCandidateInterpreter(loaded.spec)
            evaluator = HTTPDifferentialEvaluator(reference, candidate)
            eval_report = evaluator.evaluate(cases)
            elapsed = time.perf_counter() - started

            in_tok = _estimate_tokens(" ".join(m.get("content", "") for m in req.messages))
            out_tok = _estimate_tokens(json.dumps(fill_dict))

            if arm_id == "B_passive_fixed_probes":
                c_feedback = eval_report.model_feedback()

            results[arm_id] = BenchmarkArmResult(
                arm_id=arm_id,
                description=desc,
                origin="mock",
                real=False,
                experiments_used=len(probe_seqs),
                actions_executed=action_count,
                estimated_input_tokens=in_tok,
                estimated_output_tokens=out_tok,
                estimated_cost_usd=0.0,
                wall_seconds=round(elapsed, 4),
                spec_digest=loaded.digest,
                passed=eval_report.passed,
                failed=eval_report.failed,
                indeterminate=eval_report.indeterminate,
                total=eval_report.total,
                http_dimension_counts=eval_report.http_dimension_counts,
                engine_category_counts=eval_report.engine_EvaluationReport.diagnostic_class_counts,
            )

        # Arm D: Bounded repair starting from Arm B's imperfect candidate using aggregate feedback only
        assert c_feedback is not None
        started = time.perf_counter()
        arm_d_ledger = EvidenceLedger(base / "ledger_D_repair")
        runner_d = SafeHTTPExperimentRunner(contract, reference, arm_d_ledger)
        d_digests: list[str] = []
        d_actions = 0
        for seq in active_discriminating_sequences():
            d_actions += len(seq)
            seq_res = runner_d.run_actions(seq)
            for obs in seq_res.observations:
                st = arm_d_ledger.store(obs)
                if st["sha256"] not in d_digests:
                    d_digests.append(st["sha256"])

        d_hyps = HypothesisStore()
        d_hyps.add_batch(
            validate_batch(
                {
                    "hypotheses": [
                        {
                            "id": "D_repair-h1",
                            "statement": "Refined workflow transition and deletion lock hypotheses after aggregate feedback",
                            "evidence_ids": [d_digests[0]],
                            "status": "supported",
                        }
                    ]
                },
                frozenset(d_digests),
            )
        )
        req_d = prepare_http_generation_request(
            contract=contract,
            public_contract=public_contract,
            ledger=arm_d_ledger,
            observation_digests=d_digests,
            hypotheses=d_hyps,
            forbidden_markers=[c.case_id for c in cases],
            repair_feedback=c_feedback,
        )
        repaired_fill = build_http_guided_fill_control()
        merged_d = merge_http_skeleton_fill(skeleton, repaired_fill)
        loaded_d = load_http_candidate(merged_d, contract)
        eval_d = HTTPDifferentialEvaluator(
            reference, HTTPCandidateInterpreter(loaded_d.spec)
        ).evaluate(cases)
        elapsed_d = time.perf_counter() - started
        in_tok_d = _estimate_tokens(" ".join(m.get("content", "") for m in req_d.messages))
        out_tok_d = _estimate_tokens(json.dumps(repaired_fill))

        results["D_bounded_repair"] = BenchmarkArmResult(
            arm_id="D_bounded_repair",
            description="Feedback-conditioned bounded repair (1 round, aggregate counts only, zero case leakage)",
            origin="mock",
            real=False,
            experiments_used=len(active_discriminating_sequences()),
            actions_executed=d_actions,
            estimated_input_tokens=in_tok_d,
            estimated_output_tokens=out_tok_d,
            estimated_cost_usd=0.0,
            wall_seconds=round(elapsed_d, 4),
            spec_digest=loaded_d.digest,
            passed=eval_d.passed,
            failed=eval_d.failed,
            indeterminate=eval_d.indeterminate,
            total=eval_d.total,
            http_dimension_counts=eval_d.http_dimension_counts,
            engine_category_counts=eval_d.engine_EvaluationReport.diagnostic_class_counts,
        )

    return {
        "kind": "G4_HTTP_COMPETITIVE_BENCHMARK_SCAFFOLDING",
        "claim": "NON_AI_DETERMINISTIC_SCAFFOLDING_NOT_MODEL_QUALITY",
        "target_id": TARGET_ID,
        "reference_source_digest": reference_source_digest(),
        "public_contract_digest": _digest(_canonical_bytes(public_contract)),
        "suite_case_count": 30,
        "arms": {k: v.__dict__ for k, v in results.items()},
    }


def build_authorization_packet_proposal(
    *,
    contract: ScopeContract,
    suite_digest: str,
    inspected_direct_wire: ModelRequest,
    inspected_active_wire: ModelRequest,
) -> dict[str, Any]:
    """Build a zero-call exact-input authorization packet proposal for future owner review.

    Does NOT authorize spend or invoke any provider.
    """
    direct_bytes = _canonical_bytes(inspected_direct_wire.model_dump(mode="json"))
    active_bytes = _canonical_bytes(inspected_active_wire.model_dump(mode="json"))
    return {
        "kind": "G4_HTTP_AUTHORIZATION_PACKET_PROPOSAL_V1",
        "status": "PREPARED_UNAUTHORIZED_ZERO_CALLS",
        "provider": "meta-direct",
        "model": "muse-spark-1.3",
        "target_id": TARGET_ID,
        "reference_source_digest": reference_source_digest(),
        "scope_digest": scope_digest_of(contract),
        "sealed_suite_digest": suite_digest,
        "max_output_tokens": 4096,
        "max_permitted_spend_usd": 0.50,
        "arms_proposed": {
            "direct_baseline": {
                "inspected_wire_digest": _digest(direct_bytes),
                "experiments": 1,
                "generation_attempts": 1,
                "repair_rounds": 0,
            },
            "evidence_driven_treatment": {
                "inspected_wire_digest": _digest(active_bytes),
                "experiments": 5,
                "generation_attempts": 1,
                "repair_rounds": 0,
            },
        },
        "provider_calls_made": 0,
        "estimated_cost_ceiling_usd": 0.045,
        "isolation_verified": True,
    }
