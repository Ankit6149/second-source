"""Schema-validated behavioral hypotheses (G2).

Every hypothesis cites supporting evidence digests that must already exist in
the run's evidence ledger. Unknown references are rejected: no free-floating
claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, ValidationError

from .contracts import StrictModel

HYPOTHESIS_SCHEMA_VERSION = "1.0"
MAX_HYPOTHESES = 5
MAX_STATEMENT_CHARS = 500

VALID_STATUSES = ("hypothesized", "supported", "contradicted", "unresolved")


class HypothesisError(ValueError):
    """Malformed batch or unknown evidence reference."""


class Hypothesis(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=1, max_length=MAX_STATEMENT_CHARS)
    evidence_ids: frozenset[str] = Field(min_length=1)
    status: Literal["hypothesized", "supported", "contradicted", "unresolved"] = "hypothesized"
    alternatives: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()


class HypothesisBatch(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    hypotheses: tuple[Hypothesis, ...] = Field(min_length=1, max_length=MAX_HYPOTHESES)


def validate_batch(doc: dict[str, Any], known_evidence_ids: frozenset[str]) -> HypothesisBatch:
    """Parse a model batch and resolve every evidence citation against the ledger."""
    try:
        batch = HypothesisBatch.model_validate(doc)
    except ValidationError as exc:
        raise HypothesisError(f"hypothesis schema violation: {exc.errors()[0]['msg']}") from exc
    seen: set[str] = set()
    for hyp in batch.hypotheses:
        if hyp.id in seen:
            raise HypothesisError(f"duplicate hypothesis id: {hyp.id}")
        seen.add(hyp.id)
        unknown = sorted(set(hyp.evidence_ids) - set(known_evidence_ids))
        if unknown:
            raise HypothesisError(f"hypothesis {hyp.id}: unknown evidence_ids {unknown}")
    return batch


# Admission failure taxonomy (hypothesize stage only):
# - transport: provider call failed before any content (handled in gateway)
# - generation: content returned but empty / not a JSON object
# - schema: JSON object violates the closed hypothesize contract
# - scientific: schema-shaped batch citing evidence outside the ledger
FAILURE_CLASS_GENERATION = "generation"
FAILURE_CLASS_SCHEMA = "schema"
FAILURE_CLASS_SCIENTIFIC = "scientific"


@dataclass(frozen=True)
class AdmissionRejection:
    """Private record of a rejected hypothesize batch. Never public.

    Carries no raw model text: only the failure class/code, per-hypothesis
    valid/rejected counts, and the SHA-256 of the raw model content so the
    record can be joined to the gateway call receipt (same hash) offline.
    """

    stage: str
    failure_class: str
    failure_code: str
    valid_count: int
    rejected_count: int
    total_count: int
    content_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "failure_class": self.failure_class,
            "failure_code": self.failure_code,
            "valid_count": self.valid_count,
            "rejected_count": self.rejected_count,
            "total_count": self.total_count,
            "content_sha256": self.content_sha256,
        }


def per_hypothesis_counts(
    doc: Any, known_evidence_ids: frozenset[str]
) -> tuple[int, int, int]:
    """Return (valid, rejected, total) per-hypothesis counts without raising."""
    if not isinstance(doc, dict):
        return (0, 0, 0)
    items = doc.get("hypotheses")
    if not isinstance(items, list):
        return (0, 0, 0)
    valid = 0
    seen: set[str] = set()
    for item in items:
        try:
            hyp = Hypothesis.model_validate(item)
        except ValidationError:
            continue
        if hyp.id in seen:
            continue
        seen.add(hyp.id)
        if set(hyp.evidence_ids) - set(known_evidence_ids):
            continue
        valid += 1
    total = len(items)
    return (valid, total - valid, total)


def build_admission_rejection(
    doc: Any,
    known_evidence_ids: frozenset[str],
    exc: BaseException,
    *,
    content_sha256: str,
    stage: str = "hypothesize",
) -> AdmissionRejection:
    """Classify a validate_batch rejection. Classification never admits."""
    valid, rejected, total = per_hypothesis_counts(doc, known_evidence_ids)
    message = str(exc)
    if isinstance(doc, dict) and doc.get("hypotheses") == []:
        failure_class, failure_code = FAILURE_CLASS_SCHEMA, "EMPTY_BATCH"
    elif "unknown evidence_ids" in message:
        failure_class, failure_code = (
            FAILURE_CLASS_SCIENTIFIC,
            "UNKNOWN_EVIDENCE_ID",
        )
    elif "duplicate hypothesis id" in message:
        failure_class, failure_code = FAILURE_CLASS_SCHEMA, "DUPLICATE_HYPOTHESIS_ID"
    else:
        failure_class, failure_code = FAILURE_CLASS_SCHEMA, "SCHEMA_VIOLATION"
    return AdmissionRejection(
        stage=stage,
        failure_class=failure_class,
        failure_code=failure_code,
        valid_count=valid,
        rejected_count=rejected,
        total_count=total,
        content_sha256=content_sha256,
    )


class HypothesisStore:
    """Keeps competing hypotheses and their lifecycle per run."""

    def __init__(self) -> None:
        self._items: dict[str, Hypothesis] = {}

    def add_batch(self, batch: HypothesisBatch) -> None:
        for hyp in batch.hypotheses:
            if hyp.id in self._items:
                raise HypothesisError(f"hypothesis {hyp.id} already registered")
            self._items[hyp.id] = hyp

    def ids(self) -> frozenset[str]:
        return frozenset(self._items)

    def get(self, hyp_id: str) -> Hypothesis:
        return self._items[hyp_id]

    def all(self) -> tuple[Hypothesis, ...]:
        return tuple(self._items.values())

    def competing(self) -> tuple[Hypothesis, ...]:
        return tuple(h for h in self._items.values() if h.status != "contradicted")

    def update_status(self, hyp_id: str, status: str) -> None:
        if status not in VALID_STATUSES:
            raise HypothesisError(f"unknown status {status!r}")
        current = self._items[hyp_id]
        self._items[hyp_id] = current.model_copy(update={"status": status})

    def resolution_counts(self) -> dict[str, int]:
        counts = {s: 0 for s in VALID_STATUSES}
        for hyp in self._items.values():
            counts[hyp.status] += 1
        return counts
