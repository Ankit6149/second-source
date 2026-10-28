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


def test_pending_dispatch_exposes_reserved_uncertainty_without_claiming_completion(tmp_path, monkeypatch):
    """NON_AI fake-provider snapshot before result/settlement, with no HTTP."""
    from second_source.budgets import RunBudget
    from second_source.evidence import EvidenceLedger
    from second_source.g2_persistence import DiscoveryJournal, inspect_run as inspect_archive
    from second_source.live_experiment import _discovery_manifest, create_scope
    from second_source.model_gateway import ModelGateway, ModelRequest

    run = tmp_path / "pending-non-ai-fixture"
    run.mkdir()
    EvidenceLedger(run / "evidence")
    scope = create_scope(.25, 1)
    journal = DiscoveryJournal(run, _discovery_manifest(scope, "real", 1))
    budget = RunBudget(scope.budgets)
    snapshots = []

    def fake_complete(self, request):
        snapshots.append((inspect_archive(run), inspect_run(run)))
        raise KeyboardInterrupt("NON_AI interruption fixture; no transport")

    monkeypatch.setattr(MetaProvider, "complete", fake_complete)
    gateway = ModelGateway(MetaProvider("noncredential-fixture"), budget, audit=journal.append)
    with pytest.raises(KeyboardInterrupt):
        gateway.generate(ModelRequest(
            stage="hypothesize", messages=({"role": "user", "content": "NON_AI pending snapshot"},),
            estimated_input_tokens=100, max_output_tokens=20,
        ))
    archive, verdict = snapshots[0]
    assert verdict["state"] == "interrupted" and verdict["complete"] is False
    assert verdict["approvable"] is False and verdict["real_input_eligible"] is False
    assert verdict["budget"]["uncertain_cost_usd"] == 0
    assert archive["pending_attempt"]["attempt"] == 1
    assert verdict["pending_attempt"] == archive["pending_attempt"]
    assert verdict["pending_uncertain_cost_usd"] == pytest.approx(.00021)
    assert verdict["pending_uncertain_cost_usd"] == archive["pending_uncertain_cost_usd"]
