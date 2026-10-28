"""Independent NON_AI regressions for authenticated G2 discovery archives.

Local resealing below deliberately supplies no authentic owner approval. It
tests semantic consistency separately from the externally retained witness.
No legacy recorder, second workflow, credential or provider transport is used.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

import pytest

from second_source import live_experiment as live
from second_source.g2_persistence import (
    PersistenceError, canonical, digest, export_batch, inspect_run, rebuild_store,
)
from second_source.model_gateway import GatewayError, MetaProvider
from test_g2_persistence_roundtrip import run_recorded


@pytest.fixture(autouse=True)
def no_credentials_or_transport(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")

    def forbidden(*args, **kwargs):
        raise AssertionError("Independent persistence probes authorize no provider transport")

    monkeypatch.setattr(MetaProvider, "complete", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


@pytest.fixture
def archived_control(cli_scope, reference, tmp_path):
    report, run, ledger, store, budget = run_recorded(cli_scope, reference, tmp_path)
    original = inspect_run(run)
    assert original["complete"] and original["origin"] == "mock"
    assert original["budget"] == budget.summary()
    assert [r["outcome"] for r in original["model_receipts"]] == ["ok", "ok"]
    assert all(not r["real"] for r in original["model_receipts"])
    return run, original


def read_events(run):
    return [json.loads(p.read_bytes()) for p in sorted((run / "discovery").glob("*.json"))]


def reseal_non_ai_fixture(run, events):
    """Rewrite a synthetic local witness; this grants no real-input approval."""
    head = ""
    for seq, event in enumerate(events, 1):
        event["seq"] = seq
        event["previous_sha256"] = head
        raw = canonical(event)
        (run / "discovery" / f"{seq:06d}.json").write_bytes(raw)
        head = digest(raw)
    receipt_path = run / "G2_receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt.update(events=len(events), head_sha256=head)
    raw = canonical(receipt)
    receipt_path.write_bytes(raw)
    return digest(raw)


@pytest.mark.parametrize("change", [
    "missing_receipts", "original_batch_statement", "terminal_statement",
    "terminal_citations", "terminal_alternatives", "terminal_status",
    "round_proposal", "round_observation", "replayed_round",
])
def test_resealed_inconsistent_discovery_is_rejected(archived_control, tmp_path, change):
    run, original = archived_control
    events = read_events(run)
    batch = next(e["payload"] for e in events if e["kind"] == "hypothesis_batch")
    terminal = next(e["payload"] for e in events if e["kind"] == "terminal")
    round_event = next(e for e in events if e["kind"] == "round")
    if change == "missing_receipts":
        terminal["model_receipts"] = []
    elif change == "original_batch_statement":
        batch["batch"]["hypotheses"][0]["statement"] = "NON_AI substituted original statement"
    elif change == "terminal_statement":
        terminal["reconciled_hypotheses"][0]["statement"] = "NON_AI substituted final statement"
    elif change == "terminal_citations":
        terminal["reconciled_hypotheses"][0]["evidence_ids"] = ["0" * 64]
    elif change == "terminal_alternatives":
        terminal["reconciled_hypotheses"][0]["alternatives"] = ["NON_AI invented alternative"]
    elif change == "terminal_status":
        assert terminal["reconciled_hypotheses"][0]["status"] == "supported"
        terminal["reconciled_hypotheses"][0]["status"] = "contradicted"
    elif change == "round_proposal":
        round_event["payload"]["proposal_id"] = "NON_AI nonexistent proposal"
    elif change == "round_observation":
        round_event["payload"]["observation_ids"][0] = "NON_AI nonexistent observation"
    else:
        events.insert(-1, copy.deepcopy(round_event))
    fixture_witness = reseal_non_ai_fixture(run, events)
    assert fixture_witness != original["receipt_sha256"]
    with pytest.raises(PersistenceError):
        inspect_run(run, fixture_witness)
    with pytest.raises(PersistenceError):
        export_batch(run, tmp_path / "rejected.json", expected_receipt_sha256=fixture_witness)
    assert not (tmp_path / "rejected.json").exists()


def test_retained_witness_detects_semantically_valid_archive_replacement(archived_control, tmp_path):
    run, original = archived_control
    events = read_events(run)
    # A harmless progress note can remain semantically valid, but it cannot
    # match the externally retained hash of the original receipt.
    next(e["payload"] for e in events if e["kind"] == "round")["note"] = "NON_AI modified note"
    replacement_witness = reseal_non_ai_fixture(run, events)
    assert replacement_witness != original["receipt_sha256"]
    assert inspect_run(run)["complete"]
    with pytest.raises(PersistenceError, match="Pinned discovery receipt"):
        export_batch(run, tmp_path / "rejected.json", expected_receipt_sha256=original["receipt_sha256"])
    assert not (tmp_path / "rejected.json").exists()


@pytest.mark.parametrize("failure,exit_code,state", [
    (GatewayError, 3, "stopped"), (KeyboardInterrupt, 130, "interrupted"),
])
def test_later_failure_retains_original_hypothesis_and_exact_stage_usage(
    tmp_path, monkeypatch, failure, exit_code, state,
):
    responder = live._mock_response

    def fail_proposal(request):
        if request.stage == "propose":
            raise failure("NON_AI proposal failure after a valid hypothesis")
        return responder(request)

    monkeypatch.setattr(live, "_mock_response", fail_proposal)
    run = tmp_path / "failed-proposal"
    assert live.main(["--mode", "mock", "--run-dir", str(run)]) == exit_code
    loaded = inspect_run(run)
    assert loaded["state"] == state and not loaded["complete"]
    assert len(loaded["hypothesis_batches"]) == 1
    receipts = loaded["model_receipts"]
    assert [(r["stage"], r["outcome"]) for r in receipts] == [
        ("hypothesize", "ok"), ("propose", "failed"),
    ]
    assert loaded["budget"]["attempts"] == loaded["dispatch_count"] == 2
    assert loaded["budget"]["model_calls"] == 1
    assert loaded["budget"]["input_tokens"] == sum(r["input_tokens"] for r in receipts)
    assert loaded["budget"]["output_tokens"] == sum(r["output_tokens"] for r in receipts)
    assert loaded["budget"]["input_tokens"] > 0
    assert loaded["budget"]["estimated_cost_usd"] == loaded["budget"]["uncertain_cost_usd"] == 0
    response = next(e["payload"] for e in read_events(run) if e["kind"] == "model_result")
    assert json.loads(response["response"]["content_text"]) == loaded["hypothesis_batches"][0]
    restored = rebuild_store(run, expected_receipt_sha256=loaded["receipt_sha256"])
    assert restored.get("mock-rule").statement == loaded["hypothesis_batches"][0]["hypotheses"][0]["statement"]
    with pytest.raises(PersistenceError):
        export_batch(run, tmp_path / "rejected.json", expected_receipt_sha256=loaded["receipt_sha256"])


def test_scope_and_full_preflight_pins_are_stable_without_execution(tmp_path):
    source = Path(live.__file__).resolve().parents[1]
    child_code = """
import json, os, sys, urllib.request
from second_source import live_experiment as live
def forbidden(*args, **kwargs):
    raise AssertionError('Preflight must not construct or dispatch execution')
live.MetaProvider = live.MockProvider = live.CLIReferenceAdapter = forbidden
urllib.request.urlopen = forbidden
getenv = os.environ.get
def guarded(name, *args):
    if name == 'MODEL_API_KEY':
        raise AssertionError('Preflight must not read a credential')
    return getenv(name, *args)
os.environ.get = guarded
raise SystemExit(live.main(sys.argv[1:]))
"""
    manifests = []
    for seed in ("1", "37", "99"):
        env = {k: v for k, v in os.environ.items()
               if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"}}
        env.update(PYTHONPATH=str(source), PYTHONHASHSEED=seed,
                   PYTHONDONTWRITEBYTECODE="1", SECOND_SOURCE_MAX_RUN_USD="0")
        target = tmp_path / ("preflight-" + seed)
        child = subprocess.run(
            [sys.executable, "-B", "-c", child_code, "--mode", "preflight", "--max-usd", ".25",
             "--rounds", "1", "--run-dir", str(target)],
            env=env, capture_output=True, text=True, timeout=30,
        )
        assert child.returncode == 0, child.stderr
        receipt = json.loads((target / "G2_preflight.json").read_bytes())
        assert receipt["origin"] == "inspection-only" and receipt["provider_calls"] == 0
        assert receipt["manifest"]["origin"] == "real"
        manifests.append((receipt["manifest_sha256"], receipt["manifest"]["scope_digest"]))
    assert len(set(manifests)) == 1


@pytest.mark.parametrize("budget", ["nan", "inf", "-inf", "0", "-0.1"])
def test_nonfinite_or_nonpositive_approval_blocks_before_credentials(tmp_path, monkeypatch, budget):
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", ".25")
    original_get = os.environ.get

    def guarded(name, *args):
        assert name != "MODEL_API_KEY", "Invalid approval must not read credentials"
        return original_get(name, *args)

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid approval must not construct execution")

    monkeypatch.setattr(os.environ, "get", guarded)
    monkeypatch.setattr(live, "MetaProvider", forbidden)
    monkeypatch.setattr(live, "CLIReferenceAdapter", forbidden)
    target = tmp_path / "must-not-start"
    assert live.main([
        "--mode", "real", "--max-usd=" + budget, "--confirm-real-run",
        "--operator-manifest-pin", "0" * 64, "--run-dir", str(target),
    ]) == 2
    assert not target.exists()
