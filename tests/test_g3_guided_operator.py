"""Independent NON_AI operator acceptance for the pinned guided protocol.

Synthetic observations/fills exercise plumbing and negative admission. No test
uses genuine archives, provider credentials, live transport or model repairs.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from second_source import reconstruct
from second_source.candidate_generation import FILL_JSON_SCHEMA
from second_source.evidence import publish_once
from second_source.g3_verification import seal_owned_ledger_suite
from second_source.model_gateway import DEFAULT_FORBIDDEN_MARKERS, MetaProvider, MockProvider, validate_json_schema


@pytest.fixture(scope="module")
def sealed_mock(tmp_path_factory):
    directory = tmp_path_factory.mktemp("guided-operator-sealed")
    _, digest = seal_owned_ledger_suite(directory, reconstruct.create_scope(0))
    return directory, digest


@pytest.fixture(autouse=True)
def no_real_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("NON_AI acceptance must never reach real provider transport")
    monkeypatch.setattr(MetaProvider, "complete", forbidden)


def mock_args(tmp_path, sealed_mock, monkeypatch):
    from second_source import g3_verification
    directory, digest = sealed_mock
    # Reuse one already-sealed synthetic suite, never regenerate gold cases for
    # these repeated negative CLI paths. Actual loader still checks its bytes.
    monkeypatch.setattr(g3_verification, "seal_owned_ledger_suite", lambda *args: (directory / "suite.json", digest))
    return ["--mode", "mock", "--synthesis", "guided", "--max-usd", "0",
            "--run-dir", str(tmp_path / "run"), "--seal-dir", str(directory)]


def read_json(path):
    return json.loads(path.read_bytes())


def assert_not_admitted(run_dir):
    for name in ("candidate.v1.json", "broker-artifact.v1.json"):
        assert not (run_dir / name).exists(), name
    report = read_json(run_dir / "G3_report.json")
    assert report["evaluation"] is None
    assert report["stop_reason"] == "broker_failed"
    assert report["real"] is False
    assert report["usage"]["attempts"] == 1
    assert report["usage"]["estimated_cost_usd"] == 0
    assert report["usage"]["uncertain_cost_usd"] == 0
    return report


def test_guided_mock_cli_honest_score_original_receipts_and_immutable_publication(tmp_path, sealed_mock, monkeypatch):
    args = mock_args(tmp_path, sealed_mock, monkeypatch)
    assert reconstruct.main(args) == 0
    run_dir = tmp_path / "run"
    report = read_json(run_dir / "G3_report.json")
    assert report["synthesis"] == "guided"
    assert report["origin"] == "mock" and report["real"] is False
    assert {key: report["evaluation"][key] for key in ("passed", "failed", "indeterminate", "total")} == {
        "passed": 22, "failed": 3, "indeterminate": 0, "total": 25}
    assert report["evaluation"]["failure_categories"]
    assert report["usage"]["attempts"] == 1
    assert report["usage"]["estimated_cost_usd"] == report["usage"]["uncertain_cost_usd"] == 0
    dispatch_path = run_dir / "generation-dispatch.v1.private.json"
    result_path = run_dir / "generation-result.v1.private.json"
    dispatch, result = read_json(dispatch_path), read_json(result_path)
    assert dispatch["event"] == "model_dispatch" and dispatch["real"] is False
    assert dispatch["attempt"] == 1 and dispatch["prompt_version"] == "synthesize-v2"
    assert result["event"] == "model_result"
    response = result["response"]
    assert response["parsed"] == reconstruct.naive_mock_fill()
    assert json.loads(response["content_text"]) == response["parsed"]
    assert response["real"] is False and result["receipt"]["outcome"] == "ok"
    assert result["receipt"]["content_sha256"] == hashlib.sha256(response["content_text"].encode()).hexdigest()
    for counter in ("input_tokens", "output_tokens"):
        assert response[counter] == result["receipt"][counter] == report["usage"][counter]
        assert report["usage"][counter] > 0
    envelope = read_json(run_dir / "broker-artifact.v1.json")
    payload = json.loads(envelope["payload"])
    assert (run_dir / "candidate.v1.json").read_bytes() == payload["spec"].encode()
    assert payload["receipt"]["synthesis"] == "guided"
    # The audit envelope sorts object keys for persistence; the untouched model
    # content retains the provider's parsed insertion order used by the broker.
    assert payload["receipt"]["model_output_digest"] == "sha256:" + hashlib.sha256(
        json.dumps(json.loads(response["content_text"]), ensure_ascii=False,
                   allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    # Both original response stages are create-once, with exact first bytes left
    # intact if a second writer tries to replace them through the shared API.
    audit = reconstruct._generation_audit(run_dir)
    for event, path in (("model_dispatch", dispatch_path), ("model_result", result_path)):
        original = path.read_bytes()
        with pytest.raises(FileExistsError):
            audit(event, {"forged": "replacement"})
        assert path.read_bytes() == original
    public = (run_dir / "G3_report.json").read_text(encoding="utf-8")
    assert response["content_text"] not in public
    assert "content_text" not in public and "parsed" not in public
    for marker in (*DEFAULT_FORBIDDEN_MARKERS, "MODEL_API_KEY", "META_API_KEY", "PRIVATE_MODEL_RESULT"):
        assert marker not in public
    assert "MOCK" in report["report_labels"]


def test_guided_schema_valid_semantic_invalid_original_survives_without_candidate(tmp_path, sealed_mock, monkeypatch):
    fill = reconstruct.naive_mock_fill()
    fill["add"]["amount"] = {"minimum": 50, "maximum": 10}
    assert validate_json_schema(fill, FILL_JSON_SCHEMA) == []
    monkeypatch.setattr(reconstruct, "naive_mock_fill", lambda: fill)
    assert reconstruct.main(mock_args(tmp_path, sealed_mock, monkeypatch)) == 1
    run_dir = tmp_path / "run"
    report = assert_not_admitted(run_dir)
    original = read_json(run_dir / "generation-result.v1.private.json")
    assert original["response"]["parsed"] == fill
    assert json.loads(original["response"]["content_text"]) == fill
    assert original["receipt"]["outcome"] == "ok"
    assert report["broker_failure"]["failure_stage"] == "candidate_admission"
    assert report["broker_failure"]["failure_code"] == "CANDIDATE_SPEC_INVALID"
    assert report["broker_failure"]["transport_attempted"] is True
    assert report["broker_failure"]["response_id"] == original["response"]["response_id"]
    assert report["usage"]["input_tokens"] == original["response"]["input_tokens"]
    assert report["usage"]["output_tokens"] == original["response"]["output_tokens"]


@pytest.mark.parametrize("stage,expected_calls", [("dispatch", 0), ("result", 1)])
@pytest.mark.parametrize("failure", ["publication", "fsync"])
def test_guided_private_archive_failure_blocks_admission_and_preserves_accounting(
    tmp_path, sealed_mock, monkeypatch, stage, expected_calls, failure
):
    args = mock_args(tmp_path, sealed_mock, monkeypatch)
    target_name = f"generation-{stage}.v1.private.json"
    original_write = reconstruct._write_once
    original_complete = MockProvider.complete
    calls, responses = [], []
    def complete(self, request):
        calls.append(request)
        response = original_complete(self, request)
        responses.append(response)
        return response
    monkeypatch.setattr(MockProvider, "complete", complete)
    def fail_write(path, raw):
        if path.name == target_name:
            if failure == "publication":
                raise OSError("PRIVATE_DIAGNOSTIC_MUST_NOT_ESCAPE")
            with monkeypatch.context() as patch:
                def bad_fsync(*args):
                    raise OSError("PRIVATE_DIAGNOSTIC_MUST_NOT_ESCAPE")
                patch.setattr("second_source.evidence.os.fsync", bad_fsync)
                return publish_once(path, raw)
        return original_write(path, raw)
    monkeypatch.setattr(reconstruct, "_write_once", fail_write)
    assert reconstruct.main(args) == 1
    run_dir = tmp_path / "run"
    report = assert_not_admitted(run_dir)
    assert len(calls) == expected_calls
    assert not (run_dir / target_name).exists()
    assert not list(run_dir.glob("*.staging"))
    assert report["broker_failure"]["failure_stage"] == "evidence_publication"
    assert report["broker_failure"]["failure_code"] == "GENERATION_AUDIT_FAILED"
    assert report["broker_failure"]["transport_attempted"] is bool(expected_calls)
    assert "PRIVATE_DIAGNOSTIC_MUST_NOT_ESCAPE" not in (run_dir / "G3_report.json").read_text()
    if stage == "dispatch":
        assert not (run_dir / "generation-result.v1.private.json").exists()
        assert report["usage"]["input_tokens"] == report["usage"]["output_tokens"] == 0
    else:
        assert (run_dir / "generation-dispatch.v1.private.json").is_file()
        assert report["usage"]["input_tokens"] == responses[0].input_tokens > 0
        assert report["usage"]["output_tokens"] == responses[0].output_tokens > 0


def test_guided_zero_call_preflight_stable_across_process_hash_seeds_and_distinct_from_full(tmp_path):
    from test_g3_reconstruct import _operator_inputs
    ledger, hypotheses, digests = _operator_inputs(tmp_path)
    sealed = tmp_path / "frozen"
    _, digest = seal_owned_ledger_suite(sealed, reconstruct.create_scope(0.5))
    suite_raw = (sealed / "suite.json").read_bytes()
    source = Path(reconstruct.__file__).resolve().parents[1]
    script = r'''
import json,os,sys
from second_source import reconstruct
from second_source.model_gateway import MetaProvider,MockProvider
def forbidden(*args,**kwargs):
    raise AssertionError("zero-call preflight reached transport or credential")
MetaProvider.complete=forbidden
MockProvider.complete=forbidden
original_get=os.environ.get
def guarded(name,*args):
    if name in {"MODEL_API_KEY","META_API_KEY"}: forbidden()
    return original_get(name,*args)
os.environ.get=guarded
raise SystemExit(reconstruct.main(json.loads(sys.argv[1])))
'''
    receipts = []
    for seed, synthesis in (("1", "guided"), ("9281", "guided"), ("9281", "full")):
        run_dir = tmp_path / f"preflight-{seed}-{synthesis}"
        args = ["--mode", "preflight", "--synthesis", synthesis, "--max-usd", "0.5",
                "--ledger-dir", str(ledger), "--hypotheses-file", str(hypotheses),
                "--observation-digests", ",".join(digests), "--suite", str(sealed / "suite.json"),
                "--suite-digest", digest, "--run-dir", str(run_dir)]
        env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH") if key in os.environ}
        env.update(PYTHONPATH=str(source), PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run([sys.executable, "-B", "-c", script, json.dumps(args)],
            cwd=Path(reconstruct.__file__).resolve().parents[2], env=env,
            capture_output=True, timeout=90)
        assert process.returncode == 0, process.stderr.decode(errors="replace")
        receipt = read_json(run_dir / "G3_preflight.json")
        assert receipt["provider_calls"] == 0 and receipt["real"] is False
        assert receipt["real_input_eligible"] is False
        assert receipt["synthesis"] == synthesis
        assert receipt["suite_digest"] == digest
        receipts.append(receipt)
    stable = ("approved_context_digest", "inspected_request_digest", "scope_digest", "suite_digest",
              "observation_registry_digest", "hypothesis_registry_digest", "code_pins", "reference_source_digest",
              "request_max_output_tokens", "max_approved_usd")
    for field in stable:
        assert receipts[0][field] == receipts[1][field], field
    assert receipts[0]["request_max_output_tokens"] == 4096
    assert receipts[2]["request_max_output_tokens"] == 2000
    assert receipts[0]["approved_context_digest"] != receipts[2]["approved_context_digest"]
    assert receipts[0]["inspected_request_digest"] != receipts[2]["inspected_request_digest"]
    # Plan IDs include fresh run identity; approval inputs remain stable.
    assert len({receipt["plan_digest"] for receipt in receipts}) == 3
    assert (sealed / "suite.json").read_bytes() == suite_raw
