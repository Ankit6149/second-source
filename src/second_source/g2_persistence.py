"""Private create-once G2 discovery records; offline inspection never dispatches.

The journal preserves original response text and validated batches separately
from reconciled statuses. Hashes establish local integrity, not a provider
signature. An externally retained receipt hash is required to detect wholesale
replacement/truncation of a local archive. No automatic execution resume exists.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from .evidence import EvidenceLedger, publish_once
from .contracts import ScopeContract
from .hypotheses import Hypothesis, HypothesisStore, validate_batch
from .model_gateway import CallReceipt
from .planner import HYPOTHESIZE_JSON_SCHEMA, Prediction, PROPOSE_JSON_SCHEMA, reconcile_predictions
from .schema_validate import validate_json_schema

JOURNAL_VERSION = 2


class PersistenceError(ValueError):
    """Incomplete or inconsistent discovery provenance; never approved input."""


def canonical(doc: Any) -> bytes:
    def normalize(value):
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items()}
        if isinstance(value, (set, frozenset)):
            return sorted(normalize(v) for v in value)
        if isinstance(value, (list, tuple)):
            return [normalize(v) for v in value]
        return value
    return json.dumps(normalize(doc), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def scope_digest_of(contract) -> str:
    """Stable local G2 scope identity, distinct from the G3 evaluator scope."""
    return "sha256:" + digest(canonical(contract.model_dump(mode="python")))


class DiscoveryJournal:
    """One exclusive writer attached to the existing gateway and discovery loop."""

    def __init__(self, run_dir: Path, manifest: dict[str, Any], *,
                 progress: Callable[[str, str], None] | None = None):
        self.root = run_dir / "discovery"
        self.root.mkdir(mode=0o700, exist_ok=False)
        self.run_id = run_dir.name
        self.seq = 0
        self.head = ""
        self.closed = False
        self._progress = progress
        self.append("created", manifest)

    def append(self, kind: str, payload: dict[str, Any]) -> None:
        if self.closed:
            raise PersistenceError("Discovery journal is already closed")
        event = {"version": JOURNAL_VERSION, "run_id": self.run_id, "seq": self.seq + 1,
                 "previous_sha256": self.head, "kind": kind, "payload": payload}
        raw = canonical(event)
        publish_once(self.root / f"{self.seq + 1:06d}.json", raw)
        self.seq += 1
        self.head = digest(raw)
        if self._progress is not None:
            self._progress(kind, self.run_id)

    def finish(self, *, state: str, report: dict[str, Any], hypotheses: list[dict],
               receipts=()) -> Path:
        if state not in ("completed", "stopped", "interrupted", "failed"):
            raise PersistenceError("Unknown terminal state")
        self.append("terminal", {"state": state, "report": report,
                                 "reconciled_hypotheses": hypotheses,
                                 "model_receipts": [r.model_dump(mode="json") for r in receipts]})
        self.closed = True
        receipt = {"version": JOURNAL_VERSION, "run_id": self.run_id,
                   "events": self.seq, "head_sha256": self.head, "state": state}
        return publish_once(self.root.parent / "G2_receipt.json", canonical(receipt))

    def observation(self, receipt: dict[str, str]) -> None:
        self.append("observation", receipt)

    def hypothesis_batch(self, batch, known_ids, receipt_seq: int) -> None:
        doc = batch.model_dump(mode="json")
        for hyp in doc["hypotheses"]:
            hyp["evidence_ids"] = sorted(hyp["evidence_ids"])
        self.append("hypothesis_batch", {"batch": doc, "receipt_seq": receipt_seq,
                                         "known_evidence_ids": sorted(known_ids)})

    def round(self, record) -> None:
        self.append("round", asdict(record))


def inspect_run(run_dir: Path, expected_receipt_sha256: str | None = None) -> dict[str, Any]:
    try:
        return _inspect_run(run_dir, expected_receipt_sha256)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError) as exc:
        if isinstance(exc, PersistenceError):
            raise
        raise PersistenceError("Malformed discovery provenance") from exc


def _inspect_run(run_dir: Path, expected_receipt_sha256: str | None = None) -> dict[str, Any]:
    """Read/revalidate an archive without credentials, model calls or retry.

    Missing terminal/receipt is interrupted, not successful recovery. A pending
    dispatch is conservatively charged up to its recorded reservation; no
    inference is retried and no guessed hypothesis can be exported.
    """
    run_dir = Path(run_dir)
    root = run_dir / "discovery"
    if run_dir.is_symlink() or root.is_symlink() or not root.is_dir():
        raise PersistenceError("Missing or unsafe discovery archive")
    files = sorted(root.glob("*.json"))
    if not files or len(files) > 1000:
        raise PersistenceError("Missing or excessive discovery events")
    events = []
    head = ""
    for seq, path in enumerate(files, 1):
        if path.name != f"{seq:06d}.json" or path.is_symlink() or path.stat().st_size > 4_000_000:
            raise PersistenceError("Unsafe or noncontiguous discovery events")
        raw = path.read_bytes()
        try:
            doc = json.loads(raw)
            if (set(doc) != {"version", "run_id", "seq", "previous_sha256", "kind", "payload"}
                    or doc["version"] != JOURNAL_VERSION or doc["run_id"] != run_dir.name
                    or doc["seq"] != seq or doc["previous_sha256"] != head
                    or canonical(doc) != raw):
                raise PersistenceError("Discovery event identity/hash-chain mismatch")
        except (TypeError, ValueError) as exc:
            raise PersistenceError("Invalid discovery event") from exc
        head = digest(raw)
        events.append(doc)
    if events[0]["kind"] != "created":
        raise PersistenceError("Missing discovery manifest")
    manifest = events[0]["payload"]
    contract = ScopeContract.model_validate(manifest["scope"])
    if manifest["scope_digest"] != scope_digest_of(contract):
        raise PersistenceError("Scope digest differs from archived contract")
    origin = manifest.get("origin")
    if origin not in ("mock", "real"):
        raise PersistenceError("Unknown discovery origin")
    if (manifest["provider"] != ("meta-direct" if origin == "real" else "mock")
            or not isinstance(manifest["model"], str) or not manifest["model"]):
        raise PersistenceError("Invalid discovery provider identity")
    ledger_root = run_dir / "evidence"
    if ledger_root.is_symlink() or not ledger_root.is_dir():
        raise PersistenceError("Missing or unsafe observation ledger")
    ledger = EvidenceLedger(ledger_root)
    known = set()
    pending = None
    receipts = []
    responses = {}
    batches = []
    terminal = None
    budget = None
    dispatches = 0
    registered: dict[str, Hypothesis] = {}
    observations = {}
    used_observations = set()
    completed_rounds = []
    latest_proposal = None
    for event in events[1:]:
        kind, payload = event["kind"], event["payload"]
        if terminal is not None:
            raise PersistenceError("Events follow terminal discovery state")
        if kind == "observation":
            sha = payload["sha256"]
            path = ledger_root / (sha + ".json")
            if path.is_symlink():
                raise PersistenceError("Unsafe observation artifact")
            observation = ledger.inspect(sha)
            if observation.observation_id != payload["observation_id"]:
                raise PersistenceError("Observation identity mismatch")
            if observation.observation_id in observations:
                raise PersistenceError("Repeated observation identity")
            observations[observation.observation_id] = (observation, event["seq"], sha)
            known.add(sha)
        elif kind == "model_dispatch":
            if pending is not None or payload["attempt"] != len(receipts) + 1:
                raise PersistenceError("Overlapping or missing model attempt")
            if (payload["real"] != (origin == "real")
                    or payload["provider"] != manifest["provider"]
                    or payload["model"] != manifest["model"]):
                raise PersistenceError("Dispatch provenance mismatch")
            pending = payload
            dispatches += 1
            budget = payload["budget"]
        elif kind == "model_result":
            if pending is None:
                raise PersistenceError("Model receipt without dispatch")
            receipt = CallReceipt.model_validate(payload["receipt"])
            if (receipt.seq != len(receipts) + 1 or receipt.stage != pending["stage"]
                    or receipt.real != pending["real"] or receipt.provider != pending["provider"]
                    or receipt.model != pending["model"]
                    or receipt.prompt_version != pending["prompt_version"]):
                raise PersistenceError("Model receipt provenance mismatch")
            response = payload["response"]
            if receipt.outcome == "ok":
                if (not response or not receipt.response_id
                        or digest(response["content_text"].encode("utf-8")) != receipt.content_sha256
                        or len(response["content_text"]) != receipt.content_chars
                        or json.loads(response["content_text"]) != response["parsed"]
                        or any(response[key] != getattr(receipt, key) for key in
                               ("provider", "real", "model", "response_id", "input_tokens", "output_tokens"))):
                    raise PersistenceError("Original response bytes/identity mismatch")
                responses[receipt.seq] = response
                if receipt.stage == "hypothesize" and validate_json_schema(response["parsed"], HYPOTHESIZE_JSON_SCHEMA):
                    raise PersistenceError("Invalid archived hypothesis response")
                if receipt.stage == "propose":
                    if validate_json_schema(response["parsed"], PROPOSE_JSON_SCHEMA):
                        raise PersistenceError("Invalid archived proposal response")
                    latest_proposal = (response["parsed"], event["seq"], receipt.seq)
            elif response is not None:
                raise PersistenceError("Failed response cannot be promoted")
            receipts.append(receipt)
            budget = payload["budget"]
            pending = None
        elif kind == "hypothesis_batch":
            seq = payload["receipt_seq"]
            response = responses.get(seq)
            if not response or receipts[seq - 1].stage != "hypothesize":
                raise PersistenceError("Hypothesis batch lacks original response")
            if set(payload["known_evidence_ids"]) != known:
                raise PersistenceError("Hypothesis evidence registry mismatch")
            original = validate_batch(response["parsed"], frozenset(known))
            persisted = validate_batch(payload["batch"], frozenset(known))
            if original != persisted:
                raise PersistenceError("Hypothesis content differs from original response")
            batches.append(payload["batch"])
            for hyp in original.hypotheses:
                registered.setdefault(hyp.id, hyp)
        elif kind == "round":
            ids = payload["observation_ids"]
            count = payload["actions_executed"]
            if type(count) is not int or count < 0 or len(ids) != len(set(ids)):
                raise PersistenceError("Invalid experiment observation count")
            if payload["proposal_id"] is None:
                if count or ids:
                    raise PersistenceError("Observations lack a model-selected proposal")
            else:
                if latest_proposal is None:
                    raise PersistenceError("Experiment lacks original proposal response")
                proposals, after_seq, receipt_seq = latest_proposal
                matches = [p for p in proposals["proposals"] if p["proposal_id"] == payload["proposal_id"]]
                if len(matches) != 1:
                    raise PersistenceError("Ambiguous or missing original proposal")
                proposal = matches[0]
                predictions = [Prediction(p["hypothesis_id"], p["expects_ok"], p.get("expects_contains"))
                               for p in proposal["predictions"]]
                if any(p.hypothesis_id not in registered for p in predictions):
                    raise PersistenceError("Proposal predicts an unregistered hypothesis")
                if ids:
                    if count != len(ids) or count != len(proposal["actions"]):
                        raise PersistenceError("Experiment differs from full proposed sequence")
                    sequence = None
                    for index, (oid, action) in enumerate(zip(ids, proposal["actions"])):
                        if oid not in observations or oid in used_observations:
                            raise PersistenceError("Unknown or replayed experiment observation")
                        observation, observation_seq, _ = observations[oid]
                        expected_action = {"command": action["command"], **action.get("params", {})}
                        if (observation_seq <= after_seq or observation.action_index != index
                                or observation.input_action != expected_action
                                or observation.sequence_id != (sequence or observation.sequence_id)):
                            raise PersistenceError("Observation does not match model-selected action")
                        sequence = observation.sequence_id
                        used_observations.add(oid)
                    last = ledger.model_view(observations[ids[-1]][2])
                    verdicts = reconcile_predictions(predictions, last.get("output"), str(last.get("status", "")))
                    for hid, verdict in verdicts.items():
                        if verdict in ("supported", "contradicted"):
                            registered[hid] = registered[hid].model_copy(update={"status": verdict})
                    completed_rounds.append({**payload, "proposal": proposal, "receipt_seq": receipt_seq})
                elif count not in (0, len(proposal["actions"])):
                    raise PersistenceError("Invalid interrupted experiment count")
            resolution = {s: sum(h.status == s for h in registered.values())
                          for s in ("hypothesized", "supported", "contradicted", "unresolved")}
            if payload["resolution"] != resolution:
                raise PersistenceError("Round verdicts differ from archived observations")
        elif kind == "terminal":
            terminal = payload
        else:
            raise PersistenceError("Unknown discovery event kind")
    archival_gap = False
    if terminal is not None:
        if terminal["state"] not in ("completed", "stopped", "interrupted", "failed"):
            raise PersistenceError("Unknown terminal discovery state")
        final_hypotheses = [Hypothesis.model_validate(h) for h in terminal["reconciled_hypotheses"]]
        if (len(final_hypotheses) != len(registered)
                or len({h.id for h in final_hypotheses}) != len(final_hypotheses)
                or any(h.id not in registered or h.model_copy(update={"status": registered[h.id].status}) != registered[h.id]
                       for h in final_hypotheses)):
            raise PersistenceError("Final hypotheses contradict original content")
        if any(h != registered[h.id] for h in final_hypotheses):
            if terminal["state"] == "completed":
                raise PersistenceError("Final statuses differ from observed verdicts")
            archival_gap = True  # Interrupted status update without its full round record.
        final_receipts = [CallReceipt.model_validate(r) for r in terminal["model_receipts"]]
        if final_receipts[:len(receipts)] != receipts:
            raise PersistenceError("Terminal receipts contradict durable results")
        if len(final_receipts) > len(receipts):
            # A single result-write failure may leave settled accounting only
            # in the terminal record. Preserve known usage without pretending
            # the missing original response was archived.
            if pending is None or len(final_receipts) != len(receipts) + 1:
                raise PersistenceError("Unexplained terminal model receipts")
            recovered = final_receipts[-1]
            if (recovered.seq != pending["attempt"] or recovered.stage != pending["stage"]
                    or recovered.provider != pending["provider"] or recovered.real != pending["real"]
                    or recovered.model != pending["model"]):
                raise PersistenceError("Recovered receipt identity mismatch")
            receipts = final_receipts
            pending = None
            archival_gap = True
        final_budget = terminal["report"].get("budget_summary", terminal["report"].get("budget"))
        if not isinstance(final_budget, dict):
            raise PersistenceError("Missing terminal budget")
        for key in ("attempts", "model_calls", "input_tokens", "output_tokens"):
            if type(final_budget[key]) is not int or final_budget[key] < 0:
                raise PersistenceError("Invalid terminal usage counters")
        for key in ("estimated_cost_usd", "uncertain_cost_usd"):
            if not isinstance(final_budget[key], (int, float)) or not math.isfinite(final_budget[key]) or final_budget[key] < 0:
                raise PersistenceError("Invalid terminal cost counters")
        # Known-usage invalid outputs count as settled model calls as well.
        settled = [r for r in receipts if r.outcome == "ok" or r.input_tokens or r.output_tokens]
        expected_usage = {"model_calls": len(settled),
                          "input_tokens": sum(r.input_tokens for r in receipts),
                          "output_tokens": sum(r.output_tokens for r in receipts)}
        if (any(final_budget[k] != v for k, v in expected_usage.items())
                or final_budget["attempts"] < dispatches
                or final_budget["attempts"] > dispatches + (terminal["state"] == "failed")
                or final_budget["estimated_cost_usd"] != round(sum(r.estimated_cost_usd for r in receipts), 6)
                or final_budget["uncertain_cost_usd"] != round(sum(r.uncertain_cost_usd for r in receipts), 6)):
            raise PersistenceError("Terminal accounting contradicts model receipts")
        budget = final_budget
    receipt_path = run_dir / "G2_receipt.json"
    receipt_hash = None
    if receipt_path.exists():
        if receipt_path.is_symlink():
            raise PersistenceError("Unsafe discovery receipt")
        raw = receipt_path.read_bytes()
        receipt_hash = digest(raw)
        expected = {"version": JOURNAL_VERSION, "run_id": run_dir.name, "events": len(events),
                    "head_sha256": head, "state": terminal["state"] if terminal else None}
        if json.loads(raw) != expected:
            raise PersistenceError("Discovery receipt does not seal this archive")
    if expected_receipt_sha256 is not None and receipt_hash != expected_receipt_sha256:
        raise PersistenceError("Pinned discovery receipt mismatch")
    state = terminal["state"] if terminal and receipt_hash else "interrupted"
    complete = (state == "completed" and pending is None and not archival_gap and bool(batches)
                and len(receipts) >= 2 and all(r.outcome == "ok" for r in receipts)
                and bool(completed_rounds))
    if state == "completed" and not complete:
        raise PersistenceError("Completed discovery lacks required evidence")
    return {"run_id": run_dir.name, "state": state, "complete": complete,
            "origin": origin, "provider": manifest["provider"], "model": manifest["model"],
            "events": len(events), "head_sha256": head, "receipt_sha256": receipt_hash,
            "observation_digests": sorted(known), "hypothesis_batches": batches,
            "reconciled_hypotheses": [h.model_dump(mode="json") for h in registered.values()],
            "completed_rounds": completed_rounds,
            "model_receipts": [r.model_dump(mode="json") for r in receipts],
            "budget": budget, "pending_attempt": pending,
            "dispatch_count": dispatches, "response_archive_complete": not archival_gap and pending is None,
            "pending_uncertain_cost_usd": pending["reservation"]["est_cost_usd"] if pending else 0.0,
            "execution_resume_supported": False}


def export_batch(run_dir: Path, target: Path, *, expected_receipt_sha256: str) -> Path:
    """Export the last original validated batch, with no inferred historical text."""
    result = inspect_run(run_dir, expected_receipt_sha256)
    if not result["complete"]:
        raise PersistenceError("Incomplete discovery cannot supply G3 input")
    return publish_once(target, canonical(result["hypothesis_batches"][-1]))


def rebuild_store(run_dir: Path, *, expected_receipt_sha256: str) -> HypothesisStore:
    """Restore validated original hypotheses/statuses, never resume execution."""
    result = inspect_run(run_dir, expected_receipt_sha256)
    store = HypothesisStore()
    for doc in result["reconciled_hypotheses"]:
        store.add_batch(validate_batch({"hypotheses": [doc]}, frozenset(result["observation_digests"])))
    return store
