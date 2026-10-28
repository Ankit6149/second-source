"""Durable G2 persistence: record, reload, resume, reject — all nonbillable."""

import json

import pytest

from g2_helpers import add_action, pred, responder
from second_source.budgets import RunBudget
from second_source.evidence import EvidenceLedger
from second_source.g2_persistence import (
    G2Recorder,
    PersistenceError,
    load_manifest,
    manifest_completeness,
    rebuild_store,
    scope_digest_of,
    verify_ledger_coverage,
)
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.loop import DiscoveryLoop
from second_source.model_gateway import MockProvider, ModelGateway
from second_source.planner import ExperimentPlanner
from second_source.runner import SafeCLIExperimentRunner
from second_source.scope_guard import ScopeGuard

SEED = ({"command": "add", "label": "Seed", "amount": 7}, {"command": "total"})


def run_recorded(cli_scope, reference, tmp_path, ledger_name="ev", **kw):
    ledger = EvidenceLedger(tmp_path / ledger_name)
    budget = RunBudget(cli_scope.budgets)
    steps = [add_action("Dup", 3), add_action("Dup", 3)]
    preds = [pred("hyp-a", False, "duplicate_label"), pred("hyp-b", True)]
    gateway = ModelGateway(
        MockProvider(responder=responder(
            hyp_ids=("hyp-a", "hyp-b"), actions=steps, predictions=preds,
        )),
        budget,
    )
    store = HypothesisStore()
    plan = ExperimentPlanner(gateway, ScopeGuard(cli_scope), store, budget, cli_scope)
    recorder = G2Recorder(
        run_id="run_p", requirement_id="REQ-LEDGER",
        scope_digest=scope_digest_of(cli_scope),
    )
    loop = DiscoveryLoop(
        run_id="run_p", requirement_id="REQ-LEDGER", contract=cli_scope,
        runner=SafeCLIExperimentRunner(cli_scope, reference, ledger),
        ledger=ledger, hypotheses=store, planner=plan, budget=budget,
        max_rounds=1, recorder=recorder,
    )
    report = loop.run(list(SEED))
    return report, recorder, ledger, store, budget


def test_manifest_roundtrip_is_complete(cli_scope, reference, tmp_path):
    report, recorder, ledger, store, budget = run_recorded(
        cli_scope, reference, tmp_path
    )
    assert report.resolution_counts["supported"] == 1
    path = recorder.write(tmp_path / "run")
    manifest = load_manifest(path)
    assert manifest.run_id == "run_p"
    assert manifest.stop_reason == report.stop_reason
    assert manifest_completeness(manifest) == []
    assert verify_ledger_coverage(manifest, ledger) == []
    assert len(manifest.model_receipts) == 2
    assert all(r.response_id for r in manifest.model_receipts)
    statements = [
        h.statement
        for record in manifest.rounds
        for h in record.hypothesis_batch.hypotheses
    ]
    assert statements and all(s.strip() for s in statements)
    assert manifest.rounds[0].proposal is not None
    assert manifest.rounds[0].proposal.executed is True


def test_resume_restores_statuses_and_citations(cli_scope, reference, tmp_path):
    _, recorder, ledger, _, _ = run_recorded(cli_scope, reference, tmp_path)
    manifest = load_manifest(recorder.write(tmp_path / "run"))
    resumed = rebuild_store(manifest)
    assert resumed.get("hyp-a").status == "supported"
    assert resumed.get("hyp-b").status == "contradicted"
    known = {d for record in manifest.rounds for d in record.evidence_digests}
    follow_up = validate_batch(
        {"hypotheses": [{
            "id": "hyp-c",
            "statement": "follow-up citing prior evidence",
            "evidence_ids": sorted(known)[:1],
        }]},
        frozenset(known),
    )
    assert follow_up.hypotheses[0].id == "hyp-c"


def test_malformed_manifests_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"not json at all")
    with pytest.raises(PersistenceError):
        load_manifest(bad)
    schema_bad = tmp_path / "schema.json"
    schema_bad.write_bytes(json.dumps({"manifest_version": "1"}).encode())
    with pytest.raises(PersistenceError):
        load_manifest(schema_bad)
    missing = tmp_path / "missing.json"
    with pytest.raises(PersistenceError):
        load_manifest(missing)


def test_empty_recorder_refuses_manifest(cli_scope):
    recorder = G2Recorder(
        run_id="run_e", requirement_id="REQ-LEDGER",
        scope_digest=scope_digest_of(cli_scope),
    )
    with pytest.raises(PersistenceError):
        recorder.manifest(final_hypotheses=())
    with pytest.raises(PersistenceError):
        recorder.write("/nonexistent-dir-xyz")


def test_ledger_tamper_detected(cli_scope, reference, tmp_path):
    _, recorder, ledger, _, _ = run_recorded(cli_scope, reference, tmp_path)
    manifest = load_manifest(recorder.write(tmp_path / "run"))
    victim = next(iter((tmp_path / "ev").glob("*.json")))
    victim.unlink()
    missing = verify_ledger_coverage(manifest, ledger)
    assert len(missing) == 1 and victim.stem in missing[0]


def _manifest_json(tmp_path, name="run"):
    path = tmp_path / name / "g2_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_missing_receipts_invalidate_approval(cli_scope, reference, tmp_path):
    _, recorder, _, _, _ = run_recorded(cli_scope, reference, tmp_path)
    recorder.write(tmp_path / "run")
    doc = _manifest_json(tmp_path)
    assert doc["model_receipts"]
    doc["model_receipts"] = []
    stripped = tmp_path / "stripped" / "g2_manifest.json"
    stripped.parent.mkdir(parents=True)
    stripped.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PersistenceError, match="no model receipts"):
        load_manifest(stripped)


def test_final_statement_substitution_rejected(cli_scope, reference, tmp_path):
    from second_source.g2_persistence import G2RunManifest, manifest_approvable

    _, recorder, _, _, _ = run_recorded(cli_scope, reference, tmp_path)
    manifest = load_manifest(recorder.write(tmp_path / "run"))
    original = manifest.final_hypotheses[0].statement
    assert manifest_approvable(manifest) == []
    doc = _manifest_json(tmp_path)
    doc["final_hypotheses"][0]["statement"] = "fabricated replacement statement"
    forged = tmp_path / "forged" / "g2_manifest.json"
    forged.parent.mkdir(parents=True)
    forged.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PersistenceError, match="diverges"):
        load_manifest(forged)
    tampered = G2RunManifest.model_validate(doc)
    resumed = rebuild_store(tampered)
    assert resumed.get("hyp-a").statement != "fabricated replacement statement"
    assert resumed.get("hyp-a").status == "hypothesized"


def test_proposal_failure_preserves_batch_and_receipts(
    cli_scope, reference, tmp_path, monkeypatch
):
    from second_source.g2_persistence import manifest_approvable
    from second_source.model_gateway import GatewayError
    from second_source.planner import ExperimentPlanner

    def fail_propose(self, *args, **kwargs):
        raise GatewayError("SYNTHETIC_PROPOSE_FAILURE")

    monkeypatch.setattr(ExperimentPlanner, "propose", fail_propose)
    _, recorder, _, _, _ = run_recorded(cli_scope, reference, tmp_path)
    manifest = load_manifest(recorder.write(tmp_path / "run"))
    assert manifest.rounds[0].error == "provider_failed"
    assert manifest.rounds[0].hypothesis_batch.hypotheses
    assert manifest.rounds[0].receipt_seqs
    assert manifest.model_receipts
    blockers = manifest_approvable(manifest)
    assert blockers and any("recovery required" in b for b in blockers)


def test_scope_digest_stable_across_hash_seeds(tmp_path):
    import os
    import subprocess
    import sys

    script = tmp_path / "pin_seeds.py"
    script.write_text(
        "import json\n"
        "from second_source.contracts import (\n"
        "    ImplementationScope, ObservationScope, ScopeContract, ScopeMode,\n"
        "    TargetKind, TargetSpec,\n"
        ")\n"
        "from second_source.g2_persistence import scope_digest_of\n"
        "scope = ScopeContract(\n"
        "    target=TargetSpec(kind=TargetKind.CLI,\n"
        "                      reference_command_id='owned-ledger-v1',\n"
        "                      permission_ref='owned-fixture'),\n"
        "    goal='Reconstruct only the synthetic ledger CLI behaviors',\n"
        "    mode=ScopeMode.SELECTED_FLOWS,\n"
        "    observation=ObservationScope(\n"
        "        permitted_actions=frozenset({'cli'}),\n"
        "        allowed_commands=frozenset({'add', 'list', 'total', 'remove'})),\n"
        "    implementation=ImplementationScope(\n"
        "        requirements=frozenset({'REQ-LEDGER'}),\n"
        "        allowed_subsystems=frozenset({'cli_ledger'})),\n"
        ")\n"
        "print(scope_digest_of(scope))\n",
        encoding="utf-8",
    )
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parents[1]
    digests = set()
    for seed in ("1", "37", "99"):
        env = {k: v for k, v in os.environ.items()
               if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}}
        env.update(PYTHONPATH=str(root / "src"), PYTHONHASHSEED=seed,
                   PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "-B", str(script)],
            env=env, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        digests.add(result.stdout.strip())
    assert len(digests) == 1
