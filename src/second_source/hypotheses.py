"""Schema-validated behavioral hypotheses (G2).

Every hypothesis cites supporting evidence digests that must already exist in
the run's evidence ledger. Unknown references are rejected: no free-floating
claims.
"""
from __future__ import annotations

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
