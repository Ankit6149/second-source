"""Gemma hypothesize admission: offline, deterministic, no network.

Provenance: every provider here is a fake Gemma-shaped stand-in labeled
provider="gemma-test" (PIPELINE_SMOKE_NOT_META). Nothing here is Meta
evidence (REAL_MODEL) and nothing calls a live API.

Failure taxonomy exercised:
- transport: provider fails before content (gateway receipt only)
- generation: content returned but no parsed JSON object
- schema: parsed object violates the closed hypothesize contract
- scientific: schema-shaped batch citing evidence outside the ledger
"""
import hashlib
import json

import pytest

from second_source import g4_http_reconstruct as g4
from second_source.budgets import RunBudget
from second_source.hypotheses import HypothesisError, HypothesisStore
from second_source.model_gateway import (
    GatewayError,
    GemmaTestProvider,
    ModelGateway,
    ModelResponse,
)
from second_source.planner import ExperimentPlanner
from second_source.scope_guard import ScopeGuard

KNOWN = frozenset({"d1", "d2"})
EVIDENCE = [{"digest": "d1", "observation": {}}, {"digest": "d2", "observation": {}}]


def hyp(hid, digest="d1", **over):
    item = {
        "id": hid,
        "statement": f"candidate rule for {hid}",
        "evidence_ids": [digest],
        "status": "hypothesized",
        "alternatives": ["alternative explanation"],
        "unresolved_questions": ["open question?"],
    }
    item.update(over)
    return item


def batch(*items, **top):
    doc = {"schema_version": "1.0", "hypotheses": list(items)}
    doc.update(top)
    return doc


class FakeGemmaProvider(GemmaTestProvider):
    """Gemma-shaped fake: returns canned parsed content, never validates.

    Mirrors the real GemmaTestProvider contract (native transport returns
    extracted `parsed` without local schema enforcement), so admission is
    exercised at the planner/validate_batch layer exactly as in production.
    """

    def __init__(self, doc=None, *, parsed="__doc__", content_text=None, exc=None):
        self._model = "gemma-4-26b-a4b-it"
        self._rates = (1.25, 4.25)
        self._doc = doc
        self._parsed_arg = parsed
        self._content_text = content_text
        self._exc = exc

    def complete(self, request):
        if self._exc is not None:
            raise self._exc
        parsed = self._doc if self._parsed_arg == "__doc__" else self._parsed_arg
        if self._content_text is not None:
            text = self._content_text
        elif isinstance(self._doc, (dict, list)):
            text = json.dumps(self._doc)
        else:
            text = "not json at all"
        return ModelResponse(
            provider="gemma-test",
            real=True,
            model=self._model,
            response_id="fake-gemma-" + request.stage,
            content_text=text,
            parsed=parsed,
            input_tokens=120,
            output_tokens=40,
            latency_ms=1,
        )


def make_planner(cli_scope, provider, admission_audit=None):
    budget = RunBudget(cli_scope.budgets)
    store = HypothesisStore()
    gateway = ModelGateway(provider, budget)
    planner = ExperimentPlanner(
        gateway,
        ScopeGuard(cli_scope),
        store,
        budget,
        cli_scope,
        admission_audit=admission_audit,
    )
    return planner, store, gateway


def test_golden_valid_batch_accepted(cli_scope):
    planner, store, gateway = make_planner(
        cli_scope, FakeGemmaProvider(batch(hyp("hyp-1"), hyp("hyp-2", "d2")))
    )
    result = planner.hypothesize(EVIDENCE, KNOWN)
    assert [h.id for h in result.hypotheses] == ["hyp-1", "hyp-2"]
    store.add_batch(result)
    assert store.ids() == frozenset({"hyp-1", "hyp-2"})
    assert planner.admission_rejections == ()
    assert gateway.receipts[0].provider == "gemma-test"
    assert gateway.receipts[0].outcome == "ok"


def test_empty_batch_rejected_schema(cli_scope):
    planner, store, _ = make_planner(
        cli_scope, FakeGemmaProvider(batch())
    )
    with pytest.raises(HypothesisError):
        planner.hypothesize(EVIDENCE, KNOWN)
    assert store.all() == ()
    (rec,) = planner.admission_rejections
    assert rec.failure_class == "schema"
    assert rec.failure_code == "EMPTY_BATCH"
    assert (rec.valid_count, rec.rejected_count, rec.total_count) == (0, 0, 0)


def test_fabricated_evidence_citation_rejected_scientific(cli_scope):
    fabricated = "f" * 64  # digest-shaped but never observed
    doc = batch(hyp("hyp-1"), hyp("hyp-2", fabricated))
    planner, store, _ = make_planner(cli_scope, FakeGemmaProvider(doc))
    with pytest.raises(HypothesisError, match="unknown evidence_ids"):
        planner.hypothesize(EVIDENCE, KNOWN)
    assert store.all() == ()
    (rec,) = planner.admission_rejections
    assert rec.failure_class == "scientific"
    assert rec.failure_code == "UNKNOWN_EVIDENCE_ID"
    assert (rec.valid_count, rec.rejected_count, rec.total_count) == (1, 1, 2)


def test_unknown_evidence_id_rejected_scientific(cli_scope):
    planner, store, _ = make_planner(
        cli_scope, FakeGemmaProvider(batch(hyp("hyp-1", "digest-zzz")))
    )
    with pytest.raises(HypothesisError, match="digest-zzz"):
        planner.hypothesize(EVIDENCE, KNOWN)
    assert store.all() == ()
    (rec,) = planner.admission_rejections
    assert rec.failure_class == "scientific"
    assert rec.failure_code == "UNKNOWN_EVIDENCE_ID"
    assert (rec.valid_count, rec.rejected_count, rec.total_count) == (0, 1, 1)


@pytest.mark.parametrize(
    "bad_item",
    [
        hyp("hyp-1", statement=""),
        hyp("hyp-1", statement=42),
        hyp("hyp-1", evidence_ids=[]),
        hyp("hyp-1", status="proven-fact"),
        {k: v for k, v in hyp("hyp-1").items() if k != "statement"},
    ],
)
def test_malformed_fields_rejected_schema(cli_scope, bad_item):
    planner, store, _ = make_planner(
        cli_scope, FakeGemmaProvider(batch(bad_item))
    )
    with pytest.raises(HypothesisError):
        planner.hypothesize(EVIDENCE, KNOWN)
    assert store.all() == ()
    (rec,) = planner.admission_rejections
    assert rec.failure_class == "schema"
    assert rec.failure_code == "SCHEMA_VIOLATION"
    assert rec.rejected_count == 1


def test_extra_unsupported_fields_rejected_schema(cli_scope):
    # Closed contract: additionalProperties=false + StrictModel extra=forbid.
    cases = [
        batch(hyp("hyp-1", confidence=0.9)),
        batch(hyp("hyp-1"), notes="model commentary"),
    ]
    for doc in cases:
        planner, store, _ = make_planner(cli_scope, FakeGemmaProvider(doc))
        with pytest.raises(HypothesisError):
            planner.hypothesize(EVIDENCE, KNOWN)
        assert store.all() == ()
        (rec,) = planner.admission_rejections
        assert rec.failure_class == "schema"


def test_duplicate_ids_rejected_schema(cli_scope):
    planner, _, _ = make_planner(
        cli_scope, FakeGemmaProvider(batch(hyp("hyp-1"), hyp("hyp-1", "d2")))
    )
    with pytest.raises(HypothesisError, match="duplicate"):
        planner.hypothesize(EVIDENCE, KNOWN)
    (rec,) = planner.admission_rejections
    assert rec.failure_class == "schema"
    assert rec.failure_code == "DUPLICATE_HYPOTHESIS_ID"


def test_no_parsed_object_is_generation_failure(cli_scope):
    planner, store, gateway = make_planner(
        cli_scope,
        FakeGemmaProvider(None, parsed=None, content_text="prose, no json"),
    )
    with pytest.raises(GatewayError, match="no parsed object"):
        planner.hypothesize(EVIDENCE, KNOWN)
    assert store.all() == ()
    (rec,) = planner.admission_rejections
    assert rec.failure_class == "generation"
    assert rec.failure_code == "NO_PARSED_OBJECT"
    # Hash joins the private record to the gateway receipt for the same call.
    assert rec.content_sha256 == gateway.receipts[0].content_sha256
    assert rec.content_sha256 == hashlib.sha256(b"prose, no json").hexdigest()


def test_transport_failure_has_no_admission_record(cli_scope):
    planner, store, gateway = make_planner(
        cli_scope,
        FakeGemmaProvider(exc=GatewayError("Gemma test API transport failure")),
    )
    with pytest.raises(GatewayError):
        planner.hypothesize(EVIDENCE, KNOWN)
    assert store.all() == ()
    assert planner.admission_rejections == ()
    assert gateway.receipts[0].outcome == "failed"


def test_rejection_record_is_private_and_hash_only(cli_scope):
    seen = []
    doc = batch(hyp("hyp-1", "digest-zzz"))
    planner, _, gateway = make_planner(
        cli_scope, FakeGemmaProvider(doc), admission_audit=seen.append
    )
    with pytest.raises(HypothesisError):
        planner.hypothesize(EVIDENCE, KNOWN)
    (rec,) = seen
    assert rec is planner.admission_rejections[0]
    payload = rec.as_dict()
    assert set(payload) == {
        "stage", "failure_class", "failure_code",
        "valid_count", "rejected_count", "total_count", "content_sha256",
    }
    blob = json.dumps(payload)
    assert "candidate rule" not in blob  # no raw model statement text
    assert len(rec.content_sha256) == 64
    assert rec.content_sha256 == gateway.receipts[0].content_sha256


def test_gemma_native_extraction_fenced_and_embedded_json(monkeypatch):
    provider = GemmaTestProvider("test-key-not-real")

    def fake_doc(text):
        return {
            "responseId": "gemma-resp-1",
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [{"text": text}]},
            }],
            "usageMetadata": {"promptTokenCount": 5543, "candidatesTokenCount": 132},
        }

    class FakeResp:
        def __init__(self, doc):
            self._doc = doc

        def read(self):
            return json.dumps(self._doc).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    good = batch(hyp("hyp-1"))
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: FakeResp(fake_doc("```json\n" + json.dumps(good) + "\n```")),
    )
    from second_source.model_gateway import ModelRequest
    from second_source.planner import HYPOTHESIZE_JSON_SCHEMA

    req = ModelRequest(
        stage="hypothesize",
        messages=({"role": "user", "content": "evidence"},),
        json_schema=HYPOTHESIZE_JSON_SCHEMA,
        max_output_tokens=2400,
        prompt_version="hypothesize-v1",
    )
    resp = provider.complete(req)
    assert resp.provider == "gemma-test"
    assert resp.model == "gemma-4-26b-a4b-it"
    assert resp.parsed == good
    assert (resp.input_tokens, resp.output_tokens) == (5543, 132)

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: FakeResp(fake_doc("Here is the batch: " + json.dumps(good))),
    )
    assert provider.complete(req).parsed == good

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: FakeResp(fake_doc("no json here")),
    )
    # Generation gap at this layer: extraction yields parsed=None; the
    # planner records it privately as a generation failure (see above).
    assert provider.complete(req).parsed is None


class RejectingGemmaProvider(GemmaTestProvider):
    def __init__(self, api_key, model="gemma-4-26b-a4b-it"):
        self._model = model
        self._rates = (1.25, 4.25)

    def complete(self, request):
        doc = batch(hyp("hyp-1", "e" * 64))
        return ModelResponse(
            provider="gemma-test",
            real=True,
            model=self._model,
            response_id="fake-gemma-reject",
            content_text=json.dumps(doc),
            parsed=doc,
            input_tokens=5543,
            output_tokens=132,
            latency_ms=1,
        )


def test_g4_gemma_rejection_writes_private_record_only(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMMA_API_KEY", "test-key-not-real")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.50")
    monkeypatch.setattr(g4, "GemmaTestProvider", RejectingGemmaProvider)
    run_dir = tmp_path / "gemma-reject"
    rc = g4.main([
        "--mode", "discover-gemma-test",
        "--max-usd", "0.50",
        "--confirm-real-run",
        "--run-dir", str(run_dir),
    ])
    assert rc == 1
    assert not (run_dir / "hypotheses.original.json").exists()
    private = json.loads(
        (run_dir / "hypothesis-admission.v1.private.json").read_text(encoding="utf-8")
    )
    assert private["kind"] == "G4_PRIVATE_HYPOTHESIS_ADMISSION_V1"
    rejection = private["rejection"]
    assert rejection["failure_class"] == "scientific"
    assert rejection["failure_code"] == "UNKNOWN_EVIDENCE_ID"
    assert rejection["total_count"] == 1
    assert rejection["rejected_count"] == 1
    assert len(rejection["content_sha256"]) == 64

    public_text = (run_dir / "G4_report.json").read_text(encoding="utf-8")
    assert rejection["content_sha256"] not in public_text
    assert "UNKNOWN_EVIDENCE_ID" not in public_text
    assert "candidate rule" not in public_text
    assert "hypothesis-admission" not in public_text
