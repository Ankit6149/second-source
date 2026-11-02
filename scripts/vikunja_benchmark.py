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
    ("GET", "/user", None, None),
]

HELD_OUT = [
    [("PUT", "/projects", {"title": "Held A"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Write report", "priority": 5}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Review report"}, "alice"),
     ("GET", "/projects/{pid}/tasks", None, "alice")],
    [("PUT", "/projects", {"title": ""}, "alice")],
    [("PUT", "/projects", {"title": "Held B"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Toggle me"}, "alice"),
     ("POST", "/tasks/{tid}", {"done": True}, "alice"),
     ("POST", "/tasks/{tid}", {"done": False}, "alice"),
     ("GET", "/tasks/{tid}", None, "alice")],
    [("POST", "/login", {"username": "bench_alice", "password": "wrong"}, "anon")],
    [("GET", "/projects", None, "bob_fresh")],
]


def run_actions(actions, tokens, base=BASE):
    ids = {}
    results = []
    for method, path, body, who in actions:
        token = tokens.get(who)
        p = path.format(pid=ids.get("pid", 0), tid=ids.get("tid", 0))
        status, out = call(method, p, body, token, base)
        if isinstance(out, dict):
            if "id" in out and "/projects" in p and method in ("POST", "PUT") and p.count("/") == 2:
                ids["pid"] = out["id"]
            if "id" in out and "/tasks" in p and method in ("POST", "PUT"):
                ids["tid"] = out["id"]
        results.append({"status": status, "body": out})
    return results


def canonical(value, id_map, counter):
    if isinstance(value, dict):
        out = {}
        for key in sorted(value):
            if key in VOLATILE_KEYS:
                out[key] = "<ts>" if value[key] else value[key]
            elif key in POSITIONAL_KEYS:
                out[key] = "<pos>"
            elif (key == "id" or key.endswith("_id")) and isinstance(value[key], int):
                if value[key] not in id_map:
                    counter[0] += 1
                    id_map[value[key]] = f"<id{counter[0]}>"
                out[key] = id_map[value[key]]
            elif key == "token":
                out[key] = "<token>"
            else:
                out[key] = canonical(value[key], id_map, counter)
        return out
    if isinstance(value, list):
        return [canonical(v, id_map, counter) for v in value]
    return value


def canonical_result(result):
    return {"status": result["status"],
            "body": canonical(result["body"], {}, [0])}


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
        observations.append({"action": f"{method} {path}", "as": who,
                             "status": status, "body": out})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "public_observations.json").write_text(
        json.dumps(observations, indent=1), encoding="utf-8")
    print(f"probes: {len(observations)} observations -> {OUT / 'public_observations.json'}")
    for o in observations:
        print(" ", o["status"], o["action"])
    return 0


def mode_evaluate(candidate_url=None):
    cand_base = candidate_url.rstrip("/") + "/api/v1" if candidate_url else None
    passed = total = 0
    for i, seq in enumerate(HELD_OUT):
        ref = [canonical_result(r) for r in run_actions(seq, fresh_tokens())]
        if cand_base:
            got = [canonical_result(r) for r in run_actions(seq, fresh_tokens(cand_base), cand_base)]
        else:
            got = ref  # self-check placeholder replaced below
        if not cand_base:
            got = [canonical_result(r) for r in run_actions(seq, fresh_tokens())]
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
    args = ap.parse_args()
    if args.mode == "probe":
        return mode_probe()
    return mode_evaluate(args.candidate_url)


if __name__ == "__main__":
    raise SystemExit(main())
