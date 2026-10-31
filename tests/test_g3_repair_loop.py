"""Bounded repair loop acceptance; synthetic controls only, zero spend.

A scripted MockProvider queue stands in for revised fills. These tests prove
loop mechanics (same-denominator verdicts, provenance retention, bounded
stops) — NEVER model quality. No network, credentials, or paid calls.
"""
import copy
import json
from pathlib import Path

import pytest

from second_source.budgets import RunBudget
from second_source.contracts import Budgets, Observation
from second_source.evidence import EvidenceLedger
from second_source.g3_verification import PinnedEvaluatorRun, _digest, _encode, _scope_digest, _admit_suite
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.model_gateway import MockProvider
from second_source.repair_loop import run_bounded_repair

ROOT = Path(__file__).resolve().parents[1]
CONTROL = json.loads((ROOT / "tests/g3_fixtures/valid_candidate.json").read_text(encoding="utf-8"))


def good_content():
    return copy.deepcopy(CONTROL)


def mid_content():
    """Loads, but renames the list response key: list case mismatches."""
    spec = copy.deepcopy(CONTROL)
    spec["commands"]["list"]["respond"] = {"entries": "items"}
    return spec


def bad_content():
    """Loads, but renames list AND total response keys: both cases mismatch."""
    spec = copy.deepcopy(CONTROL)
    spec["commands"]["list"]["respond"] = {"entries": "items"}
    spec["commands"]["total"]["respond"] = {"n": "count", "s": "amount"}
    return spec


@pytest.fixture
def two_case_run(cli_scope, tmp_path):
    ledger = EvidenceLedger(tmp_path / "observations")
    observation = Observation(observation_id="public-obs:0", sequence_id="public-obs",
        action_index=0, input_action={"command": "list"}, output={"ok": True, "items": []},
        exit_code=0, duration_ms=0, status="ok")
    digest = ledger.store(observation)["sha256"]
    store = HypothesisStore()
    store.add_batch(validate_batch({"hypotheses": [{"id": "public-hypothesis",
        "statement": "List returns items", "evidence_ids": [digest]}]}, frozenset({digest})))
    raw = _encode({"suite_version": "1", "scope_digest": _scope_digest(cli_scope), "cases": [
        {"case_id": "SYNTHETIC_LIST", "category": "empty", "actions": [{"command": "list"}]},
        {"case_id": "SYNTHETIC_TOTAL", "category": "empty", "actions": [{"command": "total"}]},
    ]})
    suite = _admit_suite(raw, _digest(raw), cli_scope)
    run = PinnedEvaluatorRun(suite, cli_scope, ledger=ledger,
        observation_digests=(digest,), hypotheses=store)
    return run


def budget():
    return RunBudget(Budgets(max_estimated_model_spend_usd=0))


def provider_for(*contents):
    return MockProvider([{"content": content} for content in contents])


def test_repair_improves_and_keeps_both_versions(two_case_run):
    report = run_bounded_repair(two_case_run, provider=provider_for(bad_content(), good_content()),
                                budget=budget(), max_rounds=2)
    assert report.verdict == "improved"
    assert report.rounds_used == 2 and report.stop_reason == "repaired_to_perfect"
    assert [v.evaluation["failed"] for v in report.versions] == [2, 0]
    assert {v.evaluation["total"] for v in report.versions} == {2}
    assert report.versions[0].candidate_digest != report.versions[1].candidate_digest
    for attempt in report.versions:
        assert attempt.feedback["passed"] == attempt.evaluation["passed"]
        assert attempt.origin == "mock" and attempt.response_id.startswith("mock-")


def test_perfect_first_candidate_takes_no_second_attempt(two_case_run):
    calls = []
    def responder(request):
        calls.append(True)
        return {"content": good_content()}
    report = run_bounded_repair(two_case_run, provider=MockProvider(responder=responder),
                                budget=budget(), max_rounds=3)
    assert report.verdict == "no_repair_needed" and report.rounds_used == 1
    assert calls == [True] and len(report.versions) == 1


def test_repair_regression_is_reported_not_hidden(two_case_run):
    report = run_bounded_repair(two_case_run, provider=provider_for(mid_content(), bad_content()),
                                budget=budget(), max_rounds=2)
    assert report.verdict == "regressed"
    assert [v.evaluation["failed"] for v in report.versions] == [1, 2]


def test_repair_no_change_is_reported(two_case_run):
    report = run_bounded_repair(two_case_run, provider=provider_for(mid_content(), mid_content()),
                                budget=budget(), max_rounds=2)
    assert report.verdict == "no_change" and report.stop_reason == "rounds_exhausted"


def test_exhausted_provider_script_stops_with_history(two_case_run):
    report = run_bounded_repair(two_case_run, provider=provider_for(mid_content()),
                                budget=budget(), max_rounds=2)
    assert report.verdict == "unrepaired" and report.stop_reason == "broker_blocked"
    assert len(report.versions) == 1
    assert report.broker_diagnostic is None or isinstance(report.broker_diagnostic, dict)


def test_invalid_revised_output_stops_without_versions(two_case_run):
    report = run_bounded_repair(two_case_run, provider=provider_for({"bogus": 1}),
                                budget=budget(), max_rounds=2)
    assert report.verdict == "unrepaired" and report.versions == []
    assert report.stop_reason == "broker_blocked"


def test_max_rounds_is_validated(two_case_run):
    with pytest.raises(ValueError):
        run_bounded_repair(two_case_run, provider=provider_for(good_content()),
                           budget=budget(), max_rounds=0)


def _mock_report(monkeypatch, tmp_path, *extra):
    from second_source import reconstruct as operator
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")
    run_dir = tmp_path / "run"
    seal_dir = tmp_path / "sealed"
    code = operator.main(["--mode", "mock", "--run-dir", str(run_dir),
                          "--seal-dir", str(seal_dir), *extra])
    assert code == 0
    return json.loads((run_dir / "G3_report.json").read_text(encoding="utf-8"))


def test_operator_mock_defaults_to_no_repair(monkeypatch, tmp_path):
    report = _mock_report(monkeypatch, tmp_path)
    assert report["repair_history"] is None
    assert report["stop_reason"] == "completed_mock_run"


def test_operator_mock_guided_repair_records_honest_retry(monkeypatch, tmp_path):
    report = _mock_report(monkeypatch, tmp_path, "--synthesis", "guided",
                          "--repair-rounds", "2")
    history = report["repair_history"]
    assert history["verdict"] == "no_change"
    assert history["stop_reason"] == "rounds_exhausted"
    assert [(v["round"], v["evaluation"]["failed"]) for v in history["versions"]] == [(0, 3), (1, 3), (2, 3)]
    assert history["versions"][0]["candidate_digest"] == report["initial_candidate_digest"]
    assert report["selected"]["version"] == "initial"
    assert report["selection_policy"] == "best_failed_then_indeterminate_then_earliest"
    assert report["evaluation"] == report["initial_evaluation"]
    assert report["report_labels"].startswith("MOCK_")


def _seed_attempt(evaluation, digest="digest-seed"):
    from second_source.repair_loop import RepairAttempt
    return RepairAttempt(round=0, candidate_digest=digest, response_id="mock-seed",
                         origin="mock", evaluation=dict(evaluation),
                         feedback={"passed": evaluation["passed"],
                                   "failed": evaluation["failed"],
                                   "indeterminate": evaluation["indeterminate"],
                                   "total": evaluation["total"],
                                   "failure_categories": {}})


class FakeRun:
    """Duck-typed broker stand-in with scripted (evaluation, feedback) pairs."""

    def __init__(self, script):
        self.script = [(dict(evaluation), dict(feedback)) for evaluation, feedback in script]
        self.calls = 0
        self.seen = []

    def prepare(self):
        return {"ticket": self.calls}

    def generate(self, ticket, provider, budget):
        self.calls += 1
        return {"artifact": self.calls}

    def evaluate(self, artifact, claim="TRUSTED_CONTROL"):
        evaluation, _ = self.script[artifact["artifact"] - 1]
        return {"origin": {"candidate_digest": f"digest-{artifact['artifact']}",
                           "response_id": f"r-{artifact['artifact']}", "origin": "mock"},
                "evaluation": dict(evaluation)}

    def repair_feedback(self, artifact):
        return dict(self.script[artifact["artifact"] - 1][1])


def _counts(passed, failed, indeterminate, total):
    return {"passed": passed, "failed": failed,
            "indeterminate": indeterminate, "total": total}


def test_seed_baseline_anchors_improvement_verdict(two_case_run):
    from second_source.repair_loop import run_bounded_repair
    seed = _seed_attempt(_counts(1, 1, 0, 2), digest="digest-seed")
    report = run_bounded_repair(two_case_run, provider=provider_for(good_content()),
                                budget=budget(), max_rounds=1, seed=seed)
    assert report.verdict == "improved"
    assert [v.round for v in report.versions] == [0, 1]
    assert report.versions[0].candidate_digest == "digest-seed"
    assert report.rounds_used == 1


def test_seed_perfect_takes_no_new_attempt(two_case_run):
    from second_source.repair_loop import run_bounded_repair
    calls = []
    def responder(request):
        calls.append(True)
        return {"content": good_content()}
    seed = _seed_attempt(_counts(2, 0, 0, 2))
    report = run_bounded_repair(two_case_run, provider=MockProvider(responder=responder),
                                budget=budget(), max_rounds=3, seed=seed)
    assert report.verdict == "no_repair_needed"
    assert report.stop_reason == "baseline_perfect"
    assert calls == [] and report.rounds_used == 0


def test_strict_counts_and_perfect_semantics():
    from second_source.repair_loop import checked_counts, is_perfect
    assert checked_counts(_counts(2, 0, 0, 2)) == (2, 0, 0, 2)
    assert is_perfect(_counts(2, 0, 0, 2)) is True
    # Zero failures with an open case is NOT perfect. An empty denominator
    # is vacuously perfect here; empty suites are rejected at suite admission.
    assert is_perfect(_counts(1, 0, 1, 2)) is False
    assert is_perfect(_counts(0, 0, 0, 0)) is True
    for bad in ({"passed": True, "failed": 0, "indeterminate": 0, "total": 1},
                {"passed": -1, "failed": 0, "indeterminate": 0, "total": 0},
                {"passed": 1, "failed": 1, "indeterminate": 0, "total": 1},
                {"passed": 2, "failed": 0, "indeterminate": 0, "total": 1},
                {"passed": 1, "failed": 0, "indeterminate": 0}):
        with pytest.raises(ValueError):
            checked_counts(bad)


def test_indeterminate_outcome_drives_retry_not_success():
    from second_source.repair_loop import run_bounded_repair
    script = [(_counts(1, 0, 1, 2), _counts(1, 0, 1, 2)),
              (_counts(2, 0, 0, 2), _counts(2, 0, 0, 2))]
    report = run_bounded_repair(FakeRun(script), provider=object(), budget=object(),
                                max_rounds=2)
    assert report.verdict == "improved"
    assert report.stop_reason == "repaired_to_perfect"


def test_select_best_never_promotes_regression():
    from second_source.repair_loop import RepairAttempt, select_best
    def attempt(round, failed, indeterminate=0):
        return RepairAttempt(round=round, candidate_digest=f"d{round}", response_id=f"r{round}",
                             origin="mock",
                             evaluation=_counts(2 - failed - indeterminate, failed,
                                                indeterminate, 2),
                             feedback={})
    assert select_best([attempt(0, 0), attempt(1, 2), attempt(2, 1)]) == 0
    assert select_best([attempt(0, 1), attempt(1, 1)]) == 0
    assert select_best([attempt(0, 1), attempt(1, 0)]) == 1
    with pytest.raises(ValueError):
        select_best([])


def test_forged_broker_artifact_cannot_score(two_case_run):
    from second_source.g3_verification import BrokerArtifact, EvaluationBlocked
    ticket = two_case_run.prepare()
    artifact = two_case_run.generate(ticket, provider_for(good_content()), budget())
    forged = BrokerArtifact(payload=b'{"kind":"CANDIDATE_ORIGIN","forged":true}',
                            signature=artifact.signature)
    with pytest.raises(EvaluationBlocked):
        two_case_run.evaluate(forged)


def test_broker_attempt_cap_is_authoritative(cli_scope, tmp_path):
    from second_source.contracts import Budgets
    from second_source.evidence import EvidenceLedger
    from second_source.g3_verification import (
        PinnedEvaluatorRun, _digest, _encode, _scope_digest, _admit_suite,
    )
    from second_source.hypotheses import HypothesisStore, validate_batch
    from second_source.repair_loop import run_bounded_repair
    tight = cli_scope.model_copy(update={"budgets": Budgets(max_model_calls=1)})
    ledger = EvidenceLedger(tmp_path / "observations")
    observation = Observation(observation_id="public-obs:0", sequence_id="public-obs",
        action_index=0, input_action={"command": "list"}, output={"ok": True, "items": []},
        exit_code=0, duration_ms=0, status="ok")
    digest = ledger.store(observation)["sha256"]
    store = HypothesisStore()
    store.add_batch(validate_batch({"hypotheses": [{"id": "public-hypothesis",
        "statement": "List returns items", "evidence_ids": [digest]}]}, frozenset({digest})))
    raw = _encode({"suite_version": "1", "scope_digest": _scope_digest(tight), "cases": [
        {"case_id": "SYNTHETIC_LIST", "category": "empty", "actions": [{"command": "list"}]},
    ]})
    suite = _admit_suite(raw, _digest(raw), tight)
    run = PinnedEvaluatorRun(suite, tight, ledger=ledger,
        observation_digests=(digest,), hypotheses=store)
    report = run_bounded_repair(run, provider=provider_for(mid_content(), mid_content(), mid_content()),
                                budget=RunBudget(Budgets(max_model_calls=1,
                                                         max_estimated_model_spend_usd=0)),
                                max_rounds=3)
    assert report.rounds_used == 1 and report.stop_reason == "broker_blocked"
    assert report.verdict == "unrepaired" and len(report.versions) == 1


def test_interruption_propagates_with_prior_versions_observed(two_case_run):
    from second_source.repair_loop import run_bounded_repair
    seen = []
    calls = []
    def responder(request):
        calls.append(True)
        if len(calls) > 1:
            raise KeyboardInterrupt()
        return {"content": mid_content()}
    with pytest.raises(KeyboardInterrupt):
        run_bounded_repair(two_case_run, provider=MockProvider(responder=responder),
                            budget=budget(), max_rounds=3,
                            on_version=lambda attempt, artifact: seen.append(attempt.round))
    assert seen == [0] and len(calls) == 2


def test_operator_repair_versions_are_replayable(monkeypatch, tmp_path):
    from second_source.candidate_adapter import CandidateReferenceAdapter
    from second_source import reconstruct as operator
    report = _mock_report(monkeypatch, tmp_path, "--synthesis", "guided", "--repair-rounds", "1")
    history = report["repair_history"]
    assert [v["round"] for v in history["versions"]] == [0, 1]
    scope = operator.create_scope(0)
    for version in history["versions"]:
        files = version["files"]
        raw = (tmp_path / "run" / files["candidate"]).read_bytes()
        adapter = CandidateReferenceAdapter(raw, scope)
        assert adapter.spec_digest == version["candidate_digest"]
        envelope = json.loads((tmp_path / "run" / files["envelope"]).read_text(encoding="utf-8"))
        assert envelope["spec_digest"] == version["candidate_digest"]
        assert json.loads((tmp_path / "run" / files["receipt"]).read_text(encoding="utf-8"))["evaluation"] == version["evaluation"]


def test_repair_rounds_carry_no_sealed_or_reference_material(two_case_run):
    """P1 boundary proof: retry wires equal the frozen initial wire and carry
    no sealed case IDs, suite paths, reference source, or gold markers; the
    aggregate feedback likewise exposes no case identities."""
    from second_source.repair_loop import run_bounded_repair
    import json as _json
    wires = []
    def responder(request):
        wires.append(_json.dumps(request.model_dump(mode="json"), sort_keys=True))
        return {"content": mid_content()}
    report = run_bounded_repair(two_case_run, provider=MockProvider(responder=responder),
                                budget=budget(), max_rounds=2)
    assert report.rounds_used == 2 and len(wires) == 2
    assert wires[0] == wires[1]
    for wire in wires:
        for marker in ("SYNTHETIC_LIST", "SYNTHETIC_TOTAL", "reference.py",
                       "owned_ledger", "GOLD", "sealed"):
            assert marker not in wire, marker
    for attempt in report.versions:
        blob = _json.dumps(attempt.feedback, sort_keys=True)
        assert "SYNTHETIC_LIST" not in blob and "SYNTHETIC_TOTAL" not in blob


def test_operator_improved_retry_aligns_every_primary_field(monkeypatch, tmp_path, capsys):
    """Genuinely improved MOCK retry: every top-level field must describe it."""
    from second_source import reconstruct as operator
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")
    proposals = [operator.naive_mock_spec(), good_content()]
    monkeypatch.setattr(operator, "naive_mock_spec", lambda: proposals.pop(0))
    run_dir = tmp_path / "run"
    seal_dir = tmp_path / "sealed"
    code = operator.main(["--mode", "mock", "--run-dir", str(run_dir),
                          "--seal-dir", str(seal_dir), "--repair-rounds", "2"])
    assert code == 0
    report = json.loads((run_dir / "G3_report.json").read_text(encoding="utf-8"))
    history = report["repair_history"]
    assert history["verdict"] == "improved"
    initial, final = history["versions"][0], history["versions"][-1]
    assert initial["evaluation"]["failed"] > 0
    assert final["evaluation"] == {"passed": 25, "failed": 0, "indeterminate": 0,
                                   "total": 25, "failure_categories": {}}
    assert final["candidate_digest"] != initial["candidate_digest"]
    assert report["selected"]["version"] == f"repair-{final['round']}"
    # Every primary field describes the SAME selected candidate.
    assert report["evaluation"] == final["evaluation"]
    assert report["spec_digest"] == final["candidate_digest"]
    assert report["response_id"] == final["response_id"]
    assert report["candidate_artifact"] == final["files"]["candidate"]
    assert report["broker_artifact"] == final["files"]["envelope"]
    assert report["evaluation_receipt"]["evaluation"] == final["evaluation"]
    assert report["evaluation_receipt"]["origin"]["candidate_digest"] == final["candidate_digest"]
    assert report["evaluation_summary"][0].startswith("25/25 sealed cases passed")
    progress = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.startswith('{')]
    evaluated = [event for event in progress if event.get("progress") == "evaluated"]
    assert len(evaluated) == 1 and evaluated[0]["detail"] == "25/25 sealed cases"
    # The original stays preserved as immutable initial evidence.
    assert report["initial_evaluation"] == initial["evaluation"]
    assert report["initial_evaluation_receipt"]["evaluation"] == initial["evaluation"]
    assert report["initial_candidate_digest"] == initial["candidate_digest"]


def test_operator_real_mode_rejects_repair_without_authorization(monkeypatch, tmp_path, capsys):
    from second_source import reconstruct as operator
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    code = operator.main(["--mode", "real", "--repair-rounds", "1",
                          "--run-dir", str(tmp_path / "run")])
    assert code != 0
    assert "real-mode repair needs a separate owner authorization" in capsys.readouterr().err


def test_operator_mock_rejects_out_of_range_repair_rounds(monkeypatch, tmp_path):
    from second_source import reconstruct as operator
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")
    code = operator.main(["--mode", "mock", "--run-dir", str(tmp_path / "run"),
                          "--seal-dir", str(tmp_path / "sealed"), "--repair-rounds", "5"])
    assert code == 2
