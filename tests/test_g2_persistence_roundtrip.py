"""Muse round-trip, status restoration and tamper checks, ported to one journal.

No legacy G2Recorder/manifest persistence system remains. Assertions retain
original statements, receipt identities, executed proposals and final statuses.
"""
from dataclasses import asdict
import json

import pytest

from g2_helpers import add_action, pred, responder
from second_source.budgets import RunBudget
from second_source.evidence import EvidenceLedger
from second_source.g2_persistence import DiscoveryJournal, PersistenceError, inspect_run, rebuild_store, scope_digest_of
from second_source.live_experiment import _discovery_manifest
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.loop import DiscoveryLoop
from second_source.model_gateway import MockProvider, ModelGateway
from second_source.planner import ExperimentPlanner
from second_source.runner import SafeCLIExperimentRunner
from second_source.scope_guard import ScopeGuard

SEED = ({"command": "add", "label": "Seed", "amount": 7}, {"command": "total"})


def run_recorded(cli_scope, reference, tmp_path):
    run = tmp_path / "run_p"
    run.mkdir()
    ledger = EvidenceLedger(run / "evidence")
    budget = RunBudget(cli_scope.budgets)
    manifest = _discovery_manifest(cli_scope, "mock", 1)
    manifest["seed_actions"] = list(SEED)
    journal = DiscoveryJournal(run, manifest)
    steps = [add_action("Dup", 3), add_action("Dup", 3)]
    preds = [pred("hyp-a", False, "duplicate_label"), pred("hyp-b", True)]
    gateway = ModelGateway(MockProvider(responder=responder(
        hyp_ids=("hyp-a", "hyp-b"), actions=steps, predictions=preds)), budget, audit=journal.append)
    store = HypothesisStore()
    plan = ExperimentPlanner(gateway, ScopeGuard(cli_scope), store, budget, cli_scope)
    loop = DiscoveryLoop(run_id=run.name, requirement_id="REQ-LEDGER", contract=cli_scope,
        runner=SafeCLIExperimentRunner(cli_scope, reference, ledger), ledger=ledger,
        hypotheses=store, planner=plan, budget=budget, max_rounds=1, journal=journal)
    report = loop.run(list(SEED))
    journal.finish(state="completed", report=asdict(report),
                   hypotheses=[h.model_dump(mode="json") for h in store.all()], receipts=gateway.receipts)
    return report, run, ledger, store, budget


def test_manifest_roundtrip_is_complete(cli_scope, reference, tmp_path):
    report, run, ledger, store, budget = run_recorded(cli_scope, reference, tmp_path)
    assert report.resolution_counts["supported"] == 1
    manifest = inspect_run(run)
    assert manifest["run_id"] == "run_p"
    assert manifest["state"] == "completed" and manifest["complete"]
    assert len(manifest["model_receipts"]) == 2
    assert all(r["response_id"] for r in manifest["model_receipts"])
    statements = [h["statement"] for batch in manifest["hypothesis_batches"] for h in batch["hypotheses"]]
    assert statements and all(s.strip() for s in statements)
    assert len(manifest["completed_rounds"]) == 1
    selected = manifest["completed_rounds"][0]["proposal"]
    assert selected["proposal_id"] == report.rounds[0].proposal_id
    assert len(selected["actions"]) == report.rounds[0].actions_executed == 2
    assert len(selected["predictions"]) == 2
    assert all(ledger.inspect(d) for d in manifest["observation_digests"])
    assert manifest["budget"] == budget.summary()


def test_reload_restores_statuses_and_citations(cli_scope, reference, tmp_path):
    _, run, ledger, _, _ = run_recorded(cli_scope, reference, tmp_path)
    manifest = inspect_run(run)
    restored = rebuild_store(run, expected_receipt_sha256=manifest["receipt_sha256"])
    assert restored.get("hyp-a").status == "supported"
    assert restored.get("hyp-b").status == "contradicted"
    assert manifest["execution_resume_supported"] is False
    follow_up = validate_batch({"hypotheses": [{"id": "hyp-c",
        "statement": "NON_AI follow-up citing preserved evidence",
        "evidence_ids": manifest["observation_digests"][:1]}]}, frozenset(manifest["observation_digests"]))
    assert follow_up.hypotheses[0].id == "hyp-c"
    assert all(ledger.inspect(d) for h in restored.all() for d in h.evidence_ids)


def test_malformed_archives_rejected(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "discovery").mkdir()
    (bad / "discovery" / "000001.json").write_bytes(b"not json at all")
    with pytest.raises(PersistenceError):
        inspect_run(bad)
    (bad / "discovery" / "000001.json").write_text(json.dumps({"version": 2}), encoding="utf-8")
    with pytest.raises(PersistenceError):
        inspect_run(bad)
    with pytest.raises(PersistenceError):
        inspect_run(tmp_path / "missing")


def test_empty_archive_refuses_complete_input(cli_scope, tmp_path):
    run = tmp_path / "empty"
    run.mkdir()
    EvidenceLedger(run / "evidence")
    journal = DiscoveryJournal(run, _discovery_manifest(cli_scope, "mock", 1))
    assert inspect_run(run)["complete"] is False
    budget = RunBudget(cli_scope.budgets)
    journal.finish(state="completed", report={"budget": budget.summary()}, hypotheses=[])
    with pytest.raises(PersistenceError):
        inspect_run(run)
    with pytest.raises(FileExistsError):
        DiscoveryJournal(run, {})


def test_ledger_tamper_detected(cli_scope, reference, tmp_path):
    _, run, ledger, _, _ = run_recorded(cli_scope, reference, tmp_path)
    next((run / "evidence").glob("*.json")).unlink()
    with pytest.raises((OSError, ValueError)):
        inspect_run(run)


def test_proposal_failure_before_dispatch_preserves_batch_and_receipts(tmp_path, monkeypatch):
    """Muse's pre-gateway failure retains usage without inventing an attempt."""
    from second_source import live_experiment as live
    from second_source.model_gateway import GatewayError
    def refused(*args, **kwargs):
        raise GatewayError("NON_AI pre-dispatch proposal failure")
    monkeypatch.setattr(ExperimentPlanner, "propose", refused)
    run = tmp_path / "proposal-blocked"
    assert live.main(["--mode", "mock", "--run-dir", str(run)]) == 3
    result = inspect_run(run)
    assert not result["complete"] and result["state"] == "stopped"
    assert len(result["hypothesis_batches"]) == len(result["model_receipts"]) == 1
    assert result["budget"]["attempts"] == result["budget"]["model_calls"] == 1
    assert result["model_receipts"][0]["stage"] == "hypothesize"
