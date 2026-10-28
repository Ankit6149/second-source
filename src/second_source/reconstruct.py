"""Reproducible end-to-end G3 operator workflow (zero-cost engineering; real approval pending).

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
import hashlib
import json
import math
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
from .evidence import EvidenceLedger, publish_once as _write_once
from .hypotheses import HypothesisStore, validate_batch
from .model_gateway import MetaProvider

ROOT = Path(__file__).resolve().parents[2]
OWNED_REFERENCE = ROOT / "fixtures" / "owned_ledger" / "reference.py"
PUBLIC_MANIFEST = ROOT / "fixtures" / "owned_ledger" / "public_contract.json"

MAX_REAL_RUN_USD = 0.50
REAL_MODES = ("mock", "preflight", "real")


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
    """Create-once run directory: every pre-existing directory is refused.

    Empty or interrupted prior runs are never reclaimed; the operator always
    starts a fresh directory so run IDs stay unique and immutable.
    """
    if explicit:
        target = Path(explicit)
        if not target.is_absolute():
            target = ROOT / target
        if target.exists():
            raise RuntimeError(
                f"run directory {target} already exists; refusing reuse"
            )
        target.mkdir(parents=True, exist_ok=False, mode=0o700)
        return target
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = ROOT / ".runs" / ("g3-" + stamp + "-" + secrets.token_hex(4))
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    return target


def _blocked(message: str) -> int:
    print("BLOCKED_REAL_MODEL: " + message, file=sys.stderr)
    return 2


def _progress(stage: str, run_id: str, detail: str = "") -> None:
    """One stderr notification per completed stage; no claim of durable history."""
    print(
        json.dumps({"progress": stage, "run_id": run_id, "detail": detail}),
        file=sys.stderr,
    )


def _readable_summary(evaluation: dict[str, Any], mode: str) -> list[str]:
    """Plain-language evaluation lines; mock scores are never success claims."""
    lines = [
        f"{evaluation['passed']}/{evaluation['total']} sealed cases passed "
        f"({mode} transport; "
        + ("plumbing evidence only, not AI reconstruction"
           if mode == "mock" else "independent Meta-generated score")
        + ")",
    ]
    for category in sorted(evaluation.get("failure_categories", {})):
        lines.append(
            f"{evaluation['failure_categories'][category]} case(s) mismatch "
            f"in category {category}"
        )
    if evaluation.get("indeterminate"):
        lines.append(
            f"{evaluation['indeterminate']} case(s) indeterminate: reference "
            "harness fault, not candidate verdict"
        )
    return lines


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
    """Persist one immutable run report; a second write is rejected."""
    path = run_dir / "G3_report.json"
    raw = json.dumps(report, indent=2, sort_keys=True).encode("utf-8")
    return _write_once(path, raw)


def _summarize(report: dict[str, Any]) -> dict[str, Any]:
    evaluation = report.get("evaluation") or {}
    return {
        "result": report["stop_reason"],
        "run_id": report["run_id"],
        "mode": report["mode"],
        "origin": report["origin"],
        "passed": evaluation.get("passed"),
        "failed": evaluation.get("failed"),
        "indeterminate": evaluation.get("indeterminate"),
        "total": evaluation.get("total"),
        "estimated_cost_usd": report["usage"]["estimated_cost_usd"],
        "uncertain_cost_usd": report["usage"]["uncertain_cost_usd"],
        "spec_digest": report.get("spec_digest"),
        "suite_digest": report.get("suite_digest"),
        "report_path": report.get("report_path", ""),
        "next_action": _next_action(report["stop_reason"], report["mode"]),
    }


def _next_action(stop_reason: str, mode: str) -> str:
    """Operator guidance per durable run state; never a raw traceback."""
    if stop_reason == "completed_mock_run":
        return ("mock plumbing complete; review approved_context_digest, then run "
                "--mode preflight on genuine G2 inputs before any real approval")
    if stop_reason == "completed_real_run":
        return "independent sealed score recorded; optional bounded repair is a separate approval"
    if stop_reason == "preflight_ready":
        return ("preflight inspection complete with zero calls; approve the context "
                "digest and frozen suite out of band, then invoke --mode real")
    if stop_reason.startswith("blocked"):
        return "resolve the blocking approval/input and re-invoke; no attempt was dispatched"
    return "inspect the sanitized failure report; re-invoke only after fixing the failure category"


def _failure_category(stage: str) -> str:
    return {
        "inspect": "inspection_failed",
        "broker": "broker_failed",
        "evaluate": "evaluation_failed",
        "interrupted": "interrupted_stopped",
        "admit": "evidence_admission_failed",
    }.get(stage, "run_failed")


def _budget_usage(budget: Any) -> dict[str, Any]:
    """Mirror the trusted budget's actual counters; never reset used tokens."""
    return {
        "attempts": budget.attempts,
        "input_tokens": budget.input_tokens,
        "output_tokens": budget.output_tokens,
        "estimated_cost_usd": budget.estimated_cost_usd,
        "uncertain_cost_usd": budget.uncertain_cost_usd,
    }


def _write_failure_report(
    *,
    run_dir: Path,
    mode: str,
    real: bool,
    stage: str,
    budget: Any,
    suite_digest: str = "",
    scope_digest: str = "",
    interrupted: bool = False,
) -> dict[str, Any]:
    """Durable sanitized failure receipt: categories and accounting, no verbatim errors.

    ``stage`` names where the run stopped (broker/evaluate/...) so
    post-evaluate failures keep their location; ``interrupted`` marks a
    stopped outcome instead of a clean category.
    """
    report = {
        "kind": "G3_RECONSTRUCT_RUN_REPORT",
        "run_id": run_dir.name,
        "mode": mode,
        "fixture": "owned-ledger",
        "origin": "real" if real else "mock",
        "real": real,
        "stop_reason": (
            "interrupted_stopped" if interrupted else _failure_category(stage)
        ),
        "failure_stage": stage,
        "suite_digest": suite_digest,
        "scope_digest": scope_digest,
        "evaluation": None,
        "usage": _budget_usage(budget),
        "report_path": str(run_dir / "G3_report.json"),
        "note": (
            "Post-dispatch failure: the attempt was dispatched and is accounted "
            "above. Pre-dispatch blocks (missing approvals) write no report and "
            "record zero attempts."
        ),
    }
    _write_report(run_dir, report)
    _progress("stopped", run_dir.name, report["stop_reason"])
    return report


def _persist_admission(run_dir: Path, artifact: Any, spec_digest: str) -> dict[str, str]:
    """Archive the broker-issued admission immediately after generation.

    Stores the exact artifact payload/signature envelope plus the admitted
    candidate bytes, each create-once with a read-back integrity check. The
    envelope carries the broker's local attestation signature, never a
    provider attestation; the HMAC authority key is never persisted.
    """
    payload = artifact.payload
    if not isinstance(payload, bytes):
        raise RuntimeError("broker artifact payload is not bytes")
    raw_spec = json.loads(payload.decode("utf-8"))["spec"].encode("utf-8")
    candidate_path = _write_once(run_dir / "candidate.v1.json", raw_spec)
    if candidate_path.read_bytes() != raw_spec:
        raise RuntimeError("candidate archive read-back mismatch")
    envelope = {
        "kind": "BROKER_ARTIFACT_LOCAL_ATTESTATION_NOT_PROVIDER",
        "payload": payload.decode("utf-8"),
        "signature": artifact.signature,
        "spec_digest": spec_digest,
        "note": (
            "Local broker attestation for offline replay within this run's "
            "frozen evaluator only; not portable provider proof of origin."
        ),
    }
    envelope_path = _write_once(
        run_dir / "broker-artifact.v1.json",
        json.dumps(envelope, indent=2, sort_keys=True).encode("utf-8"),
    )
    return {"candidate": candidate_path.name, "envelope": envelope_path.name}


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
    g2_provenance = None
    if args.g2_manifest:
        try:
            ledger, store, digests = _load_operator_evidence(args)
            g2_provenance = _check_g2_manifest(args.g2_manifest, digests, store,
                receipt_sha256=args.g2_receipt_sha256, scope=scope)
        except (RuntimeError, OSError, ValueError):
            print("BLOCKED_EVIDENCE: complete G2 receipt/input binding rejected", file=sys.stderr)
            return 2
        run_dir = _run_directory(args.run_dir)
    else:
        run_dir = _run_directory(args.run_dir)
        ledger = EvidenceLedger(run_dir / "evidence")
        digests = _observe_mock_evidence(ledger)
        store = mock_hypotheses(digests)
    _progress("evidence_ready", run_dir.name, f"{len(digests)} observations recorded")

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
    if g2_provenance is not None:
        _write_once(run_dir / "G3_input_provenance.json", json.dumps({
            "run_id": run_dir.name, "approved_context_digest": run.inspection_manifest()["approved_context_digest"],
            "g2": g2_provenance,
        }, sort_keys=True).encode("utf-8"))
    _progress("inspected", run_dir.name, "broker request inspected, zero calls")
    proposal = naive_mock_spec()

    def _responder(request: Any) -> dict[str, Any]:
        return {"content": proposal}

    from .g3_verification import EvaluationBlocked
    from .model_gateway import GatewayError

    budget = RunBudget(scope.budgets)
    try:
        artifact = run.generate(
            ticket, MockProvider(responder=_responder), budget,
            spending_approved=False,
        )
    except KeyboardInterrupt:
        stopped = _write_failure_report(
            run_dir=run_dir, mode="mock", real=False, stage="broker",
            budget=budget, suite_digest=suite_digest, interrupted=True,
        )
        print(json.dumps(_summarize(stopped), indent=2))
        return 130
    except (EvaluationBlocked, GatewayError, RuntimeError):
        failed = _write_failure_report(
            run_dir=run_dir, mode="mock", real=False, stage="broker",
            budget=budget, suite_digest=suite_digest,
        )
        print(json.dumps(_summarize(failed), indent=2))
        return 1
    admitted_value = json.loads(artifact.payload)
    admitted = _persist_admission(
        run_dir, artifact, admitted_value["receipt"]["candidate_digest"]
    )
    _progress("admitted", run_dir.name,
              f"candidate {admitted_value['receipt']['candidate_digest']}")
    try:
        result = run.evaluate(artifact, claim="TRUSTED_CONTROL")
    except KeyboardInterrupt:
        stopped = _write_failure_report(
            run_dir=run_dir, mode="mock", real=False, stage="evaluate",
            budget=budget, suite_digest=suite_digest, interrupted=True,
        )
        print(json.dumps(_summarize(stopped), indent=2))
        return 130
    except (EvaluationBlocked, GatewayError, RuntimeError):
        failed = _write_failure_report(
            run_dir=run_dir, mode="mock", real=False, stage="evaluate",
            budget=budget, suite_digest=suite_digest,
        )
        print(json.dumps(_summarize(failed), indent=2))
        return 1
    receipt = result["origin"]
    candidate_path = admitted["candidate"]
    report = {
        "kind": "G3_RECONSTRUCT_RUN_REPORT",
        "run_id": run_dir.name,
        "mode": "mock",
        "g2_input_provenance": g2_provenance,
        "fixture": "owned-ledger",
        "origin": receipt["origin"],
        "real": receipt["real"],
        "provider": receipt["provider"],
        "model": receipt["model"],
        "response_id": receipt["response_id"],
        "spec_digest": result["candidate_digest"],
        "candidate_artifact": candidate_path,
        "broker_artifact": admitted["envelope"],
        "scope_digest": result["scope_digest"],
        "suite_digest": result["suite_digest"],
        "approved_context_digest": result["approved_context_digest"],
        "plan_digest": result["plan_digest"],
        "reference_command_id": result["reference_identity"],
        "reference_source_digest": result["reference_source_digest"],
        "evaluation": result["evaluation"],
        "evaluation_receipt": result,
        "usage": {
            "attempts": budget.attempts,
            "input_tokens": budget.input_tokens,
            "output_tokens": budget.output_tokens,
            "estimated_cost_usd": budget.estimated_cost_usd,
            "uncertain_cost_usd": budget.uncertain_cost_usd,
        },
        "stop_reason": "completed_mock_run",
        "evidence_artifact_count": len(digests),
        "evaluation_summary": _readable_summary(result["evaluation"], "mock"),
        "manifest_digest": pin_public_manifest(public),
        "report_path": str(run_dir / "G3_report.json"),
        "report_labels": "MOCK_TRANSPORT_NAIVE_SPEC_TRUSTED_CONTROL_EVALUATION",
        "note": (
            "Mock plumbing evidence only. The naive spec is scripted, the "
            "score measures the evaluator, and nothing here is Muse output. "
            "A mock-context digest never authenticates historical G2 inputs; "
            "real approval requires --mode preflight on genuine G2 material."
        ),
    }
    _write_report(run_dir, report)
    _progress("evaluated", run_dir.name,
              f"{result['evaluation']['passed']}/{result['evaluation']['total']} sealed cases")
    _progress("reported", run_dir.name, "G3_report.json")
    print(json.dumps(_summarize(report), indent=2))
    print(json.dumps({
        "approved_context_digest": result["approved_context_digest"],
        "note": "mock-context digest only; approve genuine G2 inputs via preflight",
    }))
    return 0


def _check_g2_manifest(
    manifest_path: str, digests: tuple[str, ...], store: HypothesisStore,
    *, receipt_sha256: str | None, scope: ScopeContract, require_real: bool = False,
) -> dict[str, Any]:
    """Bind the already-loaded G3 context to the sole immutable G2 journal."""
    from .g2_persistence import inspect_run

    if not receipt_sha256:
        raise RuntimeError("G2 binding requires an externally retained --g2-receipt-sha256")
    path = Path(manifest_path)
    if path.name != "G2_receipt.json" or path.is_symlink():
        raise RuntimeError("G2 binding requires the version2 G2_receipt.json")
    archive = inspect_run(path.parent, receipt_sha256)
    if not archive["complete"]:
        raise RuntimeError("incomplete G2 discovery cannot back reconstruction")
    if require_real and (archive["origin"] != "real" or not all(r["real"] for r in archive["model_receipts"])):
        raise RuntimeError("NON_AI G2 discovery cannot approve genuine reconstruction")
    g2_scope = ScopeContract.model_validate(archive["scope"])
    if (g2_scope.target != scope.target
            or archive["reference_source_digest"] != hashlib.sha256(OWNED_REFERENCE.read_bytes()).hexdigest()
            or archive["public_manifest_digest"] != hashlib.sha256(PUBLIC_MANIFEST.read_bytes()).hexdigest()):
        raise RuntimeError("G2 target/reference/public identity differs from G3")
    if set(digests) != set(archive["observation_digests"]):
        raise RuntimeError("operator digests differ from complete G2 evidence")
    original = validate_batch(archive["hypothesis_batches"][-1], frozenset(digests))
    loaded = validate_batch({"hypotheses": [h.model_dump(mode="json") for h in store.all()]}, frozenset(digests))
    if loaded != original:
        raise RuntimeError("operator hypotheses differ from original G2 response batch")
    return {"receipt_sha256": archive["receipt_sha256"], "run_id": archive["run_id"],
            "origin": archive["origin"], "provider": archive["provider"], "model": archive["model"],
            "scope_digest": archive["scope_digest"],
            "reference_source_digest": archive["reference_source_digest"],
            "public_manifest_digest": archive["public_manifest_digest"], "complete": True}


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
    try:
        for digest in digests:
            ledger.inspect(digest)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"operator evidence digest rejected: {exc}") from exc
    return ledger, store, digests


def _spend_ceiling(value: Any) -> float | None:
    """Finite positive spend ceiling, else None. Checked before inputs/providers."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(amount) or amount <= 0:
        return None
    return amount


def run_real(args: argparse.Namespace) -> int:
    """Owner-authorized real generation; fail closed on any missing approval."""
    from .g3_verification import EvaluationBlocked, PinnedEvaluatorRun, load_sealed_suite
    from .model_gateway import GatewayError

    env_limit = _spend_ceiling(os.environ.get("SECOND_SOURCE_MAX_RUN_USD", "0"))
    run_limit = _spend_ceiling(args.max_usd)
    if env_limit is None:
        return _blocked("configure MODEL_API_KEY and SECOND_SOURCE_MAX_RUN_USD securely.")
    if run_limit is None or run_limit > min(MAX_REAL_RUN_USD, env_limit):
        return _blocked(
            f"--max-usd must be finite, positive, and <= ${MAX_REAL_RUN_USD:.2f} "
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
    except (RuntimeError, OSError, ValueError):
        print("BLOCKED_EVIDENCE: operator inputs or G2 receipt rejected", file=sys.stderr)
        return 2
    except Exception:
        print("BLOCKED_EVIDENCE: operator evidence or frozen suite rejected",
              file=sys.stderr)
        return 2

    budget = RunBudget(scope.budgets)
    try:
        run = PinnedEvaluatorRun(
            suite, scope, ledger=ledger, observation_digests=digests,
            hypotheses=store,
            operator_approved_context_digest=args.operator_context_pin,
        )
        run.prepare()
    except (EvaluationBlocked, GatewayError, RuntimeError) as exc:
        print(f"BLOCKED_EVALUATOR: {type(exc).__name__}", file=sys.stderr)
        return 2
    if not args.g2_manifest:
        return _blocked("real runs require --g2-receipt and --g2-receipt-sha256.")
    try:
        g2_provenance = _check_g2_manifest(args.g2_manifest, digests, store,
            receipt_sha256=args.g2_receipt_sha256, scope=scope, require_real=True)
    except (RuntimeError, OSError, ValueError):
        print("BLOCKED_EVIDENCE: complete genuine G2 receipt/input binding rejected", file=sys.stderr)
        return 2
    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        return _blocked("configure MODEL_API_KEY securely after exact input approval.")
    run_dir = _run_directory(args.run_dir)
    _write_once(run_dir / "G3_input_provenance.json", json.dumps({
        "run_id": run_dir.name, "approved_context_digest": args.operator_context_pin,
        "g2": g2_provenance,
    }, sort_keys=True).encode("utf-8"))
    _progress("evidence_ready", run_dir.name, f"{len(digests)} approved observations")
    try:
        ticket = run.prepare()
        _progress("inspected", run_dir.name, "broker request inspected, zero calls")
        artifact = run.generate(
            ticket, MetaProvider(key), budget, spending_approved=True
        )
    except KeyboardInterrupt:
        stopped = _write_failure_report(
            run_dir=run_dir, mode="real", real=True, stage="broker",
            budget=budget, suite_digest=args.suite_digest, interrupted=True,
        )
        print(json.dumps(_summarize(stopped), indent=2))
        return 130
    except (EvaluationBlocked, GatewayError, RuntimeError):
        failed = _write_failure_report(
            run_dir=run_dir, mode="real", real=True, stage="broker",
            budget=budget, suite_digest=args.suite_digest,
        )
        print(json.dumps(_summarize(failed), indent=2))
        return 1
    admitted_value = json.loads(artifact.payload)
    admitted = _persist_admission(
        run_dir, artifact, admitted_value["receipt"]["candidate_digest"]
    )
    _progress("admitted", run_dir.name,
              f"candidate {admitted_value['receipt']['candidate_digest']}")
    try:
        result = run.evaluate(artifact, claim="REAL_MODEL")
    except KeyboardInterrupt:
        stopped = _write_failure_report(
            run_dir=run_dir, mode="real", real=True, stage="evaluate",
            budget=budget, suite_digest=args.suite_digest, interrupted=True,
        )
        print(json.dumps(_summarize(stopped), indent=2))
        return 130
    except (EvaluationBlocked, GatewayError, RuntimeError):
        failed = _write_failure_report(
            run_dir=run_dir, mode="real", real=True, stage="evaluate",
            budget=budget, suite_digest=args.suite_digest,
        )
        print(json.dumps(_summarize(failed), indent=2))
        return 1

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
        "candidate_artifact": admitted["candidate"],
        "broker_artifact": admitted["envelope"],
        "scope_digest": result["scope_digest"],
        "suite_digest": result["suite_digest"],
        "approved_context_digest": result["approved_context_digest"],
        "plan_digest": result["plan_digest"],
        "reference_command_id": result["reference_identity"],
        "reference_source_digest": result["reference_source_digest"],
        "evaluation": result["evaluation"],
        "evaluation_receipt": result,
        "usage": {
            "attempts": budget.attempts,
            "input_tokens": budget.input_tokens,
            "output_tokens": budget.output_tokens,
            "estimated_cost_usd": budget.estimated_cost_usd,
            "uncertain_cost_usd": budget.uncertain_cost_usd,
        },
        "stop_reason": "completed_real_run",
        "evidence_artifact_count": len(digests),
        "evaluation_summary": _readable_summary(result["evaluation"], "real"),
        "operator_input_pin_present": True,
        "g2_input_provenance": g2_provenance,
        "max_authorized_usd": args.max_usd,
        "report_path": str(run_dir / "G3_report.json"),
        "note": "Genuine Muse generation scored on the frozen sealed suite.",
    }
    _write_report(run_dir, report)
    _progress("evaluated", run_dir.name,
              f"{report['evaluation']['passed']}/{report['evaluation']['total']} sealed cases")
    _progress("reported", run_dir.name, "G3_report.json")
    print(json.dumps(_summarize(report), indent=2))
    return 0


def run_preflight(args: argparse.Namespace) -> int:
    """ZERO-CALL inspection of genuine operator G2 inputs; no provider, no inference.

    Loads the actual operator-supplied ledger/hypotheses, freezes (or loads)
    the sealed suite against the SAME scope and approved budget the real run
    will use, inspects the exact broker request bytes, and emits a sanitized
    digest receipt for separate owner review. The printed context digest
    authenticates THESE inputs only; a mock-context digest never approves G2.
    """
    from .g3_verification import PinnedEvaluatorRun, load_sealed_suite, seal_owned_ledger_suite

    run_limit = _spend_ceiling(args.max_usd)
    if run_limit is None or run_limit > MAX_REAL_RUN_USD:
        return _blocked(
            f"--max-usd must be a finite positive budget <= ${MAX_REAL_RUN_USD:.2f}."
        )
    for missing in ("ledger_dir", "hypotheses_file", "observation_digests"):
        if not getattr(args, missing, None):
            return _blocked(f"preflight requires --{missing.replace('_', '-')}.")

    scope = create_scope(run_limit)
    public = _public_manifest()
    if set(public.get("commands", {})) != set(scope.observation.allowed_commands):
        print("BLOCKED_CONTRACT: public manifest does not match scope", file=sys.stderr)
        return 2
    try:
        ledger, store, digests = _load_operator_evidence(args)
        g2_provenance = None
        manifest_digest = ""
        if args.g2_manifest:
            g2_provenance = _check_g2_manifest(args.g2_manifest, digests, store,
                receipt_sha256=args.g2_receipt_sha256, scope=scope)
            manifest_digest = "sha256:" + g2_provenance["receipt_sha256"]
    except (RuntimeError, OSError, ValueError):
        print("BLOCKED_EVIDENCE: operator inputs or G2 receipt rejected", file=sys.stderr)
        return 2
    if args.suite and args.suite_digest:
        try:
            suite = load_sealed_suite(args.suite, args.suite_digest, scope)
            suite_digest = args.suite_digest
        except Exception:
            print("BLOCKED_EVIDENCE: frozen suite rejected", file=sys.stderr)
            return 2
    else:
        if not args.seal_dir:
            return _blocked("preflight requires --suite/--suite-digest or --seal-dir.")
        try:
            _, suite_digest = seal_owned_ledger_suite(args.seal_dir, scope)
            suite = load_sealed_suite(
                Path(args.seal_dir) / "suite.json", suite_digest, scope
            )
        except Exception:
            print("BLOCKED_EVIDENCE: suite seal rejected", file=sys.stderr)
            return 2

    try:
        run = PinnedEvaluatorRun(
            suite, scope, ledger=ledger, observation_digests=digests,
            hypotheses=store,
        )
        run.prepare()
    except Exception:
        print("BLOCKED_EVALUATOR: pinned inspection rejected", file=sys.stderr)
        return 2
    # Authoritative frozen pins come from the evaluator's detached manifest,
    # never from operator-side recomputation: identical genuine inputs yield
    # identical approval hashes in every process regardless of hash seed.
    manifest = run.inspection_manifest()
    run_dir = _run_directory(args.run_dir)
    receipt = {
        "kind": "G3_PREFLIGHT_INSPECTION",
        "run_id": run_dir.name,
        "mode": "preflight",
        "fixture": "owned-ledger",
        "origin": "inspection-only",
        "real": False,
        "provider_calls": 0,
        "scope_digest": manifest["scope_digest"],
        "manifest_digest": pin_public_manifest(public),
        "approved_context_digest": manifest["approved_context_digest"],
        "plan_digest": manifest["plan_digest"],
        "observation_registry_digest": manifest["observation_registry_digest"],
        "hypothesis_registry_digest": manifest["hypothesis_registry_digest"],
        "code_pins": manifest["code_pins"],
        "reference_identity": manifest["reference_identity"],
        "reference_source_digest": manifest["reference_source_digest"],
        "suite_digest": manifest["suite_digest"],
        "g2_manifest_digest": manifest_digest,
        "g2_input_provenance": g2_provenance,
        "real_input_eligible": bool(g2_provenance and g2_provenance["origin"] == "real"),
        "evidence_artifact_count": len(digests),
        "max_approved_usd": run_limit,
        "stop_reason": "preflight_ready",
        "report_path": str(run_dir / "G3_preflight.json"),
        "note": (
            "Zero-call inspection of THESE operator inputs. Approve the context "
            "digest and frozen suite out of band; the real invocation must bind "
            "to exactly these digests via --operator-context-pin and "
            "--suite/--suite-digest."
        ),
    }
    _write_once(run_dir / "G3_preflight.json",
                json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8"))
    _progress("inspected", run_dir.name, "operator inputs inspected, zero calls")
    _progress("reported", run_dir.name, "G3_preflight.json")
    print(json.dumps({
        "result": "preflight_ready",
        "run_id": run_dir.name,
        "approved_context_digest": manifest["approved_context_digest"],
        "plan_digest": manifest["plan_digest"],
        "suite_digest": manifest["suite_digest"],
        "evidence_artifact_count": len(digests),
        "provider_calls": 0,
        "next_action": _next_action("preflight_ready", "preflight"),
    }, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="End-to-end G3 reconstruction operator workflow"
    )
    parser.add_argument("--fixture", default="owned-ledger",
                        help="registered fixture id (only owned-ledger)")
    parser.add_argument("--mode", default="mock", choices=REAL_MODES,
                        help=("mock: nonbillable plumbing run; preflight: zero-call "
                              "inspection of genuine operator G2 inputs; "
                              "real: gated Meta run"))
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
    parser.add_argument("--g2-receipt", "--g2-manifest", dest="g2_manifest", default=None,
                        help="G2_receipt.json from the single version2 journal (required for real)")
    parser.add_argument("--g2-receipt-sha256", default=None,
                        help="externally retained exact G2 receipt SHA-256; required with --g2-receipt")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.g2_manifest) != bool(args.g2_receipt_sha256):
        print("BLOCKED_SCOPE: --g2-receipt requires --g2-receipt-sha256 and conversely", file=sys.stderr)
        return 2
    if args.fixture != "owned-ledger":
        print(f"BLOCKED_SCOPE: unknown fixture {args.fixture!r}", file=sys.stderr)
        return 2
    if args.mode == "mock":
        if args.max_usd != 0.0 or args.confirm_real_run:
            print("BLOCKED_SCOPE: mock runs take no spend or confirmation flags",
                  file=sys.stderr)
            return 2
        inputs = (args.ledger_dir, args.hypotheses_file, args.observation_digests)
        if (any(inputs) or args.g2_manifest) and not (all(inputs) and args.g2_manifest):
            print("BLOCKED_SCOPE: bound mock requires complete G2 ledger/batch/digests/receipt", file=sys.stderr)
            return 2
        return run_mock(args)
    if args.mode == "preflight":
        if args.confirm_real_run:
            print("BLOCKED_SCOPE: preflight makes no calls and takes no confirmation",
                  file=sys.stderr)
            return 2
        return run_preflight(args)
    return run_real(args)


if __name__ == "__main__":
    raise SystemExit(main())
