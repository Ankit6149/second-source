"""Nonbillable CLI provisioning/restart contract; no server or credential use."""
import json
from second_source.backend.__main__ import main


def test_cli_provisions_and_reopens_versioned_durable_storage(tmp_path, capsys):
    args = ["--data-dir", str(tmp_path / "state"), "init"]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first == {"schema_version": 1, "ready": True,
        "real_inference_enabled": False, "paid_authorization_enabled": False}
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out) == first


def test_cli_invalid_bundle_returns_safe_error_without_traceback(tmp_path, capsys):
    bundle = tmp_path / "malformed.zip"
    bundle.write_bytes(b"PRIVATE_SENTINEL_NOT_A_ZIP")
    assert main(["--data-dir", str(tmp_path / "state"), "verify-bundle", str(bundle)]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err)["code"] == "INVALID_BUNDLE"
    assert "PRIVATE_SENTINEL" not in captured.err and "Traceback" not in captured.err
