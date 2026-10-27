"""G3-A interpreter tests on the trusted-test-fixture spec.

These assert the runtime executes the DECLARED rules deterministically with an
isolated in-memory state. The fixture itself is author-written (see
g3_fixtures/README.md) — behavioral fidelity against the owned reference is
measured ONLY by the sealed differential verifier, never claimed here.
"""

import json
from pathlib import Path

import pytest

from second_source.candidate_runtime import CandidateInterpreter
from second_source.candidate_spec import load_candidate

FIXTURE = Path(__file__).resolve().parent / "g3_fixtures" / "valid_candidate.json"


def interpreter(cli_scope, **kw):
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    loaded = load_candidate(doc, cli_scope)
    return CandidateInterpreter(loaded.spec, **kw)


def run(interp, actions, sequence_id="s"):
    return interp.execute_sequence(actions, sequence_id=sequence_id)


def test_add_list_total_remove(cli_scope):
    interp = interpreter(cli_scope)
    assert run(interp, [{"command": "add", "params": {"label": "Milk", "amount": 2}}]).observations[0].output == {"ok": True, "id": "1"}
    result = run(interp, [
        {"command": "add", "params": {"label": "Bread", "amount": 3}},
        {"command": "list"},
        {"command": "total"},
        {"command": "remove", "params": {"id": "1"}},
        {"command": "total"},
    ], sequence_id="t")
    outputs = [o.output for o in result.observations]
    assert outputs[0] == {"ok": True, "id": "1"}
    assert outputs[1] == {"ok": True, "items": [{"id": "1", "label": "Bread", "amount": 3}]}
    assert outputs[2] == {"ok": True, "count": 1, "amount": 3}
    assert outputs[3] == {"ok": True}
    assert outputs[4] == {"ok": True, "count": 0, "amount": 0}
    assert result.status == "ok"


def test_duplicate_casefold_and_whitespace(cli_scope):
    interp = interpreter(cli_scope)
    result = run(interp, [
        {"command": "add", "params": {"label": "Alpha", "amount": 1}},
        {"command": "add", "params": {"label": "  ALPHA ", "amount": 1}},
    ])
    assert result.observations[0].output == {"ok": True, "id": "1"}
    assert result.observations[1].output == {"ok": False, "error": "duplicate_label"}
    assert result.observations[1].status == "target_error"


def test_invalid_label(cli_scope):
    interp = interpreter(cli_scope)
    for bad in ("", "   ", "x" * 25, 42, None):
        result = run(interp, [{"command": "add", "params": {"label": bad, "amount": 1}}])
        assert result.observations[0].output == {"ok": False, "error": "invalid_label"}, bad


def test_invalid_amount(cli_scope):
    interp = interpreter(cli_scope)
    for bad in (0, 101, -3, "5", 2.5, True, None):
        result = run(interp, [{"command": "add", "params": {"label": "K", "amount": bad}}])
        assert result.observations[0].output == {"ok": False, "error": "invalid_amount"}, bad


def test_missing_params(cli_scope):
    interp = interpreter(cli_scope)
    result = run(interp, [{"command": "add", "params": {"label": "K"}}])
    assert result.observations[0].output == {"ok": False, "error": "invalid_amount"}


def test_remove_missing_and_bad_id(cli_scope):
    interp = interpreter(cli_scope)
    result = run(interp, [{"command": "remove", "params": {"id": "99"}}])
    assert result.observations[0].output == {"ok": False, "error": "not_found"}
    result = run(interp, [{"command": "remove", "params": {"id": 3}}])
    assert result.observations[0].output == {"ok": False, "error": "not_found"}


def test_unknown_command(cli_scope):
    interp = interpreter(cli_scope)
    result = run(interp, [{"command": "frobnicate"}])
    assert result.observations[0].output == {"ok": False, "error": "unknown_command"}


def test_malformed_action_protocol_error(cli_scope):
    interp = interpreter(cli_scope)
    result = interp.execute_sequence(["not-a-dict"], sequence_id="s")
    assert result.status == "protocol_error"
    assert result.observations == ()


def test_empty_sequence_ok(cli_scope):
    interp = interpreter(cli_scope)
    result = run(interp, [])
    assert result.status == "ok"
    assert result.observations == ()


def test_reset_boundary_fresh_state(cli_scope):
    interp = interpreter(cli_scope)
    run(interp, [{"command": "add", "params": {"label": "A", "amount": 1}}], sequence_id="s1")
    second = run(interp, [{"command": "total"}], sequence_id="s2")
    assert second.observations[0].output == {"ok": True, "count": 0, "amount": 0}
    interp.reset()
    third = run(interp, [{"command": "add", "params": {"label": "A", "amount": 1}}], sequence_id="s3")
    assert third.observations[0].output == {"ok": True, "id": "1"}


def test_deterministic_replay(cli_scope):
    interp = interpreter(cli_scope)
    actions = [
        {"command": "add", "params": {"label": "X", "amount": 4}},
        {"command": "add", "params": {"label": "Y", "amount": 6}},
        {"command": "total"},
        {"command": "list"},
    ]
    first = [o.output for o in run(interp, actions, sequence_id="a").observations]
    second = [o.output for o in run(interp, actions, sequence_id="b").observations]
    assert first == second


def test_sequence_action_cap(cli_scope):
    interp = interpreter(cli_scope, max_actions=2)
    result = run(interp, [{"command": "total"}] * 3)
    assert result.status == "protocol_error"


def test_state_record_cap(cli_scope):
    interp = interpreter(cli_scope, max_records=2)
    result = run(interp, [
        {"command": "add", "params": {"label": "A", "amount": 1}},
        {"command": "add", "params": {"label": "B", "amount": 1}},
        {"command": "add", "params": {"label": "C", "amount": 1}},
    ])
    assert result.observations[2].output == {"ok": False, "error": "resource_exhausted"}


def test_observation_ids_and_exit_codes(cli_scope):
    interp = interpreter(cli_scope)
    result = run(interp, [{"command": "total"}], sequence_id="zz")
    obs = result.observations[0]
    assert obs.observation_id == "zz:0"
    assert obs.exit_code == 0
    assert obs.duration_ms >= 0
