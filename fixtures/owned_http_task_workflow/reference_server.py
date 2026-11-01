"""Owned synthetic black-box HTTP reference server for G4 task-workflow target.

SECURITY & ISOLATION BOUNDARY:
- Never pass this file or its source contents to the reconstruction model.
- Binds strictly to 127.0.0.1 (loopback only) with bounded payload sizes and timeouts.
- Exposes deterministic reset/seed control ONLY to the trusted local harness on
  `POST /__admin/reset` (which is excluded from the model's ScopeContract).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import sys
import threading
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlsplit

MAX_BODY_BYTES = 32_768
MAX_RECORDS = 5_000
TASK_ID_RE = re.compile(r"^tsk-([1-9][0-9]{0,8})$")
OWNER_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

SYNTHETIC_ACTORS: dict[str, str] = {
    "alice": "member",
    "bob": "member",
    "viewer": "viewer",
    "admin": "admin",
}

VALID_STATUSES = ("todo", "in_progress", "blocked", "done", "cancelled")
TERMINAL_STATUSES = frozenset({"done", "cancelled"})
NON_DELETABLE_STATUSES = frozenset({"in_progress"})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "todo": frozenset({"in_progress", "blocked", "cancelled"}),
    "in_progress": frozenset({"todo", "blocked", "done", "cancelled"}),
    "blocked": frozenset({"todo", "in_progress", "cancelled"}),
    "done": frozenset(),
    "cancelled": frozenset(),
}

VALID_ORDERS = ("id_asc", "id_desc", "priority_desc", "priority_asc")


def _parse_strict_int(raw: str) -> int | None:
    if not isinstance(raw, str) or not re.fullmatch(r"-?[0-9]{1,9}", raw.strip()):
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _task_seq_num(task_id: str) -> int:
    match = TASK_ID_RE.fullmatch(task_id)
    if not match:
        raise ValueError(f"Invalid task identifier: {task_id!r}")
    return int(match.group(1))


def _checked_json_object(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_BODY_BYTES:
        raise ValueError("payload_too_large")
    if not raw or not raw.strip():
        raise ValueError("empty_body")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise ValueError("duplicate_key")
            out[k] = v
        return out

    def reject_nonfinite(val: str) -> Any:
        raise ValueError(f"nonfinite:{val}")

    parsed = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_nonfinite,
    )
    if not isinstance(parsed, dict):
        raise ValueError("not_an_object")
    return parsed


@dataclass
class TaskRecord:
    seq: int
    id: str
    title: str
    priority: int
    status: str
    owner: str
    revision: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "status": self.status,
            "owner": self.owner,
            "revision": self.revision,
        }


@dataclass
class TaskWorkflowReferenceState:
    """Thread-safe in-memory state store with deterministic reset and seeding."""

    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _tasks: dict[str, TaskRecord] = field(default_factory=dict, init=False)
    _next_seq: int = field(default=1, init=False)

    def reset(self, seed_tasks: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
        with self._lock:
            self._tasks.clear()
            self._next_seq = 1
            if seed_tasks:
                max_seq = 0
                for item in seed_tasks:
                    raw_id = str(item.get("id", f"tsk-{self._next_seq}"))
                    seq = _task_seq_num(raw_id)
                    title = str(item["title"]).strip()
                    priority = int(item["priority"])
                    status = str(item.get("status", "todo"))
                    owner = str(item.get("owner", "alice"))
                    revision = int(item.get("revision", 1))
                    if (
                        not (1 <= len(title) <= 64)
                        or not (1 <= priority <= 5)
                        or status not in VALID_STATUSES
                        or owner not in SYNTHETIC_ACTORS
                        or revision < 1
                        or raw_id in self._tasks
                    ):
                        raise ValueError("Invalid seed task specification")
                    self._tasks[raw_id] = TaskRecord(
                        seq=seq,
                        id=raw_id,
                        title=title,
                        priority=priority,
                        status=status,
                        owner=owner,
                        revision=revision,
                    )
                    if seq > max_seq:
                        max_seq = seq
                self._next_seq = max_seq + 1
            return {
                "ok": True,
                "reset": True,
                "seeded_count": len(self._tasks),
                "next_id": f"tsk-{self._next_seq}",
            }

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            ordered = sorted(self._tasks.values(), key=lambda r: r.seq)
            return [r.to_dict() for r in ordered]

    def handle_request(
        self,
        method: str,
        raw_target: str,
        headers: Mapping[str, str],
        body_bytes: bytes = b"",
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        """Process one HTTP request and return (status_code, headers, json_body)."""
        norm_headers = {k.lower(): v.strip() for k, v in headers.items()}
        parsed_url = urlsplit(raw_target)
        raw_path = parsed_url.path or "/"

        # Reject path traversal or encoded slash tricks before routing
        decoded_path = unquote(raw_path)
        if (
            "\\" in raw_target
            or "\\" in decoded_path
            or "//" in raw_path
            or ".." in decoded_path.split("/")
            or not decoded_path.startswith("/")
        ):
            return (
                400,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_path"},
            )

        path = decoded_path.rstrip("/") or "/"

        # Harness-only deterministic reset endpoint
        if path == "/__admin/reset":
            if method != "POST":
                return (
                    405,
                    {"content-type": "application/json", "allow": "POST"},
                    {"ok": False, "error": "method_not_allowed"},
                )
            seed_tasks = None
            if body_bytes.strip():
                try:
                    payload = _checked_json_object(body_bytes)
                    seed_tasks = payload.get("seed_tasks")
                    if seed_tasks is not None and not isinstance(seed_tasks, list):
                        raise ValueError("seed_tasks must be a list")
                except ValueError:
                    return (
                        400,
                        {"content-type": "application/json"},
                        {"ok": False, "error": "invalid_json"},
                    )
            try:
                out = self.reset(seed_tasks=seed_tasks)
            except ValueError:
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_seed"},
                )
            return 200, {"content-type": "application/json"}, out

        # Route existence check before auth/method dispatch?
        # Wait: checking route pattern first so unknown paths return 404 unknown_endpoint
        # or checking auth first on /v1/* routes:
        is_collection = path == "/v1/tasks"
        item_match = re.fullmatch(r"/v1/tasks/([^/]+)", path)
        if not is_collection and not item_match:
            return (
                404,
                {"content-type": "application/json"},
                {"ok": False, "error": "unknown_endpoint"},
            )

        # Method check per route (405 Method Not Allowed with Allow header)
        if is_collection and method not in ("GET", "POST"):
            return (
                405,
                {"content-type": "application/json", "allow": "GET, POST"},
                {"ok": False, "error": "method_not_allowed"},
            )
        if item_match and method not in ("GET", "PATCH", "DELETE"):
            return (
                405,
                {"content-type": "application/json", "allow": "DELETE, GET, PATCH"},
                {"ok": False, "error": "method_not_allowed"},
            )

        # Synthetic identity authentication check
        actor = norm_headers.get("x-synthetic-actor", "")
        if not actor or actor not in SYNTHETIC_ACTORS:
            return (
                401,
                {
                    "content-type": "application/json",
                    "www-authenticate": 'SyntheticActor realm="owned-task-workflow"',
                },
                {"ok": False, "error": "unauthenticated"},
            )
        role = SYNTHETIC_ACTORS[actor]

        # Role-based mutation gate: viewer is read-only across all mutating verbs
        if method in ("POST", "PATCH", "DELETE") and role == "viewer":
            return (
                403,
                {"content-type": "application/json"},
                {"ok": False, "error": "insufficient_role"},
            )

        if len(body_bytes) > MAX_BODY_BYTES:
            return (
                400,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_json"},
            )

        with self._lock:
            if is_collection and method == "POST":
                return self._handle_create(actor, body_bytes)
            if is_collection and method == "GET":
                return self._handle_list(parsed_url.query)
            assert item_match is not None
            task_id = item_match.group(1)
            if method == "GET":
                return self._handle_get(task_id)
            if method == "PATCH":
                return self._handle_patch(actor, role, task_id, body_bytes)
            return self._handle_delete(actor, role, task_id)

    def _has_duplicate_active_title(
        self, owner: str, trimmed_title: str, *, exclude_id: str | None = None
    ) -> bool:
        folded = trimmed_title.casefold()
        for record in self._tasks.values():
            if exclude_id is not None and record.id == exclude_id:
                continue
            if record.owner == owner and record.status != "cancelled":
                if record.title.casefold() == folded:
                    return True
        return False

    def _handle_create(
        self, actor: str, body_bytes: bytes
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        try:
            payload = _checked_json_object(body_bytes)
        except ValueError:
            return (
                400,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_json"},
            )

        # Precedence 1: title (string, trimmed 1..64)
        title = payload.get("title")
        if not isinstance(title, str) or not (1 <= len(title.strip()) <= 64):
            return (
                422,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_title"},
            )
        clean_title = title.strip()

        # Precedence 2: priority (strict int 1..5)
        priority = payload.get("priority")
        if type(priority) is not int or not (1 <= priority <= 5):
            return (
                422,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_priority"},
            )

        # Precedence 3: duplicate active title for the same owner
        if self._has_duplicate_active_title(actor, clean_title):
            return (
                409,
                {"content-type": "application/json"},
                {"ok": False, "error": "duplicate_title"},
            )

        if len(self._tasks) >= MAX_RECORDS:
            return (
                409,
                {"content-type": "application/json"},
                {"ok": False, "error": "resource_exhausted"},
            )

        seq = self._next_seq
        self._next_seq += 1
        task_id = f"tsk-{seq}"
        record = TaskRecord(
            seq=seq,
            id=task_id,
            title=clean_title,
            priority=priority,
            status="todo",
            owner=actor,
            revision=1,
        )
        self._tasks[task_id] = record
        return (
            201,
            {
                "content-type": "application/json",
                "location": f"/v1/tasks/{task_id}",
                "x-task-revision": "1",
            },
            {"ok": True, "task": record.to_dict()},
        )

    def _handle_get(self, task_id: str) -> tuple[int, dict[str, str], dict[str, Any]]:
        record = self._tasks.get(task_id)
        if record is None:
            return (
                404,
                {"content-type": "application/json"},
                {"ok": False, "error": "not_found"},
            )
        return (
            200,
            {
                "content-type": "application/json",
                "x-task-revision": str(record.revision),
            },
            {"ok": True, "task": record.to_dict()},
        )

    def _handle_list(self, query_string: str) -> tuple[int, dict[str, str], dict[str, Any]]:
        raw_params = parse_qs(query_string, keep_blank_values=True)
        allowed_keys = {
            "status",
            "owner",
            "min_priority",
            "max_priority",
            "order_by",
            "limit",
            "offset",
        }
        if any(k not in allowed_keys or len(v) != 1 for k, v in raw_params.items()):
            return (
                422,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_filter"},
            )
        params = {k: v[0] for k, v in raw_params.items()}

        # Validate filters in deterministic order:
        # 1. status
        status_filter: str | None = None
        if "status" in params:
            if params["status"] not in VALID_STATUSES:
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_filter"},
                )
            status_filter = params["status"]

        # 2. owner
        owner_filter: str | None = None
        if "owner" in params:
            if not OWNER_RE.fullmatch(params["owner"]):
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_filter"},
                )
            owner_filter = params["owner"]

        # 3. min_priority & 4. max_priority
        min_prio: int | None = None
        if "min_priority" in params:
            min_prio = _parse_strict_int(params["min_priority"])
            if min_prio is None or not (1 <= min_prio <= 5):
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_filter"},
                )
        max_prio: int | None = None
        if "max_priority" in params:
            max_prio = _parse_strict_int(params["max_priority"])
            if max_prio is None or not (1 <= max_prio <= 5):
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_filter"},
                )
        if min_prio is not None and max_prio is not None and min_prio > max_prio:
            return (
                422,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_filter"},
            )

        # 5. order_by
        order_by = params.get("order_by", "id_asc")
        if order_by not in VALID_ORDERS:
            return (
                422,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_order"},
            )

        # 6. limit & 7. offset
        limit = 10
        if "limit" in params:
            parsed_limit = _parse_strict_int(params["limit"])
            if parsed_limit is None or not (1 <= parsed_limit <= 50):
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_pagination"},
                )
            limit = parsed_limit

        offset = 0
        if "offset" in params:
            parsed_offset = _parse_strict_int(params["offset"])
            if parsed_offset is None or parsed_offset < 0:
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_pagination"},
                )
            offset = parsed_offset

        records = list(self._tasks.values())
        if status_filter is not None:
            records = [r for r in records if r.status == status_filter]
        if owner_filter is not None:
            records = [r for r in records if r.owner == owner_filter]
        if min_prio is not None:
            records = [r for r in records if r.priority >= min_prio]
        if max_prio is not None:
            records = [r for r in records if r.priority <= max_prio]

        if order_by == "id_asc":
            records.sort(key=lambda r: r.seq)
        elif order_by == "id_desc":
            records.sort(key=lambda r: -r.seq)
        elif order_by == "priority_desc":
            records.sort(key=lambda r: (-r.priority, r.seq))
        elif order_by == "priority_asc":
            records.sort(key=lambda r: (r.priority, r.seq))

        total = len(records)
        page = records[offset : offset + limit]
        has_more = (offset + len(page)) < total

        return (
            200,
            {"content-type": "application/json"},
            {
                "ok": True,
                "items": [r.to_dict() for r in page],
                "total": total,
                "count": len(page),
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
            },
        )

    def _handle_patch(
        self, actor: str, role: str, task_id: str, body_bytes: bytes
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        try:
            payload = _checked_json_object(body_bytes)
        except ValueError:
            return (
                400,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_json"},
            )

        record = self._tasks.get(task_id)
        if record is None:
            return (
                404,
                {"content-type": "application/json"},
                {"ok": False, "error": "not_found"},
            )

        if actor != record.owner and role != "admin":
            return (
                403,
                {"content-type": "application/json"},
                {"ok": False, "error": "not_owner"},
            )

        updatable = {"title", "priority", "status"}
        if not any(k in payload for k in updatable):
            return (
                422,
                {"content-type": "application/json"},
                {"ok": False, "error": "empty_update"},
            )

        if record.status in TERMINAL_STATUSES:
            return (
                409,
                {"content-type": "application/json"},
                {"ok": False, "error": "terminal_state_locked"},
            )

        # Field validation precedence: title -> priority -> status
        new_title = record.title
        if "title" in payload:
            raw_title = payload["title"]
            if not isinstance(raw_title, str) or not (1 <= len(raw_title.strip()) <= 64):
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_title"},
                )
            new_title = raw_title.strip()

        new_priority = record.priority
        if "priority" in payload:
            raw_prio = payload["priority"]
            if type(raw_prio) is not int or not (1 <= raw_prio <= 5):
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_priority"},
                )
            new_priority = raw_prio

        new_status = record.status
        if "status" in payload:
            raw_status = payload["status"]
            if not isinstance(raw_status, str) or raw_status not in VALID_STATUSES:
                return (
                    422,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_status"},
                )
            new_status = raw_status

        # Conflict rules: duplicate_title -> invalid_transition
        if "title" in payload and self._has_duplicate_active_title(
            record.owner, new_title, exclude_id=record.id
        ):
            return (
                409,
                {"content-type": "application/json"},
                {"ok": False, "error": "duplicate_title"},
            )

        if "status" in payload and new_status != record.status:
            if new_status not in ALLOWED_TRANSITIONS.get(record.status, frozenset()):
                return (
                    409,
                    {"content-type": "application/json"},
                    {"ok": False, "error": "invalid_transition"},
                )

        record.title = new_title
        record.priority = new_priority
        record.status = new_status
        record.revision += 1

        return (
            200,
            {
                "content-type": "application/json",
                "x-task-revision": str(record.revision),
            },
            {"ok": True, "task": record.to_dict()},
        )

    def _handle_delete(
        self, actor: str, role: str, task_id: str
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        record = self._tasks.get(task_id)
        if record is None:
            return (
                404,
                {"content-type": "application/json"},
                {"ok": False, "error": "not_found"},
            )

        if actor != record.owner and role != "admin":
            return (
                403,
                {"content-type": "application/json"},
                {"ok": False, "error": "not_owner"},
            )

        if record.status in NON_DELETABLE_STATUSES:
            return (
                409,
                {"content-type": "application/json"},
                {"ok": False, "error": "task_in_progress"},
            )

        del self._tasks[task_id]
        return (
            200,
            {"content-type": "application/json"},
            {"ok": True, "deleted": task_id},
        )


class _ReferenceHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SecondSourceOwnedTaskWorkflow/1.0"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        # Silence default stderr access logs to keep test and worker output deterministic.
        return

    def _dispatch(self, method: str) -> None:
        state: TaskWorkflowReferenceState = getattr(self.server, "reference_state")
        content_length_raw = self.headers.get("Content-Length", "0")
        try:
            content_length = int(content_length_raw)
            if content_length < 0:
                raise ValueError
        except ValueError:
            self._send_json(
                400,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_json"},
            )
            return

        if content_length > MAX_BODY_BYTES:
            # Drain up to cap and reject
            _ = self.rfile.read(min(content_length, MAX_BODY_BYTES + 1))
            self._send_json(
                400,
                {"content-type": "application/json"},
                {"ok": False, "error": "invalid_json"},
            )
            return

        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
        req_headers = {k: v for k, v in self.headers.items()}
        status, resp_headers, resp_body = state.handle_request(
            method, self.path, req_headers, body_bytes
        )
        self._send_json(status, resp_headers, resp_body)

    def _send_json(
        self, status: int, headers: Mapping[str, str], body: dict[str, Any]
    ) -> None:
        encoded = json.dumps(
            body, separators=(",", ":"), sort_keys=True, ensure_ascii=False
        ).encode("utf-8")
        self.send_response(status)
        for key, value in sorted(headers.items()):
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.wfile.flush()

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_OPTIONS(self) -> None:
        self._dispatch("OPTIONS")


class _BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        state: TaskWorkflowReferenceState,
    ) -> None:
        super().__init__(server_address, _ReferenceHTTPHandler)
        self.reference_state = state


@dataclass(frozen=True)
class RunningTaskWorkflowServer:
    server: _BoundedHTTPServer
    thread: threading.Thread
    host: str
    port: int
    state: TaskWorkflowReferenceState

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def reset(self, seed_tasks: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
        return self.state.reset(seed_tasks=seed_tasks)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3.0)


def create_reference_server(
    host: str = "127.0.0.1",
    port: int = 0,
    state: TaskWorkflowReferenceState | None = None,
) -> RunningTaskWorkflowServer:
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("Reference HTTP server may only bind to loopback")
    ref_state = state or TaskWorkflowReferenceState()
    httpd = _BoundedHTTPServer((host, port), ref_state)
    bound_host, bound_port = httpd.server_address[:2]
    thread = threading.Thread(
        target=httpd.serve_forever,
        kwargs={"poll_interval": 0.02},
        name="owned-http-task-workflow-server",
        daemon=True,
    )
    thread.start()
    return RunningTaskWorkflowServer(
        server=httpd,
        thread=thread,
        host=str(bound_host),
        port=int(bound_port),
        state=ref_state,
    )


@contextmanager
def start_reference_server(
    seed_tasks: Sequence[Mapping[str, Any]] | None = None,
) -> Iterator[RunningTaskWorkflowServer]:
    state = TaskWorkflowReferenceState()
    if seed_tasks:
        state.reset(seed_tasks=seed_tasks)
    running = create_reference_server(state=state)
    try:
        yield running
    finally:
        running.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the owned stateful HTTP task-workflow reference server locally."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Loopback bind host (127.0.0.1)")
    parser.add_argument("--port", type=int, default=0, help="Bind port (0 for ephemeral)")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Start server, run a quick health/reset check, print JSON status, and exit.",
    )
    args = parser.parse_args(argv)
    with start_reference_server() as srv:
        if args.self_test:
            status, _, body = srv.state.handle_request(
                "POST",
                "/v1/tasks",
                {"X-Synthetic-Actor": "alice"},
                json.dumps({"title": "Self-test task", "priority": 3}).encode("utf-8"),
            )
            if status != 201 or not body.get("ok"):
                return 1
            srv.reset()
            print(
                json.dumps(
                    {
                        "ok": True,
                        "target_id": "owned-http-task-workflow-v1",
                        "base_url": srv.base_url,
                        "self_test": "passed",
                    }
                )
            )
            return 0
        print(
            json.dumps({"base_url": srv.base_url, "status": "listening"}),
            flush=True,
        )
        try:
            srv.thread.join()
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
