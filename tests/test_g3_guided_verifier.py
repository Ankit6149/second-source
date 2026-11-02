"""Independent pinned guided-broker controls: entirely hand-authored NON_AI.

These fixture choices establish admission/evaluator sensitivity, never genuine
Meta reconstruction quality. Original full-mode and sealed-suite gates remain.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import urllib.request

import pytest

from second_source.budgets import RunBudget
from second_source.candidate_adapter import CandidateReferenceAdapter
from second_source import candidate_generation
from second_source.contracts import Observation
from second_source.evidence import EvidenceLedger
from second_source.g3_verification import (
    EvaluationBlocked, PinnedEvaluatorRun, _digest, _encode,
    load_sealed_suite, seal_owned_ledger_suite,
)
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.model_gateway import MetaProvider, MockProvider
from second_source.reconstruct import create_scope

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "tests/g3_fixtures/valid_candidate.json"


def positive_non_ai_fill():
    """Explicit trusted fixture values, not inferred or substituted model output."""
    return {
        "error_codes": {"unknown_command": "unknown_command", "invalid_input": "invalid_input"},
        "add": {
            "label": {"min_length": 1, "max_length": 24, "trim": True},
            "amount": {"minimum": 1, "maximum": 100},
            "unique_field": "label", "unique_casefold": True,
            "label_error": "invalid_label", "amount_error": "invalid_amount",
            "duplicate_error": "duplicate_label", "respond": {"id": "id"},
        },
        "list": {"respond": {"items": "items"}},
        "total": {"respond": {"count": "count", "amount": "amount"}},
        "remove": {"not_found_error": "not_found", "respond": {"removed": "id"}},
    }


@pytest.fixture(autouse=True)
def no_genuine_transport(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")

    def forbidden(*args, **kwargs):
        raise AssertionError("Guided verifier controls authorize no genuine provider transport")

    monkeypatch.setattr(MetaProvider, "complete", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


@pytest.fixture(scope="module")
def approved_inputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("non-ai-guided-verifier")
    scope = create_scope(0)
    ledger = EvidenceLedger(root / "observations")
    digest = ledger.store(Observation(
        observation_id="NON_AI_GUIDED:0", sequence_id="NON_AI_GUIDED", action_index=0,
        input_action={"command": "list"}, output={"ok": True, "items": []},
        exit_code=0, duration_ms=0, status="ok",
    ))["sha256"]
    store = HypothesisStore()
    store.add_batch(validate_batch({"hypotheses": [{
        "id": "NON_AI_GUIDED_EMPTY_LIST", "statement": "Synthetic empty list control",
        "evidence_ids": [digest],
    }]}, frozenset({digest})))
    suite_path, suite_digest = seal_owned_ledger_suite(root / "sealed", scope)
    suite = load_sealed_suite(suite_path, suite_digest, scope)
    return scope, ledger, digest, store, suite


def authority(inputs, synthesis="guided", **kwargs):
    scope, ledger, digest, hypotheses, suite = inputs
    return PinnedEvaluatorRun(suite, scope, ledger=ledger,
        observation_digests=(digest,), hypotheses=hypotheses, synthesis=synthesis, **kwargs)


def admit(inputs, fill, *, synthesis="guided", audit=None):
    run = authority(inputs, synthesis)
    ticket = run.prepare()
    budget = RunBudget(inputs[0].budgets)
    artifact = run.generate(ticket, MockProvider(script=[{"content": fill}]), budget, audit=audit)
    return run, ticket, budget, artifact


def test_guided_inspected_wire_equals_exact_transport_and_excludes_private_suite(approved_inputs):
    run = authority(approved_inputs)
    ticket = run.prepare()
    expected = json.loads(ticket.payload)["wire"]
    seen = []

    def respond(request):
        seen.append(request.model_dump(mode="json"))
        return {"content": positive_non_ai_fill()}

    budget = RunBudget(approved_inputs[0].budgets)
    artifact = run.generate(ticket, MockProvider(responder=respond), budget)
    assert seen == [expected]
    assert expected["max_output_tokens"] == 4096
    assert expected["json_schema"] == candidate_generation.FILL_JSON_SCHEMA
    assert "skeleton" in json.loads(next(m["content"] for m in expected["messages"] if m["role"] == "user"))
    manifest = run.inspection_manifest()
    assert manifest["synthesis"] == "guided"
    assert manifest["inspected_request_digest"] == _digest(_encode(expected))
    assert manifest["request_max_output_tokens"] == 4096
    receipt = json.loads(artifact.payload)["receipt"]
    assert receipt["request_digest"] == manifest["inspected_request_digest"]
    assert receipt["synthesis"] == "guided" and receipt["origin"] == "mock" and receipt["real"] is False
    assert receipt["model_output_digest"] == _digest(_encode(positive_non_ai_fill()))
    rendered = _encode(expected)
    assert str(ROOT).encode() not in rendered
    assert all(case.case_id.encode() not in rendered for case in approved_inputs[-1].cases())
    assert budget.attempts == budget.model_calls == 1
    assert budget.estimated_cost_usd == budget.uncertain_cost_usd == 0


def test_default_full_mode_keeps_original_wire_and_context_pin(approved_inputs):
    scope, ledger, digest, hypotheses, suite = approved_inputs
    default = PinnedEvaluatorRun(suite, scope, ledger=ledger,
        observation_digests=(digest,), hypotheses=hypotheses)
    explicit = authority(approved_inputs, "full")
    assert default.synthesis == explicit.synthesis == "full"
    assert default.approved_context_digest == explicit.approved_context_digest == _digest(default._context_raw)
    assert "synthesis" not in json.loads(default._plan_raw)
    ticket = default.prepare()
    expected = json.loads(ticket.payload)["wire"]
    assert json.loads(explicit.prepare().payload)["wire"] == expected
    assert expected["max_output_tokens"] == 2000
    assert expected["json_schema"] != candidate_generation.FILL_JSON_SCHEMA
    seen = []

    def respond(request):
        seen.append(request.model_dump(mode="json"))
        return {"content": json.loads(CONTROL.read_bytes())}

    default.generate(ticket, MockProvider(responder=respond), RunBudget(scope.budgets))
    assert seen == [expected]


def test_full_context_approval_cannot_authorize_guided_protocol(approved_inputs):
    full = authority(approved_inputs, "full")
    guided = authority(approved_inputs)
    assert guided.approved_context_digest != full.approved_context_digest
    with pytest.raises(EvaluationBlocked, match="approved G2 input pin"):
        authority(approved_inputs, operator_approved_context_digest=full.approved_context_digest)
    approved = authority(approved_inputs, operator_approved_context_digest=guided.approved_context_digest)
    assert approved.inspection_manifest()["operator_input_pin"] == guided.approved_context_digest
    with pytest.raises(AttributeError):
        approved.synthesis = "full"


def test_guided_ticket_mode_tampering_cross_run_and_replay_fail_before_transport(approved_inputs):
    run = authority(approved_inputs)
    ticket = run.prepare()
    budget = RunBudget(approved_inputs[0].budgets)
    calls = []

    def respond(request):
        calls.append(request)
        return {"content": positive_non_ai_fill()}

    provider = MockProvider(responder=respond)
    payload = json.loads(ticket.payload)
    payload["wire"]["max_output_tokens"] = 2000
    with pytest.raises(EvaluationBlocked):
        run.generate(replace(ticket, payload=_encode(payload)), provider, budget)
    with pytest.raises(EvaluationBlocked):
        run.generate(authority(approved_inputs, "full").prepare(), provider, budget)
    assert calls == [] and budget.attempts == 0
    artifact = run.generate(ticket, provider, budget)
    assert len(calls) == budget.attempts == 1
    with pytest.raises(EvaluationBlocked, match="replay"):
        run.generate(ticket, provider, budget)
    assert len(calls) == budget.attempts == 1
    with pytest.raises(EvaluationBlocked, match="real-model"):
        run.evaluate(artifact, claim="REAL_MODEL")


def test_hand_authored_guided_positive_is_non_ai_25_of_25(approved_inputs):
    run, _, budget, artifact = admit(approved_inputs, positive_non_ai_fill())
    result = run.evaluate(artifact, claim="TRUSTED_CONTROL")
    assert result["evaluation"] == {
        "passed": 25, "failed": 0, "indeterminate": 0, "total": 25, "failure_categories": {},
    }
    assert result["origin"]["origin"] == "mock" and result["origin"]["real"] is False
    assert result["origin"]["synthesis"] == "guided"
    assert budget.estimated_cost_usd == budget.uncertain_cost_usd == 0


def test_deliberate_guided_casefold_defect_still_scores_two_failures(approved_inputs):
    fill = positive_non_ai_fill()
    fill["add"]["unique_casefold"] = False
    run, _, _, artifact = admit(approved_inputs, fill)
    counts = run.evaluate(artifact, claim="TRUSTED_CONTROL")["evaluation"]
    assert (counts["passed"], counts["failed"], counts["indeterminate"], counts["total"]) == (23, 2, 0, 25)


def test_valid_different_model_fill_changes_behavior_without_adapter_repair(approved_inputs):
    fill = positive_non_ai_fill()
    fill["add"].update(unique_field="amount", duplicate_error="duplicate_amount")
    _, _, _, artifact = admit(approved_inputs, fill)
    adapter = CandidateReferenceAdapter(json.loads(artifact.payload)["spec"].encode(), approved_inputs[0])
    sequence = adapter.execute_sequence([
        {"command": "add", "label": "First", "amount": 4},
        {"command": "add", "label": "Second", "amount": 4},
    ])
    assert sequence.observations[0].output["ok"] is True
    assert sequence.observations[1].output == {"ok": False, "error": "duplicate_amount"}


def test_exact_response_is_audited_before_invalid_fill_semantic_admission(approved_inputs, monkeypatch):
    run = authority(approved_inputs)
    ticket = run.prepare()
    fill = positive_non_ai_fill()
    fill["add"]["amount"].update(minimum=3, maximum=2)
    original_text = " \n" + json.dumps(fill, indent=1) + "\n "
    events = []
    merge = candidate_generation.merge_skeleton_fill

    def audit(kind, payload):
        events.append((kind, deepcopy(payload)))

    def observed_admission(skeleton, decisions):
        result_events = [payload for kind, payload in events if kind == "model_result"]
        assert len(result_events) == 1
        assert result_events[0]["response"]["content_text"] == original_text
        return merge(skeleton, decisions)

    monkeypatch.setattr(candidate_generation, "merge_skeleton_fill", observed_admission)
    budget = RunBudget(approved_inputs[0].budgets)
    with pytest.raises(EvaluationBlocked) as failed:
        run.generate(ticket, MockProvider(script=[{"content": original_text}]), budget, audit=audit)
    assert [kind for kind, _ in events] == ["model_dispatch", "model_result"]
    recorded = events[1][1]
    assert recorded["response"]["parsed"] == fill
    assert recorded["receipt"]["content_sha256"] == hashlib.sha256(original_text.encode()).hexdigest()
    assert recorded["receipt"]["outcome"] == "ok"
    assert failed.value.broker_diagnostic["failure_stage"] == "candidate_admission"
    assert budget.attempts == budget.model_calls == 1
    assert budget.input_tokens == recorded["receipt"]["input_tokens"] > 0
    assert budget.output_tokens == recorded["receipt"]["output_tokens"] > 0
    assert budget.estimated_cost_usd == budget.uncertain_cost_usd == budget._outstanding == 0


@pytest.mark.parametrize("fault_event", ["model_dispatch", "model_result"])
def test_audit_publication_failure_issues_no_artifact_and_preserves_accounting(approved_inputs, fault_event):
    run = authority(approved_inputs)
    ticket = run.prepare()
    budget = RunBudget(approved_inputs[0].budgets)
    events, calls = [], []

    def audit(kind, payload):
        events.append((kind, deepcopy(payload)))
        if kind == fault_event:
            raise OSError("NON_AI simulated private receipt publication failure")

    def respond(request):
        calls.append(request)
        return {"content": positive_non_ai_fill()}

    with pytest.raises(EvaluationBlocked) as failed:
        run.generate(ticket, MockProvider(responder=respond), budget, audit=audit)
    diagnostic = failed.value.broker_diagnostic
    assert diagnostic["failure_stage"] == "evidence_publication"
    assert diagnostic["failure_code"] == "GENERATION_AUDIT_FAILED"
    assert diagnostic["transport_attempted"] == (fault_event == "model_result")
    assert budget.attempts == 1
    assert budget.model_calls == len(calls) == (fault_event == "model_result")
    assert budget.estimated_cost_usd == budget.uncertain_cost_usd == budget._outstanding == 0
    if fault_event == "model_result":
        receipt = events[-1][1]["receipt"]
        assert budget.input_tokens == receipt["input_tokens"] > 0
        assert budget.output_tokens == receipt["output_tokens"] > 0
    else:
        assert budget.input_tokens == budget.output_tokens == 0
    with pytest.raises(EvaluationBlocked, match="replay"):
        run.generate(ticket, MockProvider(script=[{"content": positive_non_ai_fill()}]), budget)
    assert budget.attempts == 1
