"""Evaluator-owned sealed G3 suite, controls and model-request isolation gate.

Suite bytes live outside Git checkouts and are pinned before scoring. This
module is deliberately absent from both staged worker bundles. Public tests
use synthetic suites; private suite values/IDs are never printed or sent to
the model. No provider credential handling or inference is implemented here.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import secrets
import stat
import sys
import time
from typing import Any, Mapping

from .candidate_adapter import (
    CandidateExecutionLimits, CandidateReferenceAdapter,
    _checked_json, _encode, _run_worker,
)
from .contracts import ProposedAction, ScopeContract, SequenceResult, SideEffect, TargetKind
from .scope_guard import ScopeGuard
from .verifier import DifferentialVerifier, EvaluationReport, ReferenceProtocol, SealedCase

MAX_SUITE_BYTES = 1_000_000
SUITE_VERSION = "1"
_EFFECTS = {"add": SideEffect.LOCAL_MUTATION, "remove": SideEffect.LOCAL_MUTATION,
            "list": SideEffect.READ_ONLY, "total": SideEffect.READ_ONLY}


class EvaluationBlocked(RuntimeError):
    """Invalid scope, suite, provenance or boundary; no accepted score."""


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _scope_digest(contract: ScopeContract) -> str:
    # Sort set-valued public contract fields, independent of Python hash seed.
    doc = contract.model_dump(mode="json")
    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in sorted(value.items())}
        if isinstance(value, list):
            return sorted((normalize(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
        return value
    return _digest(_encode(normalize(doc)))


def _safe_external_path(path: str | Path) -> Path:
    candidate = Path(os.path.abspath(path))
    # Check before resolve: symlinks/junctions must not disappear during normalization.
    for part in (candidate, *candidate.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise EvaluationBlocked("Evaluator storage cannot traverse links or junctions")
        if (part / ".git").exists():
            raise EvaluationBlocked("Sealed material must remain outside Git checkouts")
    return candidate


@dataclass(frozen=True)
class SealedSuite:
    """Immutable private bytes; cases are detached on every access."""
    _raw: bytes
    digest: str
    scope_digest: str

    def cases(self) -> list[SealedCase]:
        doc = _checked_json(self._raw, MAX_SUITE_BYTES)
        return [SealedCase.model_validate(case) for case in doc["cases"]]


def _admit_suite(raw: bytes, expected_digest: str, contract: ScopeContract) -> SealedSuite:
    if _digest(raw) != expected_digest:
        raise EvaluationBlocked("Sealed suite digest mismatch")
    try:
        doc = _checked_json(raw, MAX_SUITE_BYTES)
        if (type(doc) is not dict or set(doc) != {"suite_version", "scope_digest", "cases"}
                or doc["suite_version"] != SUITE_VERSION or doc["scope_digest"] != _scope_digest(contract)
                or type(doc["cases"]) is not list or not doc["cases"]):
            raise ValueError
        cases = [SealedCase.model_validate(case) for case in doc["cases"]]
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError
    except Exception:
        raise EvaluationBlocked("Malformed or wrong-scope sealed suite") from None
    return SealedSuite(bytes(raw), expected_digest, doc["scope_digest"])


def load_sealed_suite(path: str | Path, expected_digest: str, contract: ScopeContract) -> SealedSuite:
    external = _safe_external_path(path)
    try:
        if not external.is_file() or external.stat().st_size > MAX_SUITE_BYTES:
            raise ValueError
        # Bounded read; reject replacement by symlink/reparse point after the first check.
        with external.open("rb") as stream:
            info = os.fstat(stream.fileno())
            if info.st_nlink != 1 or not stat.S_ISREG(info.st_mode):
                raise ValueError
            raw = stream.read(MAX_SUITE_BYTES + 1)
        _safe_external_path(external)
    except (OSError, ValueError):
        raise EvaluationBlocked("Sealed suite storage unavailable or unsafe") from None
    return _admit_suite(raw, expected_digest, contract)


def seal_owned_ledger_suite(directory: str | Path, contract: ScopeContract) -> tuple[Path, str]:
    """Create once, outside the repo. No gold values/IDs are returned in reports."""
    root = _safe_external_path(directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Synthetic values are fixed in these bytes before any candidate is evaluated.
    rng = random.Random(secrets.randbits(256))
    token = lambda: "s" + format(rng.getrandbits(48), "012x")
    cases = []
    def case(category, *actions):
        cases.append({"case_id": secrets.token_hex(16), "category": category, "actions": list(actions)})
    def add(label=None, amount=None):
        return {"command": "add", "label": token() if label is None else label,
                "amount": rng.randint(2, 98) if amount is None else amount}
    listing, total = {"command": "list"}, {"command": "total"}
    case("empty", listing, total)
    case("create", add(), listing, total)
    case("amount_boundary", add(amount=1), add(amount=100), total)
    for amount in (0, -1, 101, "4", 2.5, True, None):
        action = add()
        action["amount"] = amount
        case("invalid_amount", action, total)
    for label in ("", "  ", "x" * 25, 3, None):
        action = add()
        action["label"] = label
        case("invalid_label", action, listing)
    case("missing_fields", {"command": "add"}, {"command": "add", "label": token()}, total)
    name = token()
    case("duplicate", add(name), add(name), listing, total)
    name = token()
    case("casefold_whitespace", add(" " + name + " "), add(name.upper()), listing)
    case("unicode", add("Straße"), add("STRASSE"), listing)
    case("remove_present", add(), {"command": "remove", "id": "1"}, listing, total)
    case("remove_missing", {"command": "remove", "id": token()}, total)
    case("remove_type", {"command": "remove", "id": 1}, {"command": "remove"}, listing)
    case("ordering", add(), add(), {"command": "remove", "id": "1"}, add(), listing, total)
    case("reset", add(), listing)
    case("reset", total, listing, add(), listing)
    cases_raw = _encode({"suite_version": SUITE_VERSION, "scope_digest": _scope_digest(contract), "cases": cases})
    digest = _digest(cases_raw)
    _admit_suite(cases_raw, digest, contract)
    path = root / "suite.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(cases_raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise EvaluationBlocked("Sealed suite already exists; never overwrite after scoring") from None
    return path, digest


def _authorize_cases(cases, contract, limits):
    if contract.target.kind != TargetKind.CLI or contract.mode.value == "analysis_only":
        raise EvaluationBlocked("Evaluation requires authorized CLI implementation scope")
    if "cli_ledger" not in contract.implementation.allowed_subsystems:
        raise EvaluationBlocked("Ledger implementation is outside scope")
    if len(cases) > contract.budgets.max_reference_experiments:
        raise EvaluationBlocked("Suite exceeds reference experiment budget")
    requirement = sorted(contract.implementation.requirements)[0]
    guard = ScopeGuard(contract)
    for case in cases:
        if len(case.actions) > limits.max_actions or len(_encode(list(case.actions))) > limits.max_input_bytes:
            raise EvaluationBlocked("Suite exceeds trusted sequence limits")
        for action in case.actions:
            command = action.get("command")
            if command not in _EFFECTS:
                raise EvaluationBlocked("Sealed action is outside the trusted command registry")
            proposed = ProposedAction(kind="cli", target=command, requirement_id=requirement,
                                      side_effect=_EFFECTS[command], payload={k: v for k, v in action.items() if k != "command"})
            if not guard.validate_action(proposed).allowed:
                raise EvaluationBlocked("Sealed action denied by scope policy")


class OwnedLedgerReferenceAdapter:
    """Only the privileged reference worker receives the fixed owned fixture source."""
    def __init__(self, contract: ScopeContract, *, limits: CandidateExecutionLimits | None = None):
        if (contract.target.kind != TargetKind.CLI or contract.target.reference_command_id
                not in {"owned-ledger-v1", "owned-ledger-cli"}):
            raise EvaluationBlocked("Reference command ID is not in the trusted registry")
        self.limits = limits or CandidateExecutionLimits()
        reference = Path(__file__).resolve().parents[2] / "fixtures/owned_ledger/reference.py"
        self.reference_digest = _digest(reference.read_bytes())

    def execute_sequence(self, actions: list[dict], *, sequence_id: str | None = None) -> SequenceResult:
        seq = sequence_id or secrets.token_hex(16)
        try:
            if type(actions) is not list or len(actions) > self.limits.max_actions:
                raise ValueError
            detached = _checked_json(_encode(actions), self.limits.max_input_bytes)
            if any(type(action) is not dict for action in detached):
                raise ValueError
        except Exception:
            return SequenceResult(sequence_id=seq, observations=(), status="protocol_error", stderr="reference_input_rejected")
        response = _run_worker("reference", {"actions": detached, "sequence_id": seq,
                              "reference_digest": self.reference_digest}, self.limits)
        if "result" in response:
            try:
                return SequenceResult.model_validate(response["result"])
            except Exception:
                pass
        status = "timeout" if response.get("failure") == "timeout" else "protocol_error"
        return SequenceResult(sequence_id=seq, observations=(), status=status, stderr="reference_worker_failed")


def evaluate_sealed_suite(
    suite: SealedSuite, contract: ScopeContract, reference: ReferenceProtocol,
    candidate: CandidateReferenceAdapter,
) -> EvaluationReport:
    # Recheck immutable bytes/digests rather than trusting a constructed dataclass.
    admitted = _admit_suite(suite._raw, suite.digest, contract)
    cases = admitted.cases()
    _authorize_cases(cases, contract, candidate.limits)
    # Establish the backend BEFORE reference execution; never turn missing isolation into a score.
    started = time.monotonic()
    candidate.check_containment()

    class BudgetedReference:
        def execute_sequence(self, actions, *, sequence_id=None):
            if time.monotonic() - started >= contract.budgets.max_wall_seconds:
                return SequenceResult(sequence_id=sequence_id, observations=(), status="timeout")
            return reference.execute_sequence(actions, sequence_id=sequence_id)

    return DifferentialVerifier(BudgetedReference(), candidate).verify(cases)


def prepare_generation_request(
    context: dict[str, Any], *, approved_evidence: Mapping[str, dict[str, Any]],
    forbidden_markers: tuple[str, ...] = (), limits: CandidateExecutionLimits | None = None,
) -> dict[str, Any]:
    """Prepare exact ModelRequest in an isolated, nonbillable worker for the broker.

    The registry must come from approved redacted OBSERVATION evidence, never
    evaluator results. Matching digest syntax alone is not provenance.
    Returned dict is a request for the provider broker, not an evaluator report.
    """
    limits = limits or CandidateExecutionLimits()
    try:
        detached = _checked_json(_encode(context), limits.max_input_bytes)
        views = detached["evidence"]
        for view in views:
            approved = approved_evidence[view["digest"]]
            if json.dumps(view["observation"], sort_keys=True, allow_nan=False) != json.dumps(approved, sort_keys=True, allow_nan=False):
                raise ValueError
        if not views:
            raise ValueError
    except Exception:
        raise EvaluationBlocked("Generation evidence is not approved observation evidence") from None
    response = _run_worker("generation", {"context": detached}, limits)
    request = response.get("request")
    if type(request) is not dict or "tools" in request:
        raise EvaluationBlocked("Isolated generation context rejected")
    rendered = _encode(request)
    if any(marker and marker.encode("utf-8") in rendered for marker in forbidden_markers):
        raise EvaluationBlocked("Protected material detected at final request boundary")
    return request


def evidence_manifest(suite: SealedSuite, candidate: CandidateReferenceAdapter, report: EvaluationReport,
                      *, reference: OwnedLedgerReferenceAdapter | None = None) -> dict:
    """Owner-safe metadata; case details and paths are deliberately absent."""
    package = Path(__file__).resolve().parent
    import pydantic
    return {
        "kind": "INDEPENDENT_EVALUATION_NOT_MODEL_PROVENANCE",
        "candidate_digest": candidate.spec_digest, "suite_digest": suite.digest,
        "scope_digest": suite.scope_digest,
        "comparator_digest": _digest((package / "verifier.py").read_bytes()),
        "interpreter_digest": _digest((package / "candidate_runtime.py").read_bytes()),
        "adapter_digest": _digest((package / "candidate_adapter.py").read_bytes()),
        "reference_digest": reference.reference_digest if reference is not None else None,
        "limits": candidate.limits.__dict__.copy(),
        "python": sys.version.split()[0], "platform": sys.platform, "pydantic": pydantic.__version__,
        "evaluation": report.model_feedback(),
        "isolation": "TRUSTED_DATA_ONLY_WORKER_WITH_OS_RESOURCE_LIMITS_AND_PYTHON_IO_GUARD",
        "arbitrary_code_sandbox": False,
    }


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Nonbillable G3 evaluator; no model calls or credential access")
    parser.add_argument("--scope", required=True)
    parser.add_argument("--seal-directory")
    parser.add_argument("--suite")
    parser.add_argument("--suite-digest")
    parser.add_argument("--candidate")
    args = parser.parse_args(argv)
    try:
        contract = ScopeContract.model_validate_json(Path(args.scope).read_bytes())
        if args.seal_directory:
            _, digest = seal_owned_ledger_suite(args.seal_directory, contract)
            print(json.dumps({"kind": "SEALED_SUITE_CREATED", "suite_digest": digest}))
            return 0
        if not all((args.suite, args.suite_digest, args.candidate)):
            raise EvaluationBlocked("Candidate, suite and pinned suite digest are required")
        suite = load_sealed_suite(args.suite, args.suite_digest, contract)
        candidate = CandidateReferenceAdapter(Path(args.candidate).read_bytes(), contract)
        reference = OwnedLedgerReferenceAdapter(contract, limits=candidate.limits)
        report = evaluate_sealed_suite(suite, contract, reference, candidate)
        print(json.dumps(evidence_manifest(suite, candidate, report, reference=reference), sort_keys=True))
        return 0 if report.passed == report.total else 1
    except Exception:
        # Errors may contain private paths/inputs; public CLI emits a fixed category.
        print(json.dumps({"kind": "EVALUATION_BLOCKED"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
