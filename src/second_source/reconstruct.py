"""Reproducible end-to-end G3 operator workflow (REAL-RUN-READY, no paid calls yet).

Single command connecting approved scope, G2 evidence/hypotheses, the pinned
generation broker, the CandidateSpec loader, the trusted interpreter (via the
evaluator-owned candidate worker), and the independent sealed evaluator:

    python -m second_source.reconstruct --mode mock
    python -m second_source.reconstruct --mode real --max-usd 0.50 \\
        --confirm-real-run --operator-context-pin sha256:... \\
        --ledger-dir <approved-ledger> --hypotheses-file <batch.json> \\
        --observation-digests <d1,d2,...> --suite <suite.json> \\
        --suite-digest <digest>

Mock mode is fully nonbillable and honestly labeled MOCK: fresh local evidence
is observed from the owned reference, deterministic mock hypotheses are
registered, a deliberately naive (imperfect) spec is proposed over a mock
channel, and the sealed evaluator scores it with exact counts. The mock score
is plumbing evidence only, never a real-model claim.

Real mode stays fail-closed until the owner supplies every authorization input:
MODEL_API_KEY, SECOND_SOURCE_MAX_RUN_USD, --max-usd, --confirm-real-run, an
operator-approved G2 context pin, and operator-supplied ledger/hypotheses plus
a frozen sealed suite. Real evidence must be authentic approved G2 material;
nothing here invents observations or substitutes mock output for inference.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from typing import Any, Sequence

from .budgets import RunBudget
from .candidate_generation import pin_public_manifest
from .contracts import (
    Budgets, ImplementationScope, ObservationScope, ScopeContract,
    ScopeMode, TargetKind, TargetSpec,
)
from .evidence import EvidenceLedger
from .hypotheses import HypothesisStore, validate_batch
from .model_gateway import MetaProvider

ROOT = Path(__file__).resolve().parents[2]
OWNED_REFERENCE = ROOT / "fixtures" / "owned_ledger" / "reference.py"
PUBLIC_MANIFEST = ROOT / "fixtures" / "owned_ledger" / "public_contract.json"

MAX_REAL_RUN_USD = 0.50
REAL_MODES = ("mock", "real")


def create_scope(max_usd: float) -> ScopeContract:
    """Pinned owned-ledger reconstruction scope (operator-approved shape)."""
    return ScopeContract(
        target=TargetSpec(
            kind=TargetKind.CLI,
            reference_command_id="owned-ledger-v1",
            permission_ref="owned-fixture",
        ),
        goal="Reconstruct only the synthetic ledger CLI behaviors",
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
            max_reference_experiments=40,
            max_model_calls=5,
            max_wall_seconds=600,
            max_estimated_model_spend_usd=max_usd,
        ),
    )


def _public_manifest() -> dict[str, Any]:
    return json.loads(PUBLIC_MANIFEST.read_text(encoding="utf-8"))


def mock_observation_sequences() -> list[list[dict[str, Any]]]:
    """Public, non-sealed observation sequences for mock evidence only."""
    return [
        [{"command": "list"}, {"command": "total"}],
        [{"command": "add", "label": "Alpha", "amount": 3}, {"command": "total"}],
        [
            {"command": "add", "label": "Alpha", "amount": 3},
            {"command": "add", "label": "alpha", "amount": 4},
            {"command": "list"},
        ],
        [{"command": "add", "label": "", "amount": 0}, {"command": "total"}],
        [
            {"command": "add", "label": "Beta", "amount": 2},
            {"command": "remove", "id": "1"},
            {"command": "list"},
        ],
    ]


def naive_mock_spec() -> dict[str, Any]:
    """Deliberately naive MOCK candidate: valid DSL, intentionally loose bounds.

    Transported over a mock channel and labeled MOCK end to end. It is
    expected to FAIL sealed cases honestly (e.g. amount 0/101+, long labels);
    a mock score never supports a real-model claim.
    """
    def param(typ: str, error: str, **bounds: Any) -> dict[str, Any]:
        return {"type": typ, "required": True, "error": error, **bounds}

    return {
        "spec_version": "1",
        "subsystem": "cli_ledger",
        "requirement_ids": ["REQ-LEDGER"],
        "unknown_command_error": "unknown_command",
        "invalid_input_error": "invalid_input",
        "commands": {
            "add": {
                "params": {
                    "label": param("string", "invalid_label", trim=True,
                                   min_length=1, max_length=200),
                    "amount": param("integer", "invalid_amount",
                                    minimum=0, maximum=1000),
                },
                "unique_field": "label",
                "unique_casefold": True,
                "unique_error": "duplicate_label",
                "store_record": True,
                "respond": {"id": "id"},
            },
            "list": {"respond": {"items": "items"}},
            "total": {
                "aggregate_count": True,
                "aggregate_sum_field": "amount",
                "respond": {"count": "count", "amount": "amount"},
            },
            "remove": {
                "params": {"id": param("string", "not_found")},
                "lookup_by": "id",
                "lookup_param": "id",
                "not_found_error": "not_found",
                "delete_after_lookup": True,
                "respond": {"removed": "id"},
            },
        },
    }


def mock_hypotheses(digests: Sequence[str]) -> HypothesisStore:
    """Deterministic mock hypotheses citing real ledger digests (MOCK only)."""
    by_index = list(digests)
    store = HypothesisStore()
    batch = validate_batch(
        {
            "hypotheses": [
                {
                    "id": "g3-mock-h1",
                    "statement": (
                        "add persists labeled amounts with generated ids; "
                        "list and total reflect stored entries"
                    ),
                    "evidence_ids": sorted(by_index[2:4]),
                    "status": "hypothesized",
                },
                {
                    "id": "g3-mock-h2",
                    "statement": (
                        "duplicate labels are rejected case-insensitively "
                        "after trimming"
                    ),
                    "evidence_ids": sorted(by_index[4:6]),
                    "status": "hypothesized",
                },
                {
                    "id": "g3-mock-h3",
                    "statement": (
                        "empty labels and out-of-range amounts are rejected; "
                        "remove deletes by id"
                    ),
                    "evidence_ids": sorted(by_index[6:]),
                    "status": "hypothesized",
                },
            ]
        },
        frozenset(by_index),
    )
    store.add_batch(batch)
    return store


def _run_directory(explicit: str | None) -> Path:
    if explicit:
        target = Path(explicit)
        if not target.is_absolute():
            target = ROOT / target
        target.mkdir(parents=True, exist_ok=True)
        return target
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = ROOT / ".runs" / ("g3-" + stamp + "-" + secrets.token_hex(4))
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    return target


def _blocked(message: str) -> int:
    print("BLOCKED_REAL_MODEL: " + message, file=sys.stderr)
    return 2


def _observe_mock_evidence(ledger: EvidenceLedger) -> list[str]:
    """Execute public observation sequences against the owned reference."""
    from .reference import CLIReferenceAdapter

    reference = CLIReferenceAdapter(
        [sys.executable, str(OWNED_REFERENCE)], cwd=ROOT
    )
    digests: list[str] = []
    for index, actions in enumerate(mock_observation_sequences()):
        result = reference.execute_sequence(actions, sequence_id=f"mock-obs-{index}")
        if result.status != "ok" or not result.observations:
            raise RuntimeError(f"mock evidence sequence {index} failed: {result.status}")
        for observation in result.observations:
            stored = ledger.store(observation)
            digests.append(stored["sha256"])
    if len(digests) < 8:
        raise RuntimeError("mock evidence set unexpectedly small")
    return digests


def _write_report(run_dir: Path, report: dict[str, Any]) -> Path:
    path = run_dir / "G3_report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _summarize(report: dict[str, Any]) -> dict[str, Any]:
    evaluation = report["evaluation"]
    return {
        "result": report["stop_reason"],
        "run_id": report["run_id"],
        "mode": report["mode"],
        "origin": report["origin"],
        "passed": evaluation["passed"],
        "failed": evaluation["failed"],
        "indeterminate": evaluation["indeterminate"],
        "total": evaluation["total"],
        "estimated_cost_usd": report["usage"]["estimated_cost_usd"],
        "uncertain_cost_usd": report["usage"]["uncertain_cost_usd"],
        "spec_digest": report["spec_digest"],
        "suite_digest": report["suite_digest"],
        "report_path": report["report_path"],
    }


def run_mock(args: argparse.Namespace) -> int:
    """Fully nonbillable run: fresh evidence, mock channel, sealed score."""
    from .g3_verification import (
        PinnedEvaluatorRun, load_sealed_suite, seal_owned_ledger_suite,
    )
    from .model_gateway import MockProvider

    scope = create_scope(0.0)
    public = _public_manifest()
    if set(public.get("commands", {})) != set(scope.observation.allowed_commands):
        print("BLOCKED_CONTRACT: public manifest does not match scope", file=sys.stderr)
        return 2
    run_dir = _run_directory(args.run_dir)
    ledger = EvidenceLedger(run_dir / "evidence")
    digests = _observe_mock_evidence(ledger)
    store = mock_hypotheses(digests)

    seal_dir = args.seal_dir or tempfile.mkdtemp(prefix="second-source-sealed-")
    _, suite_digest = seal_owned_ledger_suite(seal_dir, scope)
    suite = load_sealed_suite(
        Path(seal_dir) / "suite.json", suite_digest, scope
    )
    run = PinnedEvaluatorRun(
        suite, scope, ledger=ledger,
        observation_digests=tuple(digests), hypotheses=store,
    )
    ticket = run.prepare()
    proposal = naive_mock_spec()

    def _responder(request: Any) -> dict[str, Any]:
        return {"content": proposal}

    budget = RunBudget(scope.budgets)
    artifact = run.generate(
        ticket, MockProvider(responder=_responder), budget,
        spending_approved=False,
    )
    result = run.evaluate(artifact, claim="TRUSTED_CONTROL")
    receipt = result["origin"]
    report = {
        "kind": "G3_RECONSTRUCT_RUN_REPORT",
        "run_id": run_dir.name,
        "mode": "mock",
        "fixture": "owned-ledger",
        "origin": receipt["origin"],
        "real": receipt["real"],
        "provider": receipt["provider"],
        "model": receipt["model"],
        "response_id": receipt["response_id"],
        "spec_digest": result["candidate_digest"],
        "scope_digest": result["scope_digest"],
        "suite_digest": result["suite_digest"],
        "approved_context_digest": result["approved_context_digest"],
        "plan_digest": result["plan_digest"],
        "reference_command_id": result["reference_identity"],
        "reference_source_digest": result["reference_source_digest"],
        "evaluation": result["evaluation"],
        "usage": {
            "input_tokens": receipt["input_tokens"],
            "output_tokens": receipt["output_tokens"],
            "estimated_cost_usd": receipt["estimated_cost_usd"],
            "uncertain_cost_usd": receipt["uncertain_cost_usd"],
        },
        "stop_reason": "completed_mock_run",
        "evidence_artifact_count": len(digests),
        "manifest_digest": pin_public_manifest(public),
        "sealed_suite_path": str(Path(seal_dir) / "suite.json"),
        "report_labels": "MOCK_TRANSPORT_NAIVE_SPEC_TRUSTED_CONTROL_EVALUATION",
        "note": (
            "Mock plumbing evidence only. The naive spec is scripted, the "
            "score measures the evaluator, and nothing here is Muse output."
        ),
    }
    report_path = _write_report(run_dir, {**report, "report_path": ""})
    report["report_path"] = str(report_path)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(_summarize(report), indent=2))
    print(json.dumps({
        "approved_context_digest": result["approved_context_digest"],
        "note": "operator reviews this context digest before pinning a real run",
    }))
    return 0


def _load_operator_evidence(args: argparse.Namespace) -> tuple[EvidenceLedger, HypothesisStore, tuple[str, ...]]:
    try:
        digests = tuple(d.strip() for d in args.observation_digests.split(",") if d.strip())
        if not digests:
            raise ValueError("no observation digests")
    except (AttributeError, ValueError):
        raise RuntimeError("--observation-digests must list approved ledger digests")
    ledger = EvidenceLedger(args.ledger_dir)
    try:
        batch_doc = json.loads(Path(args.hypotheses_file).read_text(encoding="utf-8"))
        batch = validate_batch(batch_doc, frozenset(digests))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"operator hypotheses rejected: {exc}") from exc
    store = HypothesisStore()
    store.add_batch(batch)
    for digest in digests:
        ledger.inspect(digest)
    return ledger, store, digests


def run_real(args: argparse.Namespace) -> int:
    """Owner-authorized real generation; fail closed on any missing approval."""
    from .g3_verification import EvaluationBlocked, PinnedEvaluatorRun, load_sealed_suite

    key = os.environ.get("MODEL_API_KEY", "")
    try:
        env_limit = float(os.environ.get("SECOND_SOURCE_MAX_RUN_USD", "0") or "0")
    except ValueError:
        env_limit = 0.0
    if not key or env_limit <= 0:
        return _blocked("configure MODEL_API_KEY and SECOND_SOURCE_MAX_RUN_USD securely.")
    if not (0 < args.max_usd <= min(MAX_REAL_RUN_USD, env_limit)):
        return _blocked(
            f"--max-usd must be positive and <= ${MAX_REAL_RUN_USD:.2f} "
            "and <= SECOND_SOURCE_MAX_RUN_USD."
        )
    if not args.confirm_real_run:
        return _blocked("pass --confirm-real-run to authorize spend on this run.")
    if not args.operator_context_pin:
        return _blocked("pass --operator-context-pin with the approved G2 context digest.")
    for missing in ("ledger_dir", "hypotheses_file", "observation_digests",
                    "suite", "suite_digest"):
        if not getattr(args, missing, None):
            return _blocked(f"real runs require --{missing.replace('_', '-')}.")

    scope = create_scope(args.max_usd)
    try:
        ledger, store, digests = _load_operator_evidence(args)
        suite = load_sealed_suite(args.suite, args.suite_digest, scope)
    except (RuntimeError, OSError) as exc:
        print(f"BLOCKED_EVIDENCE: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print("BLOCKED_EVIDENCE: operator evidence or frozen suite rejected",
              file=sys.stderr)
        return 2

    run_dir = _run_directory(args.run_dir)
    try:
        run = PinnedEvaluatorRun(
            suite, scope, ledger=ledger, observation_digests=digests,
            hypotheses=store,
            operator_approved_context_digest=args.operator_context_pin,
        )
        ticket = run.prepare()
        budget = RunBudget(scope.budgets)
        artifact = run.generate(
            ticket, MetaProvider(key), budget, spending_approved=True
        )
        result = run.evaluate(artifact, claim="REAL_MODEL")
    except EvaluationBlocked as exc:
        print(f"BLOCKED_EVALUATOR: {exc}", file=sys.stderr)
        return 2

    receipt = result["origin"]
    report = {
        "kind": "G3_RECONSTRUCT_RUN_REPORT",
        "run_id": run_dir.name,
        "mode": "real",
        "fixture": "owned-ledger",
        "origin": receipt["origin"],
        "real": receipt["real"],
        "provider": receipt["provider"],
        "model": receipt["model"],
        "response_id": receipt["response_id"],
        "spec_digest": result["candidate_digest"],
        "scope_digest": result["scope_digest"],
        "suite_digest": result["suite_digest"],
        "approved_context_digest": result["approved_context_digest"],
        "plan_digest": result["plan_digest"],
        "reference_command_id": result["reference_identity"],
        "reference_source_digest": result["reference_source_digest"],
        "evaluation": result["evaluation"],
        "usage": {
            "input_tokens": receipt["input_tokens"],
            "output_tokens": receipt["output_tokens"],
            "estimated_cost_usd": receipt["estimated_cost_usd"],
            "uncertain_cost_usd": receipt["uncertain_cost_usd"],
        },
        "stop_reason": "completed_real_run",
        "evidence_artifact_count": len(digests),
        "operator_input_pin_present": True,
        "max_authorized_usd": args.max_usd,
        "note": "Genuine Muse generation scored on the frozen sealed suite.",
    }
    report_path = _write_report(run_dir, {**report, "report_path": ""})
    report["report_path"] = str(report_path)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(_summarize(report), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="End-to-end G3 reconstruction operator workflow"
    )
    parser.add_argument("--fixture", default="owned-ledger",
                        help="registered fixture id (only owned-ledger)")
    parser.add_argument("--mode", default="mock", choices=REAL_MODES,
                        help="mock: nonbillable plumbing run; real: gated Meta run")
    parser.add_argument("--max-usd", type=float, default=0.0,
                        help="spend cap for this run (real mode only)")
    parser.add_argument("--run-dir", default=None,
                        help="explicit run directory (default .runs/<id>)")
    parser.add_argument("--seal-dir", default=None,
                        help="external directory for a fresh sealed suite (mock only)")
    parser.add_argument("--confirm-real-run", action="store_true",
                        help="explicit spend authorization for this real run")
    parser.add_argument("--operator-context-pin", default=None,
                        help="independently approved G2 context digest (real only)")
    parser.add_argument("--ledger-dir", default=None,
                        help="approved G2 evidence ledger directory (real only)")
    parser.add_argument("--hypotheses-file", default=None,
                        help="approved G2 hypothesis batch JSON (real only)")
    parser.add_argument("--observation-digests", default=None,
                        help="comma-separated approved ledger digests (real only)")
    parser.add_argument("--suite", default=None,
                        help="frozen sealed suite path (real only)")
    parser.add_argument("--suite-digest", default=None,
                        help="frozen sealed suite digest (real only)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.fixture != "owned-ledger":
        print(f"BLOCKED_SCOPE: unknown fixture {args.fixture!r}", file=sys.stderr)
        return 2
    if args.mode == "mock":
        if args.max_usd != 0.0 or args.confirm_real_run:
            print("BLOCKED_SCOPE: mock runs take no spend or confirmation flags",
                  file=sys.stderr)
            return 2
        return run_mock(args)
    return run_real(args)


if __name__ == "__main__":
    raise SystemExit(main())
