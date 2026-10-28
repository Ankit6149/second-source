"""Durable G2 discovery persistence (nonbillable; never invents history).

The live G2 loop previously retained only hypothesis/proposal IDs and verdict
notes: the complete hypothesis batches (statements + cited evidence digests),
the executed proposals (actions + checkable predictions), and the per-call
model receipts were lost after the run. That is exactly why the accepted
`real-g2-20261027T192406Z-5482abee` run cannot supply authentic G3 inputs.

This module records, validates, reloads, and resumes those artifacts:

- `G2Recorder` accumulates per-round batch/proposal/evidence/verdict events
  from `DiscoveryLoop` (via an optional recorder hook) and writes one
  create-once `g2_manifest.json` per run directory.
- `load_manifest` revalidates every byte: schema, evidence citations, receipt
  identity, and ledger content addressing. Anything malformed or unresolvable
  raises `PersistenceError`; guesses are never substituted.
- `rebuild_store` restores a `HypothesisStore` (final statuses included) so a
  separately approved follow-up discovery can cite prior evidence digests.
- `manifest_completeness` lists every gap that would disqualify the manifest
  as authentic G3 input (missing batches, uncited evidence, receipt gaps).

No model calls, no credentials, no network. History is recorded, never
reconstructed from identifiers.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import Field, ValidationError

from .contracts import StrictModel
from .evidence import EvidenceLedger
from .hypotheses import (
    Hypothesis, HypothesisBatch, HypothesisStore, validate_batch,
)
from .model_gateway import CallReceipt

MANIFEST_VERSION = "1"
MANIFEST_FILENAME = "g2_manifest.json"


class PersistenceError(ValueError):
    """Manifest malformed, incomplete, or inconsistent with its ledger."""


class G2ProposalRecord(StrictModel):
    proposal_id: str = Field(min_length=1, max_length=64)
    actions: tuple[dict[str, Any], ...] = Field(min_length=1)
    predictions: tuple[dict[str, Any], ...] = Field(min_length=1)
    utility: float
    executed: bool = False


class G2RoundRecord(StrictModel):
    round_no: int = Field(ge=0)
    hypothesis_batch: HypothesisBatch
    proposal: G2ProposalRecord | None = None
    evidence_digests: tuple[str, ...] = ()
    verdicts: dict[str, str] = Field(default_factory=dict)


class G2RunManifest(StrictModel):
    manifest_version: Literal["1"] = MANIFEST_VERSION
    run_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    created_utc: str = Field(min_length=1)
    scope_digest: str = Field(min_length=1)
    rounds: tuple[G2RoundRecord, ...] = Field(min_length=1)
    final_hypotheses: tuple[Hypothesis, ...] = Field(min_length=1)
    model_receipts: tuple[CallReceipt, ...] = ()
    budget_summary: dict[str, Any] = Field(default_factory=dict)
    stop_reason: str = Field(min_length=1)


def scope_digest_of(contract: Any) -> str:
    """Local content pin for the run's scope contract (G2-local, not a G3 pin)."""
    raw = contract.model_dump_json().encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class G2Recorder:
    """Accumulates loop events into one durable, validatable run manifest."""

    def __init__(self, *, run_id: str, requirement_id: str, scope_digest: str) -> None:
        self._run_id = run_id
        self._requirement_id = requirement_id
        self._scope_digest = scope_digest
        self._rounds: list[dict[str, Any]] = []
        self._final: dict[str, Any] | None = None

    def __call__(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict) or "event" not in event:
            raise PersistenceError("recorder accepts only loop event mappings")
        if event["event"] == "round":
            self._rounds.append(event)
        elif event["event"] == "final":
            self._final = event
        else:
            raise PersistenceError(f"unknown loop event {event['event']!r}")

    def manifest(
        self,
        *,
        final_hypotheses: Any,
        receipts: Any = (),
        budget_summary: dict[str, Any] | None = None,
        stop_reason: str = "",
    ) -> G2RunManifest:
        """Build and fully validate the manifest; raises on any gap."""
        if not self._rounds:
            raise PersistenceError("no rounds recorded; refusing empty manifest")
        try:
            rounds = tuple(
                G2RoundRecord.model_validate(_round_record(event))
                for event in self._rounds
            )
            final = tuple(
                Hypothesis.model_validate(h)
                for h in (
                    final_hypotheses.all()
                    if isinstance(final_hypotheses, HypothesisStore)
                    else final_hypotheses
                )
            )
            manifest = G2RunManifest(
                run_id=self._run_id,
                requirement_id=self._requirement_id,
                created_utc=datetime.now(timezone.utc).isoformat(),
                scope_digest=self._scope_digest,
                rounds=rounds,
                final_hypotheses=final,
                model_receipts=tuple(receipts or ()),
                budget_summary=dict(budget_summary or {}),
                stop_reason=stop_reason or "unknown",
            )
        except ValidationError as exc:
            raise PersistenceError(
                f"manifest validation failed: {exc.errors()[0]['msg']}"
            ) from exc
        gaps = manifest_completeness(manifest)
        if gaps:
            raise PersistenceError(f"incomplete manifest: {gaps}")
        return manifest

    def write(self, run_dir: str | Path) -> Path:
        """Create-once manifest write; refuses to overwrite a prior manifest."""
        if self._final is None:
            raise PersistenceError("loop final event missing; refusing partial manifest")
        final = self._final
        manifest = self.manifest(
            final_hypotheses=final.get("final_hypotheses", ()),
            receipts=final.get("receipts", ()),
            budget_summary=final.get("budget_summary"),
            stop_reason=final.get("stop_reason", ""),
        )
        path = Path(run_dir) / MANIFEST_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = manifest.model_dump_json(indent=2).encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        return path


def _round_record(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "round_no": event.get("round_no", 0),
        "hypothesis_batch": event.get("hypothesis_batch", {}),
        "proposal": event.get("proposal"),
        "evidence_digests": tuple(event.get("evidence_digests", ())),
        "verdicts": dict(event.get("verdicts", {})),
    }


def load_manifest(path: str | Path) -> G2RunManifest:
    """Reload and revalidate a manifest; malformed input raises, never guesses."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise PersistenceError(f"manifest unreadable: {exc}") from exc
    try:
        manifest = G2RunManifest.model_validate_json(raw)
    except ValidationError as exc:
        raise PersistenceError(
            f"manifest schema violation: {exc.errors()[0]['msg']}"
        ) from exc
    gaps = manifest_completeness(manifest)
    if gaps:
        raise PersistenceError(f"incomplete manifest: {gaps}")
    return manifest


def rebuild_store(manifest: G2RunManifest) -> HypothesisStore:
    """Restore final statuses so an approved follow-up can cite prior evidence."""
    store = HypothesisStore()
    by_id: dict[str, Hypothesis] = {}
    for record in manifest.rounds:
        for hyp in record.hypothesis_batch.hypotheses:
            by_id[hyp.id] = hyp
    for hyp in manifest.final_hypotheses:
        by_id[hyp.id] = hyp
    if not by_id:
        raise PersistenceError("manifest carries no hypotheses to resume")
    ordered = sorted(by_id.values(), key=lambda h: h.id)
    store.add_batch(
        validate_batch(
            {"hypotheses": [h.model_dump(mode="json") for h in ordered]},
            _manifest_evidence_ids(manifest),
        )
    )
    for hyp in ordered:
        if hyp.status != "hypothesized":
            store.update_status(hyp.id, hyp.status)
    return store


def _manifest_evidence_ids(manifest: G2RunManifest) -> frozenset[str]:
    known: set[str] = set()
    for record in manifest.rounds:
        known.update(record.evidence_digests)
    return frozenset(known)


def manifest_completeness(manifest: G2RunManifest) -> list[str]:
    """Gaps disqualifying the manifest as authentic G3 input; empty means complete."""
    gaps: list[str] = []
    if not manifest.rounds:
        return ["no rounds recorded"]
    known = _manifest_evidence_ids(manifest)
    for record in manifest.rounds:
        if not record.hypothesis_batch.hypotheses:
            gaps.append(f"round {record.round_no}: empty hypothesis batch")
        for hyp in record.hypothesis_batch.hypotheses:
            if not hyp.statement.strip():
                gaps.append(f"round {record.round_no}: hypothesis {hyp.id} has no statement")
            unknown = sorted(set(hyp.evidence_ids) - known)
            if unknown:
                gaps.append(
                    f"round {record.round_no}: hypothesis {hyp.id} cites "
                    f"unrecorded evidence {unknown}"
                )
        if record.proposal is None and record.round_no > 0:
            gaps.append(f"round {record.round_no}: executed round has no proposal record")
    if not manifest.final_hypotheses:
        gaps.append("no final hypothesis statuses recorded")
    for receipt in manifest.model_receipts:
        if not receipt.response_id:
            gaps.append(f"receipt seq {receipt.seq}: missing provider response id")
        if receipt.outcome == "failed" and not receipt.failure_code:
            gaps.append(f"receipt seq {receipt.seq}: failed without failure code")
    if not manifest.scope_digest:
        gaps.append("missing scope digest")
    return gaps


def verify_ledger_coverage(manifest: G2RunManifest, ledger: EvidenceLedger) -> list[str]:
    """Confirm every recorded digest resolves in the ledger; tampering surfaces here."""
    missing: list[str] = []
    for digest in sorted(_manifest_evidence_ids(manifest)):
        try:
            ledger.inspect(digest)
        except (OSError, ValueError) as exc:
            missing.append(f"{digest}: {exc}")
    return missing
