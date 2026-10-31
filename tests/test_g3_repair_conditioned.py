"""Feedback-conditioned repair acceptance; synthetic controls only, zero spend.

Proves the broker amendment (synthesize-v2-repair1): repair rounds carry
ONLY the run's own aggregate evaluation (counts plus mismatch-category
names) into the next request. These tests prove loop mechanics and the
sanitization boundary — NEVER model quality. No network, credentials, or
paid calls.
"""

import copy
import json
from pathlib import Path

import pytest

from second_source.budgets import RunBudget
from second_source.candidate_generation import (
    SYNTHESIZE_PROMPT_VERSION_V2_REPAIR,
    _REPAIR_FEEDBACK_CATEGORIES,
    build_guided_repair_request,
    build_spec_skeleton,
    sanitize_repair_feedback,
)
from second_source.contracts import Budgets, Observation
from second_source.evidence import EvidenceLedger
from second_source.g3_verification import (
    EvaluationBlocked,
    PinnedEvaluatorRun,
    _admit_suite,
    _digest,
    _encode,
    _scope_digest,
)
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.model_gateway import GatewayError, MockProvider
from second_source.repair_loop import RepairAttempt, run_bounded_repair

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = json.loads(
    (ROOT / "fixtures/owned_ledger/public_contract.json").read_text(
        encoding="utf-8")
)


def base_fill():
    return {
        "error_codes": {
            "unknown_command": "unknown_command",
            "invalid_input": "invalid_input",
        },
        "add": {
            "label": {"min_length": 1, "max_length": 24, "trim": True},
            "amount": {"minimum": 1, "maximum": 100},
            "unique_field": "label",
            "unique_casefold": True,
            "label_error": "invalid_label",
            "amount_error": "invalid_amount",
            "duplicate_error": "duplicate_label",
            "respond": {"id": "id"},
        },
        "list": {"respond": {"items": "items"}},
        "total": {"respond": {"count": "count", "amount": "amount"}},
        "remove": {
            "not_found_error": "not_found",
            "respond": {"removed": "id"},
        },
    }


def renamed_list_fill():
    """Admits, but renames the list response key: the list case mismatches."""
    fill = base_fill()
    fill["list"]["respond"] = {"entries": "items"}
    return fill


def aggregate_1_1():
    return {"passed": 1, "failed": 1, "indeterminate": 0, "total": 2,
            "failure_categories": {"schema": 1}}


def _setup(cli_scope, tmp_path):
    ledger = EvidenceLedger(tmp_path / "observations")
    observation = Observation(
        observation_id="public-obs:0", sequence_id="public-obs",
        action_index=0, input_action={"command": "list"},
        output={"ok": True, "items": []},
        exit_code=0, duration_ms=0, status="ok")
    digest = ledger.store(observation)["sha256"]
    store = HypothesisStore()
    store.add_batch(validate_batch({"hypotheses": [{
        "id": "public-hypothesis", "statement": "List returns items",
        "evidence_ids": [digest]}]}, frozenset({digest})))
    raw = _encode({"suite_version": "1",
                   "scope_digest": _scope_digest(cli_scope), "cases": [
        {"case_id": "SYNTHETIC_LIST", "category": "empty",
         "actions": [{"command": "list"}]},
        {"case_id": "SYNTHETIC_TOTAL", "category": "empty",
         "actions": [{"command": "total"}]},
    ]})
    suite = _admit_suite(raw, _digest(raw), cli_scope)
    return ledger, digest, store, suite


def guided_two_case_run(cli_scope, tmp_path):
    ledger, digest, store, suite = _setup(cli_scope, tmp_path)
    return PinnedEvaluatorRun(suite, cli_scope, ledger=ledger,
                              observation_digests=(digest,), hypotheses=store,
                              synthesis="guided")


def budget():
    return RunBudget(Budgets(max_estimated_model_spend_usd=0))


def test_sanitizer_accepts_aggregate_rejects_forgery():
    from second_source import verifier
    assert (set(_REPAIR_FEEDBACK_CATEGORIES)
            == set(verifier._FAILURE_CATEGORIES))
    assert sanitize_repair_feedback(aggregate_1_1()) == aggregate_1_1()
    for forged in (
        {"passed": 1, "failed": 1, "indeterminate": 0, "total": 2,
         "failure_categories": {"schema": 1}, "case_ids": ["X"]},
        {"passed": 1, "failed": 1, "indeterminate": 0, "total": 2,
         "failure_categories": {"schema": 1},
         "expected": {"list": {"items": []}}},
        {"passed": 1, "failed": 1, "indeterminate": 0, "total": 3,
         "failure_categories": {}},
        {"passed": True, "failed": 1, "indeterminate": 0, "total": 2,
         "failure_categories": {}},
        {"passed": 1, "failed": 1, "indeterminate": 0, "total": 2,
         "failure_categories": {"unknown_category": 1}},
        {"passed": 1, "failed": 1, "indeterminate": 0, "total": 2,
         "failure_categories": {"schema": -1}},
        {"passed": 1, "failed": 1, "indeterminate": 0, "total": 2},
        [1, 1, 0, 2],
    ):
        with pytest.raises(GatewayError):
            sanitize_repair_feedback(forged)


def test_repair_builder_carries_only_aggregates():
    request = build_guided_repair_request(
        {"scope": {}, "public_commands": PUBLIC, "evidence": [],
         "hypotheses": []},
        build_spec_skeleton(PUBLIC), aggregate_1_1(), repair_round=1)
    assert request.prompt_version == SYNTHESIZE_PROMPT_VERSION_V2_REPAIR
    wire = request.model_dump(mode="json")
    user = json.loads(next(
        m["content"] for m in wire["messages"] if m["role"] == "user"))
    assert user["repair_guidance"]["round"] == 1
    assert (user["repair_guidance"]["prior_evaluation"]
            == aggregate_1_1())
    blob = json.dumps(wire, sort_keys=True)
    assert "case_id" not in blob and "SYNTHETIC" not in blob
    assert "expected" not in blob
    with pytest.raises(GatewayError):
        build_guided_repair_request({}, {}, aggregate_1_1(), repair_round=0)


def test_prepare_repair_binds_round_and_prior(cli_scope, tmp_path):
    run = guided_two_case_run(cli_scope, tmp_path)
    gateway_budget = budget()
    ticket = run.prepare()
    artifact = run.generate(
        ticket, MockProvider([{"content": renamed_list_fill()}]),
        gateway_budget)
    first = run.evaluate(artifact)
    assert first["evaluation"]["failed"] == 1
    repair_ticket = run.prepare_repair(artifact)
    assert run._repair_rounds_issued == 1
    # Single-use: the same repair ticket cannot generate twice.
    good = MockProvider([{"content": base_fill()},
                         {"content": base_fill()}])
    run.generate(repair_ticket, good, gateway_budget)
    with pytest.raises(EvaluationBlocked):
        run.generate(repair_ticket, good, gateway_budget)


def test_conditioned_repair_improves_with_lineage(cli_scope, tmp_path):
    run = guided_two_case_run(cli_scope, tmp_path)
    seen = []

    def responder(request):
        seen.append(request.model_dump(mode="json"))
        return {"content": renamed_list_fill() if len(seen) == 1
                else base_fill()}

    report = run_bounded_repair(
        run, provider=MockProvider(responder=responder),
        budget=budget(), max_rounds=2)
    assert report.verdict == "improved"
    assert report.rounds_used == 2
    assert [v.evaluation["failed"] for v in report.versions] == [1, 0]
    assert report.versions[0].artifact is not None
    assert (report.versions[1].candidate_digest
            != report.versions[0].candidate_digest)
    # The second request carried conditioned guidance, the first did not.
    first_user = json.loads(next(
        m["content"] for m in seen[0]["messages"] if m["role"] == "user"))
    second_user = json.loads(next(
        m["content"] for m in seen[1]["messages"] if m["role"] == "user"))
    assert "repair_guidance" not in first_user
    guidance = second_user["repair_guidance"]
    assert guidance["round"] == 1
    assert guidance["prior_evaluation"]["failed"] == 1
    assert seen[1]["prompt_version"] == SYNTHESIZE_PROMPT_VERSION_V2_REPAIR


def renamed_both_fill():
    """Admits, but renames list AND total response keys: both cases mismatch."""
    fill = renamed_list_fill()
    fill["total"]["respond"] = {"n": "count", "s": "amount"}
    return fill


def test_conditioned_repair_regression_is_honest(cli_scope, tmp_path):
    run = guided_two_case_run(cli_scope, tmp_path)
    report = run_bounded_repair(
        run,
        provider=MockProvider([{"content": renamed_list_fill()},
                               {"content": renamed_both_fill()}]),
        budget=budget(), max_rounds=2)
    assert report.verdict == "regressed"
    assert [v.evaluation["failed"] for v in report.versions] == [1, 2]
    from second_source.repair_loop import select_best
    assert select_best(report.versions) == 0


def test_perfect_first_version_needs_no_repair(cli_scope, tmp_path):
    run = guided_two_case_run(cli_scope, tmp_path)
    report = run_bounded_repair(
        run, provider=MockProvider([{"content": base_fill()}]),
        budget=budget(), max_rounds=2)
    assert report.verdict == "no_repair_needed"
    assert report.rounds_used == 1
    assert len(report.versions) == 1


def _full_spec():
    return json.loads(
        (ROOT / "tests/g3_fixtures/valid_candidate.json").read_text(
            encoding="utf-8"))


def _full_run(cli_scope, tmp_path):
    ledger, digest, store, suite = _setup(cli_scope, tmp_path)
    return PinnedEvaluatorRun(suite, cli_scope, ledger=ledger,
                              observation_digests=(digest,),
                              hypotheses=store)


def test_full_synthesis_refuses_prepare_repair(cli_scope, tmp_path):
    run_full = _full_run(cli_scope, tmp_path)
    ticket = run_full.prepare()
    artifact = run_full.generate(
        ticket, MockProvider([{"content": _full_spec()}]), budget())
    run_full.evaluate(artifact)
    with pytest.raises(EvaluationBlocked):
        run_full.prepare_repair(artifact)


def test_worker_main_assigns_no_builtin_names():
    """The repair branch once assigned ``round``, making it function-local
    and breaking the reference branch's builtin ``round()`` call in every
    sandboxed worker (UnboundLocalError). No _worker_main assignment may
    shadow a builtin it also calls."""
    import ast
    import builtins
    source = (ROOT / "src/second_source/candidate_adapter.py").read_text(
        encoding="utf-8")
    fn = next(node for node in ast.walk(ast.parse(source))
              if isinstance(node, ast.FunctionDef)
              and node.name == "_worker_main")
    assigned = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            assigned.add(node.id)
    called = set()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)):
            called.add(node.func.id)
    shadowed = {name for name in assigned
                if name in called and hasattr(builtins, name)}
    assert shadowed == set()


def test_unevaluated_artifact_has_no_repair(cli_scope, tmp_path):
    run = guided_two_case_run(cli_scope, tmp_path)
    ticket = run.prepare()
    artifact = run.generate(
        ticket, MockProvider([{"content": base_fill()}]), budget())
    with pytest.raises(EvaluationBlocked):
        run.prepare_repair(artifact)
