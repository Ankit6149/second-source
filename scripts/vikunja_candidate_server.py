"""Generic candidate server for the Vikunja benchmark.

Executes a candidate SPEC (JSON) authored by a model (or, for plumbing
validation only, a hand-written NON_AI oracle). The interpreter contains
no Vikunja-specific behavior: every externally observable decision Ã¢â‚¬â€
routes, methods, success statuses, validation, permissions, state
transitions Ã¢â‚¬â€ comes from the spec. State is in-memory, per-process.

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
        # Compiled routes (evidence_compiler.py): generic entity stores
        # keyed by collection name, with owner/share bookkeeping.
        self.stores: dict[str, dict[int, dict]] = {}
        self.shares: dict[int, dict[str, int]] = {}  # parent id -> user -> perm
        self._owners: dict[int, str] = {}            # top-level entity id -> alias

    def _id(self):
        self.next_id += 1
        return self.next_id

    def _user(self, headers):
        auth = headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return self.tokens.get(auth[7:])
        # Raw-header token kind (e.g. File Browser X-Auth raw string).
        # Header name comes from spec.auth, never hardcoded per app.
        raw_name = (self.spec.get("auth") or {}).get("raw_header_name")
        if raw_name:
            token = headers.get(raw_name, "")
            if token:
                return self.tokens.get(token)
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

    # --- Compiled routes: generic evidence-transcribed behavior ---
    def _fill_template(self, value, ctx):
        if isinstance(value, dict) and "$input" in value:
            req = ctx.get("request") or {}
            return req.get(value["$input"], value.get("default"))
        if isinstance(value, str):
            if value == "<entity:id>":
                return ctx.get("entity_id") or \
                    (ctx.get("creator") or {}).get("id")
            if value == "<new_id>":
                return self._id()
            if value == "<ts>":
                return "2026-01-01T00:00:00Z"
            if value == "<creator>":
                return ctx["creator"]
            if value == "<index>":
                return ctx.get("index", 1)
            if value == "<identifier>":
                return f"#{ctx.get('index', 1)}"
            if value.startswith("<input:") and value.endswith(">"):
                return (ctx.get("request") or {}).get(value[7:-1])
            if value.startswith("<path:") and value.endswith(">"):
                raw = ctx["params"].get(value[6:-1])
                if raw is None:
                    return value  # unresolved: merge rules prefer entity
                return int(raw) if str(raw).isdigit() else raw
            if value.startswith("<entity:") and value.endswith(">"):
                return ctx["entity"].get(value[8:-1])
            return value
        if isinstance(value, dict):
            return {k: self._fill_template(v, ctx) for k, v in value.items()}
        if isinstance(value, list):
            return [self._fill_template(v, ctx) for v in value]
        return value

    def _shape_fill(self, value, ctx_e, entity):
        if isinstance(value, str) and value.startswith("<"):
            if value == "<creator>":
                alias = entity.get("_owner")
                uname = self.spec.get("users", {}).get(alias, alias)
                rec = self.users.get(uname, {})
                return {"id": rec.get("id", 1), "name": "",
                        "username": uname,
                        "created": "2026-01-01T00:00:00Z",
                        "updated": "2026-01-01T00:00:00Z"}
            if value == "<identifier>":
                return f"#{entity.get('index', 1)}"
            if value == "<entity:id>":
                return entity.get("id")
        return self._fill_template(value, ctx_e)

    def _compiled_access(self, route, username, parent_id):
        access = route.get("access", "owner")
        if parent_id is None:
            return None
        # Ownership is tracked on the parent collection's first segment
        # store via the entity that owns this parent id.
        owner = self._owners.get(parent_id)
        if owner is None or owner == username:
            return None
        if access == "any_auth":
            return None
        perm = self.shares.get(parent_id, {}).get(username)
        if perm is not None and route["method"] == "GET":
            return None  # a share on the parent grants reads of children
        if access == "shared_read" and perm is not None:
            return None
        if access == "shared_write" and perm is not None and perm >= 1:
            return None
        if access == "shared_read" and route["method"] == "GET" and perm is not None:
            return None
        if route.get("forbidden_body") is not None:
            return 403, route["forbidden_body"]
        return self._forbidden()

    def _compiled(self, route, params, body, user, username):
        store = self.stores.setdefault(route["collection"], {})
        record = self.users.get(user, {})
        ctx = {"creator": {"id": record.get("id", 1), "name": "",
                           "username": user,
                           "created": "2026-01-01T00:00:00Z",
                           "updated": "2026-01-01T00:00:00Z"},
               "request": body or {}, "params": params, "entity": {},
               "query": getattr(self, "_query", "")}
        parent_raw = params.get("pid") or params.get("tid")
        if parent_raw is None:
            # Generic fallback: a single numeric path param (e.g. {id})
            # identifies the item, whatever its placeholder name is.
            numeric = [v for v in params.values() if str(v or "").isdigit()]
            parent_raw = numeric[-1] if len(numeric) == 1 else None
        parent_id = int(parent_raw) if str(parent_raw or "").isdigit() else None
        kind = route["kind"]
        status = route.get("status", 200)
        if kind == "compiled_single":
            return status, self._fill_template(route.get("template"), ctx)
        if kind == "compiled_create":
            if parent_id is not None:
                err = self._compiled_access(route, username, parent_id)
                if err:
                    return err
            dup_field = route.get("duplicate_field")
            if dup_field:
                payload = body or {}
                if isinstance(payload.get("data"), dict):
                    payload = payload["data"]
                want = payload.get(dup_field)
                if want is not None and any(
                        e.get(dup_field) == want for e in store.values()):
                    return route.get("duplicate_status", 500), route.get("duplicate_body")
            ctx["index"] = sum(1 for e in store.values()
                                if e.get("_parent") == parent_id) + 1
            ctx["entity_id"] = self._id()
            entity = self._fill_template(route.get("template"), ctx)
            if not isinstance(entity, dict):
                # Non-JSON success body (e.g. "201 Created"): the
                # created entity is described by the request payload,
                # unwrapping a {"data": {...}} envelope when present.
                payload = body or {}
                if isinstance(payload.get("data"), dict):
                    payload = payload["data"]
                entity = dict(payload) if isinstance(payload, dict) else {}
                entity.setdefault("id", ctx["entity_id"])
            if isinstance(entity, dict) and "id" in entity:
                entity["id"] = ctx["entity_id"]  # bind same-entity refs
            if isinstance(entity, dict):
                entity["_parent"] = parent_id
                entity["_owner"] = username
                import copy as _copy
                entity["_initial"] = _copy.deepcopy(
                    {k: v for k, v in entity.items() if not k.startswith("_")})
                store[entity.get("id")] = entity
                if parent_id is None:
                    self._owners[entity.get("id")] = username
            return status, {k: v for k, v in entity.items()
                            if not k.startswith("_")} \
                if isinstance(entity, dict) else entity
        if kind == "compiled_list":
            if parent_id is not None and not any(
                    e.get("id") == parent_id or e.get("_parent") == parent_id
                    for s in self.stores.values() for e in s.values()) \
                    and parent_id not in self._owners:
                fb = route.get("not_found_body")
                return (404, fb) if fb is not None else self._not_found()
            # Route-shape overlay: fields the list response itself
            # carries as null/object/empty differ per route from the
            # create shape; the observed list exemplar decides.
            template = route.get("template")
            exemplar = template[0] if isinstance(template, list) and template else {}
            if not isinstance(exemplar, dict):
                exemplar = {}
            overlay = {k: v for k, v in exemplar.items()
                       if v is None or isinstance(v, (dict, list))}
            # Model-proposed default seeding (gated experiment surface):
            # route.seed_defaults lists exemplar titles the reference
            # provides by default. Seed unseen ones for this user and
            # present seeded/created items in exemplar order.
            seed_titles = route.get("seed_defaults")
            if isinstance(seed_titles, list) and isinstance(template, list):
                known = {e.get("title") or e.get("name") for e in store.values()}
                for item in template:
                    if not isinstance(item, dict):
                        continue
                    label = item.get("title") or item.get("name")
                    if label in seed_titles and label not in known:
                        seed = self._fill_template(item, ctx)
                        if isinstance(seed, dict):
                            seed["id"] = self._id()
                            link_key = (route.get("collection") or "")[:-1] + "_id"
                            def _link(o):
                                if isinstance(o, dict):
                                    for k2, v2 in o.items():
                                        if k2 == link_key and (isinstance(v2, int) or (isinstance(v2, str) and v2.startswith("<path:"))):
                                            o[k2] = seed["id"]
                                        elif isinstance(v2, str) and v2.startswith("<path:"):
                                            o[k2] = self._id()
                                        else:
                                            _link(v2)
                                elif isinstance(o, list):
                                    for v2 in o:
                                        _link(v2)
                            _link(seed)
                            seed["_parent"] = None
                            seed["_owner"] = username
                            store[seed["id"]] = seed
                            known.add(label)
            items = []
            filtered_out = 0
            for entity in store.values():
                if parent_id is not None and entity.get("_parent") != parent_id:
                    continue
                err = self._compiled_access(route, username, entity.get("_parent") or entity.get("id"))
                if err and entity.get("_owner") != username:
                    filtered_out += 1
                    continue
                out = {k: v for k, v in entity.items()
                       if not k.startswith("_")}
                ctx_e = dict(ctx, entity=entity)
                for key, value in overlay.items():
                    if isinstance(value, (dict, list)) and \
                            out.get(key) not in (None, "", [], {}):
                        continue  # entity's own nested state wins
                    out[key] = self._shape_fill(value, ctx_e, entity)
                exemplar_tok = exemplar if isinstance(exemplar, dict) else {}
                for key, value in exemplar_tok.items():
                    if isinstance(value, str) and value.startswith("<") \
                            and out.get(key) in (None, ""):
                        out[key] = self._shape_fill(value, ctx_e, entity)
                items.append(out)
            if items == [] and store:
                owns_any = any(e.get("_owner") == username for e in store.values())
                if not owns_any and (route.get("access") == "owner" or filtered_out):
                    fb = route.get("forbidden_body")
                    return (403, fb) if fb is not None else self._forbidden()
            # Boolean query filters (e.g. ?filter=done%20%3D%20false):
            # generic field = true/false filtering over stored entities.
            query = ctx.get("query") or ""
            if "filter=" in query:
                import re as _re
                m = _re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(true|false)", query)
                if m:
                    field, want = m.group(1), m.group(2) == "true"
                    items = [i for i in items if i.get(field) is want]
            if isinstance(seed_titles, list) and isinstance(template, list):
                order = {}
                for item in template:
                    if isinstance(item, dict):
                        label = item.get("title") or item.get("name")
                        if label is not None and label not in order:
                            order[label] = len(order)
                items.sort(key=lambda i: order.get(i.get("title") or i.get("name"), 999))
            return status, items
        # Item routes resolve the entity by the trailing path param.
        entity = store.get(parent_id) if parent_id is not None else None
        if entity is None and params:
            # Name-addressed resources (e.g. /repos/{owner}/{repo-name}):
            # resolve by the observed name/title field, generically.
            trailing = list(params.values())[-1]
            for e in store.values():
                if e.get("name") == trailing or e.get("title") == trailing:
                    entity = e
                    break
        if entity is None:
            return self._not_found()
        err = self._compiled_access(
            route, username,
            entity.get("_parent", entity.get("id")))
        if err:
            return err
        if route["method"] == "DELETE":
            # HTTP DELETE semantics on the resolved entity (generic,
            # spec supplies only the success status/template).
            store.pop(entity.get("id"), None)
            return status, self._fill_template(route.get("template"), ctx)
        if kind == "compiled_get":
            out = {k: v for k, v in entity.items()
                   if not k.startswith("_")}
            template = route.get("template")
            if isinstance(template, dict):
                ctx_e = dict(ctx, entity=entity)
                for key, value in template.items():
                    if value is None or isinstance(value, (dict, list)):
                        out[key] = self._shape_fill(value, ctx_e, entity)
                    elif isinstance(value, str) and value.startswith("<") \
                            and out.get(key) in (None, ""):
                        out[key] = self._shape_fill(value, ctx_e, entity)
            return status, out
        if kind == "compiled_share":
            target = (body or {}).get("username")
            target_alias = {v: k for k, v in self.spec.get("users", {}).items()}.get(target, target)
            self.shares.setdefault(entity.get("id"), {})[target_alias] = \
                int((body or {}).get("permission", 0))
            ctx["entity"] = entity
            out = self._fill_template(route.get("template"), ctx)
            return status, out
        if kind == "compiled_update":
            prev_done_at = entity.get("done_at")
            raw_template = route.get("template")
            if isinstance(raw_template, dict):
                keep = {k: entity.get(k)
                        for k in ("_parent", "_owner", "_initial", "id")}
                filled_old = self._fill_template(
                    raw_template, dict(ctx, entity=entity))
                fresh = {}
                for k, raw in raw_template.items():
                    if isinstance(raw, (dict, list)) or \
                            (isinstance(raw, str) and raw.startswith("<")):
                        fresh[k] = entity.get(k) if entity.get(k) not in (None, "") \
                            else filled_old.get(k)
                    elif isinstance(raw, bool):
                        fresh[k] = False
                    elif isinstance(raw, (int, float)):
                        fresh[k] = 0
                    elif isinstance(raw, str) and (
                            raw.endswith("Z") or k.endswith(("_at", "_date"))
                            or k in ("created", "updated")):
                        fresh[k] = entity.get(k)
                    elif isinstance(raw, str) and k in ("title", "name"):
                        fresh[k] = entity.get(k)
                    elif isinstance(raw, str):
                        fresh[k] = ""
                    else:
                        fresh[k] = None
                entity.clear()
                entity.update(fresh)
                entity.update(keep)
            for key, value in (body or {}).items():
                entity[key] = value
            ctx["entity"] = entity
            filled = self._fill_template(route.get("template"), ctx)
            # Entity data wins for scalars (the template's exemplar
            # literals describe the probe's entity, not this one);
            # template wins for shape fields (null/object/list) and
            # timestamps the update itself produces.
            out = dict(filled) if isinstance(filled, dict) else {}
            for key, value in entity.items():
                if key.startswith("_"):
                    continue
                current = out.get(key)
                unresolved = isinstance(current, str) and current.startswith("<")
                # Entity wins for data scalars; an observed EMPTY
                # string in the update shape is a shape signal and
                # the template keeps it.
                if key not in out or unresolved or (current not in (None, "")
                        and not isinstance(current, (dict, list))):
                    out[key] = value
            if isinstance(out, dict) and (body or {}).get("done") is True \
                    and "done_at" in filled:
                out["done_at"] = filled["done_at"]
            if isinstance(out, dict) and (body or {}).get("done") is False \
                    and "done_at" in out:
                out["done_at"] = prev_done_at  # restore observed undone shape
            if isinstance(out, dict):
                for key, value in out.items():
                    # Response-shape nulls/empty strings are not state:
                    # never let an update's shape erase a stored value.
                    if value in (None, "") and entity.get(key) not in (None, ""):
                        continue
                    entity[key] = value
            return status, out if isinstance(out, dict) else entity
        return 404, {"message": "unimplemented compiled kind"}

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
        if isinstance(kind, str) and kind.startswith("compiled"):
            from urllib.parse import unquote_plus as _uq
            self._query = _uq(raw_path.split("?", 1)[1]) if "?" in raw_path else ""
            return self._compiled(route, params, body, user, username)
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
        def do_DELETE(self): self._go("DELETE")
        def log_message(self, *a): pass

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve(sys.argv[1], int(sys.argv[2]))

