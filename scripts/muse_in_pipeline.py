"""Muse (REAL_MODEL) inside the Second Source pipeline — packet
muse-in-pipeline-20261104.

Flow: public observations -> NON_AI compiler baseline -> public-ladder
conformance -> Muse proposes bounded rule repairs for the divergent
routes only (public evidence only; held-out data never enters prompts)
-> public-conformance gate -> measured before/after. The compiler is
Muse's notebook: observed templates/methods/paths are immutable, Muse
edits only contract fields (kind/status/access/collection/auth/
validate/forbidden_body). Receipts fsync-appended at each call.
"""
from __future__ import annotations
import copy, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import evidence_compiler  # noqa: E402
import vikunja_hybrid_experiment as hybrid  # noqa: E402
import vikunja_model_experiment as mx  # noqa: E402
from second_source.budgets import RunBudget  # noqa: E402
from second_source.contracts import Budgets  # noqa: E402
from second_source.model_gateway import MetaProvider, ModelGateway, ModelRequest  # noqa: E402
from second_source.orchestration.guard import SpendingGuard, SpendPacketV1  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".runs" / "muse-in-pipeline-20261104"
OBS_PATH = ROOT / ".runs" / "vikunja-benchmark" / "public_observations.json"
PACKET = SpendPacketV1(packet_id="muse-in-pipeline-20261104", owner_id="owner",
                       investigation_id="vikunja-muse-in-pipeline",
                       max_spend_usd=0.5, max_model_calls=3, fresh=True, mode="paid")
REF_PORT, CAND_PORT = 3591, 3592
MAX_CALLS = 3


def receipt_sink(kind, payload):
    RUN.mkdir(parents=True, exist_ok=True)
    with open(RUN / "receipts.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": kind, **payload}, default=str) + "\n")
        fh.flush(); os.fsync(fh.fileno())


def save(record):
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "result.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


def conformance(spec):
    proc, workdir, ref_base = mx.start_reference(REF_PORT)
    try:
        return hybrid.public_conformance(spec, ref_base, CAND_PORT)
    finally:
        mx.stop_reference(proc, workdir)


def main() -> int:
    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        print("BLOCKED: MODEL_API_KEY not set. Zero calls."); return 2
    SpendingGuard().check(PACKET, estimated_usd=0.5,
                          investigation_id=PACKET.investigation_id)
    obs_list = json.loads(OBS_PATH.read_text(encoding="utf-8"))
    compiled = evidence_compiler.compile_spec(obs_list)
    record = {"kind": "VIKUNJA_MUSE_IN_PIPELINE_V1",
              "classification": "REAL_MODEL", "provider": "meta-direct",
              "model": "muse-spark-1.3", "packet_id": PACKET.packet_id,
              "max_spend_usd": 0.5, "max_calls": MAX_CALLS, "calls": 0,
              "rounds": []}
    base = conformance(compiled)
    record["compiler_baseline_public"] = {
        "passed": base["public_passed"], "total": base["public_total"],
        "divergences": [d["action"] for d in base["divergences"]]}
    save(record)
    print(f"baseline (compiler): {base['public_passed']}/{base['public_total']}", flush=True)

    budget = RunBudget(Budgets(max_model_calls=MAX_CALLS,
                               max_estimated_model_spend_usd=0.5))
    gateway = ModelGateway(MetaProvider(api_key=key), budget, audit=receipt_sink)
    spec, conf = compiled, base
    for rnd in range(1, MAX_CALLS + 1):
        if not conf["divergences"]:
            break
        div_actions = {d["action"] for d in conf["divergences"]}
        routes = [r for r in spec.get("routes", [])
                  if f"{r.get('method')} {r.get('path')}" in div_actions]
        prompt = (
            "You are Muse inside Second Source, an evidence-first software "
            "reconstruction system. The deterministic compiler already "
            "transcribed every observed fact; the routes below are its "
            "current contract for the DIVERGENT public cases. Observed "
            "templates, methods and paths are immutable. You may edit only "
            "these fields per route: kind, status, access, collection, "
            "auth, validate, forbidden_body. Diagnose why the candidate "
            "diverges from the reference and propose corrected contracts.\n\n"
            "DIVERGENCES (public ladder only):\n"
            + hybrid.diff_text(conf["divergences"], limit=8)
            + "\n\nCURRENT ROUTES (JSON):\n"
            + json.dumps(routes, indent=1)[:12000]
            + "\n\nReply with JSON only: {\"routes\": [edited route objects]}")
        try:
            resp = gateway.generate(ModelRequest(
                stage="muse_in_pipeline_repair",
                prompt_version="muse-in-pipeline-v1",
                messages=({"role": "user", "content": prompt},),
                max_output_tokens=3000))
            record["calls"] += 1
            text = resp.content_text or ""
        except Exception as exc:
            record.update(failure_class="INFRASTRUCTURE",
                          detail=f"{type(exc).__name__}: {exc}"[:300])
            save(record); receipt_sink("run_aborted", {"error": str(exc)[:200]})
            print(json.dumps(record, indent=1)); return 0
        try:
            parsed = json.loads(text)
        except Exception:
            parsed, _ = hybrid.parse_route_json(text)
        edited_routes = parsed.get("routes") if isinstance(parsed, dict) else None
        round_rec = {"round": rnd, "admitted": bool(edited_routes)}
        if edited_routes:
            merged_spec, _ = hybrid.compose_edited(spec, {"routes": edited_routes})
            merged_spec = hybrid.enforce_compiled_facts(merged_spec, compiled)
            new_conf = conformance(merged_spec)
            round_rec.update(before=conf["public_passed"],
                             after=new_conf["public_passed"])
            if new_conf["public_passed"] >= conf["public_passed"]:
                spec, conf = merged_spec, new_conf
                round_rec["kept"] = True
            else:
                round_rec["kept"] = False
        record["rounds"].append(round_rec)
        record["candidate_public"] = {"passed": conf["public_passed"],
                                      "total": conf["public_total"],
                                      "divergences": [d["action"] for d in conf["divergences"]]}
        save(record)
        print(f"round {rnd}: {round_rec}", flush=True)
    record["budget"] = budget.summary()
    record["gate"] = ("accepted_non_regressing" if conf["public_passed"] >= base["public_passed"]
                      else "reverted_to_compiler")
    record["headline"] = (
        f"Muse in-pipeline repair: public conformance "
        f"{base['public_passed']}/{base['public_total']} -> "
        f"{conf['public_passed']}/{conf['public_total']} "
        f"({record['calls']} Muse calls, REAL_MODEL; compiler baseline NON_AI; "
        f"public cases only, held-out never in prompts)")
    save(record)
    receipt_sink("run_completed", {"headline": record["headline"]})
    print(json.dumps(record, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
