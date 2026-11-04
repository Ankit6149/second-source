"""Muse working inside the Vikunja experiment, one route at a time.

Packet muse-exp-routes-20261104. The NON_AI compiler supplies the
baseline candidate. For each initially divergent public-ladder route,
Muse receives that single compiled route, its public observations,
and the public reference/candidate divergence. Muse may change only
contract fields; compiled templates, methods, and paths are restored.
Each single-route candidate is replayed on the identical public ladder.
An edit is kept only when the score strictly improves.

Held-out cases are never loaded or shown to the model. Provider
failures are recorded and unscored. Receipts are appended with fsync by
the gateway audit sink.
"""
from __future__ import annotations

import copy
import json
import os
import sys
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
RUN = ROOT / ".runs" / "muse-exp-routes-20261104"
OBS_PATH = ROOT / ".runs" / "vikunja-benchmark" / "public_observations.json"
PACKET = SpendPacketV1(
    packet_id="muse-exp-routes-20261104",
    owner_id="owner",
    investigation_id="vikunja-muse-experiment-routes",
    max_spend_usd=0.75,
    max_model_calls=8,
    fresh=True,
    mode="paid",
)
REF_PORT = 3691
CAND_PORT = 3692
MAX_CALLS = 8


def receipt_sink(kind, payload):
    RUN.mkdir(parents=True, exist_ok=True)
    with open(RUN / "receipts.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": kind, **payload}, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def save(record):
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "result.json").write_text(
        json.dumps(record, indent=1), encoding="utf-8")


def conformance(spec):
    proc, workdir, ref_base = mx.start_reference(REF_PORT)
    try:
        return hybrid.public_conformance(spec, ref_base, CAND_PORT)
    finally:
        mx.stop_reference(proc, workdir)


def route_key(route_or_action):
    if isinstance(route_or_action, dict):
        return route_or_action.get("method", ""), route_or_action.get("path", "")
    method, path = str(route_or_action).split(" ", 1)
    return method, path.split("?")[0]


def find_route(spec, key):
    for route in spec.get("routes", []):
        if route_key(route) == key:
            return route
    return None


def replace_route(spec, key, replacement):
    out = copy.deepcopy(spec)
    for idx, route in enumerate(out.get("routes", [])):
        if route_key(route) == key:
            out["routes"][idx] = copy.deepcopy(replacement)
            return out
    raise KeyError(key)


def extract_route(parsed):
    if not isinstance(parsed, dict):
        return None
    route = parsed.get("route")
    if isinstance(route, dict):
        return route
    routes = parsed.get("routes")
    if isinstance(routes, list) and routes and isinstance(routes[0], dict):
        return routes[0]
    return None


def main() -> int:
    api_key = os.environ.get("MODEL_API_KEY", "")
    if not api_key:
        print("BLOCKED: MODEL_API_KEY not set. Zero calls.")
        return 2

    SpendingGuard().check(
        PACKET, estimated_usd=0.75,
        investigation_id=PACKET.investigation_id)
    observations = json.loads(OBS_PATH.read_text(encoding="utf-8"))
    compiled = evidence_compiler.compile_spec(observations)
    spec = copy.deepcopy(compiled)

    record = {
        "kind": "VIKUNJA_MUSE_EXPERIMENT_ROUTES_V1",
        "classification": "REAL_MODEL",
        "provider": "meta-direct",
        "model": "muse-spark-1.3",
        "packet_id": PACKET.packet_id,
        "max_spend_usd": 0.75,
        "max_calls": MAX_CALLS,
        "calls": 0,
        "method": "one divergent route per Muse call; strict public-ladder improvement gate",
        "attempts": [],
    }

    current = conformance(spec)
    record["baseline_public"] = {
        "passed": current["public_passed"],
        "total": current["public_total"],
        "divergences": [d["action"] for d in current["divergences"]],
    }
    save(record)
    print(
        f"Compiler baseline: {current['public_passed']}/{current['public_total']}",
        flush=True)

    initial_keys = []
    for divergence in current["divergences"]:
        key = route_key(divergence["action"])
        if key not in initial_keys:
            initial_keys.append(key)

    budget = RunBudget(Budgets(
        max_model_calls=MAX_CALLS,
        max_estimated_model_spend_usd=0.75))
    gateway = ModelGateway(
        MetaProvider(api_key=api_key), budget, audit=receipt_sink)

    for key in initial_keys[:MAX_CALLS]:
        route = find_route(spec, key)
        if route is None:
            record["attempts"].append({
                "route": list(key), "status": "route_not_in_candidate"})
            save(record)
            continue

        current_divergences = [
            d for d in current["divergences"]
            if route_key(d["action"]) == key]
        if not current_divergences:
            record["attempts"].append({
                "route": list(key), "status": "already_resolved"})
            save(record)
            continue

        prompt = hybrid.build_route_prompt(route, observations)
        context = (
            "\n\nINDEPENDENT PUBLIC CHECK FOR THIS ROUTE:\n"
            + hybrid.diff_text(current_divergences, limit=4)
            + "\n\nCorrect only this route. Preserve all conforming "
              "behavior and the compiled template.\n\n")
        if mx.JSON_FIRST in prompt:
            prompt = prompt.replace(
                mx.JSON_FIRST, context + mx.JSON_FIRST, 1)
        else:
            prompt += context

        before = current["public_passed"]
        attempt = {"route": list(key), "before": before}
        try:
            response = gateway.generate(ModelRequest(
                stage="muse_experiment_route_repair",
                prompt_version="muse-exp-routes-v1",
                messages=({"role": "user", "content": prompt},),
                max_output_tokens=2000))
            record["calls"] += 1
            text = response.content_text or ""
        except Exception as exc:
            attempt.update(
                status="provider_failure_unscored",
                detail=f"{type(exc).__name__}: {exc}"[:300])
            record["attempts"].append(attempt)
            record["failure_class"] = "INFRASTRUCTURE"
            save(record)
            receipt_sink("run_aborted", {
                "route": list(key), "error": str(exc)[:200]})
            break

        parsed, how = hybrid.parse_route_json(text)
        proposed_model_route = extract_route(parsed)
        attempt["parse"] = how
        if proposed_model_route is None:
            attempt["status"] = "unparseable_no_edit"
            record["attempts"].append(attempt)
            save(record)
            print(f"Muse {key}: unparseable; no edit", flush=True)
            continue

        proposed = copy.deepcopy(route)
        changed_fields = []
        for field in hybrid.REPAIR_EDITABLE_FIELDS:
            if field in proposed_model_route:
                if proposed.get(field) != proposed_model_route[field]:
                    changed_fields.append(field)
                proposed[field] = proposed_model_route[field]
        proposed["template"] = copy.deepcopy(route.get("template"))
        proposed["method"] = route.get("method")
        proposed["path"] = route.get("path")
        attempt["changed_fields"] = changed_fields

        if proposed == route:
            attempt.update(status="no_contract_change", after=before, kept=False)
            record["attempts"].append(attempt)
            save(record)
            print(f"Muse {key}: no contract change", flush=True)
            continue

        trial_spec = replace_route(spec, key, proposed)
        trial_spec = hybrid.enforce_compiled_facts(trial_spec, compiled)
        trial = conformance(trial_spec)
        after = trial["public_passed"]
        kept = after > before
        attempt.update(status="evaluated", after=after, kept=kept)
        record["attempts"].append(attempt)
        if kept:
            spec, current = trial_spec, trial
        record["candidate_public"] = {
            "passed": current["public_passed"],
            "total": current["public_total"],
            "divergences": [d["action"] for d in current["divergences"]],
        }
        save(record)
        print(
            f"Muse {key}: {before} -> {after}; kept={kept}",
            flush=True)

    record["candidate_public"] = {
        "passed": current["public_passed"],
        "total": current["public_total"],
        "divergences": [d["action"] for d in current["divergences"]],
    }
    record["accepted_routes"] = [
        a["route"] for a in record["attempts"] if a.get("kept")]
    record["budget"] = budget.summary()
    record["result"] = (
        "improved" if current["public_passed"] > record["baseline_public"]["passed"]
        else "no_deployable_improvement")
    record["headline"] = (
        f"Muse experiment (REAL_MODEL): Vikunja public ladder "
        f"{record['baseline_public']['passed']}/{record['baseline_public']['total']} -> "
        f"{current['public_passed']}/{current['public_total']} after "
        f"{record['calls']} route-level Muse calls; kept edits: "
        f"{record['accepted_routes']}")
    save(record)
    receipt_sink("run_completed", {"headline": record["headline"]})
    print(json.dumps(record, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
