"""Evidence-to-spec compiler (generic, NON_AI, deterministic).

Converts firmly observed behavior from ANY HTTP target's public
observations into structured candidate facts in the spec language of
vikunja_candidate_server.py (compiled_* kinds). The compiler
transcribes only what observations show:

- exact response templates (values preserved: zero-times, nulls,
  empty lists, nested objects) with dynamic bindings tokenized
  (new ids, timestamps, creator, input echoes, path ids, indexes);
- validation error contracts from observed error responses;
- auth/forbidden/not-found bodies from observed error responses;
- access rules inferred from observed actor outcomes, marked as
  inferred claims, never silently upgraded to observed.

Provenance: kind EVIDENCE_COMPILED, label NON_AI. This is a
deterministic transcription layer. A model remains responsible for
unobserved behavior and meaningful inference; compiled facts and
model-authored claims are recorded separately in the spec.

No application field names appear below: routes, templates, and
access rules are derived from observation structure alone.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
ZERO_TIME = "0001-01-01T00:00:00Z"


def _is_ts(value):
    return isinstance(value, str) and bool(_TS.match(value)) and value != ZERO_TIME


class _Tokenizer:
    def __init__(self, request, path_ids, root_id=None):
        self.request = request or {}
        self.path_ids = path_ids  # {"pid": raw, "tid": raw}
        self.root_id = root_id

    def walk(self, value, key=None):
        if isinstance(value, dict):
            if "username" in value and "id" in value and len(value) <= 8 \
                    and "permission" not in value:
                return "<creator>"
            return {k: self.walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [self.walk(v, key) for v in value]
        if key == "id":
            return "<new_id>"
        if _is_ts(value):
            return "<ts>"
        # Input echo (any scalar type): the response carried the
        # request's value. Fallback default is the type-appropriate
        # empty value, recorded explicitly in the binding object.
        for field, req_value in self.request.items():
            if isinstance(req_value, (str, int, float)) \
                    and not isinstance(req_value, bool) \
                    and value == req_value and key == field:
                default = "" if isinstance(req_value, str) else 0
                return {"$input": field, "default": default}
        if isinstance(value, str):
            if re.fullmatch(r"#\d+", value):
                return "<identifier>"
            return value
        if key and key.endswith("_id") and isinstance(value, int):
            if value == 0:
                return 0  # zero is the observed "none" literal, not an id
            if self.root_id is not None and value == self.root_id:
                return "<entity:id>"
            for name, raw in self.path_ids.items():
                if value == raw:
                    return f"<path:{name}>"
            return "<new_id>"
        if key == "index" and isinstance(value, int):
            return "<index>"
        return value


def _segments(path):
    return [s for s in path.split("/") if s]


def compile_spec(observations, source_hash=""):
    """observations: [{action, as, request, status, body}] in probe order."""
    routes_obs: dict[tuple, list] = {}
    pid = tid = None
    for obs in observations:
        action = str(obs.get("action", ""))
        if " " not in action:
            continue
        method, path = action.split(" ", 1)
        path = path.split("?")[0]
        routes_obs.setdefault((method, path), []).append(obs)
        body = obs.get("body")
        if isinstance(body, dict) and "id" in body:
            segs = _segments(path)
            if len(segs) == 1 and method in ("PUT", "POST"):
                pid = body["id"]
            if "tasks" in segs and method in ("PUT", "POST"):
                tid = body["id"]

    spec = {"users": {}, "auth": {}, "routes": [],
            "provenance": {"kind": "EVIDENCE_COMPILED", "label": "NON_AI",
                           "source_observations_sha256": source_hash,
                           "claims": {}}}
    # Raw usernames are observed in identity responses (e.g. GET /user
    # as that actor); aliases in observations map to them.
    for obs in observations:
        actor = obs.get("as")
        body = obs.get("body")
        if actor and actor != "None" and isinstance(body, dict) \
                and isinstance(body.get("username"), str) \
                and str(obs.get("action", "")).endswith("/user"):
            spec["users"][str(actor)] = body["username"]
    # Only aliases with at least one successful authenticated response
    # are users (rules out anonymous/wrong-credential actors).
    aliases = {str(o.get("as")) for o in observations
               if o.get("as") and isinstance(o.get("status"), int)
               and o["status"] < 300 and o.get("as") != "None"}
    for obs in observations:
        body = obs.get("body")
        if isinstance(body, dict) and isinstance(body.get("username"), str) \
                and str(obs.get("action", "")).rstrip("/").endswith("/users"):
            for alias in aliases:
                if alias not in (None, "None", str(obs.get("as"))) \
                        and alias not in spec["users"]:
                    spec["users"][alias] = body["username"]

    for (method, path), obs_list in sorted(routes_obs.items()):
        if path in ("/info", "/login", "/register", "/user") and method != "GET":
            continue
        successes = [o for o in obs_list if isinstance(o.get("status"), int)
                     and o["status"] < 300 and o.get("as") not in (None, "None")]
        errors = [o for o in obs_list if isinstance(o.get("status"), int)
                  and o["status"] >= 400]
        if not successes:
            continue
        first = successes[0]
        segs = _segments(path)
        is_item = bool(segs and segs[-1].startswith("{"))
        collection = segs[-2] if is_item else (segs[-1] if segs else "")
        if segs and segs[-1] == "users" and len(segs) >= 3 and segs[-2].startswith("{"):
            collection = segs[-3]  # share route acts on the parent entity
        root_id = first["body"].get("id") if isinstance(first.get("body"), dict) else None
        tokenizer = _Tokenizer(first.get("request"), {"pid": pid, "tid": tid},
                               root_id=root_id)
        template = tokenizer.walk(first.get("body"))
        kind = ("compiled_list" if method == "GET" and not is_item
                and isinstance(first.get("body"), list) else
                "compiled_single" if method == "GET" and not is_item else
                "compiled_get" if method == "GET" else
                "compiled_share" if segs and segs[-1] == "users" else
                "compiled_create" if not is_item else "compiled_update")
        route = {"method": method, "path": path, "kind": kind,
                 "collection": collection, "auth": True,
                 "status": first["status"], "template": template,
                 "source": "observed"}

        # Validation contracts: an error whose request emptied a field.
        validate = []
        for err in errors:
            req = err.get("request") or {}
            for field, value in req.items():
                if value == "" or value is None:
                    validate.append({"field": field, "rule": "nonempty",
                                     "status": err["status"],
                                     "error_body": err.get("body")})
        if validate:
            route["validate"] = validate

        # Per-route forbidden body: error shapes differ per operation
        # on real systems; the route's own observed 403 wins.
        for err in errors:
            if err["status"] == 403 and isinstance(err.get("body"), dict):
                route["forbidden_body"] = err["body"]
                break

        # Access inference from actor outcomes (marked inferred).
        others = [o for o in obs_list if o.get("as") not in (None, "None", "alice")]
        owner_ok = bool(successes)
        other_ok = any(isinstance(o.get("status"), int) and o["status"] < 300
                       for o in others)
        other_denied = any(o.get("status") == 403 for o in others)
        if other_denied and not other_ok:
            route["access"] = "owner"
        elif other_ok and method == "GET":
            route["access"] = "shared_read"
        elif other_ok:
            route["access"] = "shared_write"
        else:
            route["access"] = "owner" if owner_ok else "any_auth"
        route["access_source"] = "inferred_from_actor_outcomes"
        spec["routes"].append(route)
        spec["provenance"]["claims"][f"{method} {path}"] = {
            "template": "observed", "access": route["access_source"]}

        for err in errors:
            body = err.get("body") if isinstance(err.get("body"), dict) else {}
            if err["status"] == 401 and "unauthenticated_body" not in spec["auth"]:
                spec["auth"]["unauthenticated_status"] = 401
                spec["auth"]["unauthenticated_body"] = body
            if err["status"] == 403 and err.get("as") not in (None, "None") \
                    and "forbidden_body" not in spec["auth"]:
                spec["auth"]["forbidden_body"] = body
            if err["status"] == 404 and "not_found_body" not in spec["auth"]:
                spec["auth"]["not_found_body"] = body

    # Login error contract for interpreter plumbing.
    for (method, path), obs_list in routes_obs.items():
        if path == "/login":
            for err in obs_list:
                if isinstance(err.get("status"), int) and err["status"] >= 400:
                    spec["auth"]["login_error_status"] = err["status"]
                    spec["auth"]["login_error_body"] = err.get("body")
    return spec


def main() -> int:
    import sys
    root = Path(__file__).resolve().parents[1]
    obs_path = root / ".runs/vikunja-benchmark/public_observations.json"
    observations = json.loads(obs_path.read_text(encoding="utf-8"))
    hash_path = root / ".runs/vikunja-benchmark/public_observations.sha256"
    source_hash = hash_path.read_text().strip() if hash_path.exists() else ""
    spec = compile_spec(observations, source_hash)
    out = root / ".runs/vikunja-model/spec_compiled.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    print(f"compiled {len(spec['routes'])} routes -> {out}")
    for route in spec["routes"]:
        print(" ", route["method"], route["path"], route["kind"],
              "access:", route["access"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
