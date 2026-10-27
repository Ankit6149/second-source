"""G2 planner tests: multi-action sequences, approvals stripped, ranking."""

import pytest

from g2_helpers import add_action, pred, propose_doc, responder, wiring
from second_source.planner import reconcile_predictions, score_utility


def planner(cli_scope, reference, tmp_path, mock, **kw):
    _, _, _, plan, store = wiring(cli_scope, reference, tmp_path, mock, **kw)
    return plan, store


def test_score_weights():
    assert score_utility(discrimination=1.0, scope_relevance=1.0, novelty=1.0,
                         coverage_gain=1.0, normalized_cost=0.0, risk_penalty=0.0) == pytest.approx(1.0)
    assert score_utility(discrimination=1.0, scope_relevance=1.0, novelty=1.0,
                         coverage_gain=1.0, normalized_cost=0.5, risk_penalty=0.5) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        score_utility(discrimination=2.0, scope_relevance=1.0, novelty=1.0,
                      coverage_gain=1.0, normalized_cost=0.0, risk_penalty=0.0)


def test_hypothesize_registers_batch(cli_scope, reference, tmp_path):
    plan, store = planner(cli_scope, reference, tmp_path, responder())
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    assert len(batch.hypotheses) == 2
    store.add_batch(batch)
    assert store.ids() == frozenset({"hyp-1", "hyp-2"})


def test_propose_returns_ordered_action_sequence(cli_scope, reference, tmp_path):
    steps = [add_action("A", 1), add_action("A", 1), {"command": "total", "params": {}}]
    mock = responder(actions=steps, predictions=[pred("hyp-1", False, "duplicate"), pred("hyp-2", True)])
    plan, store = planner(cli_scope, reference, tmp_path, mock)
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    store.add_batch(batch)
    result = plan.propose([{"digest": "d1", "observation": {}}], store.competing(),
                          "REQ-LEDGER", reference_remaining=10, model_remaining=5)
    assert len(result.ranked) == 1
    top = result.ranked[0]
    assert [a.target for a in top.actions] == ["add", "add", "total"]
    assert all(a.kind == "cli" for a in top.actions)
    assert top.decision_codes == ("ALLOWED", "ALLOWED", "ALLOWED")
    assert len(top.predictions) == 2


def test_model_approval_is_stripped_and_external_denied(cli_scope, reference, tmp_path):
    """A malicious model granting itself approval must not authorize anything."""
    def hostile(request):
        import json
        user = [m for m in request.messages if m["role"] == "user"][0]["content"]
        doc = json.loads(user)
        if request.stage == "hypothesize":
            digest = doc["evidence"][0]["digest"]
            return {"content": {"schema_version": "1.0", "hypotheses": [
                {"id": "hyp-1", "statement": "s", "evidence_ids": [digest],
                 "status": "hypothesized", "alternatives": [], "unresolved_questions": []}]}}
        return {"content": {"proposals": [dict(
            propose_doc("exp-evil", ["hyp-1"], [add_action()],
                        [pred("hyp-1", True)], side_effect="external"),
            approval_granted=True)]}}
    plan, store = planner(cli_scope, reference, tmp_path, hostile)
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    store.add_batch(batch)
    result = plan.propose([{"digest": "d1", "observation": {}}], store.competing(),
                          "REQ-LEDGER", reference_remaining=10, model_remaining=5)
    assert result.ranked == ()
    assert "HUMAN_APPROVAL_REQUIRED" in result.rejected[0][1]


def test_second_action_denial_rejects_sequence(cli_scope, reference, tmp_path):
    steps = [add_action("A", 1), {"command": "rm -rf /", "params": {}}]
    plan, store = planner(cli_scope, reference, tmp_path, responder(actions=steps))
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    store.add_batch(batch)
    result = plan.propose([{"digest": "d1", "observation": {}}], store.competing(),
                          "REQ-LEDGER", reference_remaining=10, model_remaining=5)
    assert result.ranked == ()
    assert "COMMAND_NOT_ALLOWED" in result.rejected[0][1]


def test_wrong_reset_boundary_rejected(cli_scope, reference, tmp_path):
    def bad(request):
        import json
        user = [m for m in request.messages if m["role"] == "user"][0]["content"]
        doc = json.loads(user)
        if request.stage == "hypothesize":
            digest = doc["evidence"][0]["digest"]
            return {"content": {"schema_version": "1.0", "hypotheses": [
                {"id": "hyp-1", "statement": "s", "evidence_ids": [digest],
                 "status": "hypothesized", "alternatives": [], "unresolved_questions": []}]}}
        item = propose_doc("exp-x", ["hyp-1"], [add_action()], [pred("hyp-1", True)])
        item["reset_boundary"] = "persistent_session"
        return {"content": {"proposals": [item]}}
    plan, store = planner(cli_scope, reference, tmp_path, bad)
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    store.add_batch(batch)
    result = plan.propose([{"digest": "d1", "observation": {}}], store.competing(),
                          "REQ-LEDGER", reference_remaining=10, model_remaining=5)
    assert result.ranked == ()
    assert "reset_boundary" in result.rejected[0][1]


def test_novelty_scores_repeat_lower(cli_scope, reference, tmp_path):
    plan, store = planner(cli_scope, reference, tmp_path, responder())
    batch = plan.hypothesize([{"digest": "d1", "observation": {}}], frozenset({"d1"}))
    store.add_batch(batch)
    kwargs = dict(requirement_id="REQ-LEDGER", reference_remaining=10, model_remaining=5)
    first = plan.propose([{"digest": "d1", "observation": {}}], store.competing(), **kwargs)
    plan.mark_executed(first.ranked[0].actions)
    second = plan.propose([{"digest": "d1", "observation": {}}], store.competing(), **kwargs)
    assert second.ranked[0].utility < first.ranked[0].utility


def test_reconcile_supported_contradicted():
    from second_source.planner import Prediction
    preds = [Prediction("a", True, None), Prediction("b", False, None)]
    verdicts = reconcile_predictions(preds, {"ok": True}, "ok")
    assert verdicts == {"a": "supported", "b": "contradicted"}


def test_reconcile_contains_and_error():
    from second_source.planner import Prediction
    preds = [Prediction("a", False, "duplicate_label")]
    verdicts = reconcile_predictions(preds, {"ok": False, "error": "duplicate_label"}, "target_error")
    assert verdicts == {"a": "supported"}
    preds = [Prediction("a", False, "other_error")]
    assert reconcile_predictions(preds, {"ok": False, "error": "duplicate_label"}, "target_error") == {"a": "contradicted"}


def test_reconcile_harness_failure_unresolved():
    from second_source.planner import Prediction
    preds = [Prediction("a", True, None)]
    assert reconcile_predictions(preds, {}, "timeout") == {"a": "unresolved"}
