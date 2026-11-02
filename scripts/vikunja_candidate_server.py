"""Generic candidate server for the Vikunja benchmark.

Executes a candidate SPEC (JSON) authored by a model (or, for plumbing
validation only, a hand-written NON_AI oracle). The interpreter contains
no Vikunja-specific behavior: every externally observable decision —
routes, methods, success statuses, validation, permissions, state
transitions — comes from the spec. State is in-memory, per-process.

Spec shape:
{
  "routes": [
    {"method": "PUT", "path": "/projects", "kind": "create_project",
     "auth": true, "status": 201,
     "validate": [{"field": "title", "rule": "nonempty", "status": 400}]},
    {"method": "PUT", "path": "/projects/{pid}/tasks", "kind": "create_task",
     "auth": true, "permission": "owner_or_write", "status": 201,
     "validate": [...]},
    {"method": "GET", "path": "/projects/{pid}/tasks", "kind": "list_tasks",
     "auth": true, "permission": "owner_or_read"},
    {"method": "POST", "path": "/tasks/{tid}", "kind": "update_task",
     "auth": true, "permission": "owner_or_write", "status": 200},
    {"method": "GET", "path": "/tasks/{tid}", "kind": "get_task",
     "auth": true, "permission": "owner_or_read"},
    {"method": "PUT", "path": "/projects/{pid}/users",
     "kind": "share_project", "auth": true, "permission": "owner",
     "status": 201}
  ],
  "users": {"alice": "bench_alice", "bob": "bench_bob"}
}

Tokens: the evaluator sends the reference's real tokens, which this
server cannot validate; instead the evaluator's candidate-side tokens
are the literals "alice"/"bob" (vikunja_benchmark --candidate-url mode
uses its own registration against this server's /register + /login,
which are interpreter-provided, spec-independent plumbing).
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class Candidate:
    def __init__(self, spec):
        self.spec = spec
        self.users = {}       # username -> {"id", "password"}
        self.tokens = {}      # token -> username
        self.projects = {}    # id -> {"id","title","owner","shared":{user:perm}}
        self.tasks = {}       # id -> task dict
        self.next_id = 0

    def _id(self):
        self.next_id += 1
        return self.next_id

    def _user(self, headers):
        auth = headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return self.tokens.get(auth[7:])
        return None

    def _route(self, method, parts):
        for route in self.spec.get("routes", []):
            if route["method"] != method:
                continue
            pat = [p for p in route["path"].split("/") if p]
            if len(pat) != len(parts):
                continue
            params = {}
            ok = True
            for want, got in zip(pat, parts):
                if want.startswith("{"):
                    params[want[1:-1]] = got
                elif want != got:
                    ok = False
                    break
            if ok:
                return route, params
        return None, {}

    def _validate(self, route, body):
        for rule in route.get("validate", []):
            value = (body or {}).get(rule["field"])
            if rule["rule"] == "nonempty" and (value is None or str(value).strip() == ""):
                return rule.get("status", 400), rule.get(
                    "error_body", {"message": f"invalid {rule['field']}"})
        return None

    def _fill(self, value, ctx):
        """Substitute spec tokens in declared response fields."""
        if isinstance(value, str):
            if value == "<auto_id>":
                return self._id()
            if value == "<auto_id:same>":
                return ctx["auto_id"]
            if value == "<creator>":
                return ctx["creator"]
            if value == "<target>":
                return ctx.get("target")
            if value == "<permission>":
                return ctx.get("permission")
            if value == "<entity_id>":
                return ctx.get("entity_id")
            if value == "<index>":
                return ctx.get("index")
            if value == "<identifier>":
                return f"#{ctx.get('index')}"
            return value
        if isinstance(value, dict):
            return {k: self._fill(v, ctx) for k, v in value.items()}
        if isinstance(value, list):
            return [self._fill(v, ctx) for v in value]
        return value

    def _forbidden(self):
        return 403, self.spec.get("auth", {}).get(
            "forbidden_body", {"message": "Forbidden"})

    def _not_found(self):
        return 404, self.spec.get("auth", {}).get(
            "not_found_body", {"message": "Not Found"})

    def _permission(self, route, user, project):
        need = route.get("permission", "any_auth")
        if project is None:
            return self._not_found()

        def denied():
            if route.get("forbidden_body") is not None:
                return 403, route["forbidden_body"]
            return self._forbidden()

        if need == "any_auth" or project["owner"] == user:
            return None
        perm = project["shared"].get(user)
        if need == "owner":
            return denied()
        if need == "owner_or_read" and perm is not None:
            return None
        if need == "owner_or_write" and perm is not None and perm >= 1:
            return None
        return denied()

    def handle(self, method, raw_path, body, headers):
        path = raw_path.split("?")[0]
        parts = [p for p in path.split("/") if p]
        if parts[:2] == ["api", "v1"]:
            parts = parts[2:]
        # Plumbing (spec-independent): register/login/token issue.
        if method == "POST" and parts == ["register"]:
            name = (body or {}).get("username")
            self.users[name] = {"id": self._id(), "password": (body or {}).get("password")}
            return 200, {"id": self.users[name]["id"], "username": name}
        if method == "POST" and parts == ["login"]:
            name = (body or {}).get("username")
            record = self.users.get(name)
            if not record or record["password"] != (body or {}).get("password"):
                auth = self.spec.get("auth", {})
                return (auth.get("login_error_status", 401),
                        auth.get("login_error_body",
                                 {"message": "Invalid username or password"}))
            token = f"tok-{name}"
            self.tokens[token] = name
            return 200, {"token": token}
        route, params = self._route(method, parts)
        if route is None:
            return self._not_found()
        user = self._user(headers)
        if route.get("auth", True) and user is None:
            auth = self.spec.get("auth", {})
            return (auth.get("unauthenticated_status", 401),
                    auth.get("unauthenticated_body", {"message": "Unauthorized"}))
        username = {v: k for k, v in self.spec.get("users", {}).items()}.get(user, user)
        err = self._validate(route, body)
        if err:
            return err
        kind = route.get("kind")
        pid = int(params["pid"]) if "pid" in params else None
        tid = int(params["tid"]) if "tid" in params else None
        project = self.projects.get(pid) if pid is not None else None
        if kind in ("create_task", "list_tasks", "share_project"):
            err = self._permission(route, username, project)
            if err:
                return err
        if kind in ("update_task", "get_task"):
            task = self.tasks.get(tid)
            if task is None:
                return self._not_found()
            err = self._permission(route, username, self.projects.get(task["project_id"]))
            if err:
                return err
        status = route.get("status", 200)
        record = self.users.get(user, {})
        ctx = {"auto_id": self._id(),
               "creator": {"id": record.get("id", 1), "name": "",
                           "username": user,
                           "created": "2026-01-01T00:00:00Z",
                           "updated": "2026-01-01T00:00:00Z"},
               "target": (body or {}).get("username"),
               "permission": (body or {}).get("permission")}
        fields = self._fill(route.get("fields", {}), ctx)

        def with_fields(base):
            if route.get("fields_override"):
                return {**base, **fields}
            return {**base, **{k: v for k, v in fields.items() if k not in base}}

        if kind == "create_project":
            proj = {"id": self._id(), "title": (body or {}).get("title", ""),
                    "owner": username, "shared": {}, "created": "2026-01-01T00:00:00Z",
                    "updated": "2026-01-01T00:00:00Z", "position": 655360.0}
            ctx["entity_id"] = proj["id"]
            fields = self._fill(route.get("fields", {}), ctx)
            self.projects[proj["id"]] = proj
            return status, with_fields(
                {k: v for k, v in proj.items() if k not in ("owner", "shared")})
        if kind == "share_project":
            target = (body or {}).get("username")
            target_alias = {v: k for k, v in self.spec.get("users", {}).items()}.get(target, target)
            project["shared"][target_alias] = int((body or {}).get("permission", 0))
            return status, with_fields({"id": ctx["auto_id"]})
        if kind == "create_task":
            ctx["index"] = sum(1 for t in self.tasks.values()
                                if t["project_id"] == pid) + 1
            fields = self._fill(route.get("fields", {}), ctx)
            task = {"id": self._id(), "project_id": pid,
                    "title": (body or {}).get("title", ""),
                    "description": (body or {}).get("description", ""),
                    "priority": (body or {}).get("priority", 0),
                    "done": False,
                    "done_at": fields.get("done_at"),
                    "position": 655360.0,
                    "created": "2026-01-01T00:00:00Z", "updated": "2026-01-01T00:00:00Z"}
            for key in ("index", "identifier", "created_by"):
                if key in fields:
                    task[key] = fields[key]
            self.tasks[task["id"]] = task
            return status, with_fields(task)
        if kind == "list_tasks":
            items = [with_fields(t) for t in self.tasks.values() if t["project_id"] == pid]
            if "filter=done" in raw_path and "false" in raw_path:
                items = [t for t in items if not t["done"]]
            return status, items
        if kind == "update_task":
            task = self.tasks[tid]
            if body and "done" in body:
                task["done"] = bool(body["done"])
                task["done_at"] = "2026-01-02T00:00:00Z" if task["done"] else fields.get("done_at")
            return status, with_fields(task)
        if kind == "get_task":
            return status, with_fields(self.tasks[tid])
        if kind == "list_projects":
            items = [{k: v for k, v in p.items() if k not in ("owner", "shared")}
                     for p in self.projects.values()
                     if p["owner"] == username or username in p["shared"]]
            return status, items
        if kind == "get_user":
            return status, {"id": 1, "username": username}
        return 404, {"message": "unimplemented kind"}


def serve(spec_path, port):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    candidate = Candidate(spec)

    class Handler(BaseHTTPRequestHandler):
        def _go(self, method):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw else None
            status, out = candidate.handle(method, self.path, body, self.headers)
            data = json.dumps(out).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self): self._go("GET")
        def do_PUT(self): self._go("PUT")
        def do_POST(self): self._go("POST")
        def log_message(self, *a): pass

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve(sys.argv[1], int(sys.argv[2]))
