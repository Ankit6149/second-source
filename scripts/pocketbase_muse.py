"""Muse gated route experiments on PocketBase (new target).

Same pattern as muse_experiment_all (FB/Gitea): compiler baseline,
then Muse reviews up to 6 routes under a $0.50 / 6-call packet;
only strict public improvement is kept. Public evidence only.
"""
from __future__ import annotations
import hashlib, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import filebrowser_benchmark as fb  # noqa: E402
import pocketbase_benchmark as pb  # noqa: E402
from muse_experiment_all import run_target  # noqa: E402


def main():
    if not os.environ.get("MODEL_API_KEY"):
        print("BLOCKED: MODEL_API_KEY not set. Zero calls."); return 2
    obs = pb.public_probes()
    digest = hashlib.sha256(json.dumps(obs, sort_keys=True, default=str).encode()).hexdigest()
    spec = fb.compile_spec(obs, digest)
    spec.setdefault("auth", {})["raw_header_name"] = "X-Auth"
    spec["users"] = {"alice": "alice@ss.local"}
    rec = run_target("pocketbase", "muse-exp-pb-20261104", obs, spec,
                     pb.pb_score, "muse-exp-pb-20261104")
    print(rec["headline"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
