"""Muse (REAL_MODEL) cross-app packet muse-cross-app-20261104.

Two bounded experiments, hard-capped (4 calls, $0.50):
A) File Browser: Muse ALONE (coverage-grounded) authors a candidate spec
   from public probe observations; scored on the 7-case differential.
B) Gitea: Muse REPAIR proposes route-generalization rules for the NON_AI
   spec (baseline 2/6 on 6 public cases); rules are gated on those public
   cases, then scored ONCE on held-out cases frozen below before any
   prompt was built (repo/issue names here never appear in prompts).
Receipts append with fsync per call. Provider failures: unscored abort.
"""
from __future__ import annotations
import copy, hashlib, json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import filebrowser_benchmark as fb  # noqa: E402
import investigation_engine as eng  # noqa: E402
from second_source.budgets import RunBudget  # noqa: E402
from second_source.contracts import Budgets  # noqa: E402
from second_source.model_gateway import MetaProvider, ModelGateway, ModelRequest  # noqa: E402
from second_source.orchestration.guard import SpendingGuard, SpendPacketV1  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".runs" / "muse-cross-app-20261104"
PACKET = SpendPacketV1(packet_id="muse-cross-app-20261104", owner_id="owner",
                       investigation_id="muse-cross-app", max_spend_usd=0.50,
                       max_model_calls=4, fresh=True, mode="paid")

# Frozen BEFORE prompt construction; never in prompts.
GT_HELD_OUT = ["create_repo:gamma-hold-7", "get_repo:gamma-hold-7",
               "create_issue:gamma-hold-7#2", "list_issues:gamma-hold-7"]
GT_HELD_SHA = hashlib.sha256(json.dumps(GT_HELD_OUT).encode()).hexdigest()


def receipt(kind, payload):
    RUN.mkdir(parents=True, exist_ok=True)
    with open(RUN / "receipts.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": kind, **payload}, default=str) + "\n")
        fh.flush(); os.fsync(fh.fileno())


def parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def start_candidate(spec, name):
    path = RUN / f"{name}.json"
    path.write_text(json.dumps(spec, indent=1, default=str), encoding="utf-8")
    port = eng._next_port()
    proc = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "vikunja_candidate_server.py"),
                             str(path), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    eng._wait_candidate(base)
    return proc, base


def fb_score(spec):
    proc, cand = start_candidate(spec, "fb-muse-spec")
    try:
        fb.call(cand, "POST", "/register", fb.ADMIN)
        fb.call(cand, "POST", "/register", {"username": "genbob", "password": "genpassword456"})
        _, tok0 = fb.token_of(cand, fb.ADMIN)
        admin_entity = dict(fb.NEW_USER, username="genadmin",
                            perm={"admin": True, "execute": True, "create": True, "rename": True,
                                  "modify": True, "delete": True, "share": True, "download": True})
        fb.call(cand, "POST", "/users", {"what": "user", "which": [], "data": admin_entity,
                                         "current_password": fb.ADMIN["password"]}, token=tok0)
        results = []
        for cid, kind, name in fb.CASES:
            results.append({"case": cid, "pass": fb.run_case(fb.REF, name) == fb.run_case(cand, name)})
        bad = copy.deepcopy(spec)
        bad.setdefault("auth", {})["login_error_status"] = 200
        proc2, mut = start_candidate(bad, "fb-muse-mut")
        try:
            fb.call(mut, "POST", "/register", fb.ADMIN)
            results.append({"case": "FB-CONTROL-MUTATED",
                            "pass": fb.run_case(fb.REF, "wrong-password-login") != fb.run_case(mut, "wrong-password-login")})
        finally:
            proc2.terminate()
        return results
    finally:
        proc.terminate()


def gt_public_score(spec):
    proc, cand = start_candidate(spec, "gt-scored")
    try:
        fb.call(cand, "POST", "/register", eng.GT_ADMIN)
        _, tok = fb.token_of(cand, eng.GT_ADMIN)
        ref = eng._gt_case(eng.GT_BASE, "basic")
        got = eng._gt_case(cand, tok)
        return {k: ref[k] == got[k] for k in ref}, ref, got
    finally:
        proc.terminate()


def gt_held_out_score(spec):
    proc, cand = start_candidate(spec, "gt-held")
    try:
        fb.call(cand, "POST", "/register", eng.GT_ADMIN)
        _, tok = fb.token_of(cand, eng.GT_ADMIN)

        def run(base, auth):
            out = {}
            eng._gt_call(base, "DELETE", "/repos/ssadmin/gamma-hold-7", auth=auth)
            st, b = eng._gt_call(base, "POST", "/user/repos", {"name": "gamma-hold-7", "auto_init": True}, auth=auth)
            out["create"] = (st, b.get("name") if isinstance(b, dict) else None)
            st, b = eng._gt_call(base, "GET", "/repos/ssadmin/gamma-hold-7", auth=auth)
            out["get"] = (st, b.get("name") if isinstance(b, dict) else None)
            eng._gt_call(base, "POST", "/repos/ssadmin/gamma-hold-7/issues", {"title": "h1"}, auth=auth)
            st, b = eng._gt_call(base, "POST", "/repos/ssadmin/gamma-hold-7/issues", {"title": "h2"}, auth=auth)
            out["issue2"] = (st, b.get("title") if isinstance(b, dict) else None)
            st, b = eng._gt_call(base, "GET", "/repos/ssadmin/gamma-hold-7/issues", auth=auth)
            out["list"] = (st, len(b) if isinstance(b, list) else None)
            eng._gt_call(base, "DELETE", "/repos/ssadmin/gamma-hold-7", auth=auth)
            return out

        ref, got = run(eng.GT_BASE, "basic"), run(cand, tok)
        return {k: ref[k] == got[k] for k in ref}
    finally:
        proc.terminate()


def apply_rules(spec, rules):
    spec = copy.deepcopy(spec)
    for route in spec.get("routes", []):
        path = route.get("path", "")
        for rule in rules:
            find, repl = rule.get("find", ""), rule.get("replace", "")
            if find and find in path:
                path = path.replace(find, repl)
        route["path"] = path
    for rule in rules:
        if rule.get("add_route"):
            spec.setdefault("routes", []).append(rule["add_route"])
    return spec


def main() -> int:
    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        print("BLOCKED: MODEL_API_KEY not set. Zero calls."); return 2
    RUN.mkdir(parents=True, exist_ok=True)
    SpendingGuard().check(PACKET, estimated_usd=0.20, investigation_id=PACKET.investigation_id)
    budget = RunBudget(Budgets(max_model_calls=4, max_estimated_model_spend_usd=0.50))
    gateway = ModelGateway(MetaProvider(api_key=key), budget, audit=receipt)
    record = {"kind": "MUSE_CROSS_APP_V1", "classification": "REAL_MODEL",
              "provider": "meta-direct", "model": "muse-spark-1.3",
              "packet_id": PACKET.packet_id, "max_spend_usd": 0.50, "max_calls": 4,
              "gitea_held_out_sha256": GT_HELD_SHA, "calls": 0, "experiments": {}}
    receipt("packet_opened", {"packet": PACKET.packet_id, "held_out_sha": GT_HELD_SHA})

    def call(stage, prompt, tokens=6000):
        resp = gateway.generate(ModelRequest(
            stage=stage, prompt_version="cross-app-v1",
            messages=({"role": "user", "content": prompt},), max_output_tokens=tokens))
        record["calls"] += 1
        return resp.content_text or ""

    # ---- A) File Browser: Muse alone (grounded) ----
    try:
        obs = fb.public_probes()
        digest = hashlib.sha256(json.dumps(obs, sort_keys=True).encode()).hexdigest()
        skeleton = {"routes": [{"method": "POST", "path": "/users", "kind": "create",
                                "collection": "users", "status": 201, "body": {},
                                "validate": [], "forbidden_body": None,
                                "duplicate_field": None, "duplicate_status": None, "duplicate_body": None}],
                    "auth": {"login_path": "/login", "login_error_status": 401, "raw_header_name": "X-Auth"},
                    "users": {"alice": "genadmin"}}
        slim = [{"action": o["action"], "as": o.get("as"), "request": o.get("request"),
                 "status": o["status"], "body": json.dumps(o.get("body"))[:350]} for o in obs]
        prompt = ("You are reconstructing the File Browser API from observed public probes only.\n"
                  "Return ONLY one JSON candidate spec, no prose. Spec shape (field names exactly):\n"
                  + json.dumps(skeleton) + "\nRules: one route per distinct method+path pattern; "
                  "use {id} for numeric ids; error statuses must match observations; do not invent routes.\n"
                  "Observed public probes (JSON):\n" + json.dumps(slim))
        spec = parse_json(call("muse_filebrowser_alone", prompt))
        if not isinstance(spec, dict) or not spec.get("routes"):
            record["experiments"]["filebrowser_alone"] = {"status": "model_failure",
                "detail": "unusable JSON/spec", "passed": 0, "total": 7}
        else:
            spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
            spec["users"] = {"alice": "genadmin"}
            results = fb_score(spec)
            (RUN / "fb-claude-spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
            record["experiments"]["filebrowser_alone"] = {
                "status": "scored", "passed": sum(r["pass"] for r in results), "total": len(results),
                "cases": results, "compiler_baseline": "7/7 NON_AI"}
    except Exception as exc:
        record["experiments"]["filebrowser_alone"] = {"status": "infrastructure_failure",
            "detail": f"{type(exc).__name__}: {exc}"[:300]}

    # ---- B) Gitea: Muse repair of the generalization gap ----
    try:
        # rebuild the NON_AI spec exactly as the engine does
        eng._gt_call(eng.GT_BASE, "DELETE", "/repos/ssadmin/ss-demo", auth="basic")
        obs = []
        for action, req, path in [("GET /version", None, "/version"),
                                  ("POST /user/repos", {"name": "ss-demo", "auto_init": True}, "/user/repos"),
                                  ("GET /repos/ssadmin/ss-demo", None, "/repos/ssadmin/ss-demo"),
                                  ("POST /repos/ssadmin/ss-demo/issues", {"title": "Demo bug"}, "/repos/ssadmin/ss-demo/issues"),
                                  ("GET /repos/ssadmin/ss-demo/issues", None, "/repos/ssadmin/ss-demo/issues")]:
            st, body = eng._gt_call(eng.GT_BASE, "POST" if action.startswith("POST") else "GET",
                                    path, req, auth="basic")
            obs.append({"action": action, "as": "alice", "request": req, "status": st,
                        "body": [i.get("title") for i in body] if isinstance(body, list) else body})
        digest = hashlib.sha256(json.dumps(obs, sort_keys=True, default=str).encode()).hexdigest()
        base_spec = fb.compile_spec(obs, digest)
        base_spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
        base_spec["users"] = {"alice": "ssadmin"}
        base_public, _, _ = gt_public_score(base_spec)
        base_passed = sum(base_public.values())
        prompt = ("A deterministic compiler built this API candidate spec from public Gitea probes. "
                  "On public differential cases it passes version and repo creation, but fails "
                  "get-repo, create-issue and list-issues for a repo whose name differs from the "
                  "probed one, because route paths keep the probed repo name as a literal segment.\n"
                  "Return ONLY JSON: {\"rules\": [{\"find\": \"<path segment or substring>\", "
                  "\"replace\": \"<replacement, may use {id}>\"}, ...]}. Rules are applied as literal "
                  "substring replacements on every route path. Propose the minimal generalization "
                  "so routes work for any repo name. Do not rename methods.\nSpec routes:\n"
                  + json.dumps([{"method": r.get("method"), "path": r.get("path")} for r in base_spec.get("routes", [])]))
        parsed = parse_json(call("muse_gitea_repair", prompt, tokens=3000))
        rules = parsed.get("rules", []) if isinstance(parsed, dict) else []
        candidate_spec = apply_rules(base_spec, rules)
        gated_public, _, _ = gt_public_score(candidate_spec)
        gated_passed = sum(gated_public.values())
        regressed = [k for k, v in base_public.items() if v and not gated_public.get(k)]
        accepted = gated_passed > base_passed and not regressed
        held = gt_held_out_score(candidate_spec if accepted else base_spec)
        record["experiments"]["gitea_repair"] = {
            "status": "scored", "rules": rules, "baseline_public": f"{base_passed}/6",
            "candidate_public": f"{gated_passed}/6", "regressed": regressed, "accepted": accepted,
            "held_out": {"passed": sum(held.values()), "total": len(held), "cases": held},
            "evaluated_spec": "claude_repaired" if accepted else "compiler_baseline"}
        receipt("gitea_scored", record["experiments"]["gitea_repair"])
    except Exception as exc:
        record["experiments"]["gitea_repair"] = {"status": "infrastructure_failure",
            "detail": f"{type(exc).__name__}: {exc}"[:300]}

    record["budget"] = budget.summary()
    (RUN / "result.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    receipt("run_completed", {"calls": record["calls"], "budget": record["budget"]})
    print(json.dumps(record, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

