"""Zero-call input binding; synthetic acceptance data is never historical G2."""
import json

import pytest

from second_source import reconstruct as operator
from second_source.contracts import Observation
from second_source.evidence import EvidenceLedger
from second_source.g3_verification import (
    EvaluationBlocked, PinnedEvaluatorRun, _digest, _encode, _scope_digest,
    load_sealed_suite,
)
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.model_gateway import MetaProvider, MockProvider


@pytest.fixture
def inspected_inputs(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Zero-call preflight constructed or invoked a model provider")

    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")
    monkeypatch.setattr(operator, "MetaProvider", forbidden)
    monkeypatch.setattr(MetaProvider, "complete", forbidden)
    monkeypatch.setattr(MockProvider, "complete", forbidden)
    ledger = EvidenceLedger(tmp_path / "synthetic-ledger")
    observation = Observation(
        observation_id="NON_AI_ACCEPTANCE:0", sequence_id="NON_AI_ACCEPTANCE",
        action_index=0, input_action={"command": "list"}, output={"ok": True, "items": []},
        exit_code=0, duration_ms=0, status="ok",
    )
    digest = ledger.store(observation)["sha256"]
    batch = {"hypotheses": [{"id": "NON_AI_ACCEPTANCE_HYPOTHESIS",
             "statement": "Synthetic acceptance fixture: empty list has no items",
             "evidence_ids": [digest]}]}
    hypotheses = tmp_path / "synthetic-hypotheses.json"
    hypotheses.write_text(json.dumps(batch), encoding="utf-8")
    store = HypothesisStore()
    store.add_batch(validate_batch(batch, frozenset({digest})))
    args = ["--mode", "preflight", "--max-usd", "0.35", "--ledger-dir", str(ledger.root),
            "--hypotheses-file", str(hypotheses), "--observation-digests", digest,
            "--run-dir", str(tmp_path / "inspection"), "--seal-dir", str(tmp_path / "sealed")]
    assert operator.main(args) == 0
    receipt = json.loads((tmp_path / "inspection/G3_preflight.json").read_bytes())
    return dict(root=tmp_path, ledger=ledger, digest=digest, store=store, hypotheses=hypotheses,
                receipt=receipt, args=args, batch=batch)


def test_zero_call_preflight_matches_independent_actual_input_freeze(inspected_inputs):
    data = inspected_inputs
    receipt = data["receipt"]
    scope = operator.create_scope(0.35)
    suite = load_sealed_suite(data["root"] / "sealed/suite.json", receipt["suite_digest"], scope)
    run = PinnedEvaluatorRun(suite, scope, ledger=data["ledger"],
                            observation_digests=(data["digest"],), hypotheses=data["store"])
    context = json.loads(run._context_raw)
    assert receipt["approved_context_digest"] == run.approved_context_digest
    assert receipt["scope_digest"] == _scope_digest(scope)
    assert receipt["observation_registry_digest"] == _digest(_encode(context["evidence"]))
    assert receipt["hypothesis_registry_digest"] == _digest(_encode(context["hypotheses"]))
    assert receipt["provider_calls"] == 0 and receipt["real"] is False
    assert receipt["origin"] == "inspection-only"
    assert receipt["evidence_artifact_count"] == 1
    assert context["hypotheses"][0]["id"] == "NON_AI_ACCEPTANCE_HYPOTHESIS"
    # Pinned plans contain fresh run IDs; comparing plan digests between two
    # authorities would be wrong. Compare stable input/suite/scope identities.
    with pytest.raises(EvaluationBlocked, match="wrong-scope"):
        load_sealed_suite(data["root"] / "sealed/suite.json", receipt["suite_digest"], operator.create_scope(0.5))


@pytest.mark.parametrize("change", ["hypothesis", "observation", "budget", "suite", "pin"])
def test_changed_inspected_input_blocks_real_before_provider_construction(inspected_inputs, monkeypatch, change):
    data = inspected_inputs
    receipt = data["receipt"]
    monkeypatch.setenv("MODEL_API_KEY", "SYNTHETIC_NON_CREDENTIAL")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.5")
    limit, pin = "0.35", receipt["approved_context_digest"]
    if change == "hypothesis":
        data["batch"]["hypotheses"][0]["statement"] = "Synthetic altered hypothesis"
        data["hypotheses"].write_text(json.dumps(data["batch"]), encoding="utf-8")
    elif change == "observation":
        path = data["ledger"].root / (data["digest"] + ".json")
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "budget":
        limit = "0.5"
    elif change == "suite":
        path = data["root"] / "sealed/suite.json"
        path.write_bytes(path.read_bytes() + b" ")
    else:
        pin = "sha256:" + "0" * 64
    code = operator.main(["--mode", "real", "--max-usd", limit, "--confirm-real-run",
        "--operator-context-pin", pin, "--ledger-dir", str(data["ledger"].root),
        "--hypotheses-file", str(data["hypotheses"]), "--observation-digests", data["digest"],
        "--suite", str(data["root"] / "sealed/suite.json"), "--suite-digest", receipt["suite_digest"],
        "--run-dir", str(data["root"] / "blocked-real")])
    assert code != 0


@pytest.mark.parametrize("mode", ["preflight", "real"])
@pytest.mark.parametrize("limit", ["nan", "inf", "-inf", "0", "-0.01"])
def test_invalid_cli_spend_blocks_before_loading_any_input(tmp_path, monkeypatch, mode, limit):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid spend authorization reached evidence or provider")

    monkeypatch.setenv("MODEL_API_KEY", "SYNTHETIC_NON_CREDENTIAL")
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0.5")
    monkeypatch.setattr(operator, "_load_operator_evidence", forbidden)
    monkeypatch.setattr(operator, "MetaProvider", forbidden)
    assert operator.main(["--mode", mode, "--max-usd=" + limit,
                          "--run-dir", str(tmp_path / "blocked")]) != 0


def test_missing_original_hypothesis_is_blocked_without_fabrication(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Missing hypothesis must not be replaced or sent to a provider")

    monkeypatch.setattr(operator, "mock_hypotheses", forbidden)
    monkeypatch.setattr(operator, "MetaProvider", forbidden)
    monkeypatch.setattr(MetaProvider, "complete", forbidden)
    assert operator.main(["--mode", "preflight", "--max-usd", "0.35",
        "--ledger-dir", str(tmp_path / "ledger"), "--hypotheses-file", str(tmp_path / "MISSING_ORIGINAL.json"),
        "--observation-digests", "0" * 64, "--run-dir", str(tmp_path / "blocked"),
        "--seal-dir", str(tmp_path / "sealed")]) != 0
    assert not (tmp_path / "blocked/G3_preflight.json").exists()
