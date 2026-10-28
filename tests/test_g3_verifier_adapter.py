"""Public synthetic adapter/containment probes, never model-generated controls."""
import json
from pathlib import Path
import time
import os

import pytest

from second_source.candidate_adapter import (
    CandidateExecutionLimits, CandidateReferenceAdapter, ExecutionUnavailable,
    _run_worker,
)
from second_source.candidate_spec import CandidateError, load_candidate

FIXTURE = Path(__file__).parent / "g3_fixtures" / "valid_candidate.json"


def adapter(scope, **limits):
    return CandidateReferenceAdapter(FIXTURE.read_bytes(), scope, limits=CandidateExecutionLimits(**limits))


def test_wire_reset_digest_and_detached_scope(cli_scope):
    candidate = adapter(cli_scope)
    assert candidate.spec_digest == load_candidate(FIXTURE.read_bytes(), cli_scope).digest
    actions = [{"command": "add", "label": "public-probe", "amount": 2}, {"command": "total"}]
    first = candidate.execute_sequence(actions, sequence_id="first")
    assert first.status == "ok", first
    assert first.observations[0].input_action == actions[0]
    assert first.observations[-1].output == {"ok": True, "count": 1, "amount": 2}
    second = candidate.execute_sequence([{"command": "total"}], sequence_id="second")
    assert second.observations[0].output == {"ok": True, "count": 0, "amount": 0}


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'[' * 1000 + b']' * 1000, b'{"x":NaN}'])
def test_admission_is_bounded_and_sanitized(cli_scope, raw):
    with pytest.raises(CandidateError, match="admission rejected"):
        CandidateReferenceAdapter(raw, cli_scope)


@pytest.mark.parametrize("limits", [dict(max_actions=65), dict(memory_bytes=1), dict(wall_seconds=float('nan')), dict(cpu_seconds=True)])
def test_invalid_trusted_limits_rejected(limits):
    with pytest.raises(ValueError):
        CandidateExecutionLimits(**limits)


def test_input_and_cumulative_output_caps(cli_scope):
    small = adapter(cli_scope, max_actions=2, max_input_bytes=512, max_output_bytes=512)
    assert small.execute_sequence([{"command": "list"}] * 3).status == "protocol_error"
    assert small.execute_sequence([{"command": "add", "label": "x" * 1000, "amount": 1}]).status == "protocol_error"
    assert small.execute_sequence([{"command": "list", "x": [[[[[[[[0]]]]]]]]}]).status == "ok"
    actions = [{"command": "add", "label": f"public-{i}", "amount": 1} for i in range(8)]
    actions += [{"command": "list"}] * 8
    assert adapter(cli_scope, max_output_bytes=512).execute_sequence(actions).status == "protocol_error"


def test_worker_io_environment_and_reference_gold_denial(tmp_path, monkeypatch):
    canary = tmp_path / "restricted-reference-gold.txt"
    canary.write_text("SYNTHETIC_RESTRICTED_CANARY")
    monkeypatch.setenv("AUDIT_SYNTHETIC_SECRET", "SYNTHETIC_ENV_CANARY")
    response = _run_worker("probe", {"path": str(canary)}, CandidateExecutionLimits())
    assert response.get("checks") and all(response["checks"].values()), response


@pytest.mark.parametrize("kind", ["wall", "cpu", "memory", "output"])
def test_actual_worker_resource_limits(kind):
    limits = CandidateExecutionLimits(wall_seconds=8 if kind == "cpu" else (2 if kind == "wall" else 5),
                                      cpu_seconds=1 if kind == "cpu" else 3,
                                      memory_bytes=128 * 1024 * 1024)
    started = time.monotonic()
    response = _run_worker("limit_probe", {"kind": kind}, limits)
    assert "failure" in response and "unexpected_success" not in response
    if kind == "wall":
        assert response["failure"] == "timeout"
    if kind == "output":
        assert response["failure"] == "output_limit"
    if kind == "cpu":
        assert response["failure"] in {"cpu_limit", "worker_failure"}  # watchdog or native CPU limit
    elif kind == "memory":
        assert response["failure"] == "memory_limit"  # Allocation was rejected by the OS limit.
    assert time.monotonic() - started < 12


def test_unavailable_containment_has_no_fallback(cli_scope, monkeypatch):
    monkeypatch.setattr("second_source.candidate_adapter.sys.platform", "unsupported")
    with pytest.raises(ExecutionUnavailable):
        adapter(cli_scope).execute_sequence([{"command": "list"}])


def test_symlink_to_restricted_file_does_not_bypass_guard(tmp_path):
    target = tmp_path / "gold"
    target.write_text("SYNTHETIC_CANARY")
    link = tmp_path / "alias"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("OS does not permit unprivileged symlink creation")
    response = _run_worker("probe", {"path": str(link)}, CandidateExecutionLimits())
    assert response["checks"]["file"] is True


def test_record_limit_unknown_command_and_nondict_inputs(cli_scope):
    candidate = adapter(cli_scope, max_records=1)
    result = candidate.execute_sequence([
        {"command": "add", "label": "public-a", "amount": 1},
        {"command": "add", "label": "public-b", "amount": 1},
    ])
    assert result.observations[-1].output == {"ok": False, "error": "resource_exhausted"}
    assert candidate.execute_sequence([None]).status == "protocol_error"
    assert candidate.execute_sequence([{"command": "not-a-permitted-reference-command"}]).observations[0].status == "target_error"
    # Unknown-command robustness is candidate-only; evaluator never expands reference permissions.


def test_inheritable_parent_descriptor_is_closed_in_worker(tmp_path):
    path = tmp_path / "synthetic-secret"
    path.write_text("SYNTHETIC_FD_CANARY")
    fd = os.open(path, os.O_RDONLY)
    try:
        os.set_inheritable(fd, True)
        response = _run_worker("probe", {"path": str(path), "inherited_fd": fd}, CandidateExecutionLimits())
        assert response["checks"]["inherited_fd_closed"] is True
    finally:
        os.close(fd)


@pytest.mark.parametrize("kind", ["shell", "network", "environment", "path", "subsystem", "opcode"])
def test_hostile_spec_never_reaches_worker(cli_scope, monkeypatch, kind):
    doc = json.loads(FIXTURE.read_bytes())
    if kind == "subsystem":
        doc["subsystem"] = "admin"
    elif kind == "path":
        doc["path"] = "../escape.json"
    else:
        doc["commands"]["list"][kind] = "SYNTHETIC_ATTACK"
    monkeypatch.setattr("second_source.candidate_adapter._run_worker", lambda *a, **kw: pytest.fail("Unsafe spec executed"))
    with pytest.raises(CandidateError):
        CandidateReferenceAdapter(json.dumps(doc).encode(), cli_scope)
