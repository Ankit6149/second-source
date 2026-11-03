"""Candidate DSL interpreter for Behavioral IR v2.

Executes a BehavioralIR generically (no application field names):
in-memory stores per resource, dynamic ids, server timestamps from an
injected clock, conditional fields, validation/error contracts, auth,
owner/shared permissions, relationships via shares, state transitions,
and dependency (parent-exists) checks. State is per-instance.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from behavioral_ir import ValueKind  # noqa: E402

ZERO_TIME = "0001-01-01T00:00:00Z"


class BehavioralInterpreter:
    def __init__(self, ir, clock=None):
        self.ir = ir.require_valid()
        self.clock = clock or (lambda: "2026-01-01T00:00:00Z")
        self.stores = {r.name: {} for r in ir.resources}
        self.owners = {}   # (resource, id) -> actor
        self.shares = {}   # (resource, id) -> {actor: permission_int}
        self._next = 0

    def _id(self):
        self._next += 1
        return self._next

    def _match(self, method, path):
        parts = [p for p in path.split("/") if p]
        for op in self.ir.operations:
            if op.method != method:
                continue
            pat = [p for p in op.path.split("/") if p]
            if len(pat) != len(parts):
                continue
            params, ok = {}, True
            for want, got in zip(pat, parts):
                if want.startswith("{"):
                    params[want[1:-1]] = got
                elif want != got:
                    ok = False
                    break
            if ok:
                return op, params
        return None, {}

    def _permitted(self, op, resource, entity_id, actor, write=False):
        if actor is None:
            return False
        if op.permission == "any_auth":
            return True
        if self.owners.get((resource, entity_id)) == actor:
            return True
        perm = self.shares.get((resource, entity_id), {}).get(actor)
        if op.permission == "owner":
            return False
        if op.permission == "owner_or_read":
            return perm is not None and not write
        if op.permission == "owner_or_write":
            return perm is not None and perm >= 1
        return False

    def _render(self, op, body, actor, entity_id=None):
        out = {}
        ctx_index = entity_id if isinstance(entity_id, int) else 0
        for f in op.fields:
            if f.condition:
                # Only supported condition form: permission>=N (share echoes)
                if f.condition.startswith("permission>="):
                    try:
                        need = int(f.condition.split(">=", 1)[1])
                    except ValueError:
                        continue
                    if not isinstance(body, dict) or int(body.get("permission", 0)) < need:
                        continue
                else:
                    continue
            if f.value_kind == ValueKind.DYNAMIC_ID:
                out[f.name] = entity_id if entity_id is not None else self._id()
            elif f.value_kind == ValueKind.TIMESTAMP:
                # Observed timestamp *shape* is protected; value is server time.
                out[f.name] = self.clock()
            elif f.value_kind == ValueKind.INPUT_ECHO:
                out[f.name] = (body or {}).get(f.input_field, f.exact_value)
            elif f.value_kind == ValueKind.CREATOR:
                out[f.name] = {"username": actor}
            elif f.value_kind == ValueKind.DERIVED:
                out[f.name] = f"#{ctx_index}" if f.exact_value == "<identifier>" else f.exact_value
            else:
                out[f.name] = f.exact_value
        return out

    def handle(self, method, path, actor=None, body=None):
        """Return (status, payload). ``actor`` is the authenticated alias."""
        op, params = self._match(method, path.split("?")[0])
        if op is None:
            return 404, {"message": "not found"}
        if op.auth and actor is None:
            err = next((e for e in op.errors if e.kind == "unauthenticated"), None)
            return self.ir.auth.unauthenticated_status, (err.body if err else {"message": "unauthorized"})
        resource = op.resource
        store = self.stores.setdefault(resource, {}) if resource else {}
        # validation
        for rule in op.validate:
            value = (body or {}).get(rule.field)
            if rule.rule == "nonempty" and (value is None or str(value).strip() == ""):
                return rule.status, rule.error_body or {"message": f"invalid {rule.field}"}
        # dependency: parent path id must exist
        parent_id = None
        for dep in list(op.dependencies) + list(self.ir.dependencies):
            if dep.operation in (op.name, "*") and dep.kind == "exists":
                for v in params.values():
                    try:
                        if int(v) not in store and dep.requires == resource:
                            return 404, {"message": "dependency not found"}
                    except (TypeError, ValueError):
                        pass
        ids = [int(v) for v in params.values() if str(v).isdigit()]
        entity_id = ids[-1] if ids else None

        if op.kind in ("create", "compiled_create"):
            new_id = self._id()
            entity = self._render(op, body, actor, entity_id=new_id)
            entity.setdefault(self.ir.resource(resource).id_field if resource and self.ir.resource(resource) else "id", new_id)
            store[new_id] = entity
            self.owners[(resource, new_id)] = actor
            return op.status, entity
        if op.kind in ("list", "compiled_list"):
            items = [e for eid, e in sorted(store.items())
                     if self._permitted(op, resource, eid, actor)]
            return op.status, items
        if op.kind in ("get", "compiled_get", "compiled_single"):
            if entity_id is None or entity_id not in store:
                err = next((e for e in op.errors if e.kind == "not_found"), None)
                return 404, (err.body if err else {"message": "not found"})
            if not self._permitted(op, resource, entity_id, actor):
                err = next((e for e in op.errors if e.kind == "forbidden"), None)
                return 403, (err.body if err else {"message": "forbidden"})
            return op.status, store[entity_id]
        if op.kind in ("update", "compiled_update"):
            if entity_id is None or entity_id not in store:
                return 404, {"message": "not found"}
            if not self._permitted(op, resource, entity_id, actor, write=True):
                return 403, {"message": "forbidden"}
            current = store[entity_id]
            for t in op.transitions:
                if t.field in (body or {}) and current.get(t.field) == t.from_value \
                        and body[t.field] == t.to_value and not t.allowed:
                    return t.status_on_denied, {"message": "transition denied"}
            current.update({k: v for k, v in (body or {}).items()})
            return op.status, current
        if op.kind in ("share", "compiled_share"):
            if entity_id is None or entity_id not in store:
                return 404, {"message": "not found"}
            if self.owners.get((resource, entity_id)) != actor:
                return 403, {"message": "forbidden"}
            target = (body or {}).get("username", (body or {}).get("user", ""))
            self.shares.setdefault((resource, entity_id), {})[target] = int(
                (body or {}).get("permission", 0))
            return op.status, self._render(op, body, actor, entity_id=entity_id) or {"ok": True}
        # custom: render template only
        return op.status, self._render(op, body, actor, entity_id=entity_id)
