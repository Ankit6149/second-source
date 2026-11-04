"""Muse route-review experiments for File Browser and Gitea.

Packets muse-exp-fb-20261104 / muse-exp-gitea-20261104. Same pattern as
the Vikunja route experiment: NON_AI compiler baseline, Muse reviews
one compiled route at a time against its public observations, edits
only contract fields (templates/methods/paths immutable), and every
edit is gated on the identical public case set. Baselines here are
already perfect (FB 7/7, Gitea 6/6), so the gate is non-regression:
an edit is kept only if the full public score stays perfect.
Held-out cases are never loaded or shown. Receipts fsync-appended.
"""
from __future__ import annotations
import copy, json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import filebrowser_benchmark as fb  # noqa: E402
import investigation_engine as ie  # noqa: E402
import vikunja_hybrid_experiment as hybrid  # noqa: E402
from second_source.budgets import RunBudget  # noqa: E402
from second_source.contracts import Budgets  # noqa: E402
from second_source.model_gateway import MetaProvider, ModelGateway, ModelRequest  # noqa: E402
from second_source.orchestration.guard import SpendingGuard, SpendPacketV1  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROCS = []


def start_candidate(spec, tag):
    path = ROOT / ".runs" / f"muse-exp-{tag}-spec.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    port = ie._next_port()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "vikunja_candidate_server.py"),
         str(path), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PROCS.append(proc)
    base = f"http://127.0.0.1:{port}"
    ie._wait_candidate(base)
    return base


def stop_candidates():
    for p in PROCS:
        try:
            p.terminate(); p.wait(timeout=8)
        except Exception:
            try: p.kill()
            except Exception: pass
    PROCS.clear()


def fb_score(spec):
    cand = start_candidate(spec, "fb")
    fb.call(cand, "POST", "/register", fb.ADMIN)
    fb.call(cand, "POST", "/register", {"username": "genbob", "password": "genpassword456"})
    st0, tok0 = fb.token_of(cand, fb.ADMIN)
    admin_entity = dict(fb.NEW_USER, username="genadmin",
                        perm={"admin": True, "execute": True, "create": True,
                              "rename": True, "modify": True, "delete": True,
                              "share": True, "download": True})
    fb.call(cand, "POST", "/users",
            {"what": "user", "which": [], "data": admin_entity,
             "current_password": fb.ADMIN["password"]}, token=tok0)
    results = []
    for cid, kind, name in fb.CASES:
        results.append({"case": cid, "pass": fb.run_case(fb.REF, name) == fb.run_case(cand, name)})
    bad = copy.deepcopy(spec)
    bad["auth"]["login_error_status"] = 200
    mut = start_candidate(bad, "fb-mut")
    fb.call(mut, "POST", "/register", fb.ADMIN)
    results.append({"case": "FB-CONTROL-MUTATED",
                    "pass": fb.run_case(fb.REF, "wrong-password-login") != fb.run_case(mut, "wrong-password-login")})
    stop_candidates()
    return {"passed": sum(r["pass"] for r in results), "total": len(results),
            "divergences": [r["case"] for r in results if not r["pass"]]}


def gt_probes():
    obs = []
    def rec(action, request, status, body, actor="alice"):
        obs.append({"action": action, "as": actor, "request": request,
                    "status": status, "body": body})
    ie._gt_call(ie.GT_BASE, "DELETE", "/repos/ssadmin/ss-demo", auth="basic")
    st, b = ie._gt_call(ie.GT_BASE, "GET", "/version", auth="basic"); rec("GET /version", None, st, b)
    st, b = ie._gt_call(ie.GT_BASE, "POST", "/user/repos", {"name": "ss-demo", "auto_init": True}, auth="basic")
    rec("POST /user/repos", {"name": "ss-demo", "auto_init": True}, st, b)
    st, b = ie._gt_call(ie.GT_BASE, "GET", "/repos/ssadmin/ss-demo", auth="basic"); rec("GET /repos/ssadmin/ss-demo", None, st, b)
    st, b = ie._gt_call(ie.GT_BASE, "POST", "/repos/ssadmin/ss-demo/issues", {"title": "Demo bug"}, auth="basic")
    rec("POST /repos/ssadmin/ss-demo/issues", {"title": "Demo bug"}, st, b)
    st, b = ie._gt_call(ie.GT_BASE, "GET", "/repos/ssadmin/ss-demo/issues", auth="basic")
    rec("GET /repos/ssadmin/ss-demo/issues", None, st, [i.get("title") for i in b] if isinstance(b, list) else b)
    st, b = ie._gt_call(ie.GT_BASE, "GET", "/user", auth="basic"); rec("GET /user", None, st, b)
    st, b = ie._gt_call(ie.GT_BASE, "GET", "/user")
    obs.append({"action": "GET /user", "as": "None", "request": None, "status": st, "body": b})
    return obs


def gt_score(spec):
    cand = start_candidate(spec, "gt")
    fb.call(cand, "POST", "/register", ie.GT_ADMIN)
    _, tok = fb.token_of(cand, ie.GT_ADMIN)
    ref = ie._gt_case(ie.GT_BASE, "basic")
    got = ie._gt_case(cand, tok)
    stop_candidates()
    div = [k for k in ref if ref[k] != got[k]]
    return {"passed": len(ref) - len(div), "total": len(ref), "divergences": div}


def route_obs(obs_list, route):
    method, path = route.get("method"), route.get("path")
    out = []
    for o in obs_list:
        action = str(o.get("action", ""))
        if " " not in action:
            continue
        m, p = action.split(" ", 1)
        p = p.split("?")[0]
        norm = "/".join("{id}" if seg.isdigit() else seg for seg in p.split("/"))
        if m == method and (p == path or norm == path):
            out.append(o)
    return out


def run_target(name, packet_id, observations, spec, score_fn, run_dir):
    run = ROOT / ".runs" / run_dir
    def sink(kind, payload):
        run.mkdir(parents=True, exist_ok=True)
        with open(run / "receipts.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": kind, **payload}, default=str) + "\n")
            fh.flush(); os.fsync(fh.fileno())
    def save(rec):
        run.mkdir(parents=True, exist_ok=True)
        (run / "result.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")

    packet = SpendPacketV1(packet_id=packet_id, owner_id="owner",
                           investigation_id=f"{name}-muse-exp", max_spend_usd=0.5,
                           max_model_calls=6, fresh=True, mode="paid")
    SpendingGuard().check(packet, estimated_usd=0.5, investigation_id=packet.investigation_id)
    record = {"kind": f"{name.upper()}_MUSE_EXPERIMENT_V1", "classification": "REAL_MODEL",
              "provider": "meta-direct", "model": "muse-spark-1.3",
              "packet_id": packet_id, "max_spend_usd": 0.5, "max_calls": 6,
              "calls": 0, "attempts": []}
    base = score_fn(spec)
    record["baseline_public"] = base
    save(record)
    print(f"[{name}] compiler baseline: {base['passed']}/{base['total']}", flush=True)

    budget = RunBudget(Budgets(max_model_calls=6, max_estimated_model_spend_usd=0.5))
    gateway = ModelGateway(MetaProvider(api_key=os.environ["MODEL_API_KEY"]),
                           budget, audit=sink)
    current_spec, current = copy.deepcopy(spec), base
    for route in list(spec.get("routes", []))[:6]:
        key = f"{route.get('method')} {route.get('path')}"
        prompt = "\n\n".join([
            "Output JSON only. You are Muse reviewing ONE route contract inside "
            "Second Source. A deterministic compiler transcribed this route from "
            "public observations. Return the route corrected only if the "
            "observations contradict it; otherwise return it unchanged. Never "
            "emit a template field; set \"template_unchanged\": true. Editable "
            "fields only: kind, status, access, collection, auth, validate, forbidden_body.",
            "ROUTE:\n" + json.dumps(route, indent=1)[:6000],
            "OBSERVATIONS:\n" + json.dumps(route_obs(observations, route), indent=1, default=str)[:6000],
            "Reply: {\"route\": {...}}"])
        attempt = {"route": key}
        try:
            resp = gateway.generate(ModelRequest(
                stage="muse_experiment_all_review", prompt_version="muse-exp-all-v1",
                messages=({"role": "user", "content": prompt},), max_output_tokens=1800))
            record["calls"] += 1
            text = resp.content_text or ""
        except Exception as exc:
            attempt.update(status="provider_failure_unscored",
                           detail=f"{type(exc).__name__}: {exc}"[:250])
            record["attempts"].append(attempt); record["failure_class"] = "INFRASTRUCTURE"
            save(record); break
        parsed, how = hybrid.parse_route_json(text)
        model_route = None
        if isinstance(parsed, dict):
            model_route = parsed.get("route") or (
                parsed["routes"][0] if isinstance(parsed.get("routes"), list) and parsed["routes"] else None)
        attempt["parse"] = how
        if not isinstance(model_route, dict):
            attempt["status"] = "unparseable_no_edit"
            record["attempts"].append(attempt); save(record); continue
        live = next(r for r in current_spec["routes"]
                    if (r.get("method"), r.get("path")) == (route.get("method"), route.get("path")))
        proposed = copy.deepcopy(live)
        changed = []
        for f in hybrid.REPAIR_EDITABLE_FIELDS:
            if f in model_route and model_route[f] != live.get(f):
                proposed[f] = model_route[f]; changed.append(f)
        proposed["template"] = copy.deepcopy(live.get("template"))
        proposed["method"], proposed["path"] = live.get("method"), live.get("path")
        attempt["changed_fields"] = changed
        if proposed == live:
            attempt.update(status="no_contract_change", kept=False)
            record["attempts"].append(attempt); save(record)
            print(f"[{name}] Muse {key}: no change", flush=True); continue
        trial = copy.deepcopy(current_spec)
        for r in trial["routes"]:
            if (r.get("method"), r.get("path")) == (live.get("method"), live.get("path")):
                r.update(proposed)
        trial = hybrid.enforce_compiled_facts(trial, spec)
        got = score_fn(trial)
        kept = got["passed"] >= current["passed"]
        attempt.update(status="evaluated", after=got["passed"], kept=kept)
        if kept:
            current_spec, current = trial, got
        record["attempts"].append(attempt)
        record["candidate_public"] = current
        save(record)
        print(f"[{name}] Muse {key}: -> {got['passed']}/{got['total']} kept={kept}", flush=True)
    record["candidate_public"] = current
    record["budget"] = budget.summary()
    record["headline"] = (f"Muse experiment (REAL_MODEL) {name}: public "
                          f"{base['passed']}/{base['total']} -> {current['passed']}/{current['total']} "
                          f"after {record['calls']} route-review calls")
    save(record)
    sink("run_completed", {"headline": record["headline"]})
    print(record["headline"], flush=True)
    return record


def main():
    if not os.environ.get("MODEL_API_KEY"):
        print("BLOCKED: MODEL_API_KEY not set. Zero calls."); return 2
    results = {}
    obs = fb.public_probes()
    import hashlib
    digest = hashlib.sha256(json.dumps(obs, sort_keys=True).encode()).hexdigest()
    spec = fb.compile_spec(obs, digest)
    spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
    spec["users"] = {"alice": "genadmin"}
    results["filebrowser"] = run_target("filebrowser", "muse-exp-fb-20261104",
                                        obs, spec, fb_score, "muse-exp-fb-20261104")
    obs = gt_probes()
    digest = hashlib.sha256(json.dumps(obs, sort_keys=True, default=str).encode()).hexdigest()
    spec = fb.compile_spec(obs, digest)
    spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
    spec["users"] = {"alice": "ssadmin"}
    results["gitea"] = run_target("gitea", "muse-exp-gitea-20261104",
                                  obs, spec, gt_score, "muse-exp-gitea-20261104")
    print(json.dumps({k: v["headline"] for k, v in results.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
