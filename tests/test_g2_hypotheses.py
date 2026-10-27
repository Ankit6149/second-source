"""G2 hypothesis schema tests: every claim cites existing evidence."""

import pytest

from second_source.hypotheses import HypothesisError, HypothesisStore, validate_batch

KNOWN = frozenset({"digest-a", "digest-b"})


def batch(*items):
    return {
        "schema_version": "1.0",
        "hypotheses": [
            {"id": hid, "statement": statement, "evidence_ids": ["digest-a"]}
            for hid, statement in items
        ],
    }


def test_valid_batch():
    parsed = validate_batch(batch(("hyp-1", "duplicate labels are rejected")), KNOWN)
    assert len(parsed.hypotheses) == 1
    assert parsed.hypotheses[0].status == "hypothesized"


def test_unknown_evidence_rejected():
    doc = batch(("hyp-1", "rule"))
    doc["hypotheses"][0]["evidence_ids"] = ["digest-zzz"]
    with pytest.raises(HypothesisError, match="digest-zzz"):
        validate_batch(doc, KNOWN)


def test_empty_rejected():
    with pytest.raises(HypothesisError):
        validate_batch({"schema_version": "1.0", "hypotheses": []}, KNOWN)


def test_too_many_rejected():
    with pytest.raises(HypothesisError):
        validate_batch(
            batch(*[(f"hyp-{i}", f"rule {i}") for i in range(6)]), KNOWN
        )


def test_duplicate_ids_rejected():
    with pytest.raises(HypothesisError, match="duplicate"):
        validate_batch(batch(("hyp-1", "a"), ("hyp-1", "b")), KNOWN)


def test_bad_status_rejected():
    doc = batch(("hyp-1", "a"))
    doc["hypotheses"][0]["status"] = "proven-fact"
    with pytest.raises(HypothesisError):
        validate_batch(doc, KNOWN)


def test_store_lifecycle():
    store = HypothesisStore()
    store.add_batch(validate_batch(batch(("hyp-1", "a"), ("hyp-2", "b")), KNOWN))
    assert store.ids() == frozenset({"hyp-1", "hyp-2"})
    assert len(store.competing()) == 2
    store.update_status("hyp-1", "contradicted")
    assert len(store.competing()) == 1
    assert store.resolution_counts()["contradicted"] == 1
    with pytest.raises(HypothesisError):
        store.add_batch(validate_batch(batch(("hyp-1", "c")), KNOWN))
