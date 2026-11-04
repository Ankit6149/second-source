"""Muse (REAL_MODEL) per-route hybrid for Vikunja — packet muse-hybrid-20261104.

Compiler (NON_AI) transcribes public observations; Muse edits one route
per call (contract fields only, template restored verbatim); every edit is
gated on PUBLIC conformance; both frozen suites are scored ONCE at the end
by evaluator-only code imported only inside the scoring function.
Receipts are appended with fsync at each call completion.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import evidence_compiler  # noqa: E402
import vikunja_benchmark as vb  # noqa: E402
import vikunja_hybrid_experiment as hybrid  # noqa: E402
import vikunja_model_experiment as mx  # noqa: E402
from second_source.budgets import RunBudget  # noqa: E402
from second_source.contracts import Budgets  # noqa: E402
from second_source.model_gateway import MetaProvider, ModelGateway, ModelRequest  # noqa: E402
from second_source.orchestration.guard import SpendingGuard, SpendPacketV1  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".runs" / "vikunja-model" / "muse_hybrid_20261104"
OBS_PATH = ROOT / ".runs" / "vikunja-benchmark" / "public_observations.json"
PACKET = SpendPacketV1(packet_id="muse-hybrid-20261104", owner_id="owner",
                       investigation_id="vikunja-muse-hybrid", max_spend_usd=2.0,
                       max_model_calls=10, fresh=True, mode="paid")
REF_PORT, CAND_PORT = 3491, 3492


def receipt_sink(kind, payload):
    RUN.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"kind": kind, **payload}, default=str)
    with open(RUN / "receipts.jsonl", "a", encoding="utf-8") as fh:
        fh.write(line + "\n"); fh.flush(); os.fsync(fh.fileno())


def score_suite(spec, suite_name):
    """Evaluator-only: held-out modules imported here, never for prompts."""
    if suite_name == "frozen":
        from vikunja_held_out import HELD_OUT as seqs
    else:
        from vikunja_held_out_extended import EXTENDED_HELD_OUT as seqs
    spec_path = RUN / f"spec_score_{suite_name}.json"
    spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    proc, workdir, ref_base = mx.start_reference(3591)
    cand = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "vikunja_candidate_server.py"),
                             str(spec_path), str(3592)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        cand_base = "http://127.0.0.1:3592/api/v1"
        ref_api, cases = ref_base + "/api/v1", []
        for seq in seqs:
            ref = vb.canonical_sequence(vb.run_actions(seq, vb.fresh_tokens(ref_api), ref_api))
            got = vb.canonical_sequence(vb.run_actions(seq, vb.fresh_tokens(cand_base), cand_base))
            cases.append(ref == got)
        return {"passed": sum(cases), "total": len(cases), "cases": cases}
    finally:
        cand.terminate()
        try: cand.wait(timeout=8)
        except Exception: cand.kill()
        time.sleep(1)
        mx.stop_reference(proc, workdir)


def main() -> int:
    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        print("BLOCKED: MODEL_API_KEY not set. Zero calls."); return 2
    guard = SpendingGuard()
    guard.check(PACKET, estimated_usd=0.5, investigation_id=PACKET.investigation_id)
    obs_list = json.loads(OBS_PATH.read_text(encoding="utf-8"))
    compiled = evidence_compiler.compile_spec(obs_list)
    RUN.mkdir(parents=True, exist_ok=True)
    record = {"kind": "VIKUNJA_MUSE_HYBRID_V1", "classification": "REAL_MODEL",
              "provider": "meta-direct", "model": "muse-spark-1.3",
              "packet_id": PACKET.packet_id, "max_spend_usd": 2.0, "max_calls": 10,
              "compiler_baseline": "NON_AI", "calls": 0, "route_results": []}
    # S0: compiler public-conformance baseline (reference for the gate)
    proc, workdir, ref_base = mx.start_reference(REF_PORT)
    try:
        base_conf = hybrid.public_conformance(compiled, ref_base, CAND_PORT)
    finally:
        mx.stop_reference(proc, workdir)
    record["compiler_public_conformance"] = {
        "passed": base_conf["public_passed"], "total": base_conf["public_total"]}
    budget = RunBudget(Budgets(max_model_calls=10, max_estimated_model_spend_usd=2.0))
    gateway = ModelGateway(MetaProvider(api_key=key), budget, audit=receipt_sink)
    edited = {}
    for route in compiled.get("routes", []):
        rkey = f"{route.get('method', '')} {route.get('path', '')}"
        prompt = hybrid.build_route_prompt(route, obs_list)
        try:
            resp = gateway.generate(ModelRequest(
                stage="muse_hybrid_route", prompt_version="muse-hybrid-v1",
                messages=({"role": "user", "content": prompt},),
                max_output_tokens=2000))
            record["calls"] += 1
            text = resp.content_text or ""
        except Exception as exc:  # provider failure: recorded, unscored abort
            record.update(admitted=False, failure_class="INFRASTRUCTURE",
                          failed_route=rkey, detail=f"{type(exc).__name__}: {exc}"[:300])
            (RUN / "result.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
            receipt_sink("run_aborted", {"route": rkey, "error": str(exc)[:200]})
            print(json.dumps(record, indent=1)); return 0
        parsed, how = hybrid.parse_route_json(text)
        route_out = None
        if isinstance(parsed, dict):
            route_out = parsed.get("route")
            if route_out is None and isinstance(parsed.get("routes"), list) and parsed["routes"]:
                route_out, how = parsed["routes"][0], how + "+routes_wrapper"
        ok = isinstance(route_out, dict)
        if ok:
            import copy as _c
            route_out.pop("template_unchanged", None)
            merged = _c.deepcopy(route)
            for f in hybrid.REPAIR_EDITABLE_FIELDS:
                if f in route_out:
                    merged[f] = route_out[f]
            merged["template"] = _c.deepcopy(route.get("template"))
            merged["method"], merged["path"] = route.get("method"), route.get("path")
            edited.setdefault("routes", []).append(merged)
        record["route_results"].append({"route": rkey, "admitted_parse": ok, "how": how})
        (RUN / "result.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    full_spec, diff = hybrid.compose_edited(compiled, edited)
    full_spec = hybrid.enforce_compiled_facts(full_spec, compiled)
    record["model_diff"] = diff
    # S3 per-edit gate: keep only edits that do not regress PUBLIC conformance
    accepted_routes, gate_log = [], []
    edited_list = edited.get("routes", [])
    base_by_key = {(r.get("method"), r.get("path")): r for r in compiled.get("routes", [])}
    for er in edited_list:
        key = (er.get("method"), er.get("path"))
        if json.dumps(base_by_key.get(key), sort_keys=True) == json.dumps(er, sort_keys=True):
            accepted_routes.append(er); continue
        single, _ = hybrid.compose_edited(compiled, {"routes": [er]})
        single = hybrid.enforce_compiled_facts(single, compiled)
        proc, workdir, rb = mx.start_reference(REF_PORT)
        try: sc = hybrid.public_conformance(single, rb, CAND_PORT)
        finally: mx.stop_reference(proc, workdir)
        keep = sc["public_passed"] >= base_conf["public_passed"]
        gate_log.append({"route": list(key), "single_conformance": sc["public_passed"], "kept": keep})
        if keep: accepted_routes.append(er)
    record["per_edit_gate"] = gate_log
    spec, _ = hybrid.compose_edited(compiled, {"routes": accepted_routes})
    spec = hybrid.enforce_compiled_facts(spec, compiled)
    # S3 gate: reject the composed candidate if it regresses public conformance
    proc, workdir, ref_base = mx.start_reference(REF_PORT)
    try:
        conf = hybrid.public_conformance(spec, ref_base, CAND_PORT)
    finally:
        mx.stop_reference(proc, workdir)
    record["candidate_public_conformance"] = {
        "passed": conf["public_passed"], "total": conf["public_total"]}
    if conf["public_passed"] < base_conf["public_passed"]:
        record["gate"] = "REJECTED_REGRESSION: candidate reverted to compiler spec"
        spec = compiled
    else:
        record["gate"] = "accepted_non_regressing"
    record["budget"] = budget.summary()
    record["frozen_score"] = score_suite(spec, "frozen")
    record["extended_score"] = score_suite(spec, "extended")
    record["scored_spec"] = "candidate" if record["gate"].startswith("accepted") else "compiler"
    (RUN / "result.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    receipt_sink("run_completed", {"frozen": record["frozen_score"], "extended": record["extended_score"]})
    print(json.dumps(record, indent=1)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
