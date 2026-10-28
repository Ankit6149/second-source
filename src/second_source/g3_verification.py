"""Evaluator-owned sealed G3 suite, controls and model-request isolation gate.

Suite bytes live outside Git checkouts and are pinned before scoring. This
module is deliberately absent from both staged worker bundles. Public tests
use synthetic suites; private suite values/IDs are never printed or sent to
the model. The opt-in broker accepts a configured provider; it never reads keys.
All CLI paths remain nonbillable controls. Real calls need separate approval.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import random
import secrets
import stat
import sys
import threading
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
# Reviewed Git source with LF line endings, independent of checkout conversion.
# The raw worker bytes are separately pinned for the lifetime of each run.
OWNED_REFERENCE_DIGEST = "sha256:539cf592cee4c22c9abfece562e258aecb2d887a6a48368fce3ebc081bdde832"


class EvaluationBlocked(RuntimeError):
    """Invalid scope, suite, provenance or boundary; no accepted score."""


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _reference_identity(raw: bytes) -> str:
    return _digest(raw.replace(b"\r\n", b"\n"))


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
    """Generic TRUSTED_CONTROL interface; never establishes real-model provenance.

    Release scoring must use PinnedEvaluatorRun.evaluate, which owns the original
    reference, frozen code/suite and broker-issued immutable candidate receipt.
    """
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


@dataclass(frozen=True)
class BrokerArtifact:
    """Opaque immutable local attestation; not a provider signature or model input."""
    payload: bytes
    signature: str


def _code_pins() -> dict[str, str]:
    package = Path(__file__).resolve().parent
    names = ("verifier", "g3_verification", "candidate_adapter", "candidate_runtime",
             "candidate_spec", "candidate_generation", "model_gateway", "contracts",
             "scope_guard", "schema_validate", "evidence", "hypotheses", "budgets",
             "__init__", "runner", "reference")
    result = {}
    for name in names:
        path = package / (name + ".py")
        if path.is_symlink() or path.resolve().parent != package:
            raise EvaluationBlocked("Unsafe trusted code path")
        result["reference_adapter" if name == "reference" else name] = _digest(path.read_bytes())
    reference = package.parents[1] / "fixtures/owned_ledger/reference.py"
    public = package.parents[1] / "fixtures/owned_ledger/public_contract.json"
    for name, path in (("reference", reference), ("public_manifest", public)):
        if path.is_symlink() or path.resolve() != path:
            raise EvaluationBlocked("Unsafe registered fixture path")
        raw = path.read_bytes()
        result[name] = _digest(raw)
        if name == "reference":
            result["reference_identity"] = _reference_identity(raw)
    if result["reference_identity"] != OWNED_REFERENCE_DIGEST:
        raise EvaluationBlocked("Original reference is not the reviewed pinned fixture")
    return result


class PinnedEvaluatorRun:
    """Trusted orchestrator authority, created BEFORE generation, outside workers.

    The orchestrator selects approved ledger digests and a reconciled HypothesisStore.
    These are local approval roots, not proof of historical G2 provider provenance.
    Neither a caller mapping, a claimed receipt, nor a ReferenceProtocol is accepted
    as a release artifact. Same-process malicious Python is outside the threat model.
    Local HMAC authority is deliberately not exported; restart requires a fresh run.
    """

    def __init__(self, suite: SealedSuite, contract: ScopeContract, *, ledger,
                 observation_digests: tuple[str, ...], hypotheses,
                 limits: CandidateExecutionLimits | None = None,
                 operator_approved_context_digest: str | None = None):
        from .candidate_generation import build_generation_context, expected_scope_projection
        from .evidence import EvidenceLedger, redact
        from .hypotheses import HypothesisStore, validate_batch
        if type(ledger) is not EvidenceLedger or type(hypotheses) is not HypothesisStore:
            raise EvaluationBlocked("Trusted ledger and hypothesis store are required")
        self._contract_raw = contract.model_dump_json().encode("utf-8")
        self._suite = _admit_suite(suite._raw, suite.digest, contract)
        self._limits = limits or CandidateExecutionLimits()
        _authorize_cases(self._suite.cases(), contract, self._limits)
        OwnedLedgerReferenceAdapter(contract, limits=self._limits)
        self._pins = _code_pins()
        try:
            if (not observation_digests or len(set(observation_digests)) != len(observation_digests)
                    or len(observation_digests) > contract.budgets.max_reference_experiments):
                raise ValueError
            # inspect() authenticates content addressing before model_view() redacts.
            views = [{"digest": digest, "observation": ledger.model_view(digest)}
                     for digest in observation_digests]
            for view in views:
                obs = view["observation"]
                if obs["status"] not in {"ok", "target_error"} or obs["exit_code"] != 0:
                    raise ValueError
                action = obs["input_action"]
                command = action.get("command")
                if command not in _EFFECTS:
                    raise ValueError
                proposal = ProposedAction(kind="cli", target=command,
                    requirement_id=sorted(contract.implementation.requirements)[0],
                    side_effect=_EFFECTS[command], payload={k: v for k, v in action.items() if k != "command"})
                if not ScopeGuard(contract).validate_action(proposal).allowed:
                    raise ValueError
            batch = validate_batch({"hypotheses": [h.model_dump(mode="json") for h in hypotheses.all()]},
                                   frozenset(observation_digests))
            public = json.loads((Path(__file__).resolve().parents[2]
                                 / "fixtures/owned_ledger/public_contract.json").read_bytes())
            projection = expected_scope_projection(contract)
            context = build_generation_context(scope_goal=projection["goal"],
                requirement_ids=projection["requirement_ids"], allowed_commands=projection["allowed_commands"],
                excluded_subsystems=projection["excluded_subsystems"], public_command_manifest=public,
                redacted_views=views, hypotheses=redact([h.model_dump(mode="json") for h in batch.hypotheses]))
        except Exception:
            raise EvaluationBlocked("Approved generation registry admission failed") from None
        self._context_raw = _encode(context)
        self._approved_context_digest = _digest(self._context_raw)
        if (operator_approved_context_digest is not None
                and operator_approved_context_digest != self._approved_context_digest):
            raise EvaluationBlocked("Context does not match operator's approved G2 input pin")
        # This must come from the trusted operator configuration, never a model
        # request or an untrusted caller-supplied registry. No pin => controls only.
        self._operator_input_pin = operator_approved_context_digest
        self._plan_raw = _encode({"scope_digest": _scope_digest(contract), "suite_digest": suite.digest,
            "reference_id": contract.target.reference_command_id, "code": self._pins,
            "approved_context_digest": self._approved_context_digest,
            "operator_input_pin": operator_approved_context_digest,
            "observation_registry_digest": _digest(_encode(context["evidence"])),
            "hypothesis_registry_digest": _digest(_encode(context["hypotheses"])), "limits": self._limits.__dict__,
            "run_id": secrets.token_hex(16)})
        self._key = secrets.token_bytes(32)
        self._used_requests: set[str] = set()
        self._evaluations: dict[str, bytes] = {}
        self._budget = None
        self._budget_limits: bytes | None = None
        self._generation_attempts = 0
        self._real_attempt_failed = False
        self._generation_lock = threading.Lock()

    @property
    def plan_digest(self) -> str:
        return _digest(self._plan_raw)

    @property
    def approved_context_digest(self) -> str:
        """For trusted operator review/pinning; not automatic G2 authentication."""
        return self._approved_context_digest

    def _check_frozen(self):
        if _code_pins() != self._pins:
            raise EvaluationBlocked("Trusted code changed after run freeze")
        contract = ScopeContract.model_validate_json(self._contract_raw)
        _admit_suite(self._suite._raw, self._suite.digest, contract)
        return contract

    def _sign(self, value: dict) -> BrokerArtifact:
        raw = _encode({**value, "plan_digest": self.plan_digest})
        return BrokerArtifact(raw, hmac.new(self._key, raw, hashlib.sha256).hexdigest())

    def _verify(self, artifact: BrokerArtifact, kind: str) -> dict:
        if (type(artifact) is not BrokerArtifact or type(artifact.payload) is not bytes
                or type(artifact.signature) is not str
                or len(artifact.payload) > MAX_SUITE_BYTES or len(artifact.signature) != 64
                or any(c not in "0123456789abcdef" for c in artifact.signature)
                or not hmac.compare_digest(hmac.new(self._key, artifact.payload, hashlib.sha256).hexdigest(),
                                           artifact.signature)):
            raise EvaluationBlocked("Unattested or changed broker artifact")
        value = _checked_json(artifact.payload, MAX_SUITE_BYTES)
        if value.get("kind") != kind or value.get("plan_digest") != self.plan_digest:
            raise EvaluationBlocked("Wrong run or broker artifact kind")
        return value

    def prepare(self, context: dict | None = None) -> BrokerArtifact:
        """Inspect final wire bytes in a credential-free staged worker; no inference."""
        from .candidate_generation import pin_public_manifest, validate_context_against_pins
        contract = self._check_frozen()
        approved = json.loads(self._context_raw)
        if context is not None and _encode(context) != self._context_raw:
            raise EvaluationBlocked("Context differs from frozen observation/hypothesis approval")
        registry = {view["digest"]: view["observation"] for view in approved["evidence"]}
        try:
            validate_context_against_pins(approved, contract=contract,
                public_manifest_digest=pin_public_manifest(approved["public_commands"]), approved_evidence=registry)
        except Exception:
            raise EvaluationBlocked("Pinned generation context rejected") from None
        wire = prepare_generation_request(approved, approved_evidence=registry, limits=self._limits)
        self._check_frozen()
        return self._sign({"kind": "INSPECTED_REQUEST", "nonce": secrets.token_hex(16), "wire": wire})

    def generate(self, ticket: BrokerArtifact, provider, budget, *, spending_approved: bool = False) -> BrokerArtifact:
        """Single-use inspected broker; real transport needs owner spend/input pins."""
        # Serialize consume+attempt so concurrent replay cannot race the nonce gate.
        with self._generation_lock:
            return self._generate(ticket, provider, budget, spending_approved=spending_approved)

    def _generate(self, ticket: BrokerArtifact, provider, budget, *, spending_approved: bool) -> BrokerArtifact:
        """Single-use broker. Real transport additionally requires explicit run approval.

        Never pass the inspected wire back into ModelGateway: that would inject the
        schema twice. Rebuild the frozen logical request and compare at complete().
        No credentials are read here; the owner supplies a configured provider.
        """
        from .candidate_generation import build_synthesize_request
        from .model_gateway import MetaProvider, MockProvider, ModelGateway, GatewayError
        from .budgets import RunBudget
        contract = self._check_frozen()
        request = self._verify(ticket, "INSPECTED_REQUEST")
        nonce = request["nonce"]
        if nonce in self._used_requests:
            raise EvaluationBlocked("Generation request replay rejected")
        real = type(provider) is MetaProvider
        if type(provider) not in {MetaProvider, MockProvider}:
            raise EvaluationBlocked("Unregistered provider type")
        if type(budget) is not RunBudget:
            raise EvaluationBlocked("Trusted run budget is required")
        if real and (spending_approved is not True or provider._test_mode
                     or budget.limits.max_estimated_model_spend_usd <= 0):
            raise EvaluationBlocked("Real generation requires separate owner spending approval")
        if real and self._operator_input_pin is None:
            raise EvaluationBlocked("Real generation requires an independently approved G2 context pin")
        if real and self._real_attempt_failed:
            raise EvaluationBlocked("Failed real attempt requires fresh independent preflight")
        attempt_limit = min(contract.budgets.max_model_calls, 1 + min(2, contract.budgets.max_repair_rounds))
        if self._generation_attempts >= attempt_limit:
            raise EvaluationBlocked("Bounded generation attempt limit reached")
        if (budget.limits.max_estimated_model_spend_usd > contract.budgets.max_estimated_model_spend_usd
                or budget.limits.max_model_calls > contract.budgets.max_model_calls):
            raise EvaluationBlocked("Broker budget exceeds frozen scope")
        budget_limits = budget.limits.model_dump_json().encode("utf-8")
        if self._budget is not None and (budget is not self._budget or budget_limits != self._budget_limits):
            raise EvaluationBlocked("Run budget cannot be replaced or widened")
        self._budget, self._budget_limits = budget, budget_limits
        expected = _encode(request["wire"])
        authority = self
        calls = []

        class CheckedMock(MockProvider):
            def complete(self, wire):
                authority._check_frozen()
                if calls or _encode(wire.model_dump(mode="json")) != expected:
                    raise GatewayError("Inspected request changed or replayed")
                calls.append(True)
                try:
                    return provider.complete(wire)
                except GatewayError:
                    raise
                except Exception:
                    raise GatewayError("Provider transport failed") from None

        class CheckedMeta(MetaProvider):
            complete = CheckedMock.complete
            @property
            def rates(self):
                return provider.rates
            @property
            def model(self):
                return provider.model

        checked = CheckedMeta.__new__(CheckedMeta) if real else CheckedMock()
        gateway = ModelGateway(checked, budget)
        # Consume BEFORE attempting transport, including schema/transport failures.
        self._used_requests.add(nonce)
        self._generation_attempts += 1
        try:
            response = gateway.generate(build_synthesize_request(json.loads(self._context_raw)))
            self._check_frozen()
            if (len(calls) != 1 or response.real is not real or response.outcome != "ok"
                    or response.provider != provider.provider_name or response.model != provider.model
                    or not response.response_id or type(response.parsed) is not dict):
                raise ValueError
            spec_raw = _encode(response.parsed)
            candidate = CandidateReferenceAdapter(spec_raw, contract, limits=self._limits)
            receipt = {"origin": "real" if real else "mock", "real": real,
                "provider": response.provider, "model": response.model, "response_id": response.response_id,
                "prompt_version": response.prompt_version, "request_digest": _digest(expected),
                "candidate_digest": candidate.spec_digest, "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens, "estimated_cost_usd": response.estimated_cost_usd,
                "uncertain_cost_usd": response.uncertain_cost_usd, "attempt": self._generation_attempts}
            return self._sign({"kind": "CANDIDATE_ORIGIN", "spec": spec_raw.decode("utf-8"), "receipt": receipt})
        except Exception:
            # Details may contain model output, private paths or evidence. Budget
            # retains failed/uncertain accounting even when no artifact is issued.
            self._real_attempt_failed = self._real_attempt_failed or real
            raise EvaluationBlocked("Broker attempt failed; inspect trusted budget accounting") from None

    def evaluate(self, artifact: BrokerArtifact, *, claim: str = "TRUSTED_CONTROL") -> dict:
        """No reference injection. Real accuracy needs a real broker-issued origin."""
        contract = self._check_frozen()
        value = self._verify(artifact, "CANDIDATE_ORIGIN")
        receipt = value["receipt"]
        if claim not in {"TRUSTED_CONTROL", "REAL_MODEL"}:
            raise EvaluationBlocked("Unknown evaluation claim")
        if claim == "REAL_MODEL" and (receipt["origin"] != "real" or receipt["real"] is not True):
            raise EvaluationBlocked("Mock/control candidate cannot claim real-model accuracy")
        candidate = CandidateReferenceAdapter(value["spec"].encode("utf-8"), contract, limits=self._limits)
        if candidate.spec_digest != receipt["candidate_digest"]:
            raise EvaluationBlocked("Candidate origin digest mismatch")
        reference = OwnedLedgerReferenceAdapter(contract, limits=self._limits)
        if reference.reference_digest != self._pins["reference"]:
            raise EvaluationBlocked("Original reference pin mismatch")
        report = evaluate_sealed_suite(self._suite, contract, reference, candidate)
        self._check_frozen()
        result = evidence_manifest(self._suite, candidate, report, reference=reference)
        plan = json.loads(self._plan_raw)
        result.update(kind="PINNED_" + claim + "_EVALUATION", plan_digest=self.plan_digest,
                      origin=receipt, artifact_digest=_digest(artifact.payload), code_pins=dict(self._pins),
                      reference_identity=contract.target.reference_command_id,
                      reference_source_digest=self._pins["reference_identity"],
                      origin_receipt_digest=_digest(_encode(receipt)),
                      approved_context_digest=self._approved_context_digest,
                      observation_registry_digest=plan["observation_registry_digest"],
                      hypothesis_registry_digest=plan["hypothesis_registry_digest"],
                      g3_accepted=False, operator_input_pin=self._operator_input_pin,
                      registry_authority="LOCAL_LEDGER_AND_HYPOTHESIS_SNAPSHOT_REQUIRING_OPERATOR_G2_APPROVAL")
        self._evaluations[_digest(artifact.payload)] = _encode(report.model_feedback())
        return result

    def repair_feedback(self, artifact: BrokerArtifact) -> dict:
        """Only previously computed aggregate feedback, never a caller report/map."""
        self._check_frozen()
        self._verify(artifact, "CANDIDATE_ORIGIN")
        raw = self._evaluations.get(_digest(artifact.payload))
        if raw is None:
            raise EvaluationBlocked("Candidate has no independent evaluation")
        return json.loads(raw)


def evidence_manifest(suite: SealedSuite, candidate: CandidateReferenceAdapter, report: EvaluationReport,
                      *, reference: OwnedLedgerReferenceAdapter | None = None) -> dict:
    """Owner-safe metadata; case details and paths are deliberately absent."""
    package = Path(__file__).resolve().parent
    import pydantic
    environment = {"python": sys.version.split()[0], "platform": sys.platform, "pydantic": pydantic.__version__}
    return {
        "kind": "TRUSTED_CONTROL_EVALUATION_NOT_MODEL_PROVENANCE",
        "candidate_digest": candidate.spec_digest, "suite_digest": suite.digest,
        "scope_digest": suite.scope_digest,
        "comparator_digest": _digest((package / "verifier.py").read_bytes()),
        "interpreter_digest": _digest((package / "candidate_runtime.py").read_bytes()),
        "adapter_digest": _digest((package / "candidate_adapter.py").read_bytes()),
        "reference_digest": reference.reference_digest if reference is not None else None,
        "limits": candidate.limits.__dict__.copy(),
        **environment, "environment_digest": _digest(_encode(environment)),
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
