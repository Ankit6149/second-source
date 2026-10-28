"""Reconstruct operator workflow: mock end-to-end plus real-mode fail-closed gates."""

import json

import pytest

from second_source.model_gateway import DEFAULT_FORBIDDEN_MARKERS
from second_source.reconstruct import (
    create_scope,
    main,
    mock_hypotheses,
    naive_mock_spec,
)


def test_naive_mock_spec_loads_under_scope():
    from second_source.candidate_spec import load_candidate

    loaded = load_candidate(naive_mock_spec(), create_scope(0.0))
    assert loaded.digest.startswith("sha256:")


def test_scope_matches_public_manifest():
    import json as _json
    from pathlib import Path as _Path

    public = _json.loads(
        (_Path(__file__).resolve().parents[1]
         / "fixtures" / "owned_ledger" / "public_contract.json").read_text()
    )
    scope = create_scope(0.0)
    assert set(public["commands"]) == set(scope.observation.allowed_commands)


def test_mock_run_end_to_end(tmp_path):
    run_dir = tmp_path / "g3test"
    assert main(["--mode", "mock", "--run-dir", str(run_dir)]) == 0
    report_path = run_dir / "G3_report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["kind"] == "G3_RECONSTRUCT_RUN_REPORT"
    assert report["mode"] == "mock"
    assert report["origin"] == "mock"
    assert report["real"] is False
    assert report["stop_reason"] == "completed_mock_run"
    evaluation = report["evaluation"]
    assert evaluation["total"] == 25
    assert (evaluation["passed"] + evaluation["failed"]
            + evaluation["indeterminate"]) == 25
    assert report["spec_digest"].startswith("sha256:")
    assert report["usage"]["estimated_cost_usd"] == 0.0
    assert report["usage"]["uncertain_cost_usd"] == 0.0
    assert "MOCK" in report["report_labels"]
    blob = report_path.read_text(encoding="utf-8")
    for marker in DEFAULT_FORBIDDEN_MARKERS:
        assert marker not in blob
    assert "MODEL_API_KEY" not in blob


def test_mock_rejects_spend_flags(tmp_path):
    assert main(["--mode", "mock", "--max-usd", "1",
                 "--run-dir", str(tmp_path / "x")]) == 2


def test_unknown_fixture_rejected(tmp_path):
    assert main(["--fixture", "nope", "--run-dir",
                 str(tmp_path / "x")]) == 2


def _no_transport(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("provider transport must not be reached")

    monkeypatch.setattr("second_source.reconstruct.MetaProvider", _boom)


def test_real_blocked_without_env(monkeypatch, tmp_path):
    _no_transport(monkeypatch)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("SECOND_SOURCE_MAX_RUN_USD", raising=False)
    assert main(["--mode", "real", "--max-usd", "0.5",
                 "--run-dir", str(tmp_path / "x")]) == 2


def test_real_blocked_without_confirmation(monkeypatch, tmp_path):
    _no_transport(monkeypatch)
    monkeypatch.setenv("MODEL_API_KEY", "test-key-000")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.5")
    assert main(["--mode", "real", "--max-usd", "0.5",
                 "--run-dir", str(tmp_path / "x")]) == 2


def test_real_blocked_without_context_pin(monkeypatch, tmp_path):
    _no_transport(monkeypatch)
    monkeypatch.setenv("MODEL_API_KEY", "test-key-000")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.5")
    assert main(["--mode", "real", "--max-usd", "0.5", "--confirm-real-run",
                 "--run-dir", str(tmp_path / "x")]) == 2


def test_real_blocked_above_spend_cap(monkeypatch, tmp_path):
    _no_transport(monkeypatch)
    monkeypatch.setenv("MODEL_API_KEY", "test-key-000")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "5")
    assert main(["--mode", "real", "--max-usd", "5", "--confirm-real-run",
                 "--operator-context-pin", "sha256:" + "0" * 64,
                 "--run-dir", str(tmp_path / "x")]) == 2
