"""Vikunja professional-benchmark harness (NON_AI infrastructure).

Modes:
  probe    -- run the public discovery ladder against the reference and
              save observations JSON (what a reconstruction agent may see).
  evaluate -- run frozen held-out sequences against reference and, when
              --candidate-url is given, a candidate implementation.
              Without a candidate this is a reference self-check that
              validates reset + canonicalization soundness.

Black-box only: HTTP against 127.0.0.1. No reference source, no model
calls. Held-out sequences in this file are evaluator-side material and
must never be copied into model context.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:3456/api/v1"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".runs" / "vikunja-benchmark"

ALICE = {"username": "bench_alice", "email": "alice@bench.local", "password": "BenchPass123!"}
BOB = {"username": "bench_bob", "email": "bob@bench.local", "password": "BenchPass456!"}

VOLATILE_KEYS = {"created", "updated", "done_at"}
# Server-assigned ordering counters: presence is behavior, exact value is
# global server state accumulated across runs, not case behavior.
POSITIONAL_KEYS = {"position"}


def call(method, path, body=None, token=None, base=BASE):
    req = urllib.request.Request(base + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, data=data, timeout=20) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:200]}


def login(user, base=BASE):
    # Reference rate-limits auth (observed 429): bounded backoff, then fail.
    import time
    for attempt in range(4):
        status, body = call("POST", "/login",
                            {"username": user["username"], "password": user["password"]}, base=base)
        if status == 200 and body.get("token"):
            return body["token"]
        if status != 429:
            break
        time.sleep(15 * (attempt + 1))
    raise AssertionError(f"login failed: {status} {body}")


def ensure_user(user, base=BASE):
    call("POST", "/register", user, base=base)
    return login(user, base)


# A probe/action is (method, path_template, body, user) where {pid}/{tid}
# are filled from previously created project/task ids.
PUBLIC_PROBES = [
    ("PUT", "/projects", {"title": "Bench Project"}, "alice"),
    ("PUT", "/projects/{pid}/tasks", {"title": "First task", "description": "d", "priority": 3}, "alice"),
    ("PUT", "/projects/{pid}/tasks", {"title": ""}, "alice"),
    ("GET", "/projects/{pid}/tasks", None, "alice"),
    ("POST", "/tasks/{tid}", {"done": True}, "alice"),
    ("GET", "/projects/{pid}/tasks?filter=done%20%3D%20false", None, "alice"),
    ("GET", "/projects/999999/tasks", None, "alice"),
    ("GET", "/projects/{pid}/tasks", None, "bob"),
    ("GET", "/tasks/{tid}", None, "bob"),
    ("GET", "/user", None, None),
    ("PUT", "/projects/{pid}/users", {"username": "bench_bob", "permission": 0}, "alice"),
    ("GET", "/projects/{pid}/tasks", None, "bob"),
    ("POST", "/tasks/{tid}", {"done": True}, "bob"),
    ("PUT", "/projects", {"title": ""}, "alice"),
    ("POST", "/login", {"username": "bench_alice", "password": "wrong"}, "anon"),
    ("GET", "/projects", None, "alice"),
    ("GET", "/tasks/{tid}", None, "alice"),
    ("GET", "/user", None, "alice"),
    ("PUT", "/projects/{pid}/tasks", {"title": "Bob attempt"}, "bob"),
]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vikunja_held_out import HELD_OUT  # evaluator-only; see that module


def run_actions(actions, tokens, base=BASE):
    ids = {}
    results = []
    for method, path, body, who in actions:
        token = tokens.get(who)
        p = path.format(pid=ids.get("pid", 0), tid=ids.get("tid", 0))
        status, out = call(method, p, body, token, base)
        if isinstance(out, dict):
            # Only a project creation binds {pid}: any other 1-segment
            # create (e.g. PUT /labels) must not overwrite it.
            if "id" in out and method in ("POST", "PUT") and p.rstrip("/") == "/projects":
                ids["pid"] = out["id"]
            if "id" in out and "/tasks" in p and method in ("POST", "PUT"):
                ids["tid"] = out["id"]
        results.append({"status": status, "body": out})
    return results


def _id_namespace(key, parent):
    """Server ids are per-entity-type sequences (project 1 and task 1
    coexist), so placeholders are namespaced by entity, not global.
    Unknown shapes fall back to a shape fingerprint — never a shared
    bucket that would merge distinct entity types."""
    if key == "id":
        if "permission" in parent and "username" in parent:
            return "share"
        if "done" in parent:
            return "task"
        if "views" in parent or "owner" in parent or "max_permission" in parent:
            return "project"
        if "username" in parent:
            return "user"
        if "view_kind" in parent:
            return "view"
        shape = "|".join(sorted(k for k in parent
                                if k not in VOLATILE_KEYS and k != "id"))
        return f"shape:{shape}"
    base = key[:-3]
    return {"project": "project", "parent_project": "project",
            "user": "user", "bucket": "bucket", "default_bucket": "bucket",
            "done_bucket": "bucket", "label": "label",
            "task": "task"}.get(base, base)


def canonical(value, id_map, counter, ranked=False, view_ns=None):
    if view_ns is None:
        view_ns = ({}, {})
    if isinstance(value, dict):
        out = {}
        for key in sorted(value):
            if key == "views" and isinstance(value[key], list):
                # Default view sub-ids live in their own namespace so
                # server-generated view counters cannot shift the main
                # entity-id placeholders.
                out[key] = canonical(value[key], view_ns[0], view_ns[1],
                                     ranked=ranked, view_ns=view_ns)
                continue
            if key in VOLATILE_KEYS:
                out[key] = "<ts>" if value[key] else value[key]
            elif key in POSITIONAL_KEYS:
                # Ranked by the enclosing list, or erased as server state.
                out[key] = value[key] if ranked else "<pos>"
            elif (key == "id" or key.endswith("_id")) and isinstance(value[key], int):
                if key == "id" and isinstance(value.get("username"), str):
                    # User-shaped objects are identified by username so
                    # the same user keeps one placeholder across shapes
                    # (profile, created_by, share rows). Two shares for
                    # one user in a sequence would merge; our bounded
                    # scope has at most one.
                    out[key] = f"<user:{value['username']}>"
                    continue
                ns = _id_namespace(key, value)
                map_key = (ns, value[key])
                if map_key not in id_map:
                    counter[ns] = counter.get(ns, 0) + 1
                    id_map[map_key] = f"<{ns}-{counter[ns]}>"
                out[key] = id_map[map_key]
            elif key == "token":
                out[key] = "<token>"
            else:
                out[key] = canonical(value[key], id_map, counter, view_ns=view_ns)
        return out
    if isinstance(value, list):
        items = list(value)
        # Ordering behavior matters, counter magnitude does not: rank
        # positions within a list instead of erasing them.
        ranked_items = False
        if items and all(isinstance(v, dict) and isinstance(v.get("position"), (int, float))
                         for v in items):
            order = sorted({v["position"] for v in items})
            rank = {p: i for i, p in enumerate(order)}
            items = [{**v, "position": rank[v["position"]]} for v in items]
            ranked_items = True
        return [canonical(v, id_map, counter, ranked=ranked_items, view_ns=view_ns)
                for v in items]
    return value


def canonical_sequence(results):
    """Canonicalize a whole sequence with ONE id map: the same server id
    must map to the same placeholder at every step, or cross-response
    identity relationships are silently lost."""
    id_map, counter, view_ns = {}, {}, ({}, {})
    return [{"status": r["status"],
             "body": canonical(r["body"], id_map, counter, view_ns=view_ns)}
            for r in results]


_TOKEN_CACHE: dict[str, dict] = {}


def fresh_tokens(base=BASE):
    # Vikunja rate-limits login (observed HTTP 429): register/login once
    # per base URL and reuse tokens across cases.
    if base not in _TOKEN_CACHE:
        alice = ensure_user(ALICE, base)
        bob = ensure_user(BOB, base)
        _TOKEN_CACHE[base] = {"alice": alice, "bob": bob,
                              "anon": None, "bob_fresh": bob}
    return _TOKEN_CACHE[base]


def mode_probe():
    tokens = fresh_tokens()
    observations = []
    status, info = call("GET", "/info")
    observations.append({"action": "GET /info", "status": status, "body": info})
    ids = {}
    for method, path, body, who in PUBLIC_PROBES:
        p = path.format(pid=ids.get("pid", 0), tid=ids.get("tid", 0))
        status, out = call(method, p, body, tokens.get(who))
        if isinstance(out, dict) and "id" in out:
            if p == "/projects":
                ids["pid"] = out["id"]
            elif "/tasks" in p:
                ids["tid"] = out["id"]
        # Lossless evidence: request AND response, actor, and order.
        observations.append({"action": f"{method} {path}", "as": who,
                             "request": body, "status": status, "body": out})
    OUT.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(observations, indent=1)
    # Bytes, not text: text mode would translate newlines on Windows and
    # the file would no longer match its own recorded hash.
    (OUT / "public_observations.json").write_bytes(payload.encode("utf-8"))
    # Original evidence is hashed; every derived summary references this.
    import hashlib
    (OUT / "public_observations.sha256").write_bytes(
        ("sha256:" + hashlib.sha256(payload.encode()).hexdigest()).encode("utf-8"))
    print(f"probes: {len(observations)} observations -> {OUT / 'public_observations.json'}")
    for o in observations:
        print(" ", o["status"], o["action"])
    return 0


def mode_evaluate(candidate_url=None, reference_url=None):
    global BASE
    if reference_url:
        BASE = reference_url.rstrip("/") + "/api/v1"
    cand_base = candidate_url.rstrip("/") + "/api/v1" if candidate_url else None
    passed = total = 0
    for i, seq in enumerate(HELD_OUT):
        ref = canonical_sequence(run_actions(seq, fresh_tokens(BASE), BASE))
        if cand_base:
            got = canonical_sequence(run_actions(seq, fresh_tokens(cand_base), cand_base))
        else:
            got = canonical_sequence(run_actions(seq, fresh_tokens(BASE), BASE))
        ok = ref == got
        total += 1
        passed += ok
        print(f"  case {i}: {'PASS' if ok else 'FAIL'}")
        if not ok:
            for j, (a, b) in enumerate(zip(ref, got)):
                if a != b:
                    print(f"    step {j}: ref={json.dumps(a)[:160]}")
                    print(f"    step {j}: got={json.dumps(b)[:160]}")
    print(f"held-out: {passed}/{total} ({'candidate' if cand_base else 'reference self-check'})")
    return 0 if passed == total else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["probe", "evaluate"], required=True)
    ap.add_argument("--candidate-url")
    ap.add_argument("--reference-url")
    args = ap.parse_args()
    if args.mode == "probe":
        return mode_probe()
    return mode_evaluate(args.candidate_url, args.reference_url)


if __name__ == "__main__":
    raise SystemExit(main())
