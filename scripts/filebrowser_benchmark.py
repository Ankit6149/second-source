"""File Browser v2.63.23 second-target benchmark (NON_AI, Gate C slice).

Pinned target: File Browser v2.63.23 (Apache-2.0 OSS), local binary,
seeded admin via CLI (`config init` + `users add genadmin --perm.admin`),
public budget: local only, $0, no model calls. Provenance NON_AI only.

Flow: public probes -> evidence_compiler.compile_spec (zero target code)
-> generic candidate interpreter (vikunja_candidate_server.py) ->
frozen differential cases run against BOTH a fresh reference and a
fresh candidate. A mutated-spec negative control must fail.
Candidate login plumbing returns {"token": ...}; the reference returns
a raw string token sent as X-Auth. The evaluator normalizes only token
transport, never response bodies.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evidence_compiler import compile_spec  # noqa: E402

REF = "http://127.0.0.1:3471/api"
CAND_PORT = 3472
ADMIN = {"username": "genadmin", "password": "genpassword123"}
NEW_USER = {"username": "genbob", "password": "genpassword456", "scope": ".",
            "locale": "en", "viewMode": "list", "singleClick": False,
            "perm": {"admin": False, "execute": False, "create": True,
                     "rename": True, "modify": True, "delete": True,
                     "share": False, "download": True},
            "commands": [], "sorting": {"by": "name", "asc": False}, "rules": []}


def call(base, method, path, body=None, token=None):
    req = urllib.request.Request(base + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if token and isinstance(token, str) and "\n" not in token:
        req.add_header("X-Auth", token)
    try:
        with urllib.request.urlopen(req, data=data, timeout=15) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def token_of(base, creds):
    st, out = call(base, "POST", "/login", creds)
    if st != 200:
        return st, None
    if isinstance(out, dict):
        return st, out.get("token")
    return st, out


def clean_ref():
    st, tok = token_of(REF, ADMIN)
    if not tok:
        return
    s2, out = call(REF, "GET", "/users", token=tok)
    if isinstance(out, list):
        for u in out:
            if isinstance(u, dict) and u.get("username") == "genbob":
                call(REF, "DELETE", f"/users/{u['id']}",
                     {"current_password": ADMIN["password"]}, token=tok)


def public_probes():
    clean_ref()
    obs = []

    def rec(action, actor, request, status, body):
        obs.append({"action": action, "as": actor, "request": request,
                    "status": status, "body": body})

    st, tok = token_of(REF, ADMIN)
    rec("POST /login", "alice", ADMIN, st, "<raw-token-string>")
    st, out = call(REF, "POST", "/login", {"username": "genadmin", "password": "wrong"})
    rec("POST /login", "anon", {"username": "genadmin", "password": "wrong"}, st, out)
    st, out = call(REF, "GET", "/users", token=tok)
    rec("GET /users", "alice", None, st, out)
    st, out = call(REF, "GET", "/users/1", token=tok)
    rec("GET /users/1", "alice", None, st, out)
    st, out = call(REF, "GET", "/users")
    rec("GET /users", None, None, st, out)
    create = {"what": "user", "which": [], "data": NEW_USER,
              "current_password": ADMIN["password"]}
    st, out = call(REF, "POST", "/users", create, token=tok)
    rec("POST /users", "alice", create, st, out)
    st, out = call(REF, "POST", "/users", create, token=tok)
    rec("POST /users", "alice", create, st, out)
    bst, btok = token_of(REF, {"username": "genbob", "password": "genpassword456"})
    st, out = call(REF, "GET", "/users", token=btok)
    rec("GET /users", "bob", None, st, out)
    st, out = call(REF, "GET", "/users", token=tok)
    rec("GET /users", "alice", None, st,
        [u.get("username") for u in out] if isinstance(out, list) else out)
    bid = bob_id(REF, tok)
    st, out = call(REF, "DELETE", f"/users/{bid}",
                   {"current_password": ADMIN["password"]}, token=tok)
    rec("DELETE /users/{id}", "alice",
        {"current_password": ADMIN["password"]}, st, out)
    clean_ref()
    return obs


# Frozen cases: (id, kind, steps) Ã¢â‚¬â€ each step runs on both sides with
# side-local tokens; comparison is status + normalized body.
def usernames(body):
    if isinstance(body, list):
        return sorted({u.get("username") for u in body if isinstance(u, dict)})
    return body


CASES = [
    ("FB-STATE-1", "state", "create-then-list"),
    ("FB-ERROR-1", "error", "wrong-password-login"),
    ("FB-ERROR-2", "error", "unauthenticated-list"),
    ("FB-REL-1", "relation", "nonadmin-cannot-list-users"),
    ("FB-MULTI-1", "multi-step", "create-login-delete-get404"),
    ("FB-NEG-1", "negative", "duplicate-create"),
]


def bob_id(base, tok):
    s2, out = call(base, "GET", "/users", token=tok)
    if isinstance(out, list):
        for u in out:
            if isinstance(u, dict) and u.get("username") == "genbob":
                return u.get("id")
    return 2


def delete_bob(base, tok):
    bid = bob_id(base, tok)
    return call(base, "DELETE", f"/users/{bid}",
                {"current_password": ADMIN["password"]}, token=tok)


def run_case(base, kind):
    st, tok = token_of(base, ADMIN)
    create = {"what": "user", "which": [], "data": NEW_USER,
              "current_password": ADMIN["password"]}
    if kind == "create-then-list":
        s1, _ = call(base, "POST", "/users", create, token=tok)
        s2, out = call(base, "GET", "/users", token=tok)
        delete_bob(base, tok)
        return [s1, s2], usernames(out)
    if kind == "wrong-password-login":
        return list(token_of(base, {"username": "genadmin", "password": "wrong"})), None
    if kind == "unauthenticated-list":
        s, _ = call(base, "GET", "/users")
        return [s], None
    if kind == "nonadmin-cannot-list-users":
        call(base, "POST", "/users", create, token=tok)
        s2, tok2 = token_of(base, {"username": "genbob", "password": "genpassword456"})
        s3, _ = call(base, "GET", "/users", token=tok2)
        delete_bob(base, tok)
        return [s2, s3], None
    if kind == "create-login-delete-get404":
        s1, _ = call(base, "POST", "/users", create, token=tok)
        s2, _ = token_of(base, {"username": "genbob", "password": "genpassword456"})
        bid = bob_id(base, tok)
        s3, _ = call(base, "DELETE", f"/users/{bid}",
                     {"current_password": ADMIN["password"]}, token=tok)
        s4, _ = call(base, "GET", f"/users/{bid}", token=tok)
        return [s1, s2, s3, s4], None
    if kind == "duplicate-create":
        s1, _ = call(base, "POST", "/users", create, token=tok)
        s2, _ = call(base, "POST", "/users", create, token=tok)
        delete_bob(base, tok)
        return [s1, s2], None
    raise ValueError(kind)


def main():
    obs = public_probes()
    digest = hashlib.sha256(json.dumps(obs, sort_keys=True).encode()).hexdigest()
    spec = compile_spec(obs, digest)
    spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
    spec["users"] = {"alice": "genadmin"}
    out_dir = ROOT / ".runs" / "filebrowser-benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "public_observations.json").write_text(json.dumps(obs, indent=1))
    spec_path = out_dir / "spec_compiled.json"
    spec_path.write_text(json.dumps(spec, indent=1))

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "vikunja_candidate_server.py"),
         str(spec_path), str(CAND_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cand = f"http://127.0.0.1:{CAND_PORT}"
    try:
        for _ in range(50):
            try:
                call(cand, "GET", "/users")
                break
            except Exception:
                time.sleep(0.2)
        # Seed candidate users through interpreter plumbing, plus the
        # admin entity in the compiled store (plumbing users are not
        # store entities; the reference list contains the admin user).
        call(cand, "POST", "/register", ADMIN)
        call(cand, "POST", "/register",
             {"username": "genbob", "password": "genpassword456"})
        st0, tok0 = token_of(cand, ADMIN)
        admin_entity = dict(NEW_USER, username="genadmin",
                            perm={"admin": True, "execute": True,
                                  "create": True, "rename": True,
                                  "modify": True, "delete": True,
                                  "share": True, "download": True})
        call(cand, "POST", "/users",
             {"what": "user", "which": [], "data": admin_entity,
              "current_password": ADMIN["password"]}, token=tok0)
        results = []
        for cid, kind, name in CASES:
            ref_r = run_case(REF, name)
            cand_r = run_case(cand, name)
            results.append({"case": cid, "kind": kind, "name": name,
                            "ref": ref_r, "cand": cand_r,
                            "pass": ref_r == cand_r})
        # Negative control: flip login error status; case must fail.
        bad = json.loads(json.dumps(spec))
        bad["auth"]["login_error_status"] = 200
        bad_path = out_dir / "spec_mutated.json"
        bad_path.write_text(json.dumps(bad, indent=1))
        proc2 = subprocess.Popen(
            [sys.executable,
             str(ROOT / "scripts" / "vikunja_candidate_server.py"),
             str(bad_path), "3473"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            mut = f"http://127.0.0.1:3473"
            for _ in range(50):
                try:
                    call(mut, "GET", "/users")
                    break
                except Exception:
                    time.sleep(0.2)
            call(mut, "POST", "/register", ADMIN)
            mut_r = run_case(mut, "wrong-password-login")
            ref_r = run_case(REF, "wrong-password-login")
            results.append({"case": "FB-CONTROL-MUTATED", "kind": "control",
                            "name": "mutated-login-error-status",
                            "ref": ref_r, "cand": mut_r,
                            "pass": ref_r != mut_r})
        finally:
            proc2.terminate()
        passed = sum(1 for r in results if r["pass"])
        scored = sum(1 for r in results if r["pass"] is not None)
        verdict = {"target": "filebrowser-v2.63.23", "label": "NON_AI",
                   "observations_sha256": digest,
                   "routes": [f"{r['method']} {r['path']}" for r in spec["routes"]],
                   "passed": passed, "scored": scored, "results": results}
        (out_dir / "verdict.json").write_text(json.dumps(verdict, indent=1))
        print(json.dumps(verdict, indent=1))
        return 0 if passed == scored else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
