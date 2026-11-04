"""Muse must IMPROVE a failing PocketBase baseline (public evidence only).

Baseline candidate scores 9/12: filter/sort/pagination divergences.
One gated Muse call may propose query_features on the list route;
the identical case suite decides. Packet: 1 call / $0.50 max.
"""
from __future__ import annotations
import hashlib, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import filebrowser_benchmark as fb  # noqa: E402
import pocketbase_benchmark as pb  # noqa: E402
from muse_pipeline_repair import attempt_muse_public_repair  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".runs" / "muse-pb-repair-20261104"
CASE_ACTION = {
    "filter_done": "GET /api/collections/notes/records?filter=(done = true)",
    "sort_title": "GET /api/collections/notes/records?sort=title",
    "pagination": "GET /api/collections/notes/records?perPage=2",
}


def to_conf(res):
    divs = [{"action": CASE_ACTION.get(k, k),
             "reference": res["detail"][k]["ref"],
             "candidate": res["detail"][k]["cand"]} for k in res["divergences"]]
    return {"public_passed": res["passed"], "public_total": res["total"],
            "divergences": divs}


def main():
    if not os.environ.get("MODEL_API_KEY"):
        print("BLOCKED: MODEL_API_KEY not set. Zero calls."); return 2
    obs = pb.public_probes()
    digest = hashlib.sha256(json.dumps(obs, sort_keys=True, default=str).encode()).hexdigest()
    spec = fb.compile_spec(obs, digest)
    spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
    spec["users"] = {"alice": "alice@ss.local"}
    base = to_conf(pb.pb_score(spec))
    print(f"baseline {base['public_passed']}/{base['public_total']} "
          f"div={[d['action'] for d in base['divergences']]}", flush=True)
    RUN.mkdir(parents=True, exist_ok=True)
    audit = RUN / "receipts.jsonl"

    def sink(kind, payload):
        with open(audit, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": kind, **payload}, default=str) + "\n")
            fh.flush(); os.fsync(fh.fileno())

    selected, conf, summary = attempt_muse_public_repair(
        compiled=spec, observations=obs, baseline=base,
        measure=lambda s: to_conf(pb.pb_score(s)),
        api_key=os.environ["MODEL_API_KEY"], record_audit=sink)
    record = {"target": "pocketbase-v0.28.4", "baseline": base,
              "final": {"passed": conf["public_passed"], "total": conf["public_total"]},
              "model": summary}
    (RUN / "result.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"outcome": summary.get("outcome"), "called": summary.get("called"),
                      "accepted": summary.get("accepted"),
                      "changed": summary.get("changed_fields"),
                      "baseline": base["public_passed"], "final": conf["public_passed"],
                      "total": conf["public_total"],
                      "cost_usd": (summary.get("receipt") or {}).get("estimated_cost_usd")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
