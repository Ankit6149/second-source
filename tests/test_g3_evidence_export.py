"""Exporter acceptance: sanitized bundle, private receipts excluded."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_g3_evidence.py"


def make_run(directory):
    run = Path(directory) / "run-1"
    run.mkdir(parents=True)
    (run / "G3_report.json").write_text(json.dumps({
        "kind": "G3_RECONSTRUCT_RUN_REPORT",
        "run_id": "run-1",
        "origin": "real",
        "synthesis": "guided",
        "spec_digest": "sha256:abc",
        "suite_digest": "sha256:def",
    }), encoding="utf-8")
    (run / "candidate.v1.json").write_text(
        '{"spec_version": "1"}', encoding="utf-8")
    (run / "broker-artifact.v1.json").write_text(
        '{"kind": "BROKER_ARTIFACT"}', encoding="utf-8")
    (run / "generation-result.v1.private.json").write_text(
        '{"response_id": "chatcmpl-secret", "content_text": "x"}',
        encoding="utf-8")
    return run


def test_export_copies_sanitized_excludes_private(tmp_path):
    run = make_run(tmp_path)
    out = tmp_path / "bundle"
    completed = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(run), str(out)],
        capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    names = sorted(p.name for p in out.iterdir())
    assert names == ["G3_report.json", "broker-artifact.v1.json",
                     "candidate.v1.json", "export-manifest.json"]
    manifest = json.loads(
        (out / "export-manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "G3_EVIDENCE_EXPORT_V1"
    assert manifest["run_id"] == "run-1"
    assert manifest["excluded_private"] == [
        "generation-result.v1.private.json"]
    assert set(manifest["files"]) == {
        "G3_report.json", "broker-artifact.v1.json", "candidate.v1.json"}
    bundle_text = "\n".join(
        p.read_text(encoding="utf-8") for p in out.iterdir())
    assert "chatcmpl-secret" not in bundle_text


def test_export_refuses_missing_report_and_existing_dir(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    completed = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(empty), str(tmp_path / "o")],
        capture_output=True, text=True, timeout=120)
    assert completed.returncode == 2
    run = make_run(tmp_path / "second")
    out = tmp_path / "taken"
    out.mkdir()
    completed = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(run), str(out)],
        capture_output=True, text=True, timeout=120)
    assert completed.returncode == 2
