"""Reproduce G2 provenance regressions in Muse checkpoint c0e82b5, NON_AI only.

Usage: python scripts/audit_g2_checkpoint.py --repo <clean-c0e82b5-checkout>
Does not checkout, alter project artifacts, dispatch HTTP or use credentials.
Exit 1 means reproduced defects; 2 means the pinned snapshot is unavailable.
This is a retained historical probe, not another product workflow.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

CHECKPOINT = "c0e82b5d763f99ff4631d81dc05363b39b29da0e"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    repo = parser.parse_args().repo.resolve()
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    clean = subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "--", "src", "tests"])
    if head != CHECKPOINT or clean.returncode:
        print("BLOCKED: probe requires the clean pinned source/test snapshot", file=sys.stderr)
        return 2
    sys.path[:0] = [str(repo / "src"), str(repo / "tests")]
    from conftest import cli_scope, reference
    from test_g2_persistence import run_recorded, SEED
    from g2_helpers import responder
    from second_source.budgets import RunBudget
    from second_source.evidence import EvidenceLedger
    from second_source.g2_persistence import G2Recorder, PersistenceError, load_manifest, rebuild_store, scope_digest_of
    from second_source.hypotheses import HypothesisStore
    from second_source.loop import DiscoveryLoop
    from second_source.model_gateway import GatewayError, MetaProvider, MockProvider, ModelGateway
    from second_source.planner import ExperimentPlanner
    from second_source.runner import SafeCLIExperimentRunner
    from second_source.scope_guard import ScopeGuard

    def forbidden(*args, **kwargs):
        raise AssertionError("No genuine provider/HTTP call is authorized")
    MetaProvider.complete = forbidden
    urllib.request.urlopen = forbidden
    scope, ref = cli_scope.__wrapped__(), reference.__wrapped__()
    results = {"source_sha": head, "origin": "NON_AI", "provider_transport_calls": 0}
    with tempfile.TemporaryDirectory(prefix="codex-g2-checkpoint-") as temporary:
        root = Path(temporary)
        _, recorder, _, _, _ = run_recorded(scope, ref, root)
        path = recorder.write(root / "run")
        original = json.loads(path.read_bytes())
        path.write_text(json.dumps(dict(original, model_receipts=[])), encoding="utf-8")
        try:
            load_manifest(path)
            results["missing_all_receipts_accepted"] = True
        except PersistenceError:
            results["missing_all_receipts_accepted"] = False
        changed = json.loads(json.dumps(original))
        changed["final_hypotheses"][0]["statement"] = "NON_AI deliberately substituted statement"
        path.write_text(json.dumps(changed), encoding="utf-8")
        try:
            restored = rebuild_store(load_manifest(path))
            results["substituted_final_statement_accepted"] = any(
                h.statement.startswith("NON_AI deliberately") for h in restored.all()
            )
        except PersistenceError:
            results["substituted_final_statement_accepted"] = False
        partial = root / "failure"
        partial.mkdir()
        ledger = EvidenceLedger(partial / "evidence")
        budget = RunBudget(scope.budgets)
        original_response = responder()
        def fail_propose(request):
            if request.stage == "propose":
                raise GatewayError("NON_AI proposal failure")
            return original_response(request)
        gateway = ModelGateway(MockProvider(responder=fail_propose), budget)
        store = HypothesisStore()
        planner = ExperimentPlanner(gateway, ScopeGuard(scope), store, budget, scope)
        recorder = G2Recorder(run_id="failure", requirement_id="REQ-LEDGER", scope_digest=scope_digest_of(scope))
        loop = DiscoveryLoop(run_id="failure", requirement_id="REQ-LEDGER", contract=scope,
                             runner=SafeCLIExperimentRunner(scope, ref, ledger), ledger=ledger,
                             hypotheses=store, planner=planner, budget=budget, max_rounds=1, recorder=recorder)
        loop.run(list(SEED))
        try:
            recorder.write(partial)
            results["propose_failure_loses_successful_hypothesis"] = False
        except PersistenceError:
            results["propose_failure_loses_successful_hypothesis"] = bool(store.all()) and not (partial / "g2_manifest.json").exists()
        results["failure_attempts"] = budget.attempts
        results["failure_settled_calls"] = budget.model_calls
    pins = []
    for seed in ("1", "37", "99"):
        env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH") if name in os.environ}
        env.update(PYTHONPATH=str(repo / "src"), PYTHONHASHSEED=seed, SECOND_SOURCE_MAX_RUN_USD="0")
        code = ("from second_source.live_experiment import create_scope; "
                "from second_source.g2_persistence import scope_digest_of; "
                "print(scope_digest_of(create_scope(.25,1)))")
        pins.append(subprocess.check_output([sys.executable, "-B", "-c", code], env=env, text=True).strip())
    results["scope_hash_seed_stable"] = len(set(pins)) == 1
    print(json.dumps(results, indent=2))
    defects = (results["missing_all_receipts_accepted"], results["substituted_final_statement_accepted"],
               results["propose_failure_loses_successful_hypothesis"], not results["scope_hash_seed_stable"])
    return int(any(defects))


if __name__ == "__main__":
    raise SystemExit(main())
