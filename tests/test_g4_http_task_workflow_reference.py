"""Reference server behavioral, stateful, RBAC, and adversarial HTTP tests for G4."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from fixtures.owned_http_task_workflow import (
    HTTPReferenceAdapter,
    load_public_contract,
    start_reference_server,
)
from fixtures.owned_http_task_workflow.reference_server import main as server_main


def _raw_http(
    base_url: str,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    raw_body: bytes | None = None,
) -> tuple[int, dict[str, str], dict[str, object]]:
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=raw_body,
        method=method,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            status = int(resp.status)
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            payload = json.loads(resp.read().decode("utf-8"))
            return status, resp_headers, payload
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        payload = json.loads(exc.read().decode("utf-8"))
        return status, resp_headers, payload


def test_reference_server_self_test_cli_passes(capsys) -> None:
    rc = server_main(["--self-test"])
    assert rc == 0
    captured = json.loads(capsys.readouterr().out.strip())
    assert captured["ok"] is True
    assert captured["self_test"] == "passed"
    assert captured["target_id"] == "owned-http-task-workflow-v1"


def test_public_contract_omits_hidden_oracle_markers() -> None:
    contract = load_public_contract()
    assert contract["target_id"] == "owned-http-task-workflow-v1"
    serialized = json.dumps(contract)
    assert "/__admin/reset" not in serialized
    assert "TaskWorkflowReferenceState" not in serialized
    assert "terminal_state_locked" not in serialized


def test_crud_and_workflow_state_machine_transitions() -> None:
    with start_reference_server() as srv:
        ref = HTTPReferenceAdapter(srv)
        seq = ref.execute_sequence(
            [
                # 0: Create task as alice (trimmed title, priority 3)
                {
                    "operation": "create_task",
                    "actor": "alice",
                    "body": {"title": "  Configure worker  ", "priority": 3},
                },
                # 1: Direct todo -> done is forbidden (409 invalid_transition)
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                    "body": {"status": "done"},
                },
                # 2: Valid todo -> in_progress (with priority update to 5)
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                    "body": {"status": "in_progress", "priority": 5},
                },
                # 3: Cannot delete while in_progress (409 task_in_progress)
                {
                    "operation": "delete_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                },
                # 4: in_progress -> blocked
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                    "body": {"status": "blocked"},
                },
                # 5: blocked -> done is forbidden (409 invalid_transition)
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                    "body": {"status": "done"},
                },
                # 6: blocked -> in_progress
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                    "body": {"status": "in_progress"},
                },
                # 7: in_progress -> done
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                    "body": {"status": "done"},
                },
                # 8: Terminal state lock on done (409 terminal_state_locked)
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                    "body": {"priority": 1},
                },
                # 9: Delete done task succeeds
                {
                    "operation": "delete_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                },
                # 10: Next created task gets tsk-2 (monotonic ID counter does not rewind)
                {
                    "operation": "create_task",
                    "actor": "alice",
                    "body": {"title": "Second task", "priority": 2},
                },
            ]
        )
        assert seq.status == "ok"
        obs = seq.observations

        # Step 0: Created
        assert obs[0].output["http_status"] == 201
        assert obs[0].output["headers"]["location"] == "/v1/tasks/tsk-1"
        assert obs[0].output["headers"]["x-task-revision"] == "1"
        assert obs[0].output["body"]["task"] == {
            "id": "tsk-1",
            "owner": "alice",
            "priority": 3,
            "revision": 1,
            "status": "todo",
            "title": "Configure worker",
        }

        # Step 1: todo -> done rejected
        assert obs[1].output["http_status"] == 409
        assert obs[1].output["error"] == "invalid_transition"

        # Step 2: todo -> in_progress
        assert obs[2].output["http_status"] == 200
        assert obs[2].output["headers"]["x-task-revision"] == "2"
        assert obs[2].output["body"]["task"]["status"] == "in_progress"
        assert obs[2].output["body"]["task"]["priority"] == 5

        # Step 3: delete while in_progress rejected
        assert obs[3].output["http_status"] == 409
        assert obs[3].output["error"] == "task_in_progress"

        # Step 4: in_progress -> blocked
        assert obs[4].output["http_status"] == 200
        assert obs[4].output["body"]["task"]["revision"] == 3

        # Step 5: blocked -> done rejected
        assert obs[5].output["http_status"] == 409
        assert obs[5].output["error"] == "invalid_transition"

        # Step 6 & 7: blocked -> in_progress -> done
        assert obs[6].output["http_status"] == 200
        assert obs[7].output["http_status"] == 200
        assert obs[7].output["body"]["task"]["status"] == "done"
        assert obs[7].output["body"]["task"]["revision"] == 5

        # Step 8: terminal state lock on done
        assert obs[8].output["http_status"] == 409
        assert obs[8].output["error"] == "terminal_state_locked"

        # Step 9: delete done task succeeds
        assert obs[9].output["http_status"] == 200
        assert obs[9].output["body"] == {"deleted": "tsk-1", "ok": True}

        # Step 10: monotonic ID tsk-2
        assert obs[10].output["http_status"] == 201
        assert obs[10].output["body"]["task"]["id"] == "tsk-2"


def test_duplicate_title_per_owner_and_cancelled_release() -> None:
    with start_reference_server() as srv:
        ref = HTTPReferenceAdapter(srv)
        seq = ref.execute_sequence(
            [
                {
                    "operation": "create_task",
                    "actor": "alice",
                    "body": {"title": "Audit Logs", "priority": 3},
                },
                {
                    "operation": "create_task",
                    "actor": "alice",
                    "body": {"title": "  audit logs ", "priority": 2},
                },
                {
                    "operation": "create_task",
                    "actor": "bob",
                    "body": {"title": "audit logs", "priority": 4},
                },
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "alice",
                    "body": {"status": "cancelled"},
                },
                {
                    "operation": "create_task",
                    "actor": "alice",
                    "body": {"title": "Audit Logs", "priority": 5},
                },
            ]
        )
        assert seq.status == "ok"
        obs = seq.observations
        assert obs[0].output["http_status"] == 201
        assert obs[1].output["http_status"] == 409
        assert obs[1].output["error"] == "duplicate_title"
        assert obs[2].output["http_status"] == 201
        assert obs[2].output["body"]["task"]["id"] == "tsk-2"
        assert obs[3].output["http_status"] == 200
        assert obs[4].output["http_status"] == 201
        assert obs[4].output["body"]["task"]["id"] == "tsk-3"


def test_rbac_synthetic_actors_and_validation_precedence() -> None:
    seed = [
        {"id": "tsk-1", "title": "Alice item", "priority": 3, "status": "todo", "owner": "alice", "revision": 1},
    ]
    with start_reference_server() as srv:
        ref = HTTPReferenceAdapter(srv)
        seq = ref.execute_sequence(
            [
                # 0: Missing actor -> 401 with WWW-Authenticate (also seeds initial state)
                {
                    "method": "GET",
                    "path": "/v1/tasks",
                    "actor": None,
                    "seed_tasks": seed,
                },
                # 1: Viewer can GET
                {
                    "operation": "get_task",
                    "task_id": "tsk-1",
                    "actor": "viewer",
                },
                # 2: Viewer cannot POST (403 insufficient_role takes precedence over invalid body)
                {
                    "operation": "create_task",
                    "actor": "viewer",
                    "body": {"title": "", "priority": 99},
                },
                # 3: Bob cannot PATCH Alice's task (403 not_owner takes precedence over invalid priority)
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "bob",
                    "body": {"priority": 999},
                },
                # 4: Non-existent task returns 404 before ownership check
                {
                    "operation": "update_task",
                    "task_id": "tsk-99",
                    "actor": "bob",
                    "body": {"priority": 4},
                },
                # 5: Admin can transition Alice's task
                {
                    "operation": "update_task",
                    "task_id": "tsk-1",
                    "actor": "admin",
                    "body": {"status": "in_progress"},
                },
            ]
        )
        assert seq.status == "ok"
        obs = seq.observations

        assert obs[0].output["http_status"] == 401
        assert obs[0].output["error"] == "unauthenticated"
        assert "SyntheticActor" in obs[0].output["headers"].get("www-authenticate", "")

        assert obs[1].output["http_status"] == 200
        assert obs[2].output["http_status"] == 403
        assert obs[2].output["error"] == "insufficient_role"

        assert obs[3].output["http_status"] == 403
        assert obs[3].output["error"] == "not_owner"

        assert obs[4].output["http_status"] == 404
        assert obs[4].output["error"] == "not_found"

        assert obs[5].output["http_status"] == 200
        assert obs[5].output["body"]["task"]["status"] == "in_progress"
        assert obs[5].output["body"]["task"]["owner"] == "alice"


def test_filtering_ordering_pagination_and_query_validation() -> None:
    seed = [
        {"id": "tsk-1", "title": "T1", "priority": 2, "status": "todo", "owner": "alice", "revision": 1},
        {"id": "tsk-2", "title": "T2", "priority": 5, "status": "in_progress", "owner": "bob", "revision": 2},
        {"id": "tsk-3", "title": "T3", "priority": 5, "status": "todo", "owner": "alice", "revision": 1},
        {"id": "tsk-4", "title": "T4", "priority": 1, "status": "blocked", "owner": "bob", "revision": 3},
    ]
    with start_reference_server() as srv:
        ref = HTTPReferenceAdapter(srv)
        seq = ref.execute_sequence(
            [
                {
                    "operation": "list_tasks",
                    "actor": "viewer",
                    "seed_tasks": seed,
                    "query": {"order_by": "priority_desc", "limit": 2, "offset": 1},
                },
                {
                    "operation": "list_tasks",
                    "actor": "alice",
                    "query": {"owner": "alice", "min_priority": 3},
                },
                {
                    "operation": "list_tasks",
                    "actor": "alice",
                    "query": {"min_priority": 4, "max_priority": 2},
                },
            ]
        )
        assert seq.status == "ok"
        obs = seq.observations

        page_body = obs[0].output["body"]
        assert obs[0].output["http_status"] == 200
        assert page_body["total"] == 4
        assert page_body["count"] == 2
        assert page_body["has_more"] is True
        assert [item["id"] for item in page_body["items"]] == ["tsk-3", "tsk-1"]

        filt_body = obs[1].output["body"]
        assert obs[1].output["http_status"] == 200
        assert [item["id"] for item in filt_body["items"]] == ["tsk-3"]

        assert obs[2].output["http_status"] == 422
        assert obs[2].output["error"] == "invalid_filter"


def test_adversarial_http_requests_and_admin_reset_isolation() -> None:
    with start_reference_server() as srv:
        # 1. Malformed JSON
        status, _, body = _raw_http(
            srv.base_url,
            "POST",
            "/v1/tasks",
            headers={"X-Synthetic-Actor": "alice", "Content-Type": "application/json"},
            raw_body=b'{"title": "unterminated',
        )
        assert status == 400
        assert body["error"] == "invalid_json"

        # 2. Duplicate JSON keys rejected
        status, _, body = _raw_http(
            srv.base_url,
            "POST",
            "/v1/tasks",
            headers={"X-Synthetic-Actor": "alice", "Content-Type": "application/json"},
            raw_body=b'{"title": "First", "title": "Second", "priority": 2}',
        )
        assert status == 400
        assert body["error"] == "invalid_json"

        # 3. Non-finite JSON constant (NaN) rejected
        status, _, body = _raw_http(
            srv.base_url,
            "POST",
            "/v1/tasks",
            headers={"X-Synthetic-Actor": "alice", "Content-Type": "application/json"},
            raw_body=b'{"title": "NaN test", "priority": NaN}',
        )
        assert status == 400
        assert body["error"] == "invalid_json"

        # 4. Oversized payload (> 32 KiB) rejected
        status, _, body = _raw_http(
            srv.base_url,
            "POST",
            "/v1/tasks",
            headers={"X-Synthetic-Actor": "alice", "Content-Type": "application/json"},
            raw_body=b'{"title": "' + (b"x" * 34000) + b'"}',
        )
        assert status == 400
        assert body["error"] == "invalid_json"

        # 5. Method not allowed returns 405 and Allow header
        status, headers, body = _raw_http(
            srv.base_url,
            "DELETE",
            "/v1/tasks",
            headers={"X-Synthetic-Actor": "alice"},
        )
        assert status == 405
        assert headers.get("allow") == "GET, POST"
        assert body["error"] == "method_not_allowed"

        # 6. Path traversal rejected with 400 invalid_path
        status, _, body = _raw_http(
            srv.base_url,
            "GET",
            "/v1/tasks/../../etc/passwd",
            headers={"X-Synthetic-Actor": "alice"},
        )
        assert status == 400
        assert body["error"] == "invalid_path"

        # 7. HTTPReferenceAdapter blocks direct model/runner calls to /__admin/reset
        ref = HTTPReferenceAdapter(srv)
        blocked = ref.execute_sequence(
            [{"method": "POST", "path": "/__admin/reset", "actor": "admin", "body": {}}]
        )
        assert blocked.status == "protocol_error"
        assert blocked.stderr == "control_plane_access_denied"
