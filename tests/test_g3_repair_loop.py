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
    assert [(v["round"], v["evaluation"]["failed"]) for v in history["versions"]] == [(1, 3), (2, 3)]
    assert report["report_labels"].startswith("MOCK_")


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
