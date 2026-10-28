"""Zero-call G2 archive inspection: approvable, incomplete, unreadable."""

import json

from test_g2_persistence import run_recorded

from second_source.g2_inspect import inspect_run, main


def _recorded_run(cli_scope, reference, tmp_path):
    _, recorder, _, _, _ = run_recorded(
        cli_scope, reference, tmp_path, ledger_name="run/evidence"
    )
    run_dir = tmp_path / "run"
    recorder.write(run_dir)
    return run_dir


def test_inspect_approvable_run(cli_scope, reference, tmp_path, capsys):
    run_dir = _recorded_run(cli_scope, reference, tmp_path)
    assert main([str(run_dir)]) == 0
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["kind"] == "G2_INSPECTION_VERDICT"
    assert verdict["approvable"] is True
    assert verdict["completeness_gaps"] == []
    assert verdict["ledger_coverage_missing"] == []
    assert verdict["model_receipts"] >= 2


def test_inspect_stripped_manifest_not_approvable(
    cli_scope, reference, tmp_path, capsys
):
    run_dir = _recorded_run(cli_scope, reference, tmp_path)
    manifest_path = run_dir / "g2_manifest.json"
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["model_receipts"] = []
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")
    assert main([str(run_dir)]) == 1
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["approvable"] is False
    assert verdict["completeness_gaps"]


def test_inspect_missing_archive_blocked(tmp_path, capsys):
    assert main([str(tmp_path / "absent")]) == 2
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["approvable"] is False


def test_inspect_return_matches_function(cli_scope, reference, tmp_path):
    run_dir = _recorded_run(cli_scope, reference, tmp_path)
    verdict = inspect_run(run_dir)
    assert verdict["approvable"] is True
    assert verdict["stop_reason"] == "stalled"
