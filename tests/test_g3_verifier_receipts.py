"""Independent durable-artifact faults. All inputs and failures are NON_AI."""
from concurrent.futures import ThreadPoolExecutor
import json
import os

import pytest

from second_source import reconstruct as operator
from second_source.g3_verification import EvaluationBlocked, PinnedEvaluatorRun


def test_concurrent_reports_publish_one_complete_receipt(tmp_path):
    reports = [{"kind": "NON_AI_COLLISION_CONTROL", "writer": index,
                "padding": "x" * 8192} for index in range(2)]

    def write(report):
        try:
            operator._write_report(tmp_path, report)
            return report
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, reports))
    winners = [value for value in outcomes if value is not None]
    assert len(winners) == 1
    assert json.loads((tmp_path / "G3_report.json").read_bytes()) == winners[0]


def test_partial_write_never_publishes_a_truncated_final_receipt(tmp_path, monkeypatch):
    final = tmp_path / "G3_report.json"
    fdopen = os.fdopen
    observed = []

    class InterruptedStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def write(self, raw):
            self.stream.write(raw[:len(raw) // 2])
            self.stream.flush()
            # Observe the public final name during a real partial filesystem
            # write. A temporary unpublished file is fine; truncated final is not.
            observed.append(final.exists())
            raise OSError("SYNTHETIC_DISK_FAILURE")

    monkeypatch.setattr(os, "fdopen", lambda *a, **k: InterruptedStream(fdopen(*a, **k)))
    with pytest.raises(OSError):
        operator._write_report(tmp_path, {"kind": "NON_AI_PARTIAL_WRITE", "padding": "x" * 8192})
    assert observed == [False], "A reader could observe a truncated report at its final name"
    assert not final.exists()


def test_fsync_failure_cannot_be_mistaken_for_a_completed_receipt(tmp_path, monkeypatch):
    def fail_sync(fd):
        raise OSError("SYNTHETIC_FSYNC_FAILURE")

    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(OSError):
        operator._write_report(tmp_path, {"kind": "NON_AI_SYNC_FAILURE"})
    assert not (tmp_path / "G3_report.json").exists()


def test_empty_prior_run_directory_is_not_reclaimed(tmp_path):
    prior = tmp_path / "interrupted-run"
    prior.mkdir()
    with pytest.raises((OSError, RuntimeError, EvaluationBlocked)):
        operator._run_directory(str(prior))
    assert list(prior.iterdir()) == []


@pytest.mark.parametrize("fault", ["evaluator", "interruption"])
def test_evaluator_failure_retains_admitted_artifact_and_exact_budget(tmp_path, monkeypatch, capsys, fault):
    seen = {}
    generate = PinnedEvaluatorRun.generate

    def capture(run, *args, **kwargs):
        artifact = generate(run, *args, **kwargs)
        seen.update(artifact=artifact, budget=args[2])
        return artifact

    def fail_evaluation(*args, **kwargs):
        if fault == "interruption":
            raise KeyboardInterrupt
        raise EvaluationBlocked("SYNTHETIC_EVALUATOR_SECRET")

    monkeypatch.setattr(PinnedEvaluatorRun, "generate", capture)
    monkeypatch.setattr(PinnedEvaluatorRun, "evaluate", fail_evaluation)
    directory = tmp_path / "failed-evaluation"
    try:
        code = operator.main(["--mode", "mock", "--run-dir", str(directory),
                              "--seal-dir", str(tmp_path / "sealed")])
    except KeyboardInterrupt:
        code = None
    assert type(code) is int and code != 0
    report = json.loads((directory / "G3_report.json").read_bytes())
    assert "evaluat" in report.get("failure_stage", "") + report["stop_reason"]
    if fault == "interruption":
        assert any(word in report["stop_reason"] for word in ("interrupt", "stop", "cancel"))
    for key in ("attempts", "input_tokens", "output_tokens", "estimated_cost_usd", "uncertain_cost_usd"):
        assert report["usage"][key] == getattr(seen["budget"], key), key
    artifact = seen["artifact"]
    spec = json.loads(artifact.payload)["spec"].encode("utf-8")
    files = [path.read_bytes() for path in directory.rglob("*") if path.is_file()]
    assert spec in files, "An admitted candidate was discarded when scoring failed"
    assert any(artifact.signature.encode() in raw and artifact.payload.decode() in raw.decode(errors="replace")
               for raw in files) or any(
        _has_serialized_artifact(raw, artifact) for raw in files
    ), "The broker artifact/receipt was discarded after admission"
    captured = capsys.readouterr()
    assert "SYNTHETIC_EVALUATOR_SECRET" not in (json.dumps(report) + captured.out + captured.err)


def test_invalid_admitted_spec_preserves_reported_token_accounting(tmp_path, monkeypatch):
    seen = {}
    generate = PinnedEvaluatorRun.generate
    spec = operator.naive_mock_spec()
    spec["commands"]["add"]["params"]["amount"].update(minimum=3, maximum=2)

    def capture(run, *args, **kwargs):
        seen["budget"] = args[2]
        return generate(run, *args, **kwargs)

    monkeypatch.setattr(PinnedEvaluatorRun, "generate", capture)
    monkeypatch.setattr(operator, "naive_mock_spec", lambda: spec)
    directory = tmp_path / "invalid-spec"
    assert operator.main(["--mode", "mock", "--run-dir", str(directory),
                          "--seal-dir", str(tmp_path / "sealed")]) != 0
    budget = seen["budget"]
    assert budget.attempts == 1 and budget.input_tokens > 0 and budget.output_tokens > 0
    report = json.loads((directory / "G3_report.json").read_bytes())
    for key in ("attempts", "input_tokens", "output_tokens", "estimated_cost_usd", "uncertain_cost_usd"):
        assert report["usage"][key] == getattr(budget, key), key


def _has_serialized_artifact(raw, artifact):
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        return False
    if not isinstance(value, dict):
        return False
    return (value.get("payload") == artifact.payload.decode() and value.get("signature") == artifact.signature
            or any(_has_serialized_artifact(json.dumps(child).encode(), artifact)
                   for child in value.values() if isinstance(child, dict)))
