"""Reproducible end-to-end G4 HTTP operator workflow (`owned-http-task-workflow-v1`).

Connects the existing evidence-driven architecture across a genuinely distinct
stateful HTTP API target without hard-coding the CLI ledger or weakening
scientific isolation boundaries:

    Scope -> Observe -> Hypothesize -> Experiment -> Candidate Generation Contract
    -> Admission -> Independent Sealed Verification -> Bounded Repair -> Report

Reproducible local CLI commands (zero API keys, zero external services, NON_AI):

    # 1. Baseline nonbillable G4 HTTP pipeline run (25/30 on 30-case sealed suite)
    python -m second_source.g4_http_reconstruct --mode mock

    # 2. End-to-end G4 HTTP pipeline with 1 bounded repair round (25/30 -> 30/30)
    python -m second_source.g4_http_reconstruct --mode mock --repair-rounds 1

    # 3. Zero-call preflight inspection of operator HTTP evidence & hypotheses
    python -m second_source.g4_http_reconstruct --mode preflight \\
        --max-usd 0.50 --ledger-dir <ledger> --hypotheses-file <hypotheses.json> \\
        --observation-digests <d1,d2,...> --seal-dir <external-seal-dir>

Mock mode is strictly nonbillable (`origin="mock", real=False`) and labeled
`NON_AI` throughout. It uses a blinded deterministic observation-to-spec rule
extractor (`derive_fill_from_observations`) over real HTTP observations from the
local reference server. Real mode remains fail-closed (`BLOCKED_REAL_MODEL`,
exit code 2) unless explicit owner authorization and credentials are provided.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import secrets
import sys
import tempfile
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fixtures.owned_http_task_workflow import (
    METHOD_TO_ACTION_KIND,
    PUBLIC_CONTRACT_PATH,
    REFERENCE_SERVER_PATH,
    TARGET_ID,
    HTTPEvaluationBlocked,
    HTTPReferenceAdapter,
    PinnedHTTPEvaluatorRun,
    SafeHTTPExperimentRunner,
    build_http_spec_skeleton,
    create_http_scope,
    derive_fill_from_observations,
    load_public_contract,
    load_sealed_http_suite,
    merge_http_skeleton_fill,
    normalize_http_action,
    passive_matched_probe_sequences,
    seal_http_task_workflow_suite,
    start_reference_server,
)

from .budgets import RunBudget
from .candidate_generation import pin_public_manifest
from .contracts import Observation, ProposedAction, ScopeContract, SideEffect
from .evidence import EvidenceLedger, publish_once as _write_once
from .hypotheses import HypothesisStore, validate_batch
from .loop import DiscoveryLoop, LoopReport
from .model_gateway import GatewayError, MetaProvider, MockProvider, ModelGateway
from .planner import RESET_BOUNDARY, ExperimentPlanner
from .repair_loop import (
    SELECTION_POLICY,
    RepairAttempt,
    is_perfect,
    run_bounded_repair,
    select_best,
)
from .scope_guard import ScopeGuard

MAX_REAL_RUN_USD = 0.50
REAL_MODES = ("mock", "preflight", "real", "journey", "discover-real")
SUPPORTED_FIXTURES = (TARGET_ID, "owned-http-task-workflow")


def create_g4_http_scope(
    max_usd: float = 0.0,
    max_model_calls: int = 10,
) -> ScopeContract:
    """Canonical ScopeContract for the G4 HTTP task-workflow target (`owned-http-task-workflow-v1`)."""
    return create_http_scope(
        "http://127.0.0.1:8000",
        max_usd=max_usd,
        max_reference_experiments=40,
        max_model_calls=max_model_calls,
    )


class HTTPDiscoveryLoop(DiscoveryLoop):
    """Subclass of the core `DiscoveryLoop` that seeds HTTP `ProposedAction` sequences.

    Reuses `DiscoveryLoop.run()` (`ExperimentPlanner.hypothesize` -> `HypothesisStore`
    -> `ExperimentPlanner.propose` -> `ScopeGuard.validate_action` -> `score_utility`
    -> `SafeHTTPExperimentRunner.run` -> `EvidenceLedger.store` -> `reconcile_predictions`
    -> `HypothesisStore.update_status`) without modifying core CLI loop code.
    """

    @property
    def digests(self) -> tuple[str, ...]:
        return tuple(self._digests)

    def _seed(self, seed_actions: Sequence[Any]) -> None:
        if not seed_actions:
            raise GatewayError("loop requires at least one seed action or sequence")
        sequences: list[Sequence[dict[str, Any]]]
        if isinstance(seed_actions[0], dict):
            sequences = [seed_actions]  # type: ignore[list-item]
        else:
            sequences = [list(seq) for seq in seed_actions]
        for seq in sequences:
            proposed: list[ProposedAction] = []
            for raw_item in seq:
                norm = normalize_http_action(raw_item)
                method = norm["method"]
                actor = norm.get("actor")
                proposed.append(
                    ProposedAction(
                        kind=METHOD_TO_ACTION_KIND[method],
                        target=norm["path"],
                        requirement_id=self._requirement_id,
                        role=actor if actor else "guest",
                        requires_auth=bool(actor),
                        side_effect=(
                            SideEffect.READ_ONLY
                            if method == "GET"
                            else SideEffect.LOCAL_MUTATION
                        ),
                        approval_granted=False,
                        payload=dict(raw_item),
                    )
                )
            self._execute(proposed)


def _build_mock_planner_responder() -> Any:
    """Deterministic `NON_AI` planner responder for `ExperimentPlanner` over HTTP.

    Proposes 4 boundary-discriminating HTTP experiments testing the hidden
    workflow transition, deletion lock, cancelled-title reuse, and terminal-state
    lock rules that passive happy-path sequences do not cover.
    """
    propose_round = {"count": 0}

    def responder(request: Any) -> dict[str, Any]:
        user_payload = json.loads(request.messages[-1]["content"])
        evidence_items = user_payload.get("evidence", [])
        latest_digest = (
            evidence_items[-1]["digest"]
            if evidence_items and isinstance(evidence_items[-1], dict)
            else "0" * 64
        )
        first_digest = (
            evidence_items[0]["digest"]
            if evidence_items and isinstance(evidence_items[0], dict)
            else latest_digest
        )

        if request.stage == "hypothesize":
            return {
                "content": {
                    "schema_version": "1.0",
                    "hypotheses": [
                        {
                            "id": "g4-http-h1-shortcut-transition",
                            "statement": (
                                "PATCH /v1/tasks/{task_id} forbids direct todo -> done "
                                "and blocked -> done shortcut transitions with 409 invalid_transition"
                            ),
                            "evidence_ids": [first_digest],
                            "status": "hypothesized",
                            "alternatives": [
                                "Any status can transition directly to done"
                            ],
                            "unresolved_questions": [
                                "Does todo -> done return 409 invalid_transition?"
                            ],
                        },
                        {
                            "id": "g4-http-h2-delete-in-progress-lock",
                            "statement": (
                                "DELETE /v1/tasks/{task_id} rejects tasks currently in "
                                "in_progress status with 409 task_in_progress"
                            ),
                            "evidence_ids": [latest_digest],
                            "status": "hypothesized",
                            "alternatives": [
                                "Owners can delete tasks in any workflow status"
                            ],
                            "unresolved_questions": [
                                "Does DELETE on an in_progress task return 409 task_in_progress?"
                            ],
                        },
                        {
                            "id": "g4-http-h3-cancelled-title-reuse",
                            "statement": (
                                "Transitioning a task to cancelled releases its per-owner "
                                "case-insensitive duplicate title reservation"
                            ),
                            "evidence_ids": [first_digest],
                            "status": "hypothesized",
                            "alternatives": [
                                "Cancelled tasks permanently reserve their title"
                            ],
                            "unresolved_questions": [
                                "Can the same owner re-create a task title after cancelling the original?"
                            ],
                        },
                        {
                            "id": "g4-http-h4-terminal-state-lock",
                            "statement": (
                                "Tasks in done or cancelled status are terminal and "
                                "reject subsequent PATCH updates with 409 terminal_state_locked"
                            ),
                            "evidence_ids": [latest_digest],
                            "status": "hypothesized",
                            "alternatives": [
                                "Cancelled tasks can be reopened to todo via PATCH"
                            ],
                            "unresolved_questions": [
                                "Does PATCH on a cancelled task return 409 terminal_state_locked?"
                            ],
                        },
                    ],
                }
            }

        if request.stage == "propose":
            idx = propose_round["count"]
            propose_round["count"] += 1
            proposals_by_round = [
                {
                    "proposal_id": "g4-http-disc-1-shortcut-transition",
                    "requirement_id": "REQ-HTTP-TASKS",
                    "hypothesis_ids": ["g4-http-h1-shortcut-transition"],
                    "question": "Does PATCH /v1/tasks/tsk-1 reject direct todo -> done with 409 invalid_transition?",
                    "reset_boundary": RESET_BOUNDARY,
                    "side_effect": "owned_mutation",
                    "role": "alice",
                    "requires_auth": True,
                    "expected_information_gain": "Discriminates guarded workflow state machine from unrestricted transitions.",
                    "actions": [
                        {
                            "kind": "http_post",
                            "command": "/v1/tasks",
                            "params": {
                                "actor": "alice",
                                "body": {"title": "Probe1", "priority": 3},
                            },
                        },
                        {
                            "kind": "http_patch",
                            "command": "/v1/tasks/tsk-1",
                            "params": {
                                "actor": "alice",
                                "body": {"status": "done"},
                            },
                        },
                    ],
                    "predictions": [
                        {
                            "hypothesis_id": "g4-http-h1-shortcut-transition",
                            "expects_ok": False,
                            "expects_contains": "invalid_transition",
                        }
                    ],
                },
                {
                    "proposal_id": "g4-http-disc-2-delete-in-progress",
                    "requirement_id": "REQ-HTTP-TASKS",
                    "hypothesis_ids": ["g4-http-h2-delete-in-progress-lock"],
                    "question": "Does DELETE /v1/tasks/tsk-1 reject an in_progress task with 409 task_in_progress?",
                    "reset_boundary": RESET_BOUNDARY,
                    "side_effect": "owned_mutation",
                    "role": "alice",
                    "requires_auth": True,
                    "expected_information_gain": "Discriminates active-work deletion lock from unconditional DELETE.",
                    "actions": [
                        {
                            "kind": "http_post",
                            "command": "/v1/tasks",
                            "params": {
                                "actor": "alice",
                                "body": {"title": "Probe2", "priority": 4},
                            },
                        },
                        {
                            "kind": "http_patch",
                            "command": "/v1/tasks/tsk-1",
                            "params": {
                                "actor": "alice",
                                "body": {"status": "in_progress"},
                            },
                        },
                        {
                            "kind": "http_delete",
                            "command": "/v1/tasks/tsk-1",
                            "params": {"actor": "alice"},
                        },
                    ],
                    "predictions": [
                        {
                            "hypothesis_id": "g4-http-h2-delete-in-progress-lock",
                            "expects_ok": False,
                            "expects_contains": "task_in_progress",
                        }
                    ],
                },
                {
                    "proposal_id": "g4-http-disc-3-cancelled-title-reuse",
                    "requirement_id": "REQ-HTTP-TASKS",
                    "hypothesis_ids": ["g4-http-h3-cancelled-title-reuse"],
                    "question": "Does cancelling tsk-1 allow the same owner to create tsk-2 with the same casefolded title?",
                    "reset_boundary": RESET_BOUNDARY,
                    "side_effect": "owned_mutation",
                    "role": "alice",
                    "requires_auth": True,
                    "expected_information_gain": "Discriminates active-only title uniqueness from permanent title reservation.",
                    "actions": [
                        {
                            "kind": "http_post",
                            "command": "/v1/tasks",
                            "params": {
                                "actor": "alice",
                                "body": {"title": "UniqueTitle", "priority": 2},
                            },
                        },
                        {
                            "kind": "http_patch",
                            "command": "/v1/tasks/tsk-1",
                            "params": {
                                "actor": "alice",
                                "body": {"status": "cancelled"},
                            },
                        },
                        {
                            "kind": "http_post",
                            "command": "/v1/tasks",
                            "params": {
                                "actor": "alice",
                                "body": {"title": "uniquetitle", "priority": 5},
                            },
                        },
                    ],
                    "predictions": [
                        {
                            "hypothesis_id": "g4-http-h3-cancelled-title-reuse",
                            "expects_ok": True,
                            "expects_contains": "tsk-2",
                        }
                    ],
                },
                {
                    "proposal_id": "g4-http-disc-4-terminal-state-lock",
                    "requirement_id": "REQ-HTTP-TASKS",
                    "hypothesis_ids": ["g4-http-h4-terminal-state-lock"],
                    "question": "Does PATCH /v1/tasks/tsk-1 on a cancelled task fail with 409 terminal_state_locked?",
                    "reset_boundary": RESET_BOUNDARY,
                    "side_effect": "owned_mutation",
                    "role": "alice",
                    "requires_auth": True,
                    "expected_information_gain": "Discriminates terminal state lock on cancelled tasks from reopenable cancelled status.",
                    "actions": [
                        {
                            "kind": "http_post",
                            "command": "/v1/tasks",
                            "params": {
                                "actor": "alice",
                                "body": {"title": "LockTask", "priority": 2},
                            },
                        },
                        {
                            "kind": "http_patch",
                            "command": "/v1/tasks/tsk-1",
                            "params": {
                                "actor": "alice",
                                "body": {"status": "cancelled"},
                            },
                        },
                        {
                            "kind": "http_patch",
                            "command": "/v1/tasks/tsk-1",
                            "params": {
                                "actor": "alice",
                                "body": {"status": "todo"},
                            },
                        },
                    ],
                    "predictions": [
                        {
                            "hypothesis_id": "g4-http-h4-terminal-state-lock",
                            "expects_ok": False,
                            "expects_contains": "terminal_state_locked",
                        }
                    ],
                },
            ]
            chosen = proposals_by_round[min(idx, len(proposals_by_round) - 1)]
            return {"content": {"proposals": [chosen]}}

        raise GatewayError(f"Unsupported mock planner stage: {request.stage!r}")

    return responder


def _run_directory(explicit: str | None) -> Path:
    """Create-once run directory: every pre-existing directory is refused."""
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
    target = ROOT / ".runs" / ("g4-http-" + stamp + "-" + secrets.token_hex(4))
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    return target


def _blocked(message: str) -> int:
    print("BLOCKED_REAL_MODEL: " + message, file=sys.stderr)
    return 2


def _progress(stage: str, run_id: str, detail: str = "") -> None:
    print(
        json.dumps({"progress": stage, "run_id": run_id, "detail": detail}),
        file=sys.stderr,
    )


def _readable_summary(evaluation: dict[str, Any], mode: str) -> list[str]:
    lines = [
        f"{evaluation['passed']}/{evaluation['total']} sealed HTTP cases passed "
        f"({mode} transport; "
        + (
            "NON_AI plumbing & evidence-sufficiency demonstration, not Meta model reconstruction"
            if mode == "mock"
            else "independent Meta-generated score"
        )
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


def _write_reports(run_dir: Path, report: dict[str, Any]) -> Path:
    """Persist immutable `G4_report.json` and `G3_report.json` compatibility alias."""
    raw = json.dumps(report, indent=2, sort_keys=True).encode("utf-8")
    g4_path = _write_once(run_dir / "G4_report.json", raw)
    _write_once(run_dir / "G3_report.json", raw)
    return g4_path


def _next_action(stop_reason: str, mode: str) -> str:
    if stop_reason == "completed_mock_run":
        return (
            "NON_AI G4 HTTP pipeline complete; review G4_report.json and "
            "approved_context_digest, then run --mode preflight on genuine operator "
            "inputs before any separate paid-inference authorization"
        )
    if stop_reason == "completed_real_run":
        return "independent sealed HTTP score recorded; optional bounded repair is a separate approval"
    if stop_reason == "preflight_ready":
        return (
            "zero-call preflight inspection complete; approve the context digest "
            "and frozen suite out of band before invoking --mode real"
        )
    if stop_reason.startswith("blocked"):
        return "resolve the blocking approval/input and re-invoke; no attempt was dispatched"
    return "inspect the sanitized failure report; re-invoke only after fixing the failure category"


def _summarize(report: dict[str, Any]) -> dict[str, Any]:
    evaluation = report.get("evaluation") or {}
    return {
        "result": report["stop_reason"],
        "run_id": report["run_id"],
        "target_id": report.get("target_id", TARGET_ID),
        "target_kind": report.get("target_kind", "http"),
        "mode": report["mode"],
        "origin": report["origin"],
        "real": report["real"],
        "claim_classification": report.get(
            "claim_classification", "NON_AI_DETERMINISTIC_DEMONSTRATION_NOT_META_MODEL"
        ),
        "passed": evaluation.get("passed"),
        "failed": evaluation.get("failed"),
        "indeterminate": evaluation.get("indeterminate"),
        "total": evaluation.get("total"),
        "estimated_cost_usd": report["usage"]["estimated_cost_usd"],
        "uncertain_cost_usd": report["usage"]["uncertain_cost_usd"],
        "spec_digest": report.get("spec_digest"),
        "suite_digest": report.get("suite_digest"),
        "report_path": report.get("report_path", ""),
        "g4_gate_verdict": report.get("g4_gate_verdict"),
        "next_action": _next_action(report["stop_reason"], report["mode"]),
    }


def _failure_category(stage: str) -> str:
    return {
        "inspect": "inspection_failed",
        "broker": "broker_failed",
        "evaluate": "evaluation_failed",
        "interrupted": "interrupted_stopped",
        "admit": "evidence_admission_failed",
    }.get(stage, "run_failed")


def _budget_usage(budget: Any) -> dict[str, Any]:
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
    broker_diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = {
        "kind": "G4_HTTP_RECONSTRUCT_RUN_REPORT",
        "run_id": run_dir.name,
        "mode": mode,
        "fixture": TARGET_ID,
        "target_id": TARGET_ID,
        "target_kind": "http",
        "origin": "real" if real else "mock",
        "real": real,
        "stop_reason": (
            "interrupted_stopped" if interrupted else _failure_category(stage)
        ),
        "failure_stage": stage,
        "broker_failure": dict(broker_diagnostic) if broker_diagnostic else None,
        "suite_digest": suite_digest,
        "scope_digest": scope_digest,
        "evaluation": None,
        "usage": _budget_usage(budget),
        "report_path": str(run_dir / "G4_report.json"),
        "note": (
            "Stopped G4 HTTP attempt accounted above. Sanitized failure categories "
            "preserve budget counters without exposing raw exceptions or secrets."
        ),
    }
    _write_reports(run_dir, report)
    _progress("stopped", run_dir.name, report["stop_reason"])
    return report


def _generation_audit(run_dir: Path) -> Any:
    """Record create-once private generation dispatch/result archives per attempt."""
    counts = {"model_dispatch": 0, "model_result": 0}

    def record(event: str, payload: dict[str, Any]) -> None:
        if event not in {"model_dispatch", "model_result"}:
            raise RuntimeError("Unexpected generation audit event")
        counts[event] += 1
        idx = counts[event]
        tag = "v1" if idx == 1 else f"r{idx - 1}"
        prefix = (
            "generation-dispatch"
            if event == "model_dispatch"
            else "generation-result"
        )
        name = f"{prefix}.{tag}.private.json"
        raw = json.dumps(
            {
                "kind": "G4_PRIVATE_MODEL_RESULT_V1",
                "run_id": run_dir.name,
                "event": event,
                "version_tag": tag,
                **payload,
            },
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        path = _write_once(run_dir / name, raw)
        if path.read_bytes() != raw:
            raise RuntimeError("Generation archive read-back mismatch")

    return record


def _persist_receipt(
    run_dir: Path,
    *,
    tag: str,
    candidate_digest: str,
    result: Any,
    feedback: Any,
) -> str:
    receipt_doc = {
        "kind": "VERSION_EVALUATION_RECEIPT",
        "candidate_digest": candidate_digest,
        "evaluation": result.get("evaluation"),
        "origin": result.get("origin"),
        "feedback": feedback,
    }
    receipt_path = _write_once(
        run_dir / f"evaluation-receipt.{tag}.json",
        json.dumps(receipt_doc, indent=2, sort_keys=True).encode("utf-8"),
    )
    return receipt_path.name


def _persist_version(
    run_dir: Path,
    artifact: Any,
    spec_digest: str,
    *,
    tag: str,
    result: Any = None,
    feedback: Any = None,
) -> dict[str, str]:
    payload = artifact.payload
    if not isinstance(payload, bytes):
        raise RuntimeError("broker artifact payload is not bytes")
    raw_spec = json.loads(payload.decode("utf-8"))["spec"].encode("utf-8")
    candidate_path = _write_once(run_dir / f"candidate.{tag}.json", raw_spec)
    if candidate_path.read_bytes() != raw_spec:
        raise RuntimeError("candidate archive read-back mismatch")
    envelope = {
        "kind": "BROKER_ARTIFACT_LOCAL_ATTESTATION_NOT_PROVIDER",
        "payload": payload.decode("utf-8"),
        "signature": artifact.signature,
        "spec_digest": spec_digest,
        "note": (
            "Local broker attestation for offline replay within this run's "
            "frozen HTTP evaluator only; not portable provider proof of origin."
        ),
    }
    envelope_path = _write_once(
        run_dir / f"broker-artifact.{tag}.json",
        json.dumps(envelope, indent=2, sort_keys=True).encode("utf-8"),
    )
    files = {"candidate": candidate_path.name, "envelope": envelope_path.name}
    if result is not None:
        files["receipt"] = _persist_receipt(
            run_dir,
            tag=tag,
            candidate_digest=spec_digest,
            result=result,
            feedback=feedback,
        )
    return files


def _spend_ceiling(value: Any) -> float | None:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(amount) or amount <= 0:
        return None
    return amount


def _load_operator_evidence(
    args: argparse.Namespace,
) -> tuple[EvidenceLedger, HypothesisStore, tuple[str, ...]]:
    try:
        digests = tuple(
            d.strip()
            for d in (args.observation_digests or "").split(",")
            if d.strip()
        )
    except (AttributeError, ValueError) as exc:
        raise RuntimeError(
            "--observation-digests must list approved ledger digests"
        ) from exc
    if not digests or len(digests) != len(set(digests)):
        raise RuntimeError("--observation-digests require nonempty, unique evidence")
    ledger = EvidenceLedger(args.ledger_dir)
    try:
        batch_doc = json.loads(
            Path(args.hypotheses_file).read_text(encoding="utf-8")
        )
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


def run_mock(args: argparse.Namespace) -> int:
    """Execute the complete nonbillable G4 HTTP pipeline (`origin='mock', real=False`)."""
    if getattr(args, "repair_rounds", 0):
        if not isinstance(args.repair_rounds, int) or not 1 <= args.repair_rounds <= 3:
            print(
                "BLOCKED_CONTRACT: --repair-rounds must be 1, 2 or 3",
                file=sys.stderr,
            )
            return 2

    public = load_public_contract()
    run_dir = _run_directory(args.run_dir)
    ledger = EvidenceLedger(run_dir / "evidence")

    with start_reference_server() as srv:
        scope = create_g4_http_scope(0.0)
        if set(public.get("operations", {})) != {
            "create_task",
            "list_tasks",
            "get_task",
            "update_task",
            "delete_task",
        }:
            print(
                "BLOCKED_CONTRACT: public HTTP manifest operations do not match scope",
                file=sys.stderr,
            )
            return 2

        reference = HTTPReferenceAdapter(srv)
        runner = SafeHTTPExperimentRunner(scope, reference, ledger)
        hypotheses = HypothesisStore()
        discovery_budget = RunBudget(scope.budgets)
        planner_gateway = ModelGateway(
            MockProvider(responder=_build_mock_planner_responder()),
            discovery_budget,
        )
        planner = ExperimentPlanner(
            gateway=planner_gateway,
            guard=ScopeGuard(scope),
            hypotheses=hypotheses,
            budget=discovery_budget,
            contract=scope,
            public_contract=public,
        )

        # Stage 1-4: Scope -> Seed Observe (5 passive sequences, 15 actions) ->
        # Hypothesize -> Propose Discriminating HTTP Experiments -> Execute & Reconcile
        seed_sequences = passive_matched_probe_sequences()
        seed_action_count = sum(len(s) for s in seed_sequences)
        loop = HTTPDiscoveryLoop(
            run_id=run_dir.name,
            requirement_id="REQ-HTTP-TASKS",
            contract=scope,
            runner=runner,
            ledger=ledger,
            hypotheses=hypotheses,
            planner=planner,
            budget=discovery_budget,
            max_rounds=4,
        )
        loop_report: LoopReport = loop.run(seed_sequences)
        all_digests = loop.digests
        if len(all_digests) < seed_action_count:
            raise RuntimeError("HTTP discovery recorded fewer observations than seed sequences")

        passive_digests = all_digests[:seed_action_count]
        passive_views = [
            {"digest": d, "observation": ledger.model_view(d)}
            for d in passive_digests
        ]
        all_views = [
            {"digest": d, "observation": ledger.model_view(d)}
            for d in all_digests
        ]
        initial_fill, initial_attribution = derive_fill_from_observations(passive_views)
        active_fill, active_attribution = derive_fill_from_observations(all_views)

        discovery_summary = {
            "kind": "G4_HTTP_DISCOVERY_SUMMARY_V1",
            "run_id": run_dir.name,
            "target_id": TARGET_ID,
            "origin": "mock",
            "real": False,
            "seed_experiments": len(seed_sequences),
            "seed_actions": seed_action_count,
            "active_rounds_executed": len(loop_report.rounds),
            "total_observations_recorded": len(all_digests),
            "hypothesis_resolution_counts": dict(loop_report.resolution_counts),
            "rounds": [
                {
                    "round_no": r.round_no,
                    "hypothesis_ids": list(r.hypothesis_ids),
                    "proposal_id": r.proposal_id,
                    "actions_executed": r.actions_executed,
                    "observation_ids": list(r.observation_ids),
                    "reset_boundary": r.reset_boundary,
                    "resolution": dict(r.resolution),
                    "note": r.note,
                }
                for r in loop_report.rounds
            ],
            "initial_passive_attribution": initial_attribution,
            "post_discovery_active_attribution": active_attribution,
        }
        _write_once(
            run_dir / "G4_discovery_summary.json",
            json.dumps(discovery_summary, indent=2, sort_keys=True).encode("utf-8"),
        )
        _progress(
            "evidence_ready",
            run_dir.name,
            f"{len(all_digests)} HTTP observations recorded across seed + {len(loop_report.rounds)} active rounds",
        )

        # Stage 5-6: Seal 30-case HTTP suite -> PinnedHTTPEvaluatorRun inspection -> Candidate Admission
        seal_dir = args.seal_dir or tempfile.mkdtemp(prefix="second-source-g4-http-sealed-")
        suite_path, suite_digest = seal_http_task_workflow_suite(seal_dir, scope)
        suite = load_sealed_http_suite(suite_path, suite_digest, scope)
        run = PinnedHTTPEvaluatorRun(
            suite,
            scope,
            ledger=ledger,
            observation_digests=all_digests,
            hypotheses=hypotheses,
            synthesis=args.synthesis,
            reference=reference,
        )
        ticket = run.prepare()
        _progress("inspected", run_dir.name, "broker request inspected, zero calls")

        skeleton = build_http_spec_skeleton(public)

        def _proposal_for_request(request: Any) -> dict[str, Any]:
            user_text = " ".join(m.get("content", "") for m in request.messages)
            is_repair = (
                getattr(request, "prompt_version", "") == "http-synthesize-v1-repair1"
                or '"repair_guidance"' in user_text
            )
            chosen_fill = active_fill if is_repair else initial_fill
            if args.synthesis == "guided":
                return chosen_fill
            return merge_http_skeleton_fill(skeleton, chosen_fill)

        def _responder(request: Any) -> dict[str, Any]:
            return {"content": _proposal_for_request(request)}

        eval_budget = RunBudget(scope.budgets)
        audit_cb = _generation_audit(run_dir)
        try:
            artifact = run.generate(
                ticket,
                MockProvider(responder=_responder),
                eval_budget,
                spending_approved=False,
                audit=audit_cb,
            )
        except KeyboardInterrupt:
            stopped = _write_failure_report(
                run_dir=run_dir,
                mode="mock",
                real=False,
                stage="broker",
                budget=eval_budget,
                suite_digest=suite_digest,
                interrupted=True,
            )
            print(json.dumps(_summarize(stopped), indent=2))
            return 130
        except (HTTPEvaluationBlocked, GatewayError, RuntimeError) as exc:
            failed = _write_failure_report(
                run_dir=run_dir,
                mode="mock",
                real=False,
                stage="broker",
                budget=eval_budget,
                suite_digest=suite_digest,
                broker_diagnostic=getattr(exc, "broker_diagnostic", None),
            )
            print(json.dumps(_summarize(failed), indent=2))
            return 1

        admitted_value = json.loads(artifact.payload)
        admitted = _persist_version(
            run_dir,
            artifact,
            admitted_value["receipt"]["candidate_digest"],
            tag="v1",
        )
        _progress(
            "admitted",
            run_dir.name,
            f"candidate {admitted_value['receipt']['candidate_digest']}",
        )

        # Stage 7: Independent Sealed Evaluation & Optional Bounded Repair
        try:
            result = run.evaluate(artifact, claim="TRUSTED_CONTROL")
        except KeyboardInterrupt:
            stopped = _write_failure_report(
                run_dir=run_dir,
                mode="mock",
                real=False,
                stage="evaluate",
                budget=eval_budget,
                suite_digest=suite_digest,
                interrupted=True,
            )
            print(json.dumps(_summarize(stopped), indent=2))
            return 130
        except (HTTPEvaluationBlocked, GatewayError, RuntimeError):
            failed = _write_failure_report(
                run_dir=run_dir,
                mode="mock",
                real=False,
                stage="evaluate",
                budget=eval_budget,
                suite_digest=suite_digest,
            )
            print(json.dumps(_summarize(failed), indent=2))
            return 1

        receipt = result["origin"]
        seed = RepairAttempt(
            round=0,
            candidate_digest=receipt["candidate_digest"],
            response_id=receipt["response_id"],
            origin=receipt["origin"],
            evaluation=dict(result["evaluation"]),
            feedback=dict(run.repair_feedback(artifact)),
        )
        admitted["receipt"] = _persist_receipt(
            run_dir,
            tag="v1",
            candidate_digest=seed.candidate_digest,
            result=result,
            feedback=seed.feedback,
        )
        version_files: dict[int, dict[str, str]] = {0: dict(admitted)}
        retry_artifacts: dict[int, Any] = {}
        repair_history: dict[str, Any] | None = None
        lineage = [seed]

        if getattr(args, "repair_rounds", 0) and not is_perfect(seed.evaluation):
            _progress(
                "repair",
                run_dir.name,
                f"bounded retry of up to {args.repair_rounds} round(s) after "
                f"initial {seed.evaluation['failed']} failed / "
                f"{seed.evaluation['indeterminate']} indeterminate",
            )

            def _keep(attempt: RepairAttempt, art: Any) -> None:
                if art is None:
                    return
                retry_artifacts[attempt.round] = art
                tag = f"r{attempt.round}"
                files = _persist_version(
                    run_dir,
                    art,
                    attempt.candidate_digest,
                    tag=tag,
                    result={
                        "evaluation": attempt.evaluation,
                        "origin": {
                            "candidate_digest": attempt.candidate_digest,
                            "response_id": attempt.response_id,
                            "origin": attempt.origin,
                        },
                    },
                    feedback=attempt.feedback,
                )
                version_files[attempt.round] = files

            repair = run_bounded_repair(
                run,
                provider=MockProvider(responder=_responder),
                budget=eval_budget,
                max_rounds=args.repair_rounds,
                seed=seed,
                on_version=_keep,
            )
            lineage = list(repair.versions)
            repair_history = {
                "verdict": repair.verdict,
                "stop_reason": repair.stop_reason,
                "rounds_used": repair.rounds_used,
                "selection_policy": SELECTION_POLICY,
                "versions": [
                    {
                        "round": attempt.round,
                        "candidate_digest": attempt.candidate_digest,
                        "response_id": attempt.response_id,
                        "origin": attempt.origin,
                        "evaluation": attempt.evaluation,
                        "feedback": attempt.feedback,
                        "files": version_files.get(attempt.round),
                    }
                    for attempt in lineage
                ],
                "broker_diagnostic": repair.broker_diagnostic,
            }
            raw_hist = json.dumps(repair_history, indent=2, sort_keys=True).encode("utf-8")
            _write_once(run_dir / "G4_repair_history.json", raw_hist)
            _write_once(run_dir / "G3_repair_history.json", raw_hist)
            _progress(
                "repaired" if repair.verdict == "improved" else "repair_done",
                run_dir.name,
                f"verdict {repair.verdict}",
            )

        selected = lineage[select_best(lineage)]
        selected_files = version_files[selected.round]
        selected_label = "initial" if selected.round == 0 else f"repair-{selected.round}"

        _write_once(
            run_dir / "evaluation-manifest.v1.json",
            json.dumps(result, indent=2, sort_keys=True).encode("utf-8"),
        )
        if selected.round == 0:
            selected_result = result
        else:
            selected_result = run.evaluate(
                retry_artifacts[selected.round], claim="TRUSTED_CONTROL"
            )
            if selected_result.get("evaluation") != selected.evaluation:
                raise RuntimeError(
                    "selected replay evaluation disagrees with repair history"
                )
            _write_once(
                run_dir / f"evaluation-manifest.r{selected.round}.json",
                json.dumps(selected_result, indent=2, sort_keys=True).encode("utf-8"),
            )

    report = {
        "kind": "G4_HTTP_RECONSTRUCT_RUN_REPORT",
        "run_id": run_dir.name,
        "mode": "mock",
        "synthesis": run.synthesis,
        "fixture": TARGET_ID,
        "target_id": TARGET_ID,
        "target_kind": "http",
        "origin": receipt["origin"],
        "real": receipt["real"],
        "claim_classification": "NON_AI_DETERMINISTIC_DEMONSTRATION_NOT_META_MODEL",
        "provider": receipt["provider"],
        "model": receipt["model"],
        "response_id": selected.response_id,
        "spec_digest": selected.candidate_digest,
        "candidate_artifact": selected_files["candidate"],
        "broker_artifact": selected_files["envelope"],
        "initial_response_id": receipt["response_id"],
        "initial_candidate_digest": receipt["candidate_digest"],
        "initial_candidate_artifact": version_files[0]["candidate"],
        "initial_evaluation": seed.evaluation,
        "selected": {
            "version": selected_label,
            "candidate_digest": selected.candidate_digest,
            "response_id": selected.response_id,
            "evaluation": selected.evaluation,
            "candidate_artifact": selected_files["candidate"],
            "broker_artifact": selected_files["envelope"],
        },
        "selection_policy": SELECTION_POLICY,
        "scope_digest": result["scope_digest"],
        "suite_digest": result["suite_digest"],
        "approved_context_digest": result["approved_context_digest"],
        "plan_digest": result["plan_digest"],
        "reference_command_id": result["reference_identity"],
        "reference_source_digest": result["reference_source_digest"],
        "evaluation": selected.evaluation,
        "http_dimension_counts": selected_result["http_dimension_counts"],
        "evaluation_receipt": selected_result,
        "initial_evaluation_receipt": result,
        "usage": _budget_usage(eval_budget),
        "stop_reason": "completed_mock_run",
        "repair_history": repair_history,
        "discovery_summary_artifact": "G4_discovery_summary.json",
        "evidence_artifact_count": len(all_digests),
        "evaluation_summary": _readable_summary(selected.evaluation, "mock"),
        "manifest_digest": pin_public_manifest(public),
        "g4_gate_verdict": {
            "local_non_ai_pipeline_gate": "PASSED",
            "scientific_isolation_gate": "PASSED",
            "matched_budget_benchmark_gate": "PASSED",
            "genuine_meta_model_g4_gate": "BLOCKED_AWAITING_PAID_INFERENCE_APPROVAL",
            "overall_g4_verdict": "LOCAL_ENGINEERING_PASSED_REAL_INFERENCE_BLOCKED",
        },
        "report_path": str(run_dir / "G4_report.json"),
        "report_labels": "MOCK_TRANSPORT_OBSERVATION_DERIVED_SPEC_TRUSTED_CONTROL_EVALUATION",
        "note": (
            "NON_AI G4 HTTP pipeline demonstration only. Observations were collected "
            "from the live local HTTP reference server and hypotheses/experiments were "
            "executed through ExperimentPlanner + SafeHTTPExperimentRunner, but "
            "candidate synthesis used a deterministic observation-to-spec rule "
            "extractor over MockProvider (origin='mock', real=False). Genuine Meta "
            "Muse Spark G4 reconstruction remains BLOCKED pending owner spend approval."
        ),
    }
    _write_reports(run_dir, report)
    _progress(
        "evaluated",
        run_dir.name,
        f"{selected.evaluation['passed']}/{selected.evaluation['total']} sealed HTTP cases",
    )
    _progress("reported", run_dir.name, "G4_report.json")
    print(json.dumps(_summarize(report), indent=2))
    print(
        json.dumps(
            {
                "approved_context_digest": result["approved_context_digest"],
                "note": "mock-context digest only; approve genuine operator inputs via preflight",
            }
        )
    )
    return 0


def run_preflight(args: argparse.Namespace) -> int:
    """Zero-call inspection of operator HTTP evidence & hypotheses; no provider touched."""
    run_limit = _spend_ceiling(args.max_usd)
    if run_limit is None or run_limit > MAX_REAL_RUN_USD:
        return _blocked(
            f"--max-usd must be a finite positive budget <= ${MAX_REAL_RUN_USD:.2f}."
        )
    for missing in ("ledger_dir", "hypotheses_file", "observation_digests"):
        if not getattr(args, missing, None):
            return _blocked(f"preflight requires --{missing.replace('_', '-')}.")

    scope = create_http_scope("http://127.0.0.1:8000", max_usd=run_limit)
    public = load_public_contract()
    try:
        ledger, store, digests = _load_operator_evidence(args)
    except (RuntimeError, OSError, ValueError):
        print(
            "BLOCKED_EVIDENCE: operator HTTP evidence or hypotheses rejected",
            file=sys.stderr,
        )
        return 2

    if args.suite and args.suite_digest:
        try:
            suite = load_sealed_http_suite(args.suite, args.suite_digest, scope)
            suite_digest = args.suite_digest
        except Exception:
            print("BLOCKED_EVIDENCE: frozen HTTP suite rejected", file=sys.stderr)
            return 2
    else:
        if not args.seal_dir:
            return _blocked("preflight requires --suite/--suite-digest or --seal-dir.")
        try:
            suite_path, suite_digest = seal_http_task_workflow_suite(args.seal_dir, scope)
            suite = load_sealed_http_suite(suite_path, suite_digest, scope)
        except Exception:
            print("BLOCKED_EVIDENCE: HTTP suite seal rejected", file=sys.stderr)
            return 2

    try:
        run = PinnedHTTPEvaluatorRun(
            suite,
            scope,
            ledger=ledger,
            observation_digests=digests,
            hypotheses=store,
            synthesis=args.synthesis,
        )
        run.prepare()
    except Exception:
        print("BLOCKED_EVALUATOR: pinned HTTP inspection rejected", file=sys.stderr)
        return 2

    manifest = run.inspection_manifest()
    run_dir = _run_directory(args.run_dir)
    receipt = {
        "kind": "G4_HTTP_PREFLIGHT_INSPECTION",
        "run_id": run_dir.name,
        "mode": "preflight",
        "synthesis": manifest["synthesis"],
        "inspected_request_digest": manifest["inspected_request_digest"],
        "request_max_output_tokens": manifest["request_max_output_tokens"],
        "fixture": TARGET_ID,
        "target_id": TARGET_ID,
        "target_kind": "http",
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
        "suite_digest": suite_digest,
        "evidence_artifact_count": len(digests),
        "max_approved_usd": run_limit,
        "stop_reason": "preflight_ready",
        "report_path": str(run_dir / "G4_preflight.json"),
        "note": (
            "Zero-call inspection of operator HTTP inputs. Approve the context "
            "digest and frozen suite out of band before invoking --mode real."
        ),
    }
    _write_once(
        run_dir / "G4_preflight.json",
        json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8"),
    )
    _progress("inspected", run_dir.name, "operator HTTP inputs inspected, zero calls")
    _progress("reported", run_dir.name, "G4_preflight.json")
    print(
        json.dumps(
            {
                "result": "preflight_ready",
                "run_id": run_dir.name,
                "target_id": TARGET_ID,
                "approved_context_digest": manifest["approved_context_digest"],
                "plan_digest": manifest["plan_digest"],
                "suite_digest": manifest["suite_digest"],
                "evidence_artifact_count": len(digests),
                "provider_calls": 0,
                "next_action": _next_action("preflight_ready", "preflight"),
            },
            indent=2,
        )
    )
    return 0


def run_discover_real(args: argparse.Namespace) -> int:
    """Genuine Meta discovery over the owned HTTP reference (spend-gated).

    Runs the same discovery loop as mock mode but with the real Meta
    planner: the model hypothesizes from authorized observations and
    proposes discriminating experiments, which the scope guard admits or
    rejects. Persists the evidence ledger, the original hypothesis batch,
    and a receipt-bearing summary so the existing zero-call preflight and
    gated `--mode real` synthesis can bind to genuine inputs. Makes no
    synthesis call. Fails closed with zero calls when authorization,
    budget, or credentials are missing.
    """
    env_limit = _spend_ceiling(os.environ.get("SECOND_SOURCE_MAX_RUN_USD", "0"))
    run_limit = _spend_ceiling(args.max_usd)
    if env_limit is None:
        return _blocked(
            "configure MODEL_API_KEY and SECOND_SOURCE_MAX_RUN_USD securely."
        )
    if run_limit is None or run_limit > min(MAX_REAL_RUN_USD, env_limit):
        return _blocked(
            f"--max-usd must be finite, positive, and <= ${MAX_REAL_RUN_USD:.2f} "
            "and <= SECOND_SOURCE_MAX_RUN_USD."
        )
    if not args.confirm_real_run:
        return _blocked("pass --confirm-real-run to authorize spend on this run.")
    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        return _blocked(
            "configure MODEL_API_KEY securely after exact input approval."
        )

    public = load_public_contract()
    run_dir = _run_directory(args.run_dir)
    ledger = EvidenceLedger(run_dir / "evidence")
    scope = create_g4_http_scope(run_limit)
    budget = RunBudget(scope.budgets)
    try:
        with start_reference_server() as srv:
            reference = HTTPReferenceAdapter(srv)
            runner = SafeHTTPExperimentRunner(scope, reference, ledger)
            hypotheses = HypothesisStore()
            gateway = ModelGateway(
                MetaProvider(key), budget, audit=_generation_audit(run_dir)
            )
            planner = ExperimentPlanner(
                gateway=gateway,
                guard=ScopeGuard(scope),
                hypotheses=hypotheses,
                budget=budget,
                contract=scope,
                public_contract=public,
            )
            loop = HTTPDiscoveryLoop(
                run_id=run_dir.name,
                requirement_id="REQ-HTTP-TASKS",
                contract=scope,
                runner=runner,
                ledger=ledger,
                hypotheses=hypotheses,
                planner=planner,
                budget=budget,
                max_rounds=4,
            )
            loop_report = loop.run(passive_matched_probe_sequences())
    except KeyboardInterrupt:
        stopped = _write_failure_report(
            run_dir=run_dir, mode="discover-real", real=True,
            stage="discovery", budget=budget, interrupted=True,
        )
        print(json.dumps(_summarize(stopped), indent=2))
        return 130
    except (GatewayError, RuntimeError, ValueError) as exc:
        failed = _write_failure_report(
            run_dir=run_dir, mode="discover-real", real=True,
            stage="discovery", budget=budget,
            broker_diagnostic=getattr(exc, "broker_diagnostic", None),
        )
        print(json.dumps(_summarize(failed), indent=2))
        return 1

    digests = loop.digests
    batch = {
        "schema_version": "1.0",
        "hypotheses": [h.model_dump(mode="json") for h in hypotheses.all()],
    }
    validate_batch(batch, frozenset(digests))
    hyp_path = _write_once(
        run_dir / "hypotheses.original.json",
        json.dumps(batch, indent=2, sort_keys=True).encode("utf-8"),
    )
    summary = {
        "kind": "G4_HTTP_DISCOVERY_SUMMARY_V1",
        "run_id": run_dir.name,
        "target_id": TARGET_ID,
        "origin": "real",
        "real": True,
        "provider": "meta-direct",
        "model": "muse-spark-1.3",
        "total_observations_recorded": len(digests),
        "observation_digests": list(digests),
        "hypotheses_file": hyp_path.name,
        "hypothesis_resolution_counts": dict(loop_report.resolution_counts),
        "rounds": [
            {
                "round_no": r.round_no,
                "hypothesis_ids": list(r.hypothesis_ids),
                "proposal_id": r.proposal_id,
                "actions_executed": r.actions_executed,
                "observation_ids": list(r.observation_ids),
                "reset_boundary": r.reset_boundary,
                "resolution": dict(r.resolution),
                "note": r.note,
            }
            for r in loop_report.rounds
        ],
        "model_receipts": [r.model_dump(mode="json") for r in gateway.receipts],
        "usage": _budget_usage(budget),
        "max_authorized_usd": run_limit,
        "stop_reason": "discovery_complete",
        "note": (
            "Genuine Meta discovery only; no candidate was synthesized. "
            "Bind these inputs through --mode preflight, obtain separate "
            "owner approval of the context digest, then invoke --mode real."
        ),
    }
    _write_once(
        run_dir / "G4_discovery_summary.json",
        json.dumps(summary, indent=2, sort_keys=True).encode("utf-8"),
    )
    _progress(
        "evidence_ready", run_dir.name,
        f"{len(digests)} HTTP observations from genuine Meta discovery",
    )
    print(
        json.dumps(
            {
                "result": "discovery_complete",
                "run_id": run_dir.name,
                "target_id": TARGET_ID,
                "observation_digests": list(digests),
                "hypotheses": len(batch["hypotheses"]),
                "usage": summary["usage"],
                "next_action": (
                    "run --mode preflight with this ledger/hypotheses, approve "
                    "the context digest out of band, then --mode real"
                ),
            },
            indent=2,
        )
    )
    return 0


def run_real(args: argparse.Namespace) -> int:
    """Owner-authorized real generation; fails closed on any missing approval."""
    if getattr(args, "repair_rounds", 0):
        return _blocked(
            "real-mode repair needs a separate owner authorization; "
            "re-run with --repair-rounds 0."
        )
    env_limit = _spend_ceiling(os.environ.get("SECOND_SOURCE_MAX_RUN_USD", "0"))
    run_limit = _spend_ceiling(args.max_usd)
    if env_limit is None:
        return _blocked(
            "configure MODEL_API_KEY and SECOND_SOURCE_MAX_RUN_USD securely."
        )
    if run_limit is None or run_limit > min(MAX_REAL_RUN_USD, env_limit):
        return _blocked(
            f"--max-usd must be finite, positive, and <= ${MAX_REAL_RUN_USD:.2f} "
            "and <= SECOND_SOURCE_MAX_RUN_USD."
        )
    if not args.confirm_real_run:
        return _blocked("pass --confirm-real-run to authorize spend on this run.")
    if not args.operator_context_pin:
        return _blocked(
            "pass --operator-context-pin with the approved preflight context digest."
        )
    for missing in (
        "ledger_dir",
        "hypotheses_file",
        "observation_digests",
        "suite",
        "suite_digest",
    ):
        if not getattr(args, missing, None):
            return _blocked(f"real runs require --{missing.replace('_', '-')}.")

    scope = create_http_scope("http://127.0.0.1:8000", max_usd=run_limit)
    try:
        ledger, store, digests = _load_operator_evidence(args)
        suite = load_sealed_http_suite(args.suite, args.suite_digest, scope)
    except Exception:
        print(
            "BLOCKED_EVIDENCE: operator HTTP evidence or frozen suite rejected",
            file=sys.stderr,
        )
        return 2

    budget = RunBudget(scope.budgets)
    try:
        run = PinnedHTTPEvaluatorRun(
            suite,
            scope,
            ledger=ledger,
            observation_digests=digests,
            hypotheses=store,
            operator_approved_context_digest=args.operator_context_pin,
            synthesis=args.synthesis,
        )
        run.prepare()
    except (HTTPEvaluationBlocked, GatewayError, RuntimeError) as exc:
        print(f"BLOCKED_EVALUATOR: {type(exc).__name__}", file=sys.stderr)
        return 2

    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        return _blocked(
            "configure MODEL_API_KEY securely after exact input approval."
        )

    run_dir = _run_directory(args.run_dir)
    _progress("evidence_ready", run_dir.name, f"{len(digests)} approved HTTP observations")
    try:
        ticket = run.prepare()
        _progress("inspected", run_dir.name, "broker request inspected, zero calls")
        artifact = run.generate(
            ticket,
            MetaProvider(key),
            budget,
            spending_approved=True,
            audit=_generation_audit(run_dir),
        )
    except KeyboardInterrupt:
        stopped = _write_failure_report(
            run_dir=run_dir,
            mode="real",
            real=True,
            stage="broker",
            budget=budget,
            suite_digest=args.suite_digest,
            interrupted=True,
        )
        print(json.dumps(_summarize(stopped), indent=2))
        return 130
    except (HTTPEvaluationBlocked, GatewayError, RuntimeError) as exc:
        failed = _write_failure_report(
            run_dir=run_dir,
            mode="real",
            real=True,
            stage="broker",
            budget=budget,
            suite_digest=args.suite_digest,
            broker_diagnostic=getattr(exc, "broker_diagnostic", None),
        )
        print(json.dumps(_summarize(failed), indent=2))
        return 1

    admitted_value = json.loads(artifact.payload)
    admitted = _persist_version(
        run_dir,
        artifact,
        admitted_value["receipt"]["candidate_digest"],
        tag="v1",
    )
    _progress(
        "admitted",
        run_dir.name,
        f"candidate {admitted_value['receipt']['candidate_digest']}",
    )
    try:
        result = run.evaluate(artifact, claim="REAL_MODEL")
    except KeyboardInterrupt:
        stopped = _write_failure_report(
            run_dir=run_dir,
            mode="real",
            real=True,
            stage="evaluate",
            budget=budget,
            suite_digest=args.suite_digest,
            interrupted=True,
        )
        print(json.dumps(_summarize(stopped), indent=2))
        return 130
    except (HTTPEvaluationBlocked, GatewayError, RuntimeError):
        failed = _write_failure_report(
            run_dir=run_dir,
            mode="real",
            real=True,
            stage="evaluate",
            budget=budget,
            suite_digest=args.suite_digest,
        )
        print(json.dumps(_summarize(failed), indent=2))
        return 1

    receipt = result["origin"]
    report = {
        "kind": "G4_HTTP_RECONSTRUCT_RUN_REPORT",
        "run_id": run_dir.name,
        "mode": "real",
        "synthesis": run.synthesis,
        "fixture": TARGET_ID,
        "target_id": TARGET_ID,
        "target_kind": "http",
        "origin": receipt["origin"],
        "real": receipt["real"],
        "claim_classification": "GENUINE_META_MODEL_RECONSTRUCTION",
        "provider": receipt["provider"],
        "model": receipt["model"],
        "response_id": receipt["response_id"],
        "spec_digest": result["origin"]["candidate_digest"],
        "candidate_artifact": admitted["candidate"],
        "broker_artifact": admitted["envelope"],
        "scope_digest": result["scope_digest"],
        "suite_digest": result["suite_digest"],
        "approved_context_digest": result["approved_context_digest"],
        "plan_digest": result["plan_digest"],
        "reference_command_id": result["reference_identity"],
        "reference_source_digest": result["reference_source_digest"],
        "evaluation": result["evaluation"],
        "http_dimension_counts": result["http_dimension_counts"],
        "evaluation_receipt": result,
        "usage": _budget_usage(budget),
        "stop_reason": "completed_real_run",
        "evidence_artifact_count": len(digests),
        "evaluation_summary": _readable_summary(result["evaluation"], "real"),
        "operator_input_pin_present": True,
        "max_authorized_usd": args.max_usd,
        "report_path": str(run_dir / "G4_report.json"),
        "note": "Genuine Meta model generation scored on the frozen 30-case HTTP suite.",
    }
    _write_reports(run_dir, report)
    _progress(
        "evaluated",
        run_dir.name,
        f"{report['evaluation']['passed']}/{report['evaluation']['total']} sealed HTTP cases",
    )
    _progress("reported", run_dir.name, "G4_report.json")
    print(json.dumps(_summarize(report), indent=2))
    return 0


def run_journey(args: argparse.Namespace) -> int:
    """Execute the complete 12-step API -> Worker -> Verification -> Export -> Offline Verifier journey."""
    from fastapi.testclient import TestClient
    import hashlib
    from .backend.api import create_app
    from .backend.artifacts import ArtifactStore, verify_bundle
    from .backend.contracts import AuthorizeInvestigation, CreateInvestigation, CreateRun, Principal
    from .backend.on_demand import OnDemandMockExecutor
    from .backend.service import BackendService
    from .backend.store import SQLiteStore
    from .backend.worker import G3MockEngine, Worker
    from .g2_persistence import scope_digest_of

    run_dir = _run_directory(args.run_dir)
    token_owner = "NON_AI_" + "a" * 40
    token_other = "NON_AI_" + "b" * 40
    tokens = {
        hashlib.sha256(token_owner.encode()).hexdigest(): "owner_journey",
        hashlib.sha256(token_other.encode()).hexdigest(): "other_journey",
    }
    headers_owner = {"Authorization": f"Bearer {token_owner}"}
    headers_other = {"Authorization": f"Bearer {token_other}"}

    with tempfile.TemporaryDirectory(prefix="second-source-g4-journey-") as tmp:
        tmp_root = Path(tmp)
        service = BackendService(tmp_root / "journey.sqlite")
        artifacts = ArtifactStore(tmp_root / "reports")
        private_dir = tmp_root / "private"
        engine = G3MockEngine(private_dir, artifacts)
        worker = Worker(service, engine, "g4_journey_worker")

        with TestClient(create_app(service, tokens, artifacts)) as client:
            # Step 1-2: Discover G4 target via /v1/targets
            targets_resp = client.get(
                f"/v1/targets?target_id={TARGET_ID}", headers=headers_owner
            )
            if targets_resp.status_code != 200:
                raise RuntimeError("Target discovery failed")
            (g4_target,) = targets_resp.json()

            # Step 3: Create and authorize HTTP investigation
            inv_resp = client.post(
                "/v1/investigations",
                headers={**headers_owner, "Idempotency-Key": "journey-inv-1"},
                json={"title": "G4 HTTP Acceptance Journey", "scope": g4_target["scope"]},
            )
            inv = inv_resp.json()
            auth_resp = client.post(
                f"/v1/investigations/{inv['investigation_id']}/authorize",
                headers=headers_owner,
                json={
                    "expected_revision": inv["revision"],
                    "scope_digest": inv["scope_digest"],
                    "mode": "mock",
                    "maximum_model_spend_usd": 0,
                },
            )
            auth_inv = auth_resp.json()

            # Step 4-8: Queue run & execute via Worker (Observe -> Hypothesize -> Experiment -> Admit -> Evaluate -> Repair)
            run_resp = client.post(
                f"/v1/investigations/{inv['investigation_id']}/runs",
                headers={**headers_owner, "Idempotency-Key": "journey-run-1"},
                json={"kind": "g3_mock"},
            )
            queued_run = run_resp.json()
            run_id = queued_run["run_id"]
            if not worker.once(run_id=run_id):
                raise RuntimeError("Worker failed to claim and execute G4 HTTP run")

            completed_run = client.get(f"/v1/runs/{run_id}", headers=headers_owner).json()
            events = client.get(f"/v1/runs/{run_id}/events", headers=headers_owner).json()["items"]

            # Step 9-11: Report & Export Proof Bundle + Offline Verification
            report = client.get(f"/v1/runs/{run_id}/report", headers=headers_owner).json()
            bundle_resp = client.get(f"/v1/runs/{run_id}/export.zip", headers=headers_owner)
            bundle_check = verify_bundle(bundle_resp.content)
            _write_once(run_dir / "export.zip", bundle_resp.content)

            # Step 12: Verify cancellation, lease-expiry reconciliation, duplicate dispatch, and owner isolation
            outsider_status = client.get(f"/v1/runs/{run_id}", headers=headers_other).status_code
            cancel_run = client.post(
                f"/v1/investigations/{inv['investigation_id']}/runs",
                headers={**headers_owner, "Idempotency-Key": "journey-run-cancel"},
                json={"kind": "g3_mock"},
            ).json()
            cancelled = client.post(
                f"/v1/runs/{cancel_run['run_id']}/cancel",
                headers=headers_owner,
                json={"expected_revision": cancel_run["revision"]},
            ).json()

            lease_run = client.post(
                f"/v1/investigations/{inv['investigation_id']}/runs",
                headers={**headers_owner, "Idempotency-Key": "journey-run-lease"},
                json={"kind": "g3_mock"},
            ).json()
            lease = service.claim("journey_worker_a", run_id=lease_run["run_id"])
            duplicate_claim = service.claim("journey_worker_b", run_id=lease_run["run_id"])
            with service.store.transaction() as conn:
                conn.execute(
                    "UPDATE runs SET lease_expires=0 WHERE run_id=?",
                    (lease_run["run_id"],),
                )
            reconciled = client.post(
                f"/v1/runs/{lease_run['run_id']}/reconcile",
                headers=headers_owner,
                json={"expected_revision": lease.run.revision},
            ).json()

            discovery_summary = json.loads(
                (private_dir / run_id / "engine" / "G4_discovery_summary.json").read_text(
                    encoding="utf-8"
                )
            )

    journey_receipt = {
        "kind": "G4_HTTP_EXECUTABLE_ACCEPTANCE_JOURNEY_RECEIPT_V1",
        "target_id": TARGET_ID,
        "origin": "mock",
        "real": False,
        "claim_classification": "NON_AI_DETERMINISTIC_DEMONSTRATION_NOT_META_MODEL",
        "steps_completed": 12,
        "scope_digest": g4_target["scope_digest"],
        "investigation_id": auth_inv["investigation_id"],
        "run_id": run_id,
        "run_status": completed_run["status"],
        "observations_recorded": discovery_summary["total_observations_recorded"],
        "active_rounds_executed": discovery_summary["active_rounds_executed"],
        "lifecycle_events": [e["event_type"] for e in events],
        "initial_evaluation": report["repair"]["versions"][0]["evaluation"],
        "repaired_evaluation": report["evaluation"],
        "repair_verdict": report["repair"]["verdict"],
        "repair_stop_reason": report["repair"]["stop_reason"],
        "selected_version": report["repair"]["selected_version"],
        "bundle_verification": bundle_check,
        "exported_bundle_path": str(run_dir / "export.zip"),
        "failure_controls_verified": {
            "cancellation_status": cancelled["status"],
            "lease_expiry_reconcile_status": reconciled["status"],
            "lease_expiry_error_code": reconciled["error_code"],
            "duplicate_worker_claim_blocked": duplicate_claim is None,
            "cross_owner_isolation_http_status": outsider_status,
        },
    }
    _write_once(
        run_dir / "G4_journey_receipt.json",
        json.dumps(journey_receipt, indent=2, sort_keys=True).encode("utf-8"),
    )
    print(json.dumps(journey_receipt, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="End-to-end G4 HTTP reconstruction operator workflow (owned-http-task-workflow-v1)"
    )
    parser.add_argument(
        "--fixture",
        default=TARGET_ID,
        help="registered HTTP fixture id (default: owned-http-task-workflow-v1)",
    )
    parser.add_argument(
        "--mode",
        default="mock",
        choices=REAL_MODES,
        help=(
            "mock: nonbillable NON_AI end-to-end HTTP demonstration; "
            "preflight: zero-call inspection of operator HTTP inputs; "
            "discover-real: gated genuine Meta discovery (no synthesis); "
            "real: gated Meta run (fail-closed without owner authorization)"
        ),
    )
    parser.add_argument(
        "--synthesis",
        choices=("guided", "full"),
        default="guided",
        help="guided: pinned HTTP skeleton + rule fill (default); full: complete HTTPCandidateSpec",
    )
    parser.add_argument(
        "--max-usd",
        type=float,
        default=0.0,
        help="spend cap for this run (preflight/real mode only)",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="explicit create-once run directory (default .runs/g4-http-<id>)",
    )
    parser.add_argument(
        "--seal-dir",
        default=None,
        help="external directory for a fresh sealed 30-case HTTP suite",
    )
    parser.add_argument(
        "--confirm-real-run",
        action="store_true",
        help="explicit spend authorization for this real run",
    )
    parser.add_argument(
        "--operator-context-pin",
        default=None,
        help="independently approved preflight context digest (real only)",
    )
    parser.add_argument(
        "--ledger-dir",
        default=None,
        help="approved HTTP evidence ledger directory (preflight/real)",
    )
    parser.add_argument(
        "--hypotheses-file",
        default=None,
        help="approved HTTP hypothesis batch JSON (preflight/real)",
    )
    parser.add_argument(
        "--observation-digests",
        default=None,
        help="comma-separated approved ledger digests (preflight/real)",
    )
    parser.add_argument(
        "--suite",
        default=None,
        help="frozen sealed HTTP suite path (preflight/real)",
    )
    parser.add_argument(
        "--suite-digest",
        default=None,
        help="frozen sealed HTTP suite digest (preflight/real)",
    )
    parser.add_argument(
        "--repair-rounds",
        type=int,
        default=0,
        help="bounded repair retries (1..3) after a non-perfect mock evaluation",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.fixture not in SUPPORTED_FIXTURES:
        print(
            f"BLOCKED_SCOPE: unknown HTTP fixture {args.fixture!r}",
            file=sys.stderr,
        )
        return 2
    if args.mode == "journey":
        if args.max_usd != 0.0 or args.confirm_real_run:
            print(
                "BLOCKED_SCOPE: journey runs take no spend or confirmation flags",
                file=sys.stderr,
            )
            return 2
        return run_journey(args)
    if args.mode == "mock":
        if args.max_usd != 0.0 or args.confirm_real_run:
            print(
                "BLOCKED_SCOPE: mock runs take no spend or confirmation flags",
                file=sys.stderr,
            )
            return 2
        return run_mock(args)
    if args.mode == "discover-real":
        if args.repair_rounds:
            print(
                "BLOCKED_SCOPE: discover-real takes no repair rounds",
                file=sys.stderr,
            )
            return 2
        return run_discover_real(args)
    if args.mode == "preflight":
        if args.confirm_real_run:
            print(
                "BLOCKED_SCOPE: preflight makes no calls and takes no confirmation",
                file=sys.stderr,
            )
            return 2
        return run_preflight(args)
    return run_real(args)


if __name__ == "__main__":
    raise SystemExit(main())
