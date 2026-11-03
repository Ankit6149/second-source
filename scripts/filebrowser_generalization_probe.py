"""Generalization probe: File Browser v2.63.23 (independent OSS app).

Black-box probes of an app the evidence compiler has never seen,
recorded in the compiler's observation format. Companion evidence to
the generalization section of docs/BENCHMARK_VIKUNJA.md. Requires a
local File Browser started with a seeded admin (see benchmark doc).
This probe is operator tooling; its outputs are evidence, never
model prompt material for the Vikunja arms.
"""
import json, urllib.request, urllib.error

BASE = "http://127.0.0.1:3471/api"

def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if token:
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

obs = []
def rec(action, actor, request, status, body):
    obs.append({"action": action, "as": actor, "request": request,
                "status": status, "body": body})
    print(status, action, "as", actor)

st, tok = call("POST", "/login", {"username": "genadmin", "password": "genpassword123"})
rec("POST /login", "alice", {"username": "genadmin", "password": "genpassword123"}, st,
    tok if isinstance(tok, dict) else f"<raw-token-string len={len(str(tok))}>")
st, out = call("POST", "/login", {"username": "genadmin", "password": "wrong"})
rec("POST /login", "anon", {"username": "genadmin", "password": "wrong"}, st, out)
st, out = call("GET", "/users", token=tok)
rec("GET /users", "alice", None, st, out)
st, out = call("GET", "/users/1", token=tok)
rec("GET /users/1", "alice", None, st, out)
st, out = call("GET", "/users")
rec("GET /users", None, None, st, out)
new_user = {"what": "user", "which": [], "data": {"username": "genbob",
            "password": "genpassword456", "scope": ".", "locale": "en",
            "viewMode": "list", "singleClick": False,
            "perm": {"admin": False, "execute": False, "create": True,
                     "rename": True, "modify": True, "delete": True,
                     "share": False, "download": True}, "commands": [],
            "sorting": {"by": "name", "asc": False}, "rules": []}}
st, out = call("POST", "/users", new_user, token=tok)
rec("POST /users", "alice", new_user, st, out)
st, out = call("GET", "/users", token=tok)
rec("GET /users", "alice", None, st,
    [u.get("username") for u in out] if isinstance(out, list) else out)
st, out = call("POST", "/users", new_user, token=tok)
rec("POST /users", "alice", new_user, st, out)

path = r"C:\tmp\fb_observations.json"
open(path, "w", encoding="utf-8").write(json.dumps(obs, indent=1))
print("wrote", len(obs), "observations ->", path)
