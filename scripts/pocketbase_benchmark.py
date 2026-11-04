"""PocketBase (real professional backend) as a new Second Source target.

First-contact test of the generic pipeline on an app nothing was built
for: public probes -> evidence compile -> candidate -> differential
cases. Setup creates a superuser, an auth-only `notes` collection and
one user on the operator-run local PocketBase at 127.0.0.1:8090.
"""
from __future__ import annotations
import hashlib, json, subprocess, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import filebrowser_benchmark as fb  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REF = "http://127.0.0.1:8090"
ADMIN = {"email": "admin@ss.local", "password": "SsPass#12345"}
ALICE = {"identity": "alice@ss.local", "password": "Alice#12345"}
_state: dict = {}


def call(base, method, path, body=None, bearer=None):
    req = urllib.request.Request(base + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if bearer:
        req.add_header("Authorization", "Bearer " + bearer)
    try:
        with urllib.request.urlopen(req, data=data, timeout=15) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else None
        except Exception:
            return e.code, raw


def setup_ref():
    if _state:
        return _state
    call(REF, "POST", "/api/collections/_superusers/records",
         {"email": ADMIN["email"], "password": ADMIN["password"],
          "passwordConfirm": ADMIN["password"]})
    st, out = call(REF, "POST", "/api/collections/_superusers/auth-with-password",
                   {"identity": ADMIN["email"], "password": ADMIN["password"]})
    assert st == 200, f"superuser auth failed: {st} {out}"
    su = out["token"]
    st, cols = call(REF, "GET", "/api/collections", bearer=su)
    items = (cols or {}).get("items") if isinstance(cols, dict) else cols
    names = {c.get("name") for c in (items or []) if isinstance(c, dict)}
    if "notes" not in names:
        rule = "@request.auth.id != ''"
        st, out = call(REF, "POST", "/api/collections", {
            "name": "notes", "type": "base",
            "listRule": rule, "viewRule": rule, "createRule": rule,
            "updateRule": rule, "deleteRule": rule,
            "fields": [
                {"name": "title", "type": "text", "required": True, "presentable": True},
                {"name": "done", "type": "bool", "required": False},
            ]}, bearer=su)
        assert st in (200, 201), f"collection create failed: {st} {out}"
    call(REF, "POST", "/api/collections/users/records",
         {"email": ALICE["identity"], "password": ALICE["password"],
          "passwordConfirm": ALICE["password"], "name": "Alice"}, bearer=su)
    st, out = call(REF, "POST", "/api/collections/users/auth-with-password", ALICE)
    assert st == 200, f"alice auth failed: {st} {out}"
    _state.update(su=su, alice=out["token"])
    return _state


def public_probes():
    s = setup_ref()
    obs = []
    def rec(action, who, request, status, body):
        obs.append({"action": action, "as": who, "request": request,
                    "status": status, "body": body})
    st, b = call(REF, "GET", "/api/health")
    rec("GET /api/health", "alice", None, st, b)
    st, b = call(REF, "POST", "/api/collections/users/auth-with-password", ALICE)
    rec("POST /api/collections/users/auth-with-password", "alice", ALICE, st,
        {"token": "<token>"} if isinstance(b, dict) else b)
    tok = s["alice"]
    st, b = call(REF, "POST", "/api/collections/notes/records",
                 {"title": "First note", "done": False}, bearer=tok)
    rec("POST /api/collections/notes/records", "alice",
        {"title": "First note", "done": False}, st, b)
    pid = b.get("id") if isinstance(b, dict) else "x"
    st, b = call(REF, "GET", "/api/collections/notes/records", bearer=tok)
    rec("GET /api/collections/notes/records", "alice", None, st, b)
    st, b = call(REF, "GET", f"/api/collections/notes/records/{pid}", bearer=tok)
    rec("GET /api/collections/notes/records/{pid}", "alice", None, st, b)
    st, b = call(REF, "PATCH", f"/api/collections/notes/records/{pid}",
                 {"done": True}, bearer=tok)
    rec("PATCH /api/collections/notes/records/{pid}", "alice", {"done": True}, st, b)
    st, b = call(REF, "POST", "/api/collections/notes/records",
                 {"done": True}, bearer=tok)
    rec("POST /api/collections/notes/records", "alice", {"done": True}, st, b)
    st, b = call(REF, "GET", f"/api/collections/notes/records/{pid}")
    rec("GET /api/collections/notes/records/{pid}", "None", None, st, b)
    st, b = call(REF, "GET", "/api/collections/notes/records/000000000000001", bearer=tok)
    rec("GET /api/collections/notes/records/{pid}", "alice", None, st, b)
    st, b = call(REF, "GET", "/api/collections/notes/records?filter=(done%20%3D%20true)", bearer=tok)
    rec("GET /api/collections/notes/records?filter=(done = true)", "alice", None, st, b)
    st, b = call(REF, "GET", "/api/collections/notes/records?sort=title", bearer=tok)
    rec("GET /api/collections/notes/records?sort=title", "alice", None, st, b)
    st, b = call(REF, "GET", "/api/collections/notes/records?perPage=1", bearer=tok)
    rec("GET /api/collections/notes/records?perPage=1", "alice", None, st, b)
    st, b = call(REF, "DELETE", f"/api/collections/notes/records/{pid}", bearer=tok)
    rec("DELETE /api/collections/notes/records/{pid}", "alice", None, st, None)
    st, b = call(REF, "GET", "/api/collections/notes/records", bearer=tok)
    rec("GET /api/collections/notes/records", "alice", None, st, b)
    return obs


def _cases_ref():
    s = setup_ref()
    tok = s["alice"]
    st, b = call(REF, "GET", "/api/collections/notes/records?perPage=200", bearer=tok)
    for i in ((b or {}).get("items") or []):
        call(REF, "DELETE", f"/api/collections/notes/records/{i.get('id')}", bearer=tok)
    out = {}
    st, b = call(REF, "GET", "/api/health")
    out["health"] = (st, (b or {}).get("code"))
    st, b = call(REF, "POST", "/api/collections/notes/records",
                 {"title": "Case note", "done": False}, bearer=tok)
    out["create"] = (st, (b or {}).get("title"), (b or {}).get("done"))
    pid = (b or {}).get("id", "x")
    st, b = call(REF, "PATCH", f"/api/collections/notes/records/{pid}",
                 {"done": True}, bearer=tok)
    out["update"] = (st, (b or {}).get("done"))
    st, b = call(REF, "GET", "/api/collections/notes/records", bearer=tok)
    items = (b or {}).get("items") or []
    out["list"] = (st, sorted(i.get("title") for i in items))
    call(REF, "POST", "/api/collections/notes/records", {"title": "Bravo", "done": True}, bearer=tok)
    call(REF, "POST", "/api/collections/notes/records", {"title": "Alpha", "done": False}, bearer=tok)
    st, b = call(REF, "GET", "/api/collections/notes/records?filter=(done%20%3D%20true)", bearer=tok)
    out["filter_done"] = (st, sorted(i.get("title") for i in ((b or {}).get("items") or [])))
    st, b = call(REF, "GET", "/api/collections/notes/records?sort=title", bearer=tok)
    out["sort_title"] = (st, [i.get("title") for i in ((b or {}).get("items") or [])])
    st, b = call(REF, "GET", "/api/collections/notes/records?perPage=2", bearer=tok)
    out["pagination"] = (st, len((b or {}).get("items") or []), (b or {}).get("totalItems"))
    st, b = call(REF, "POST", "/api/collections/notes/records", {"done": True}, bearer=tok)
    out["validation"] = (st,)
    st, b = call(REF, "GET", f"/api/collections/notes/records/{pid}")
    out["unauth"] = (st,)
    st, b = call(REF, "GET", "/api/collections/notes/records/000000000000001", bearer=tok)
    out["missing"] = (st,)
    st, b = call(REF, "DELETE", f"/api/collections/notes/records/{pid}", bearer=tok)
    out["delete"] = (st,)
    st, b = call(REF, "GET", "/api/collections/notes/records", bearer=tok)
    out["list_after"] = (st, len((b or {}).get("items") or []))
    return out


def _cases_cand(cand, tok):
    out = {}
    st, b = fb.call(cand, "GET", "/api/health", None, tok)
    out["health"] = (st, (b or {}).get("code") if isinstance(b, dict) else None)  # with token below
    st, b = fb.call(cand, "POST", "/api/collections/notes/records",
                    {"title": "Case note", "done": False}, tok)
    out["create"] = (st, (b or {}).get("title") if isinstance(b, dict) else None,
                     (b or {}).get("done") if isinstance(b, dict) else None)
    pid = (b or {}).get("id", "x") if isinstance(b, dict) else "x"
    st, b = fb.call(cand, "PATCH", f"/api/collections/notes/records/{pid}",
                    {"done": True}, tok)
    out["update"] = (st, (b or {}).get("done") if isinstance(b, dict) else None)
    st, b = fb.call(cand, "GET", "/api/collections/notes/records", None, tok)
    items = []
    if isinstance(b, dict):
        items = b.get("items") or []
    elif isinstance(b, list):
        items = b
    out["list"] = (st, sorted(i.get("title") for i in items if isinstance(i, dict)))
    fb.call(cand, "POST", "/api/collections/notes/records", {"title": "Bravo", "done": True}, tok)
    fb.call(cand, "POST", "/api/collections/notes/records", {"title": "Alpha", "done": False}, tok)
    def _items(b):
        if isinstance(b, dict):
            return b.get("items") or []
        return b if isinstance(b, list) else []
    st, b = fb.call(cand, "GET", "/api/collections/notes/records?filter=(done%20%3D%20true)", None, tok)
    out["filter_done"] = (st, sorted(i.get("title") for i in _items(b) if isinstance(i, dict)))
    st, b = fb.call(cand, "GET", "/api/collections/notes/records?sort=title", None, tok)
    out["sort_title"] = (st, [i.get("title") for i in _items(b) if isinstance(i, dict)])
    st, b = fb.call(cand, "GET", "/api/collections/notes/records?perPage=2", None, tok)
    out["pagination"] = (st, len(_items(b)), (b or {}).get("totalItems") if isinstance(b, dict) else None)
    st, b = fb.call(cand, "POST", "/api/collections/notes/records", {"done": True}, tok)
    out["validation"] = (st,)
    st, b = fb.call(cand, "GET", f"/api/collections/notes/records/{pid}")
    out["unauth"] = (st,)
    st, b = fb.call(cand, "GET", "/api/collections/notes/records/000000000000001", None, tok)
    out["missing"] = (st,)
    st, b = fb.call(cand, "DELETE", f"/api/collections/notes/records/{pid}", None, tok)
    out["delete"] = (st,)
    st, b = fb.call(cand, "GET", "/api/collections/notes/records", None, tok)
    if isinstance(b, dict):
        n = len(b.get("items") or [])
    elif isinstance(b, list):
        n = len(b)
    else:
        n = None
    out["list_after"] = (st, n)
    return out


_procs: list = []

def start_candidate(spec, tag):
    path = ROOT / ".runs" / f"pb-{tag}-spec.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=1, default=str), encoding="utf-8")
    port = 5311 + (abs(hash(tag)) % 300)
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "vikunja_candidate_server.py"),
         str(path), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _procs.append(proc)
    time.sleep(2)
    return f"http://127.0.0.1:{port}"


def stop_candidates():
    for proc in _procs:
        try:
            proc.terminate()
        except Exception:
            pass
    _procs.clear()


def pb_score(spec):
    cand = start_candidate(spec, "score")
    try:
        fb.call(cand, "POST", "/register", {"username": "alice@ss.local", "password": "pw"})
        _, tok = fb.token_of(cand, {"username": "alice@ss.local", "password": "pw"})
        ref = _cases_ref()
        got = _cases_cand(cand, tok)
        div = [k for k in ref if ref[k] != got[k]]
        return {"passed": len(ref) - len(div), "total": len(ref),
                "divergences": div,
                "detail": {k: {"ref": ref[k], "cand": got[k]} for k in div}}
    finally:
        stop_candidates()


def main():
    obs = public_probes()
    digest = hashlib.sha256(json.dumps(obs, sort_keys=True, default=str).encode()).hexdigest()
    spec = fb.compile_spec(obs, digest)
    spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
    spec["users"] = {"alice": "alice@ss.local"}
    print(f"probes={len(obs)} routes={len(spec.get('routes', []))}")
    res = pb_score(spec)
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
