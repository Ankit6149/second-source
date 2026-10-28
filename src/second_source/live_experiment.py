"""Durable discovery on the owned CLI: inspection, NON_AI mock, or approved Meta.

This command is deliberately NOT a code-generation demo. It only proves the G2
causal path: real Muse -> hypotheses -> proposed in-scope actions -> guarded
reference execution -> evidence hashes -> prediction reconciliation.

No credentials are written into the run directory or printed. Explicitly
approved real mode is billable; inspection and mock modes are not.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
import re
from pathlib import Path
import secrets
import sys

from .budgets import MODEL_PRICING, RunBudget, TokenCaps
from .contracts import (
    Budgets, ImplementationScope, ObservationScope, ScopeContract,
    ScopeMode, TargetKind, TargetSpec,
)
from .evidence import EvidenceLedger, publish_once, redact
from .g2_persistence import DiscoveryJournal, canonical, digest, export_batch, inspect_run, scope_digest_of
from .hypotheses import HypothesisStore
from .loop import DiscoveryLoop
from .model_gateway import DEFAULT_MODEL, MetaProvider, MockProvider, ModelGateway
from .planner import ExperimentPlanner
from .reference import CLIReferenceAdapter
from .runner import SafeCLIExperimentRunner
from .scope_guard import ScopeGuard
from .verifier import DifferentialVerifier, SealedCase

MAX_FIRST_RUN_USD = 0.25
ROOT = Path(__file__).resolve().parents[2]


def _authorized_limit() -> float:
    try:
        value = float(os.environ.get("SECOND_SOURCE_MAX_RUN_USD", "0") or "0")
        return value if math.isfinite(value) else 0.0
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


def _run_directory(mode="real", explicit: Path | None = None) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = explicit if explicit is not None else ROOT / ".runs" / (mode + "-g2-" + stamp + "-" + secrets.token_hex(4))
    p.mkdir(parents=True, exist_ok=False, mode=0o700)
    return p


def _mock_response(request):
    """Scripted plumbing control, explicitly NON_AI; never historical evidence."""
    user = json.loads(next(m["content"] for m in request.messages if m["role"] == "user"))
    if request.stage == "hypothesize":
        return {"content": {"schema_version": "1.0", "hypotheses": [{
            "id": "mock-rule", "statement": "NON_AI control: total accepts an empty parameter set",
            "evidence_ids": [user["evidence"][0]["digest"]], "status": "hypothesized",
            "alternatives": ["total requires a parameter"], "unresolved_questions": [],
        }]}}
    return {"content": {"proposals": [{
        "proposal_id": "mock-probe", "requirement_id": "REQ-LEDGER",
        "hypothesis_ids": ["mock-rule"], "question": "NON_AI total probe",
        "reset_boundary": "fresh_process_per_sequence",
        "actions": [{"command": "total", "params": {}}],
        "predictions": [{"hypothesis_id": "mock-rule", "expects_ok": True}],
        "expected_information_gain": "control", "side_effect": "read_only",
        "role": "guest", "requires_auth": False,
    }]}}


def _discovery_manifest(scope, mode, rounds):
    names = ("live_experiment", "g2_persistence", "loop", "planner", "model_gateway",
             "budgets", "hypotheses", "evidence", "runner", "reference", "scope_guard", "contracts",
             "schema_validate", "__init__")
    package = Path(__file__).resolve().parent
    pins = {name: digest((package / (name + ".py")).read_bytes()) for name in names}
    pins["reference_fixture"] = digest((ROOT / "fixtures/owned_ledger/reference.py").read_bytes())
    pins["public_manifest"] = digest((ROOT / "fixtures/owned_ledger/public_contract.json").read_bytes())
    return {"origin": mode, "provider": "mock" if mode == "mock" else "meta-direct",
            "model": "mock-muse-0" if mode == "mock" else DEFAULT_MODEL,
            "scope": json.loads(canonical(scope.model_dump(mode="python"))),
            "scope_digest": scope_digest_of(scope), "rounds": rounds, "code_pins": pins,
            "seed_actions": _seed_actions(),
            "token_caps": TokenCaps().model_dump(mode="json"),
            "pricing_usd_per_million": list(MODEL_PRICING[DEFAULT_MODEL]) if mode == "real" else [0.0, 0.0],
            "response_archive": "private-local-original-text-not-sanitized-export",
            "automatic_resume": False}


def _seed_actions():
    return [{"command": "add", "label": "Alpha", "amount": 3}, {"command": "total"}]


def _progress(stage, run_id):
    """Announce an already published journal stage; never print private payloads."""
    print(json.dumps({"progress": stage, "run_id": run_id}), file=sys.stderr)


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
        "--max-usd", type=float, default=0.0,
        help="Approved spend for this single run; initial cap must not exceed $0.25",
    )
    parser.add_argument("--mode", choices=("real", "mock", "preflight"), default="real")
    parser.add_argument("--confirm-real-run", action="store_true")
    parser.add_argument("--operator-manifest-pin", help="Owner-approved G2 preflight manifest SHA-256")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--inspect-run", type=Path, help="Offline read-only reload; no execution resume")
    parser.add_argument("--receipt-sha256", help="Externally retained exact G2_receipt.json hash")
    parser.add_argument("--export-batch", type=Path, help="Create-once G3 input from a complete inspected run")
    parser.add_argument(
        "--rounds", type=int, default=1, choices=(1, 2),
        help="Maximum experiment rounds (each needs 2 model calls)",
    )
    args = parser.parse_args(argv)
    if args.inspect_run:
        try:
            result = inspect_run(args.inspect_run, args.receipt_sha256)
            if args.export_batch:
                if not args.receipt_sha256:
                    raise ValueError("Export requires --receipt-sha256")
                export_batch(args.inspect_run, args.export_batch,
                             expected_receipt_sha256=args.receipt_sha256)
            summary = {k: v for k, v in result.items()
                       if k not in ("hypothesis_batches", "pending_attempt", "reconciled_hypotheses", "completed_rounds")}
            print(json.dumps(redact(summary), indent=2))
            return 0 if result["complete"] else 3
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print("BLOCKED_ARCHIVE: " + type(exc).__name__, file=sys.stderr)
            return 2
    if args.export_batch or args.receipt_sha256:
        parser.error("--export-batch/--receipt-sha256 require --inspect-run")
    key = ""
    env_limit = _authorized_limit()
    if args.mode == "real" and env_limit <= 0:
        print(
            "BLOCKED_REAL_MODEL: configure MODEL_API_KEY and "
            "SECOND_SOURCE_MAX_RUN_USD in your local secure environment.",
            file=sys.stderr,
        )
        return 2
    if (not math.isfinite(args.max_usd) or
            (args.mode == "real" and not (0 < args.max_usd <= min(MAX_FIRST_RUN_USD, env_limit))) or
            (args.mode == "preflight" and not (0 < args.max_usd <= MAX_FIRST_RUN_USD)) or
            (args.mode == "mock" and args.max_usd != 0)):
        print(
            "BLOCKED_BUDGET: --max-usd must be positive and <= both "
            "SECOND_SOURCE_MAX_RUN_USD and $0.25 for the initial run.",
            file=sys.stderr,
        )
        return 2
    if args.mode == "real":
        if not args.confirm_real_run:
            print("BLOCKED_REAL_MODEL: explicit --confirm-real-run is required", file=sys.stderr)
            return 2

    with (ROOT / "fixtures/owned_ledger/public_contract.json").open(
        encoding="utf-8"
    ) as source:
        public = json.load(source)
    scope = create_scope(args.max_usd, args.rounds)
    if set(public.get("commands", {})) != set(scope.observation.allowed_commands):
        print("BLOCKED_CONTRACT: public command signatures do not match scope", file=sys.stderr)
        return 2

    manifest = _discovery_manifest(scope, "real" if args.mode == "preflight" else args.mode, args.rounds)
    manifest_pin = digest(canonical(manifest))
    if args.mode == "preflight":
        run_dir = _run_directory(args.mode, args.run_dir)
        receipt = {"origin": "inspection-only", "provider_calls": 0,
                   "manifest_sha256": manifest_pin, "manifest": manifest}
        path = publish_once(run_dir / "G2_preflight.json", canonical(receipt))
        _progress("preflight_ready", run_dir.name)
        print(json.dumps({"origin": "inspection-only", "provider_calls": 0,
                          "manifest_sha256": manifest_pin, "receipt_sha256": digest(path.read_bytes()),
                          "report_path": str(path)}, indent=2))
        return 0
    if args.mode == "real":
        if args.operator_manifest_pin != manifest_pin:
            print("BLOCKED_REAL_MODEL: exact owner-approved --operator-manifest-pin is required", file=sys.stderr)
            return 2
        key = os.environ.get("MODEL_API_KEY", "")
        if not key:
            print("BLOCKED_REAL_MODEL: server-side key is required", file=sys.stderr)
            return 2

    run_dir = _run_directory(args.mode, args.run_dir)
    ledger = EvidenceLedger(run_dir / "evidence")
    budget = RunBudget(scope.budgets)
    journal = DiscoveryJournal(run_dir, manifest, progress=_progress)
    gateway = ModelGateway(MockProvider(responder=_mock_response) if args.mode == "mock" else MetaProvider(key),
                           budget, audit=journal.append)
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
        journal=journal,
    )

    # This is a permitted baseline, not a scripted substitute for the model's
    # proposed experiment. No reference source or withheld cases go to Muse.
    try:
        report = loop.run(_seed_actions())
    except BaseException as exc:
        # Never persist exception text, request headers, keys or guessed usage.
        journal.finish(state="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                       report={"failure_code": type(exc).__name__, "budget": budget.summary()},
                       hypotheses=[h.model_dump(mode="json") for h in store.all()], receipts=gateway.receipts)
        if isinstance(exc, KeyboardInterrupt):
            return 130
        raise
    executed = [
        r for r in report.rounds if r.actions_executed > 0 and r.observation_ids
    ]
    complete = bool(executed) and report.stop_reason == "stalled" and len(gateway.receipts) >= 2
    prefix = "MOCK" if args.mode == "mock" else "REAL"
    status = prefix + ("_EXPERIMENT_OBSERVED" if complete else "_EXPERIMENT_INCOMPLETE")
    journal.finish(state="completed" if complete else "stopped", report=asdict(report),
                   hypotheses=[h.model_dump(mode="json") for h in store.all()], receipts=gateway.receipts)
    archive = inspect_run(run_dir)

    failure_code = None
    if report.stop_reason == "model_error":
        notes = [r.note for r in report.rounds if r.note.startswith("model stop:")]
        failure_code = classify_model_failure(notes[-1]) if notes else "MODEL_GATEWAY_ERROR"

    output = {
        "result": status,
        "failure_code": failure_code,
        "run_id": report.run_id,
        "report": asdict(report),
        "model_receipts": [r.model_dump(mode="json") for r in gateway.receipts],
        "evidence_artifact_count": len(list(ledger.root.glob("*.json"))),
        "independent_fixture_verifier": fixture_verifier_summary(reference),
        "real_vs_mock": args.mode,
        "discovery_receipt_sha256": archive["receipt_sha256"],
        "note": (
            "Reference source and sealed test inputs are never sent to the model; "
            "report proves scoped discovery only, NOT candidate reconstruction."
        ),
    }
    report_path = run_dir / "run_report.json"
    publish_once(report_path, canonical(redact(output)))
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
    return 0 if complete else 3


if __name__ == "__main__":
    raise SystemExit(main())
