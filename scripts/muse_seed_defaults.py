"""Muse causal-contribution experiment: default-entity seeding.

Packet muse-seed-20261104 (max 2 calls / $0.25). Baseline candidate
scores 18/19 on the Vikunja public ladder; the sole divergence is
GET /projects: the reference lists per-user default projects the
candidate never creates. Muse is shown only public evidence (the
observed project-list titles, the titles created in observations, and
the divergence shape) and proposes which titles are system defaults.
The candidate's seed_defaults rule applies exactly Muse's titles;
the identical public ladder decides. Public data only.
"""
from __future__ import annotations
import copy, json, os, sys
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
RUN = ROOT / ".runs" / "muse-seed-20261104b"
PACKET = SpendPacketV1(packet_id="muse-seed-20261104b", owner_id="owner",
                       investigation_id="vikunja-muse-seed-defaults",
                       max_spend_usd=0.25, max_model_calls=2, fresh=True, mode="paid")


def sink(kind, payload):
    RUN.mkdir(parents=True, exist_ok=True)
    with open(RUN / "receipts.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": kind, **payload}, default=str) + "\n")
        fh.flush(); os.fsync(fh.fileno())


def save(rec):
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "result.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")


def conformance(spec):
    proc, workdir, ref_base = mx.start_reference(4291)
    try:
        return hybrid.public_conformance(spec, ref_base, 4292)
    finally:
        mx.stop_reference(proc, workdir)


def main():
    if not os.environ.get("MODEL_API_KEY"):
        print("BLOCKED: MODEL_API_KEY not set."); return 2
    SpendingGuard().check(PACKET, estimated_usd=0.25,
                          investigation_id=PACKET.investigation_id)
    obs = json.loads((ROOT / ".runs/vikunja-benchmark/public_observations.json").read_text(encoding="utf-8"))
    spec = evidence_compiler.compile_spec(obs)
    base = conformance(spec)
    record = {"kind": "MUSE_SEED_DEFAULTS_V1", "classification": "REAL_MODEL",
              "packet_id": PACKET.packet_id, "calls": 0,
              "baseline": {"passed": base["public_passed"], "total": base["public_total"]}}
    save(record)
    print(f"baseline {base['public_passed']}/{base['public_total']}", flush=True)

    list_obs = next(o for o in obs if o.get("action") == "GET /projects" and isinstance(o.get("body"), list))
    exemplar_titles = [i.get("title") for i in list_obs["body"] if isinstance(i, dict)]
    created_titles = sorted({(o.get("request") or {}).get("title") for o in obs
                             if isinstance(o.get("request"), dict) and (o.get("request") or {}).get("title")})
    prompt = (
        "You are Muse inside Second Source. Independent verification shows one "
        "remaining divergence on the Vikunja public ladder: for GET /projects the "
        "reference returns 3 projects for a user, the candidate returns only the "
        "1 project the user created. The reference evidently creates some "
        "projects by default for every new user.\n\n"
        f"Titles in the observed full project list: {json.dumps(exemplar_titles)}\n"
        f"Titles explicitly created in observed requests: {json.dumps(created_titles)}\n\n"
        "Which titles are system-default projects every user receives (not "
        "user-created)? Reply JSON only: {\"seed_titles\": [\"...\"]}")
    budget = RunBudget(Budgets(max_model_calls=2, max_estimated_model_spend_usd=0.25))
    gateway = ModelGateway(MetaProvider(api_key=os.environ["MODEL_API_KEY"]), budget, audit=sink)
    try:
        resp = gateway.generate(ModelRequest(
            stage="muse_seed_defaults", prompt_version="muse-seed-v1",
            messages=({"role": "user", "content": prompt},), max_output_tokens=1500))
        record["calls"] += 1
        titles = json.loads(resp.content_text or "{}").get("seed_titles")
    except Exception as exc:
        record.update(failure_class="INFRASTRUCTURE", detail=f"{type(exc).__name__}: {exc}"[:250])
        save(record); print(json.dumps(record, indent=1)); return 0
    record["muse_seed_titles"] = titles
    if not isinstance(titles, list) or not titles:
        record["outcome"] = "no_seed_proposal"
        save(record); print(json.dumps(record, indent=1)); return 0
    trial = copy.deepcopy(spec)
    for route in trial["routes"]:
        if route.get("method") == "GET" and route.get("path") == "/projects":
            route["seed_defaults"] = titles
    got = conformance(trial)
    record["after"] = {"passed": got["public_passed"], "total": got["public_total"],
                       "divergences": [d["action"] for d in got["divergences"]]}
    record["outcome"] = ("accepted_improvement" if got["public_passed"] > base["public_passed"]
                         else "not_improving")
    record["headline"] = (f"Muse default-seeding: {base['public_passed']}/{base['public_total']} -> "
                          f"{got['public_passed']}/{got['public_total']} (titles={titles})")
    record["budget"] = budget.summary()
    save(record)
    sink("run_completed", {"headline": record["headline"]})
    print(json.dumps(record, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
