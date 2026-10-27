import sys
from pathlib import Path
from second_source.reference import CLIReferenceAdapter

ROOT = Path(__file__).resolve().parents[1]


def test_stateful_observation_and_reset(reference):
    actions = [
        {"command": "add", "label": "Alpha", "amount": 4},
        {"command": "add", "label": "alpha", "amount": 7},
        {"command": "total"},
        {"command": "list"},
    ]
    a = reference.execute_sequence(actions)
    b = reference.execute_sequence(actions)
    assert a.status == b.status == "ok"
    assert [o.output for o in a.observations] == [o.output for o in b.observations]
    assert a.observations[0].output == {"ok": True, "id": "1"}
    assert a.observations[1].output == {"ok": False, "error": "duplicate_label"}
    assert a.observations[2].output == {"ok": True, "count": 1, "amount": 4}
    assert all(o.sequence_id == a.sequence_id for o in a.observations)
    assert [o.action_index for o in a.observations] == [0, 1, 2, 3]


def test_input_validation(reference):
    run = reference.execute_sequence([{"command": "add", "label": "", "amount": 3}, {"command": "add", "label": "hi", "amount": True}, {"command": "add", "label": "hi", "amount": 101}])
    assert [o.output["error"] for o in run.observations] == ["invalid_label", "invalid_amount", "invalid_amount"]


def test_timeout_and_bad_protocol():
    timeout = CLIReferenceAdapter([sys.executable, str(ROOT / "fixtures/candidates/timeout.py")], cwd=ROOT, timeout_seconds=0.15)
    bad = CLIReferenceAdapter([sys.executable, str(ROOT / "fixtures/candidates/protocol_broken.py")], cwd=ROOT)
    assert timeout.execute_sequence([{"command": "total"}]).status == "timeout"
    assert bad.execute_sequence([{"command": "total"}]).status == "protocol_error"


def test_output_cap(reference):
    tiny = CLIReferenceAdapter([sys.executable, str(ROOT / "fixtures/owned_ledger/reference.py")], cwd=ROOT, max_output_bytes=512)
    actions = [{"command": "list"} for _ in range(100)]
    assert tiny.execute_sequence(actions).status == "protocol_error"
