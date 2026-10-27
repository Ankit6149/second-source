import json
from pathlib import Path
import pytest
from second_source.contracts import Observation
from second_source.evidence import EvidenceLedger


def sample():
    return Observation(observation_id="obs-1", sequence_id="seq-1", action_index=0,
        input_action={"Authorization": "Bearer secret1234", "command": "list"},
        output={"ok": True, "password": "sensitivepass", "nested": {"refresh_token": "abc", "message": "Bearer xyz987"}},
        exit_code=0, duration_ms=4, status="ok")


def test_hash_addressing_and_redacted_view(tmp_path):
    ledger = EvidenceLedger(tmp_path / "ledger")
    a = ledger.store(sample())
    b = ledger.store(sample())
    assert a["sha256"] == b["sha256"]
    assert ledger.inspect(a["sha256"]).input_action["Authorization"] == "Bearer secret1234"
    model_view = json.dumps(ledger.model_view(a["sha256"]))
    for secret in ["secret1234", "sensitivepass", "xyz987", '"abc"']:
        assert secret not in model_view
    assert "[REDACTED]" in model_view


def test_tampering_is_detected(tmp_path):
    ledger = EvidenceLedger(tmp_path / "ledger")
    obj = ledger.store(sample())
    p = ledger.root / obj["artifact"]
    p.write_bytes(p.read_bytes() + b"oops")
    with pytest.raises(ValueError, match="Tampered"):
        ledger.inspect(obj["sha256"])
    with pytest.raises(ValueError, match="corrupted"):
        ledger.store(sample())


def test_digest_path_cannot_traverse(tmp_path):
    ledger = EvidenceLedger(tmp_path)
    with pytest.raises(ValueError):
        ledger.inspect("../.env")
