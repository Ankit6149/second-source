"""Zero-call view of the sole discovery journal, with honest NON_AI labels."""
import json
import urllib.request

import pytest

from test_g2_persistence_roundtrip import run_recorded
from test_g2_verifier_persistence import read_events, reseal_non_ai_fixture
from second_source.g2_inspect import inspect_run, main
from second_source.model_gateway import MetaProvider


@pytest.fixture(autouse=True)
def no_inference(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")

    def forbidden(*args, **kwargs):
        raise AssertionError("Archive inspection authorizes no provider transport")

    monkeypatch.setattr(MetaProvider, "complete", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def _recorded_run(cli_scope, reference, tmp_path):
    _, run, _, _, _ = run_recorded(cli_scope, reference, tmp_path)
    return run


def test_inspect_complete_mock_never_approves_real_input(cli_scope, reference, tmp_path, capsys):
    run_dir = _recorded_run(cli_scope, reference, tmp_path)
    assert main([str(run_dir)]) == 0
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["kind"] == "G2_INSPECTION_VERDICT"
    assert verdict["complete"] is True and verdict["origin"] == "mock"
    assert verdict["approvable"] is False and verdict["real_input_eligible"] is False
    assert verdict["completeness_gaps"] == verdict["ledger_coverage_missing"] == []
    assert verdict["model_receipts"] >= 2
    assert verdict["provider_calls"] == 0 and verdict["execution_resume_supported"] is False


def test_inspect_stripped_archive_fails_closed(cli_scope, reference, tmp_path, capsys):
    run_dir = _recorded_run(cli_scope, reference, tmp_path)
    events = read_events(run_dir)
    next(e["payload"] for e in events if e["kind"] == "terminal")["model_receipts"] = []
    fixture_witness = reseal_non_ai_fixture(run_dir, events)
    assert main([str(run_dir), "--receipt-sha256", fixture_witness]) == 2
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["approvable"] is False and verdict["complete"] is False
    assert verdict["real_input_eligible"] is False and verdict["provider_calls"] == 0
    assert verdict["error"] == "INVALID_OR_UNREADABLE_ARCHIVE"


def test_inspect_missing_archive_blocked(tmp_path, capsys):
    absent = tmp_path / "absent"
    assert main([str(absent)]) == 2
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["approvable"] is False and verdict["real_input_eligible"] is False
    assert not absent.exists()


def test_inspect_return_matches_function_with_pinned_mock_witness(cli_scope, reference, tmp_path, capsys):
    run_dir = _recorded_run(cli_scope, reference, tmp_path)
    witness = inspect_run(run_dir)["receipt_sha256"]
    expected = inspect_run(run_dir, witness)
    assert main([str(run_dir), "--receipt-sha256", witness]) == 0
    verdict = json.loads(capsys.readouterr().out)
    assert verdict == expected
    assert verdict["receipt_pinned"] is True and verdict["complete"] is True
    assert verdict["approvable"] is False and verdict["real_input_eligible"] is False
    assert verdict["stop_reason"] == "stalled"
