"""Nonbillable discovery archive/reload and G2 -> zero-call G3 preflight gates."""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

import pytest

from second_source import live_experiment as live
from second_source.budgets import RunBudget
from second_source.evidence import EvidenceLedger
from second_source.g2_persistence import (
    DiscoveryJournal, PersistenceError, canonical, digest, export_batch, inspect_run,
)
from second_source.model_gateway import (
    GatewayError, MetaProvider, MockProvider, ModelGateway, ModelRequest,
)


@pytest.fixture(autouse=True)
def no_paid_transport(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")
    def forbidden(*args, **kwargs):
        raise AssertionError("No HTTP transport is authorized in persistence tests")
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def mock_run(tmp_path):
    run = tmp_path / "mock-g2-test"
    assert live.main(["--mode", "mock", "--run-dir", str(run)]) == 0
    return run


def gateway_archive(tmp_path, real=False):
    run = tmp_path / "partial"
    run.mkdir()
    EvidenceLedger(run / "evidence")
    scope = live.create_scope(.25 if real else 0, 1)
    journal = DiscoveryJournal(run, live._discovery_manifest(scope, "real" if real else "mock", 1))
    budget = RunBudget(scope.budgets)
    return run, journal, budget


def clean_env():
    env = {k: v for k, v in os.environ.items()
           if k.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"}}
    env.update(PYTHONPATH=str(live.ROOT / "src"), PYTHONDONTWRITEBYTECODE="1",
               SECOND_SOURCE_MAX_RUN_USD="0")
    return env


def test_original_response_batch_receipt_reload_and_zero_call_preflight(tmp_path, capsys):
    run = mock_run(tmp_path)
    result = inspect_run(run)
    assert result["complete"] and result["state"] == "completed"
    assert result["origin"] == "mock" and result["model"] == "mock-muse-0"
    assert result["execution_resume_supported"] is False
    assert result["budget"]["attempts"] == 2
    assert result["budget"]["model_calls"] == 2
    assert result["budget"]["estimated_cost_usd"] == result["budget"]["uncertain_cost_usd"] == 0
    assert result["budget"]["input_tokens"] > 0 and result["budget"]["output_tokens"] > 0
    events = [json.loads(p.read_bytes()) for p in sorted((run / "discovery").glob("*.json"))]
    response = next(e["payload"] for e in events if e["kind"] == "model_result")
    assert digest(response["response"]["content_text"].encode()) == response["receipt"]["content_sha256"]
    assert json.loads(response["response"]["content_text"]) == result["hypothesis_batches"][0]
    exported = export_batch(run, tmp_path / "batch.json", expected_receipt_sha256=result["receipt_sha256"])
    assert json.loads(exported.read_bytes()) == result["hypothesis_batches"][0]
    assert all(not r["real"] and r["outcome"] == "ok" for r in result["model_receipts"])
    child = subprocess.run([sys.executable, "-B", "-m", "second_source.live_experiment",
                            "--inspect-run", str(run), "--receipt-sha256", result["receipt_sha256"]],
                           env=clean_env(), capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout)["receipt_sha256"] == result["receipt_sha256"]
    # A mock archive can exercise inspection; it is never genuine input approval.
    child = subprocess.run([sys.executable, "-B", "-m", "second_source.reconstruct", "--mode", "preflight",
                            "--max-usd", ".50", "--ledger-dir", str(run / "evidence"),
                            "--hypotheses-file", str(exported), "--observation-digests",
                            ",".join(result["observation_digests"]), "--seal-dir", str(tmp_path / "seal"),
                            "--run-dir", str(tmp_path / "preflight")],
                           env=clean_env(), capture_output=True, text=True, timeout=45)
    assert child.returncode == 0, child.stdout + child.stderr
    receipt = json.loads((tmp_path / "preflight" / "G3_preflight.json").read_bytes())
    assert receipt["provider_calls"] == 0


def test_run_identity_exclusive_and_export_requires_pinned_complete_archive(tmp_path):
    run = mock_run(tmp_path)
    result = inspect_run(run)
    with pytest.raises(FileExistsError):
        live.main(["--mode", "mock", "--run-dir", str(run)])
    with pytest.raises(FileExistsError):
        DiscoveryJournal(run, {})
    with pytest.raises(PersistenceError):
        export_batch(run, tmp_path / "bad.json", expected_receipt_sha256="0" * 64)
    target = export_batch(run, tmp_path / "batch.json", expected_receipt_sha256=result["receipt_sha256"])
    with pytest.raises(FileExistsError):
        export_batch(run, target, expected_receipt_sha256=result["receipt_sha256"])
    assert not (tmp_path / "bad.json").exists()


@pytest.mark.parametrize("damage", ["observation", "response", "missing_event", "missing_receipt", "renamed_run"])
def test_mutated_or_incomplete_archives_cannot_export(tmp_path, damage):
    run = mock_run(tmp_path)
    pinned = inspect_run(run)["receipt_sha256"]
    if damage == "observation":
        next((run / "evidence").glob("*.json")).write_bytes(b"{}")
    elif damage == "response":
        path = next(p for p in sorted((run / "discovery").glob("*.json"))
                    if json.loads(p.read_bytes())["kind"] == "model_result")
        doc = json.loads(path.read_bytes())
        doc["payload"]["response"]["content_text"] = "{}"
        path.write_bytes(canonical(doc))
    elif damage == "missing_event":
        (run / "discovery" / "000002.json").unlink()
    elif damage == "missing_receipt":
        (run / "G2_receipt.json").unlink()
        assert inspect_run(run)["state"] == "interrupted"
    else:
        moved = tmp_path / "other-run"
        run.rename(moved)
        run = moved
    with pytest.raises((ValueError, OSError)):
        export_batch(run, tmp_path / "bad.json", expected_receipt_sha256=pinned)
    assert not (tmp_path / "bad.json").exists()


@pytest.mark.parametrize("failure", ["malformed", "unknown_citation", "provider"])
def test_bad_responses_preserve_incomplete_records_without_fabrication(tmp_path, monkeypatch, failure):
    original = live._mock_response
    def respond(request):
        if failure == "provider":
            raise GatewayError("fixture unavailable")
        doc = original(request)
        if failure == "malformed":
            return {"content": "{"}
        doc["content"]["hypotheses"][0]["evidence_ids"] = ["0" * 64]
        return doc
    monkeypatch.setattr(live, "_mock_response", respond)
    run = tmp_path / "failed"
    assert live.main(["--mode", "mock", "--run-dir", str(run)]) == 3
    result = inspect_run(run)
    assert not result["complete"] and result["state"] == "stopped"
    assert result["budget"]["attempts"] == 1
    assert result["hypothesis_batches"] == []
    assert result["budget"]["estimated_cost_usd"] == result["budget"]["uncertain_cost_usd"] == 0
    with pytest.raises(PersistenceError):
        export_batch(run, tmp_path / "bad.json", expected_receipt_sha256=result["receipt_sha256"])


@pytest.mark.parametrize("failure", [KeyboardInterrupt, GatewayError, RuntimeError])
def test_interrupt_and_provider_failure_preserve_exact_uncertain_reservation(tmp_path, monkeypatch, failure):
    run, journal, budget = gateway_archive(tmp_path, real=True)
    observed_pending = []
    def complete(self, request):
        # No network: inspect the durable pre-transport record inside the stub.
        observed_pending.append(inspect_run(run))
        raise failure("fixture failure")
    monkeypatch.setattr(MetaProvider, "complete", complete)
    gateway = ModelGateway(MetaProvider("noncredential-fixture"), budget, audit=journal.append)
    with pytest.raises(failure):
        gateway.generate(ModelRequest(stage="hypothesize", messages=({"role": "user", "content": "fixture"},),
                                      estimated_input_tokens=100, max_output_tokens=20))
    pending = observed_pending[0]
    assert pending["state"] == "interrupted" and not pending["complete"]
    assert pending["pending_attempt"]["attempt"] == 1
    assert pending["pending_uncertain_cost_usd"] == pytest.approx(.00021)
    result = inspect_run(run)
    assert result["pending_attempt"] is None and result["budget"]["attempts"] == 1
    assert result["budget"]["model_calls"] == 0
    assert result["budget"]["input_tokens"] == result["budget"]["output_tokens"] == 0
    assert result["budget"]["uncertain_cost_usd"] == pytest.approx(.00021)
    assert gateway.receipts[0].outcome == "failed"
    assert budget._outstanding == 0


def test_dispatch_persistence_failure_blocks_transport_and_releases_dollars(tmp_path, monkeypatch):
    run, journal, budget = gateway_archive(tmp_path, real=True)
    calls = []
    monkeypatch.setattr(MetaProvider, "complete", lambda *args: calls.append(1))
    def failed_write(*args):
        raise OSError("fixture fsync failure")
    monkeypatch.setattr(journal, "append", failed_write)
    gateway = ModelGateway(MetaProvider("noncredential-fixture"), budget, audit=journal.append)
    with pytest.raises(OSError):
        gateway.generate(ModelRequest(stage="hypothesize", messages=(), max_output_tokens=20))
    assert not calls and not gateway.receipts
    assert budget.attempts == 1 and budget.model_calls == 0
    assert budget._outstanding == budget.uncertain_cost_usd == budget.estimated_cost_usd == 0
    assert inspect_run(run)["complete"] is False


@pytest.mark.parametrize("stage", ["model_dispatch", "model_result"])
def test_one_shot_journal_failure_preserves_terminal_accounting(tmp_path, monkeypatch, stage):
    original = DiscoveryJournal.append
    failed = []
    def injected(self, kind, payload):
        if kind == stage and not failed:
            failed.append(True)
            raise OSError("fixture artifact write failure")
        return original(self, kind, payload)
    monkeypatch.setattr(DiscoveryJournal, "append", injected)
    run = tmp_path / "write-failed"
    with pytest.raises(OSError):
        live.main(["--mode", "mock", "--run-dir", str(run)])
    result = inspect_run(run)
    assert result["state"] == "failed" and not result["complete"]
    assert result["budget"]["attempts"] == 1
    assert result["budget"]["model_calls"] == (stage == "model_result")
    assert result["dispatch_count"] == (stage == "model_result")
    assert result["pending_attempt"] is None
    assert result["budget"]["uncertain_cost_usd"] == result["budget"]["estimated_cost_usd"] == 0
    if stage == "model_result":
        assert result["budget"]["input_tokens"] > 0 and result["budget"]["output_tokens"] > 0
        assert result["response_archive_complete"] is False
    with pytest.raises(PersistenceError):
        export_batch(run, tmp_path / "bad.json", expected_receipt_sha256=result["receipt_sha256"])


def test_offline_incomplete_inspection_and_nonfinite_approval_fail_closed(tmp_path, monkeypatch, capsys):
    run, journal, budget = gateway_archive(tmp_path)
    assert live.main(["--inspect-run", str(run)]) == 3
    assert "interrupted" in capsys.readouterr().out
    for value in ("nan", "inf", "-inf"):
        monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", value)
        assert live._authorized_limit() == 0
        assert live.main(["--max-usd", "0.25", "--confirm-real-run"]) == 2
    assert live.main(["--mode", "mock", "--max-usd", "nan"]) == 2


def test_g2_preflight_has_stable_pins_and_invalid_approval_never_reads_key(tmp_path, monkeypatch):
    pins = []
    for seed in ("1", "99"):
        path = tmp_path / ("preflight-" + seed)
        env = clean_env()
        env["PYTHONHASHSEED"] = seed
        child = subprocess.run([sys.executable, "-B", "-m", "second_source.live_experiment",
                                "--mode", "preflight", "--max-usd", ".25", "--rounds", "1",
                                "--run-dir", str(path)], env=env, capture_output=True, text=True, timeout=30)
        assert child.returncode == 0, child.stderr
        doc = json.loads((path / "G2_preflight.json").read_bytes())
        assert doc["origin"] == "inspection-only" and doc["provider_calls"] == 0
        assert doc["manifest"]["scope"]["budgets"]["max_model_calls"] == 3
        assert doc["manifest"]["origin"] == "real"
        pins.append(doc["manifest_sha256"])
    assert pins[0] == pins[1]
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", ".25")
    original_get = os.environ.get
    def read(name, *args):
        assert name != "MODEL_API_KEY", "Invalid approval must not read credentials"
        return original_get(name, *args)
    monkeypatch.setattr(os.environ, "get", read)
    for pin, budget, rounds in (("0" * 64, ".25", "1"), (pins[0], ".20", "1"), (pins[0], ".25", "2")):
        assert live.main(["--mode", "real", "--max-usd", budget, "--rounds", rounds,
                          "--confirm-real-run", "--operator-manifest-pin", pin]) == 2


@pytest.mark.parametrize("change", ["missing_receipts", "substituted_batch"])
def test_semantic_provenance_validation_rejects_internally_resealed_fixture(tmp_path, change):
    run = mock_run(tmp_path)
    # Deliberately recompute the fixture's local hash chain, exercising semantic
    # consistency as well as hashes. This supplies no authentic owner approval.
    head = ""
    for path in sorted((run / "discovery").glob("*.json")):
        doc = json.loads(path.read_bytes())
        if change == "missing_receipts" and doc["kind"] == "terminal":
            doc["payload"]["model_receipts"] = []
        if change == "substituted_batch" and doc["kind"] == "hypothesis_batch":
            doc["payload"]["batch"]["hypotheses"][0]["statement"] = "NON_AI deliberately substituted rule"
        doc["previous_sha256"] = head
        raw = canonical(doc)
        path.write_bytes(raw)
        head = digest(raw)
    receipt = json.loads((run / "G2_receipt.json").read_bytes())
    receipt["head_sha256"] = head
    raw = canonical(receipt)
    (run / "G2_receipt.json").write_bytes(raw)
    with pytest.raises(PersistenceError):
        export_batch(run, tmp_path / "bad.json", expected_receipt_sha256=digest(raw))


@pytest.mark.parametrize("failure,code,state", [(GatewayError, 3, "stopped"), (KeyboardInterrupt, 130, "interrupted")])
def test_later_proposal_failure_retains_original_hypothesis_and_receipts(tmp_path, monkeypatch, failure, code, state):
    original = live._mock_response
    def response(request):
        if request.stage == "propose":
            raise failure("NON_AI interruption after a valid hypothesis")
        return original(request)
    monkeypatch.setattr(live, "_mock_response", response)
    run = tmp_path / "later-failure"
    assert live.main(["--mode", "mock", "--run-dir", str(run)]) == code
    result = inspect_run(run)
    assert result["state"] == state and not result["complete"]
    assert len(result["hypothesis_batches"]) == 1
    assert result["hypothesis_batches"][0]["hypotheses"][0]["statement"].startswith("NON_AI control")
    assert result["budget"]["attempts"] == 2 and result["budget"]["model_calls"] == 1
    assert [r["outcome"] for r in result["model_receipts"]] == ["ok", "failed"]
    with pytest.raises(PersistenceError):
        export_batch(run, tmp_path / "bad.json", expected_receipt_sha256=result["receipt_sha256"])


def test_model_budget_stop_retains_first_batch_without_an_extra_dispatch(tmp_path, monkeypatch):
    original = live.create_scope
    def scope(max_usd, max_rounds):
        value = original(max_usd, max_rounds)
        return value.model_copy(update={"budgets": value.budgets.model_copy(update={"max_model_calls": 1})})
    monkeypatch.setattr(live, "create_scope", scope)
    run = tmp_path / "budget-stop"
    assert live.main(["--mode", "mock", "--run-dir", str(run)]) == 3
    result = inspect_run(run)
    assert result["state"] == "stopped" and not result["complete"]
    assert result["budget"]["attempts"] == result["dispatch_count"] == 1
    assert len(result["hypothesis_batches"]) == 1
    assert len(result["model_receipts"]) == 1
