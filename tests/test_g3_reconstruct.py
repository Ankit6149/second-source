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


def _operator_inputs(tmp_path):
    from second_source.evidence import EvidenceLedger
    from second_source.reconstruct import _observe_mock_evidence

    ledger_dir = tmp_path / "ledger"
    ledger = EvidenceLedger(ledger_dir)
    digests = _observe_mock_evidence(ledger)
    store = mock_hypotheses(digests)
    hypotheses_file = tmp_path / "hypotheses.json"
    hypotheses_file.write_text(
        json.dumps({"hypotheses": [h.model_dump(mode="json") for h in store.all()]}),
        encoding="utf-8",
    )
    return ledger_dir, hypotheses_file, digests


def test_preflight_inspects_genuine_shaped_inputs_with_zero_calls(
    monkeypatch, tmp_path, capsys
):
    _no_transport(monkeypatch)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    ledger_dir, hypotheses_file, digests = _operator_inputs(tmp_path)
    run_dir = tmp_path / "preflight-run"
    code = main([
        "--mode", "preflight", "--max-usd", "0.5",
        "--ledger-dir", str(ledger_dir),
        "--hypotheses-file", str(hypotheses_file),
        "--observation-digests", ",".join(digests),
        "--seal-dir", str(tmp_path / "sealed"),
        "--run-dir", str(run_dir),
    ])
    assert code == 0
    receipt_path = run_dir / "G3_preflight.json"
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["kind"] == "G3_PREFLIGHT_INSPECTION"
    assert receipt["stop_reason"] == "preflight_ready"
    assert receipt["real"] is False
    assert receipt["evidence_artifact_count"] == len(digests)
    assert receipt["suite_digest"].startswith("sha256:")
    from second_source.evidence import EvidenceLedger
    from second_source.g3_verification import PinnedEvaluatorRun, load_sealed_suite
    from second_source.hypotheses import HypothesisStore, validate_batch
    from second_source.reconstruct import create_scope as _scope

    scope = _scope(0.5)
    suite = load_sealed_suite(
        tmp_path / "sealed" / "suite.json", receipt["suite_digest"], scope
    )
    batch = json.loads(hypotheses_file.read_text(encoding="utf-8"))
    store = HypothesisStore()
    store.add_batch(validate_batch(batch, frozenset(digests)))
    manifest = PinnedEvaluatorRun(
        suite, scope, ledger=EvidenceLedger(ledger_dir),
        observation_digests=tuple(digests), hypotheses=store,
    ).inspection_manifest()
    for key in ("approved_context_digest", "scope_digest", "suite_digest",
                "observation_registry_digest", "hypothesis_registry_digest"):
        assert receipt[key] == manifest[key], key
    # Plan digests embed a fresh run id per authority; stable identities above
    # are the cross-authority equality contract.
    assert receipt["plan_digest"].startswith("sha256:")
    emitted = receipt_path.read_text(encoding="utf-8") + capsys.readouterr().out
    assert "MODEL_API_KEY" not in emitted


def test_preflight_rejects_nonfinite_spend(monkeypatch, tmp_path):
    _no_transport(monkeypatch)
    ledger_dir, hypotheses_file, digests = _operator_inputs(tmp_path)
    for bad in ("nan", "inf", "-inf", "0", "-1"):
        code = main([
            "--mode", "preflight", f"--max-usd={bad}",
            "--ledger-dir", str(ledger_dir),
            "--hypotheses-file", str(hypotheses_file),
            "--observation-digests", ",".join(digests),
            "--seal-dir", str(tmp_path / f"sealed-{bad}"),
            "--run-dir", str(tmp_path / f"run-{bad}"),
        ])
        assert code == 2


def test_mock_run_emits_ordered_progress_and_readable_summary(tmp_path, capsys):
    run_dir = tmp_path / "progress-run"
    assert main(["--mode", "mock", "--run-dir", str(run_dir),
                 "--seal-dir", str(tmp_path / "sealed")]) == 0
    report = json.loads((run_dir / "G3_report.json").read_text(encoding="utf-8"))
    summary = report["evaluation_summary"]
    assert summary[0].startswith(
        f"{report['evaluation']['passed']}/{report['evaluation']['total']}"
    )
    assert "not AI reconstruction" in summary[0]
    stages = [
        json.loads(line)["progress"] for line in capsys.readouterr().err.splitlines()
        if line.strip().startswith('{"progress"')
    ]
    assert stages == ["evidence_ready", "inspected", "admitted",
                      "evaluated", "reported"]


def test_mock_failure_persists_sanitized_receipt(monkeypatch, tmp_path, capsys):
    import second_source.reconstruct as operator

    monkeypatch.setattr(operator, "naive_mock_spec",
                        lambda: {"shell": "FORBIDDEN_MODEL_CODE"})
    run_dir = tmp_path / "failed-run"
    code = operator.main(["--mode", "mock", "--run-dir", str(run_dir),
                          "--seal-dir", str(tmp_path / "sealed")])
    assert type(code) is int and code != 0
    report = json.loads((run_dir / "G3_report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "mock" and report.get("real") is not True
    assert "fail" in report["stop_reason"]
    assert report["usage"]["attempts"] == 1
    emitted = (run_dir / "G3_report.json").read_text(encoding="utf-8")
    emitted += capsys.readouterr().out + capsys.readouterr().err
    assert "FORBIDDEN_MODEL_CODE" not in emitted
