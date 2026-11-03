"""Reports/artifacts slice: actual-data reports, bundles, runnable candidate ZIP."""
import io
import json
import zipfile

import pytest

from second_source import reporting as R


def sample_data(**over):
    data = {
        "investigation_id": "inv-001", "title": "Demo <script>alert(1)</script>",
        "generated_at": "2026-11-03T00:00:00Z",
        "evidence": {"E1": {"kind": "observation", "source": "probe", "sha256": "a" * 64},
                     "E2": {"kind": "test", "source": "pytest"}},
        "summary": {"claims": [{"text": "Observed 2 routes", "status": "OBSERVED", "evidence_ids": ["E1"]}],
                    "data": {"routes": 2}},
        "fidelity": {"claims": [{"text": "22/25 passed", "status": "OBSERVED", "evidence_ids": ["E2"]}],
                     "data": {"passed": 22, "failed": 3, "indeterminate": 0, "total": 25}},
        "auth": {"claims": [{"text": "Token kind unknown", "status": "UNKNOWN", "evidence_ids": []}]},
        "mismatches": {"claims": [{"text": "Old claim contradicted by E1", "status": "CONTRADICTED", "evidence_ids": ["E1"]}]},
        "security": {"data": {"api_key": "SECRET_SENTINEL", "note": "Bearer abc.def"}},
    }
    data.update(over)
    return data


def test_all_sections_present_and_missing_are_unknown_not_fabricated():
    report = R.build_report(sample_data())
    assert [s["id"] for s in report["sections"]] == list(R.SECTION_IDS)
    assert len(report["sections"]) == 24
    by_id = {s["id"]: s for s in report["sections"]}
    assert by_id["observations"]["claims"][0]["status"] == "UNKNOWN"
    assert by_id["observations"]["claims"][0]["evidence_ids"] == []
    assert by_id["summary"]["claims"][0]["status"] == "OBSERVED"
    assert report["claim_counts"]["OBSERVED"] == 2


def test_evidence_linkage_fails_closed():
    bad = sample_data(summary={"claims": [{"text": "x", "status": "OBSERVED", "evidence_ids": ["NOPE"]}]})
    with pytest.raises(R.ReportError, match="unknown evidence"):
        R.build_report(bad)
    bad2 = sample_data(summary={"claims": [{"text": "x", "status": "INFERRED", "evidence_ids": []}]})
    with pytest.raises(R.ReportError, match="requires at least one"):
        R.build_report(bad2)
    bad3 = sample_data(summary={"claims": [{"text": "x", "status": "MAYBE", "evidence_ids": []}]})
    with pytest.raises(R.ReportError):
        R.build_report(bad3)


def test_fidelity_counts_must_sum_and_secrets_redacted():
    with pytest.raises(R.ReportError, match="sum to total"):
        R.build_report(sample_data(fidelity={"data": {"passed": 1, "failed": 1, "indeterminate": 0, "total": 99}}))
    report = R.build_report(sample_data())
    blob = json.dumps(report)
    assert "SECRET_SENTINEL" not in blob and "abc.def" not in blob and "[REDACTED]" in blob


def test_markdown_html_manifest_and_bundle_roundtrip_and_tamper():
    report = R.build_report(sample_data())
    md, html_text = R.render_markdown(report), R.render_html(report)
    for _, title in R.SECTIONS:
        assert title in md and title in html_text
    assert "<script>alert(1)</script>" not in html_text and "&lt;script&gt;" in html_text
    assert "OBSERVED" in md and "`E1`" in md
    bundle = R.export_report_bundle(report)
    assert R.verify_report_bundle(bundle)["valid"]
    manifest = R.build_manifest(report, {"report.json": b"{}"})
    assert manifest["files"]["report.json"]["size_bytes"] == 2
    # Deterministic export
    assert R.export_report_bundle(report) == bundle
    # Tamper: flip a byte in report.md inside a rebuilt zip
    with zipfile.ZipFile(io.BytesIO(bundle)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    files["report.md"] += b"tampered"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    with pytest.raises(R.ReportError):
        R.verify_report_bundle(out.getvalue())


def test_file_inventory_hashes_actual_files(tmp_path):
    (tmp_path / "a.py").write_text("x=1\n")
    inv = R.build_file_inventory(tmp_path)
    assert inv[0]["path"] == "a.py" and len(inv[0]["sha256"]) == 64
    with pytest.raises(R.ReportError):
        R.build_file_inventory(tmp_path, ["../escape.py"])
    with pytest.raises(R.ReportError):
        R.build_file_inventory(tmp_path, ["missing.py"])


def _candidate(tmp_path):
    src = tmp_path / "cand"
    src.mkdir()
    (src / "README.md").write_text("# Candidate\nRun: python main.py\n")
    (src / "pyproject.toml").write_text('[project]\nname="cand"\nversion="0.1.0"\ndependencies=[]\n')
    (src / "main.py").write_text("print('candidate-ok')\n")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "x.pyc").write_bytes(b"junk")
    (src / ".env").write_text("SECRET=1\n")
    return src


def test_candidate_zip_verifies_and_runs_in_clean_temp(tmp_path):
    bundle = R.build_candidate_bundle(_candidate(tmp_path))
    info = R.verify_candidate_bundle(bundle)
    assert info["valid"] and "main.py" in info["files"]
    with zipfile.ZipFile(io.BytesIO(bundle)) as z:
        names = z.namelist()
    assert not any("__pycache__" in n or n.endswith(".env") for n in names)
    result = R.extract_and_run_candidate(bundle, ["{python}", "main.py"])
    assert result["returncode"] == 0 and "candidate-ok" in result["stdout"]


def test_candidate_installs_deps_in_extracted_dir(tmp_path):
    src = tmp_path / "cand2"
    src.mkdir()
    (src / "README.md").write_text("# Candidate\n")
    (src / "requirements.txt").write_text("# no third-party deps\n")
    (src / "main.py").write_text("print('ok')\n")
    bundle = R.build_candidate_bundle(src)
    pip = R.extract_and_run_candidate(bundle, ["{python}", "-m", "pip", "install", "-q", "-r", "requirements.txt"])
    assert pip["returncode"] == 0
    run = R.extract_and_run_candidate(bundle, ["{python}", "main.py"])
    assert run["returncode"] == 0 and "ok" in run["stdout"]


def test_candidate_requires_readme_deps_and_code(tmp_path):
    src = tmp_path / "bad"
    src.mkdir()
    (src / "main.py").write_text("pass\n")
    with pytest.raises(R.ReportError, match="README"):
        R.build_candidate_bundle(src)
    (src / "README.md").write_text("x\n")
    with pytest.raises(R.ReportError, match="dependency"):
        R.build_candidate_bundle(src)


def test_candidate_tamper_and_zipslip_rejected(tmp_path):
    bundle = R.build_candidate_bundle(_candidate(tmp_path))
    with zipfile.ZipFile(io.BytesIO(bundle)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    files["main.py"] = b"print('evil')\n"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    with pytest.raises(R.ReportError):
        R.verify_candidate_bundle(out.getvalue())
    # Zip-slip entry must never extract
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../evil.py", "x")
        z.writestr("candidate-manifest.json", b"{}")
    with pytest.raises(R.ReportError):
        R.extract_and_run_candidate(evil.getvalue(), ["{python}", "main.py"])


def test_write_report_files(tmp_path):
    report = R.build_report(sample_data())
    out = R.write_report_files(report, tmp_path / "out")
    assert "report-bundle.zip" in out["files"]
    raw = (tmp_path / "out" / "report-bundle.zip").read_bytes()
    assert R.verify_report_bundle(raw)["report_id"] == report["report_id"]
