"""Owner-local MCP evidence and bounded black-box probe functions.

This module is transport-agnostic. The official MCP SDK is loaded by
mcp_server.py only; importing this module never opens a network port or
initiates a model call.

The public G3 archive is immutable evidence, not a live model connection.
Digest checks establish local consistency, not third-party provider identity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .candidate_adapter import CandidateExecutionLimits, CandidateReferenceAdapter
from .contracts import ProposedAction, SideEffect
from .g3_verification import OwnedLedgerReferenceAdapter
from .reconstruct import create_scope
from .scope_guard import ScopeGuard

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ARCHIVE = _PROJECT_ROOT / "docs" / "evidence" / "g3-rev6-sanitized"
_MANIFEST = _ARCHIVE / "export-manifest.json"
_MAX_ARTIFACT_BYTES = 131_072
_MAX_PROBE_BYTES = 3_072
_MAX_PROBE_ACTIONS = 6
_ALLOWED_ARTIFACTS = frozenset({"G3_report.json", "candidate.v1.json"})
_FIELDS = {
    "add": frozenset({"command", "label", "amount"}),
    "list": frozenset({"command"}),
    "total": frozenset({"command"}),
    "remove": frozenset({"command", "id"}),
}
_EFFECTS = {"add": SideEffect.LOCAL_MUTATION, "remove": SideEffect.LOCAL_MUTATION,
            "list": SideEffect.READ_ONLY, "total": SideEffect.READ_ONLY}


def _read_bounded_file(path: Path, max_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise RuntimeError("Public evidence file is missing or unsafe")
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise RuntimeError("Public evidence file exceeds limit")
    return raw


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("Public evidence is malformed") from None
    if type(data) is not dict:
        raise RuntimeError("Public evidence must be an object")
    return data


def _load_artifact_bytes(name: str) -> bytes:
    if name not in _ALLOWED_ARTIFACTS:
        raise ValueError("Artifact is not on the public evidence allowlist")
    manifest = _json_object(_read_bounded_file(_MANIFEST, 10_000))
    if manifest.get("kind") != "G3_EVIDENCE_EXPORT_V1":
        raise RuntimeError("Public evidence manifest type mismatch")
    files = manifest.get("files")
    expected = files.get(name) if type(files) is dict else None
    if type(expected) is not str or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise RuntimeError("Missing trusted public artifact digest")
    raw = _read_bounded_file(_ARCHIVE / name, _MAX_ARTIFACT_BYTES)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise RuntimeError("Public evidence integrity failure")
    return raw


def _load_artifact(name: str) -> dict[str, Any]:
    return _json_object(_load_artifact_bytes(name))


def capabilities() -> dict[str, Any]:
    """Describe the only capabilities available through this MCP boundary."""
    return {
        "service": "second-source",
        "adapter": "owner-local-stdio-readonly-v1",
        "targets": [{
            "id": "owned-ledger-v1",
            "class": "owned-synthetic-cli",
            "operations": ["add", "list", "total", "remove"],
            "max_actions_per_probe": _MAX_PROBE_ACTIONS,
            "probe_mode": "live local isolated comparison, state reset each call",
        }],
        "tools": ["second_source_capabilities", "second_source_reconstruction_report",
                  "second_source_candidate_rules", "second_source_compare_ledger"],
        "model_calls": False,
        "paid_operations": False,
        "remote_targets": False,
        "private_sealed_tests_exposed": False,
        "write_operations_on_external_systems": False,
        "claim": "One historical genuine Meta candidate; live probes do not invoke Meta.",
    }


def reconstruction_report() -> dict[str, Any]:
    """Return a curated, allowlisted view of the historical genuine result."""
    report = _load_artifact("G3_report.json")
    evaluation = report.get("evaluation")
    receipt = report.get("evaluation_receipt")
    if type(evaluation) is not dict or type(receipt) is not dict:
        raise RuntimeError("Public evaluation fields are incomplete")
    origin = receipt.get("origin")
    if type(origin) is not dict:
        raise RuntimeError("Public model identity is missing")
    result = {k: evaluation[k] for k in ("passed", "failed", "indeterminate", "total", "failure_categories")}
    if any(type(result[k]) is not int for k in ("passed", "failed", "indeterminate", "total")):
        raise RuntimeError("Public evaluation counters are malformed")
    if result["passed"] + result["failed"] + result["indeterminate"] != result["total"]:
        raise RuntimeError("Public evaluation totals are inconsistent")
    return {
        "target": "owned-ledger-v1",
        "status": "historical_REAL_MODEL_partial_reconstruction",
        "model": origin.get("model"),
        "provider": origin.get("provider"),
        "response_id": origin.get("response_id"),
        "candidate_digest": origin.get("candidate_digest"),
        "suite_digest": receipt.get("suite_digest"),
        "evaluation": result,
        "accepted": receipt.get("g3_accepted") is True,
        "provenance": "redacted local broker record; provider signature not independently attested",
        "verification": "pinned-source offline replay consistent; not a new Meta call",
        "limits": ["One genuine candidate and owned CLI target",
                   "No genuine model-driven repair measured",
                   "Private sealed inputs and original receipts are not exposed"],
    }


def candidate_rules() -> dict[str, Any]:
    """Expose the already-public declarative candidate, never oracle source."""
    spec = _load_artifact("candidate.v1.json")
    report = reconstruction_report()
    if spec.get("spec_version") != "1" or spec.get("subsystem") != "cli_ledger":
        raise RuntimeError("Unsupported public candidate")
    return {
        "candidate_digest": report["candidate_digest"],
        "classification": "historical_Meta_generated_declarative_candidate",
        "source": "docs/evidence/g3-rev6-sanitized/candidate.v1.json",
        "specification": spec,
        "note": "This is a model proposal, NOT the reference rules or original source.",
    }


def _validated_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if type(actions) is not list or not 1 <= len(actions) <= _MAX_PROBE_ACTIONS:
        raise ValueError("Provide between 1 and 6 synthetic ledger actions")
    try:
        raw = json.dumps(actions, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("Probe must be plain finite JSON") from None
    if len(raw) > _MAX_PROBE_BYTES:
        raise ValueError("Probe exceeds public byte limit")
    scope = create_scope(0.0)
    guard = ScopeGuard(scope)
    for action in actions:
        if type(action) is not dict:
            raise ValueError("Each action must be a JSON object")
        command = action.get("command")
        if type(command) is not str or command not in _FIELDS:
            raise ValueError("Only owned ledger commands are allowed")
        if not action.keys() <= _FIELDS[command]:
            raise ValueError("Unexpected action fields are not permitted")
        for key in ("label", "id"):
            if key in action and action[key] is not None and (type(action[key]) is not str or len(action[key]) > 128):
                raise ValueError("Text fields must be bounded strings or null")
        if "amount" in action and action["amount"] is not None:
            value = action["amount"]
            if type(value) is not int or abs(value) > 1000:
                raise ValueError("Amounts must be bounded integers or null")
        decision = guard.validate_action(ProposedAction(
            kind="cli", target=command, requirement_id="REQ-LEDGER",
            side_effect=_EFFECTS[command],
            payload={key: value for key, value in action.items() if key != "command"},
        ))
        if not decision.allowed:
            raise ValueError("Probe is outside the approved owned-fixture scope")
    # JSON roundtrip detaches mutable or subclassed caller input.
    return json.loads(raw)


def compare_ledger(actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Run both versions on the same PUBLIC inputs in isolated local workers.

    This is an interactive *public* experiment; it does not touch the sealed
    25-case suite, modify persisted investigations, or contact an AI provider.
    """
    allowed = _validated_actions(actions)
    scope = create_scope(0.0)
    limits = CandidateExecutionLimits(max_actions=_MAX_PROBE_ACTIONS,
                                      max_input_bytes=16_384,
                                      max_output_bytes=16_384,
                                      max_records=64,
                                      wall_seconds=4.0,
                                      cpu_seconds=3.0)
    # Use the same digest-verified bytes for the trusted candidate interpreter.
    candidate_spec = _load_artifact_bytes("candidate.v1.json")
    reference = OwnedLedgerReferenceAdapter(scope, limits=limits).execute_sequence(allowed)
    candidate = CandidateReferenceAdapter(candidate_spec, scope, limits=limits).execute_sequence(allowed)
    if reference.status != "ok" or candidate.status != "ok":
        return {
            "status": "inconclusive",
            "reference_status": reference.status,
            "candidate_status": candidate.status,
            "not_a_score": True,
        }
    if len(reference.observations) != len(allowed) or len(candidate.observations) != len(allowed):
        return {"status": "inconclusive", "reason": "Incomplete local worker observations",
                "not_a_score": True}
    comparisons = []
    for n, (ref, cand) in enumerate(zip(reference.observations, candidate.observations)):
        comparisons.append({
            "step": n + 1, "input": allowed[n],
            "reference_output": ref.output, "candidate_output": cand.output,
            "equal": ref.output == cand.output and ref.status == cand.status,
        })
    return {
        "status": "completed_public_probe",
        "provenance": "trusted local owned reference vs replay of historical Meta candidate",
        "model_called": False, "sealed_cases_used": False, "not_a_score": True,
        "matches": sum(item["equal"] for item in comparisons),
        "steps": comparisons,
    }
