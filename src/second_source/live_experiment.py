"""Run a real, budgeted Muse-selected experiment on the owned CLI fixture.

This command is deliberately NOT a code-generation demo. It only proves the G2
causal path: real Muse -> hypotheses -> proposed in-scope actions -> guarded
reference execution -> evidence hashes -> prediction reconciliation.

No credentials are written into the run directory or printed. This is an
explicitly opt-in, billable command; CI never invokes it.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import secrets
import sys

from .budgets import RunBudget
from .contracts import (
    Budgets, ImplementationScope, ObservationScope, ScopeContract,
    ScopeMode, TargetKind, TargetSpec,
)
from .evidence import EvidenceLedger
from .g2_persistence import G2Recorder, PersistenceError, scope_digest_of
from .hypotheses import HypothesisStore
from .loop import DiscoveryLoop
from .model_gateway import MetaProvider, ModelGateway
from .planner import ExperimentPlanner
from .reference import CLIReferenceAdapter
from .runner import SafeCLIExperimentRunner
from .scope_guard import ScopeGuard
from .verifier import DifferentialVerifier, SealedCase

MAX_FIRST_RUN_USD = 0.25
ROOT = Path(__file__).resolve().parents[2]


def _authorized_limit() -> float:
    try:
        return float(os.environ.get("SECOND_SOURCE_MAX_RUN_USD", "0") or "0")
    except ValueError:
        return 0.0


def create_scope(max_usd: float, max_rounds: int) -> ScopeContract:
    """Minimal owned-fixture investigation, with explicit usage controls."""
    return ScopeContract(
        target=TargetSpec(
            kind=TargetKind.CLI,
            reference_command_id="owned-ledger-v1",
            permission_ref="owned-fixture",
        ),
        goal="Discover authorized observable rules of the synthetic ledger CLI",
        mode=ScopeMode.SELECTED_FLOWS,
        observation=ObservationScope(
            permitted_actions=frozenset({"cli"}),
            allowed_commands=frozenset({"add", "list", "total", "remove"}),
        ),
        implementation=ImplementationScope(
            requirements=frozenset({"REQ-LEDGER"}),
            allowed_subsystems=frozenset({"cli_ledger"}),
        ),
        budgets=Budgets(
            max_reference_experiments=max_rounds + 2,
            max_model_calls=2 * max_rounds + 1,  # one guarded corrective propose
            max_wall_seconds=240,
            max_estimated_model_spend_usd=max_usd,
        ),
    )


def _run_directory() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = ROOT / ".runs" / ("real-g2-" + stamp + "-" + secrets.token_hex(4))
    p.mkdir(parents=True, exist_ok=False, mode=0o700)
    return p


def fixture_verifier_summary(reference: CLIReferenceAdapter) -> dict:
    """Trusted verifier-only check: the model never sees these cases or outputs.

    The intentionally faulty candidate is only a harness negative-control,
    NOT a Muse-generated reconstruction.
    """
    buggy = CLIReferenceAdapter(
        [sys.executable, str(ROOT / "fixtures/candidates/buggy.py")],
        cwd=ROOT,
    )
    cases = [
        SealedCase(case_id="harness-empty", actions=({"command": "list"},)),
        SealedCase(
            case_id="harness-duplicate",
            actions=(
                {"command": "add", "label": "Alpha", "amount": 3},
                {"command": "add", "label": "alpha", "amount": 4},
            ),
        ),
    ]
    result = DifferentialVerifier(reference, buggy).verify(cases)
    return {
        "kind": "trusted_harness_negative_control_not_generated_candidate",
        "model_feedback": result.model_feedback(),
    }


def classify_model_failure(note: str) -> str:
    """Redaction-safe failure category for CLI output, never raw model text."""
    if "Meta API HTTP" in note:
        match = re.search(r"Meta API HTTP\s+(\d{3})", note)
        return "META_HTTP_" + match.group(1) if match else "META_HTTP_ERROR"
    if "transport failure" in note:
        return "META_TRANSPORT_ERROR"
    if "MODEL_JSON_INVALID" in note:
        return "MODEL_JSON_INVALID"
    if "MODEL_SCHEMA_INVALID" in note:
        return "MODEL_SCHEMA_INVALID"
    if "empty message content" in note:
        return "EMPTY_MODEL_RESPONSE"
    if "violated JSON schema" in note or "schema violation" in note:
        return "MODEL_SCHEMA_ERROR"
    if "missing choices/message/usage" in note:
        return "META_RESPONSE_SHAPE_ERROR"
    if "forbidden marker" in note:
        return "PROMPT_ISOLATION_ERROR"
    return "MODEL_GATEWAY_ERROR"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explicitly billable G2 smoke: real Muse hypotheses and a guarded experiment"
    )
    parser.add_argument(
        "--max-usd", type=float, required=True,
        help="Approved spend for this single run; initial cap must not exceed $0.25",
    )
    parser.add_argument(
        "--rounds", type=int, default=1, choices=(1, 2),
        help="Maximum experiment rounds (each needs 2 model calls)",
    )
    args = parser.parse_args(argv)

    key = os.environ.get("MODEL_API_KEY", "")
    env_limit = _authorized_limit()
    if not key or env_limit <= 0:
        print(
            "BLOCKED_REAL_MODEL: configure MODEL_API_KEY and "
            "SECOND_SOURCE_MAX_RUN_USD in your local secure environment.",
            file=sys.stderr,
        )
        return 2
    if not (0 < args.max_usd <= min(MAX_FIRST_RUN_USD, env_limit)):
        print(
            "BLOCKED_BUDGET: --max-usd must be positive and <= both "
            "SECOND_SOURCE_MAX_RUN_USD and $0.25 for the initial run.",
            file=sys.stderr,
        )
        return 2

    with (ROOT / "fixtures/owned_ledger/public_contract.json").open(
        encoding="utf-8"
    ) as source:
        public = json.load(source)
    scope = create_scope(args.max_usd, args.rounds)
    if set(public.get("commands", {})) != set(scope.observation.allowed_commands):
        print("BLOCKED_CONTRACT: public command signatures do not match scope", file=sys.stderr)
        return 2

    run_dir = _run_directory()
    ledger = EvidenceLedger(run_dir / "evidence")
    budget = RunBudget(scope.budgets)
    gateway = ModelGateway(MetaProvider(key), budget)
    store = HypothesisStore()
    planner = ExperimentPlanner(
        gateway, ScopeGuard(scope), store, budget, scope,
        public_contract=public,
    )
    reference = CLIReferenceAdapter(
        [sys.executable, str(ROOT / "fixtures/owned_ledger/reference.py")],
        cwd=ROOT,
    )
    runner = SafeCLIExperimentRunner(scope, reference, ledger)
    recorder = G2Recorder(
        run_id=run_dir.name,
        requirement_id="REQ-LEDGER",
        scope_digest=scope_digest_of(scope),
    )
    loop = DiscoveryLoop(
        run_id=run_dir.name,
        requirement_id="REQ-LEDGER",
        contract=scope,
        runner=runner,
        ledger=ledger,
        hypotheses=store,
        planner=planner,
        budget=budget,
        max_rounds=args.rounds,
        recorder=recorder,
    )

    # This is a permitted baseline, not a scripted substitute for the model's
    # proposed experiment. No reference source or withheld cases go to Muse.
    report = loop.run(
        [{"command": "add", "label": "Alpha", "amount": 3}, {"command": "total"}]
    )
    executed = [
        r for r in report.rounds if r.actions_executed > 0 and r.observation_ids
    ]
    status = "REAL_EXPERIMENT_OBSERVED" if (
        report.real_model_calls >= 2 and executed
    ) else "REAL_EXPERIMENT_INCOMPLETE"

    failure_code = None
    if report.stop_reason == "model_error":
        notes = [r.note for r in report.rounds if r.note.startswith("model stop:")]
        failure_code = classify_model_failure(notes[-1]) if notes else "MODEL_GATEWAY_ERROR"

    try:
        manifest_path = recorder.write(run_dir)
        manifest_error = None
    except PersistenceError as exc:
        manifest_path = None
        manifest_error = type(exc).__name__
    output = {
        "result": status,
        "failure_code": failure_code,
        "run_id": report.run_id,
        "report": asdict(report),
        "model_receipts": [r.model_dump(mode="json") for r in gateway.receipts],
        "evidence_artifact_count": len(list(ledger.root.glob("*.json"))),
        "g2_manifest_path": str(manifest_path) if manifest_path else None,
        "g2_manifest_error": manifest_error,
        "independent_fixture_verifier": fixture_verifier_summary(reference),
        "real_vs_mock": "real",
        "note": (
            "Reference source and sealed test inputs are never sent to the model; "
            "report proves scoped discovery only, NOT candidate reconstruction."
        ),
    }
    report_path = run_dir / "run_report.json"
    report_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({
        "result": status,
        "run_id": report.run_id,
        "stop_reason": report.stop_reason,
        "failure_code": failure_code,
        "rejection_codes": list(report.rejection_codes),
        "real_model_calls": report.real_model_calls,
        "actions_observed": sum(r.actions_executed for r in executed),
        "estimated_model_cost_usd": report.budget_summary["estimated_cost_usd"],
        "uncertain_cost_usd": report.budget_summary["uncertain_cost_usd"],
        "report_path": str(report_path),
    }, indent=2))
    return 0 if status == "REAL_EXPERIMENT_OBSERVED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
