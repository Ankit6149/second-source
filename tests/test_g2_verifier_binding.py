"""Independent NON_AI G2 -> G3 input binding and pre-credential refusal gates."""
import copy
import json
import os
import urllib.request

import pytest

from second_source import reconstruct as operator
from second_source.contracts import ScopeContract
from second_source.g2_persistence import export_batch, inspect_run, scope_digest_of
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.model_gateway import MetaProvider
from second_source.model_gateway import MockProvider
from test_g2_persistence_roundtrip import run_recorded
from test_g2_verifier_persistence import read_events, reseal_non_ai_fixture


@pytest.fixture(autouse=True)
def no_credentials_or_transport(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")

    def forbidden(*args, **kwargs):
        raise AssertionError("No genuine provider transport is authorized")

    monkeypatch.setattr(MetaProvider, "complete", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


@pytest.fixture
def bound_control(cli_scope, reference, tmp_path):
    _, run, _, _, _ = run_recorded(cli_scope, reference, tmp_path)
    archive = inspect_run(run)
    batch = archive["hypothesis_batches"][-1]
    store = HypothesisStore()
    store.add_batch(validate_batch(batch, frozenset(archive["observation_digests"])))
    return run, archive, store, operator.create_scope(.50)


def check(control, **overrides):
    run, archive, store, scope = control
    args = {
        "manifest_path": str(run / "G2_receipt.json"),
        "digests": tuple(archive["observation_digests"]), "store": store,
        "receipt_sha256": archive["receipt_sha256"], "scope": scope,
    }
    args.update(overrides)
    return operator._check_g2_manifest(**args)


def test_complete_mock_binds_for_inspection_but_not_real_dispatch(bound_control):
    receipt = check(bound_control)
    assert receipt["complete"] is True and receipt["origin"] == "mock"
    assert receipt["receipt_sha256"] == bound_control[1]["receipt_sha256"]
    with pytest.raises(RuntimeError, match="NON_AI"):
        check(bound_control, require_real=True)


@pytest.mark.parametrize("witness", [None, "0" * 64])
def test_binding_requires_the_external_receipt_witness(bound_control, witness):
    with pytest.raises((RuntimeError, ValueError)):
        check(bound_control, receipt_sha256=witness)


@pytest.mark.parametrize("field", ["statement", "citations", "alternatives", "questions", "status", "subset"])
def test_all_original_hypothesis_fields_are_bound(bound_control, field):
    _, archive, _, _ = bound_control
    batch = copy.deepcopy(archive["hypothesis_batches"][-1])
    hypothesis = batch["hypotheses"][0]
    if field == "statement":
        hypothesis["statement"] = "NON_AI altered reconstruction context"
    elif field == "citations":
        hypothesis["evidence_ids"] = [next(d for d in archive["observation_digests"]
                                              if d not in hypothesis["evidence_ids"])]
    elif field == "alternatives":
        hypothesis["alternatives"] = ["NON_AI substituted alternative"]
    elif field == "questions":
        hypothesis["unresolved_questions"] = ["NON_AI substituted question"]
    elif field == "status":
        hypothesis["status"] = "supported"
    else:
        batch["hypotheses"] = batch["hypotheses"][:1]
    changed = HypothesisStore()
    changed.add_batch(validate_batch(batch, frozenset(archive["observation_digests"])))
    with pytest.raises(RuntimeError, match="original G2 response batch"):
        check(bound_control, store=changed)


def test_complete_evidence_set_is_bound(bound_control):
    digests = tuple(bound_control[1]["observation_digests"])
    assert len(digests) > 1
    with pytest.raises(RuntimeError, match="complete G2 evidence"):
        check(bound_control, digests=digests[:-1])


@pytest.mark.parametrize("identity", ["target", "reference", "public"])
def test_other_target_or_reference_identity_cannot_back_g3(bound_control, identity):
    run, _, _, _ = bound_control
    events = read_events(run)
    manifest = events[0]["payload"]
    if identity == "target":
        manifest["scope"]["target"]["reference_command_id"] = "NON_AI-other-target"
        manifest["scope_digest"] = scope_digest_of(ScopeContract.model_validate(manifest["scope"]))
    elif identity == "reference":
        manifest["code_pins"]["reference_fixture"] = "0" * 64
    else:
        manifest["code_pins"]["public_manifest"] = "0" * 64
    fixture_witness = reseal_non_ai_fixture(run, events)
    with pytest.raises(RuntimeError, match="target/reference/public identity"):
        check(bound_control, receipt_sha256=fixture_witness)


@pytest.mark.parametrize("reason", ["missing_receipt", "wrong_witness", "mock_origin"])
def test_valid_evaluator_context_still_requires_genuine_g2_before_key(
    bound_control, tmp_path, monkeypatch, reason,
):
    run, archive, _, _ = bound_control
    batch_file = export_batch(run, tmp_path / "original-batch.json",
                              expected_receipt_sha256=archive["receipt_sha256"])
    common = ["--max-usd", ".50", "--ledger-dir", str(run / "evidence"),
              "--hypotheses-file", str(batch_file), "--observation-digests",
              ",".join(archive["observation_digests"])]
    sealed = tmp_path / "sealed"
    preflight = tmp_path / "preflight"
    assert operator.main(["--mode", "preflight", *common, "--seal-dir", str(sealed),
                          "--run-dir", str(preflight)]) == 0
    inspected = json.loads((preflight / "G3_preflight.json").read_bytes())
    assert inspected["provider_calls"] == 0 and inspected["real_input_eligible"] is False
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", ".50")
    original_get = os.environ.get

    def guarded(name, *args):
        assert name != "MODEL_API_KEY", "Genuine G2 binding must precede credential access"
        return original_get(name, *args)

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid genuine input must not construct a provider")

    monkeypatch.setattr(os.environ, "get", guarded)
    monkeypatch.setattr(operator, "MetaProvider", forbidden)
    target = tmp_path / "must-not-dispatch"
    args = ["--mode", "real", *common, "--confirm-real-run", "--operator-context-pin",
            inspected["approved_context_digest"], "--suite", str(sealed / "suite.json"),
            "--suite-digest", inspected["suite_digest"], "--run-dir", str(target)]
    if reason != "missing_receipt":
        args += ["--g2-receipt", str(run / "G2_receipt.json"), "--g2-receipt-sha256",
                 "0" * 64 if reason == "wrong_witness" else archive["receipt_sha256"]]
    assert operator.main(args) == 2
    assert not target.exists()


def test_bound_mock_discovery_to_candidate_verification_reuses_exact_g2_context(
    bound_control, tmp_path, monkeypatch,
):
    run, archive, _, _ = bound_control
    exported = export_batch(run, tmp_path / "original-batch.json",
                            expected_receipt_sha256=archive["receipt_sha256"])
    target = tmp_path / "bound-g3-mock"
    original_get = os.environ.get
    original_complete = MockProvider.complete
    dispatched = []

    def guarded(name, *args):
        assert name != "MODEL_API_KEY", "Bound NON_AI workflow must not read credentials"
        return original_get(name, *args)

    def forbidden(*args, **kwargs):
        raise AssertionError("Bound mock must reuse G2 inputs without real execution or replacement")

    def inspect_mock_dispatch(self, request):
        provenance = json.loads((target / "G3_input_provenance.json").read_bytes())
        assert provenance["g2"]["receipt_sha256"] == archive["receipt_sha256"]
        assert provenance["g2"]["run_id"] == archive["run_id"]
        dispatched.append(request.stage)
        return original_complete(self, request)

    monkeypatch.setattr(os.environ, "get", guarded)
    monkeypatch.setattr(operator, "MetaProvider", forbidden)
    monkeypatch.setattr(operator, "_observe_mock_evidence", forbidden)
    monkeypatch.setattr(operator, "mock_hypotheses", forbidden)
    monkeypatch.setattr(MockProvider, "complete", inspect_mock_dispatch)
    assert operator.main([
        "--mode", "mock", "--ledger-dir", str(run / "evidence"),
        "--hypotheses-file", str(exported), "--observation-digests",
        ",".join(archive["observation_digests"]), "--g2-receipt", str(run / "G2_receipt.json"),
        "--g2-receipt-sha256", archive["receipt_sha256"],
        "--seal-dir", str(tmp_path / "sealed"), "--run-dir", str(target),
    ]) == 0
    assert len(dispatched) == 1
    report = json.loads((target / "G3_report.json").read_bytes())
    assert report["mode"] == report["origin"] == report["provider"] == "mock"
    assert report["real"] is False and report["stop_reason"] == "completed_mock_run"
    assert {k: report["evaluation"][k] for k in ("passed", "failed", "indeterminate", "total")} == {
        "passed": 22, "failed": 3, "indeterminate": 0, "total": 25,
    }
    assert report["usage"]["attempts"] == 1
    assert report["usage"]["estimated_cost_usd"] == report["usage"]["uncertain_cost_usd"] == 0
    assert report["g2_input_provenance"]["receipt_sha256"] == archive["receipt_sha256"]
    assert report["g2_input_provenance"]["origin"] == "mock"
    assert report["evidence_artifact_count"] == len(archive["observation_digests"])
    provenance = json.loads((target / "G3_input_provenance.json").read_bytes())
    assert provenance["approved_context_digest"] == report["approved_context_digest"]
    assert provenance["g2"] == report["g2_input_provenance"]
    assert (target / report["candidate_artifact"]).is_file()
    assert (target / report["broker_artifact"]).is_file()


def test_g3_loads_complete_evidence_from_authenticated_g2_receipt(bound_control, tmp_path):
    """NON_AI: auto-binding includes uncited observations in original G2 order."""
    from argparse import Namespace
    from second_source.g2_persistence import export_batch

    run, archive, _, _ = bound_control
    exported = export_batch(run, tmp_path / "original.json",
                            expected_receipt_sha256=archive["receipt_sha256"])
    args = Namespace(
        observation_digests="@g2", g2_manifest=str(run / "G2_receipt.json"),
        g2_receipt_sha256=archive["receipt_sha256"],
        ledger_dir=str(run / "evidence"), hypotheses_file=str(exported),
    )
    _, _, digests = operator._load_operator_evidence(args)
    assert digests == tuple(archive["observation_digests"])
    assert len(digests) > 1


def test_g3_autobinding_requires_real_external_receipt_witness(bound_control, tmp_path):
    from argparse import Namespace
    run, archive, _, _ = bound_control
    args = Namespace(
        observation_digests="@g2", g2_manifest=str(run / "G2_receipt.json"),
        g2_receipt_sha256=None, ledger_dir=str(run / "evidence"),
        hypotheses_file=str(tmp_path / "none.json"),
    )
    with pytest.raises(RuntimeError, match="external G2 receipt witness"):
        operator._load_operator_evidence(args)
    args.g2_receipt_sha256 = "0" * 64
    with pytest.raises(RuntimeError, match="not authenticated"):
        operator._load_operator_evidence(args)
