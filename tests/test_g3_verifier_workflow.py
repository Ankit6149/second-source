"""Independent operator acceptance. Synthetic controls only; never paid inference.

The workflow is tested through its real mock broker, trusted worker and sealed
evaluator. Hand-authored positive/negative fixtures remain explicitly NON_AI.
No historical G2 hypothesis or provider receipt is invented by these tests.
"""
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

from second_source import reconstruct as operator
from second_source.candidate_adapter import CandidateReferenceAdapter
from second_source.g3_verification import (
    EvaluationBlocked, OWNED_REFERENCE_DIGEST, PinnedEvaluatorRun,
    _digest, _encode, load_sealed_suite, seal_owned_ledger_suite,
)
from second_source.model_gateway import GatewayError, MockProvider

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "tests/g3_fixtures/valid_candidate.json"


@pytest.fixture(scope="module")
def workflow_control(tmp_path_factory):
    """One actual mock workflow execution; spies observe without bypassing gates."""
    root = tmp_path_factory.mktemp("independent-operator")
    run_dir, seal_dir = root / "run", root / "sealed"
    seen = {"wire": []}
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SYNTHETIC_SECRET", "ENVIRONMENT_CANARY")
        patch.delenv("MODEL_API_KEY", raising=False)
        patch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")
        patch.setattr(operator, "naive_mock_spec", lambda: json.loads(CONTROL.read_bytes()))
        complete = MockProvider.complete
        generate = PinnedEvaluatorRun.generate
        evaluate = PinnedEvaluatorRun.evaluate

        def capture_wire(provider, request):
            seen["wire"].append(request.model_dump(mode="json"))
            return complete(provider, request)

        def capture_origin(run, ticket, provider, budget, **kwargs):
            artifact = generate(run, ticket, provider, budget, **kwargs)
            seen.update(run=run, ticket=ticket, artifact=artifact, budget=budget)
            return artifact

        def capture_evaluation(run, artifact, **kwargs):
            result = evaluate(run, artifact, **kwargs)
            seen["evaluation_receipt"] = result
            return result

        patch.setattr(MockProvider, "complete", capture_wire)
        patch.setattr(PinnedEvaluatorRun, "generate", capture_origin)
        patch.setattr(PinnedEvaluatorRun, "evaluate", capture_evaluation)
        code = operator.main(["--mode", "mock", "--run-dir", str(run_dir), "--seal-dir", str(seal_dir)])
    assert code == 0
    seen.update(root=root, run_dir=run_dir, seal_dir=seal_dir,
                report=json.loads((run_dir / "G3_report.json").read_bytes()))
    return seen


def test_full_workflow_positive_control_is_25_of_25_and_honestly_mock(workflow_control):
    report = workflow_control["report"]
    assert report["evaluation"] == {"passed": 25, "failed": 0, "indeterminate": 0,
                                     "total": 25, "failure_categories": {}}
    assert report["mode"] == report["origin"] == "mock" and report["real"] is False
    assert report["response_id"].startswith("mock-")
    assert report["usage"]["estimated_cost_usd"] == report["usage"]["uncertain_cost_usd"] == 0
    assert report["reference_source_digest"] == OWNED_REFERENCE_DIGEST
    assert report["evaluation"] == workflow_control["evaluation_receipt"]["evaluation"]


def test_full_workflow_retains_scoring_environment_and_origin_pins(workflow_control):
    report, trusted = workflow_control["report"], workflow_control["evaluation_receipt"]
    # A wrapper may preserve the pinned manifest at top level or in a nested
    # evaluator receipt; losing these hashes prevents independent replay/audit.
    def contains_pair(value, key, expected):
        return isinstance(value, dict) and (value.get(key) == expected or any(
            contains_pair(child, key, expected) for child in value.values() if isinstance(child, dict)))
    required = ("comparator_digest", "interpreter_digest", "adapter_digest", "reference_digest",
                "environment_digest", "origin_receipt_digest", "observation_registry_digest",
                "hypothesis_registry_digest")
    missing = [key for key in required if not contains_pair(report, key, trusted[key])]
    assert not missing, f"Operator report dropped pinned evaluator evidence: {missing}"


def test_full_workflow_persists_exact_immutable_candidate_bytes(workflow_control):
    raw = json.loads(workflow_control["artifact"].payload)["spec"].encode("utf-8")
    expected = workflow_control["report"]["spec_digest"]
    assert _digest(raw) == expected
    candidates = [path for path in workflow_control["run_dir"].rglob("*")
                  if path.is_file() and path.name != "G3_report.json" and path.read_bytes() == raw]
    assert candidates, "Validated candidate bytes were discarded; a digest alone cannot reproduce this version"
    adapter = CandidateReferenceAdapter(candidates[0].read_bytes(), operator.create_scope(0))
    assert adapter.spec_digest == expected


def test_full_workflow_model_and_repair_views_exclude_sealed_material(workflow_control):
    seen = workflow_control
    scope = operator.create_scope(0)
    suite = load_sealed_suite(seen["seal_dir"] / "suite.json", seen["report"]["suite_digest"], scope)
    assert len(seen["wire"]) == 1 and "tools" not in seen["wire"][0]
    feedback = seen["run"].repair_feedback(seen["artifact"])
    assert feedback == seen["report"]["evaluation"]
    wire = _encode(seen["wire"]).decode()
    feedback_wire = _encode(feedback).decode()
    for marker in ("ENVIRONMENT_CANARY", str(seen["seal_dir"]),
                   str(ROOT / "fixtures/owned_ledger/reference.py"), *(case.case_id for case in suite.cases())):
        assert marker not in wire and marker not in feedback_wire
    assert set(feedback) == {"passed", "failed", "indeterminate", "total", "failure_categories"}
    feedback["passed"] = -1
    assert seen["run"].repair_feedback(seen["artifact"])["passed"] == 25


def test_full_workflow_cannot_relabel_origin_or_replay_request(workflow_control):
    seen = workflow_control
    value = json.loads(seen["artifact"].payload)
    value["receipt"].update(real=True, origin="real", response_id="FABRICATED_RECEIPT")
    with pytest.raises(EvaluationBlocked, match="Unattested"):
        seen["run"].evaluate(replace(seen["artifact"], payload=_encode(value)), claim="REAL_MODEL")
    before = seen["budget"].attempts
    with pytest.raises(EvaluationBlocked, match="replay"):
        seen["run"].generate(seen["ticket"], MockProvider(), seen["budget"])
    assert seen["budget"].attempts == before


def test_full_workflow_approved_inputs_cannot_change_after_inspection(workflow_control):
    run = workflow_control["run"]
    changed = json.loads(run._context_raw)
    changed["hypotheses"][0]["statement"] = "FABRICATED_G2_HYPOTHESIS"
    with pytest.raises(EvaluationBlocked, match="frozen"):
        run.prepare(changed)
    assert run.approved_context_digest == workflow_control["report"]["approved_context_digest"]


def test_full_workflow_sealed_bytes_are_create_once_and_digest_checked(workflow_control):
    seen = workflow_control
    scope = operator.create_scope(0)
    path = seen["seal_dir"] / "suite.json"
    original = path.read_bytes()
    with pytest.raises(EvaluationBlocked, match="never overwrite"):
        seal_owned_ledger_suite(seen["seal_dir"], scope)
    changed = seen["root"] / "changed-suite.json"
    changed.write_bytes(original + b" ")
    with pytest.raises(EvaluationBlocked, match="digest mismatch"):
        load_sealed_suite(changed, seen["report"]["suite_digest"], scope)
    assert path.read_bytes() == original


def test_existing_run_directory_is_not_reused(tmp_path):
    directory = tmp_path / "existing-run"
    directory.mkdir()
    receipt = directory / "G3_report.json"
    receipt.write_bytes(b'{"kind":"IMMUTABLE_PRIOR_RUN"}')
    before = receipt.read_bytes()
    try:
        operator._run_directory(str(directory))
    except (OSError, RuntimeError, EvaluationBlocked):
        pass
    else:
        pytest.fail("Existing run directory was accepted for reuse")
    assert receipt.read_bytes() == before


def test_report_receipt_is_create_once(tmp_path):
    directory = tmp_path / "run"
    directory.mkdir()
    path = operator._write_report(directory, {"kind": "FIRST_IMMUTABLE_RECEIPT"})
    before = path.read_bytes()
    try:
        operator._write_report(directory, {"kind": "REPLACEMENT_RECEIPT"})
    except (OSError, RuntimeError, EvaluationBlocked):
        pass
    assert path.read_bytes() == before, "An existing report/receipt was silently overwritten"


@pytest.mark.parametrize("failure", ["provider", "invalid_candidate"])
def test_failed_workflow_persists_sanitized_failure_and_budget_receipt(tmp_path, monkeypatch, capsys, failure):
    run_dir = tmp_path / "run"
    if failure == "provider":
        def fail_without_transport(provider, request):
            raise GatewayError("SYNTHETIC_PROVIDER_SECRET_CANARY")
        monkeypatch.setattr(MockProvider, "complete", fail_without_transport)
    else:
        monkeypatch.setattr(operator, "naive_mock_spec", lambda: {"shell": "FORBIDDEN_MODEL_CODE"})
    code = None
    try:
        code = operator.main(["--mode", "mock", "--run-dir", str(run_dir),
                              "--seal-dir", str(tmp_path / "sealed")])
    except Exception:
        # Raising does not substitute for the required auditable failed receipt.
        pass
    path = run_dir / "G3_report.json"
    assert path.is_file(), "Failed generation discarded its outcome and budget accounting"
    report = json.loads(path.read_bytes())
    assert type(code) is int and code != 0
    assert report["mode"] == "mock" and report.get("real") is not True
    assert any(category in report["stop_reason"] for category in ("fail", "block", "error"))
    usage = report["usage"]
    assert usage["attempts"] == 1
    assert usage["estimated_cost_usd"] == usage["uncertain_cost_usd"] == 0
    captured = capsys.readouterr()
    emitted = path.read_text(encoding="utf-8") + captured.out + captured.err
    for marker in ("SYNTHETIC_PROVIDER_SECRET_CANARY", "FORBIDDEN_MODEL_CODE"):
        assert marker not in emitted


@pytest.mark.parametrize("limit", ["0", "-1", "nan", "inf", "-inf"])
def test_invalid_real_spend_ceiling_is_rejected_before_input_or_provider_access(tmp_path, monkeypatch, limit):
    # Only preflight is exercised. The genuine real-model path never runs.
    calls = []
    monkeypatch.setenv("MODEL_API_KEY", "SYNTHETIC_NON_CREDENTIAL")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", limit)
    def never_load(args):
        calls.append("input_loader")
        raise RuntimeError("SYNTHETIC_PREFLIGHT_STOP")
    monkeypatch.setattr(operator, "_load_operator_evidence", never_load)
    monkeypatch.setattr(operator, "MetaProvider", lambda *a, **k: pytest.fail("Provider constructed before valid approvals"))
    code = operator.main(["--mode", "real", "--max-usd", "0.5", "--confirm-real-run",
        "--operator-context-pin", "sha256:" + "0" * 64, "--ledger-dir", str(tmp_path / "ledger"),
        "--hypotheses-file", str(tmp_path / "hypotheses.json"), "--observation-digests", "0" * 64,
        "--suite", str(tmp_path / "suite.json"), "--suite-digest", "sha256:" + "0" * 64])
    assert code != 0
    assert calls == [], "Nonfinite/nonpositive spend authorization reached input loading"


def test_clean_subprocess_mock_is_nonbillable_and_reports_actual_naive_score(tmp_path):
    run_dir = tmp_path / "clean-process"
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}}
    env.update(PYTHONPATH=str(ROOT / "src"), SECOND_SOURCE_MAX_RUN_USD="0", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-B", "-m", "second_source.reconstruct", "--mode", "mock",
        "--run-dir", str(run_dir), "--seal-dir", str(tmp_path / "sealed")],
        cwd=ROOT, env=env, capture_output=True, timeout=180)
    assert result.returncode == 0
    report = json.loads((run_dir / "G3_report.json").read_bytes())
    assert report["origin"] == "mock" and report["real"] is False
    evaluation = report["evaluation"]
    assert evaluation["total"] == 25 and evaluation["indeterminate"] == 0
    assert 0 < evaluation["failed"] < 25
    assert evaluation["passed"] + evaluation["failed"] == 25
    assert report["usage"]["estimated_cost_usd"] == report["usage"]["uncertain_cost_usd"] == 0
    assert math.isfinite(report["usage"]["estimated_cost_usd"])


def test_archived_broker_artifact_keeps_exact_receipt_and_private_authority(workflow_control):
    from second_source.g3_verification import BrokerArtifact
    seen = workflow_control
    artifact = seen["artifact"]

    def find_archive(value):
        if isinstance(value, dict):
            if value.get("payload") == artifact.payload.decode() and value.get("signature") == artifact.signature:
                return BrokerArtifact(value["payload"].encode(), value["signature"])
            for child in value.values():
                found = find_archive(child)
                if found is not None:
                    return found
        return None

    restored = None
    for path in seen["run_dir"].rglob("*"):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        assert seen["run"]._key not in raw
        assert seen["run"]._key.hex().encode() not in raw
        try:
            found = find_archive(json.loads(raw))
        except (ValueError, UnicodeError):
            continue
        if found is not None:
            restored = found
    assert restored == artifact, "Immutable broker payload/signature was not archived exactly"
    admitted = seen["run"]._verify(restored, "CANDIDATE_ORIGIN")
    assert admitted["receipt"] == seen["report"]["evaluation_receipt"]["origin"]
    assert _digest(restored.payload) == seen["report"]["evaluation_receipt"]["artifact_digest"]
    with pytest.raises(EvaluationBlocked, match="Unattested"):
        seen["run"]._verify(replace(restored, payload=restored.payload + b" "), "CANDIDATE_ORIGIN")


def test_persisted_candidate_offline_rescore_retains_non_ai_claim(workflow_control):
    from second_source.g3_verification import OwnedLedgerReferenceAdapter, evaluate_sealed_suite
    seen = workflow_control
    raw = json.loads(seen["artifact"].payload)["spec"].encode()
    candidates = [path for path in seen["run_dir"].rglob("*") if path.is_file() and path.read_bytes() == raw]
    assert candidates, "Offline re-score requires the admitted candidate bytes"
    scope = operator.create_scope(0)
    suite = load_sealed_suite(seen["seal_dir"] / "suite.json", seen["report"]["suite_digest"], scope)
    report = evaluate_sealed_suite(suite, scope, OwnedLedgerReferenceAdapter(scope),
                                   CandidateReferenceAdapter(candidates[0].read_bytes(), scope))
    assert report.model_feedback() == seen["report"]["evaluation"]
    # An archived local signature is not a portable provider attestation.
    # Re-score confirms behavior; it does not grant a new REAL_MODEL origin.
    assert seen["report"]["origin"] == "mock" and seen["report"]["real"] is False
