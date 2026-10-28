"""Independent request/provenance probes; no network, credentials or paid calls."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from second_source.candidate_adapter import CandidateExecutionLimits, _run_worker
from second_source.budgets import RunBudget
from second_source.candidate_generation import build_generation_context, request_candidate_spec
from second_source.contracts import Budgets, Observation
from second_source.evidence import EvidenceLedger
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.model_gateway import MetaProvider, MockProvider, ModelGateway, ModelRequest
from second_source.g3_verification import (
    BrokerArtifact, EvaluationBlocked, PinnedEvaluatorRun, OWNED_REFERENCE_DIGEST,
    _digest, _encode, _scope_digest, _admit_suite, _reference_identity, _code_pins,
    load_sealed_suite, prepare_generation_request, seal_owned_ledger_suite,
)

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "tests/g3_fixtures/valid_candidate.json"


def approved_context():
    observation = {
        "observation_id": "public:0", "sequence_id": "public", "action_index": 0,
        "input_action": {"command": "list"}, "output": {"ok": True, "items": []},
        "exit_code": 0, "duration_ms": 0, "status": "ok",
    }
    digest = hashlib.sha256(json.dumps(observation, sort_keys=True).encode()).hexdigest()
    context = build_generation_context(
        scope_goal="Reconstruct authorized public ledger behavior", requirement_ids=["REQ-LEDGER"],
        allowed_commands=["add", "list", "total", "remove"], excluded_subsystems=["payments"],
        public_command_manifest=json.loads((ROOT / "fixtures/owned_ledger/public_contract.json").read_bytes()),
        redacted_views=[{"digest": digest, "observation": observation}],
        hypotheses=[{"id": "public-hypothesis", "statement": "List returns record items", "evidence_ids": [digest]}],
    )
    return context, {digest: deepcopy(observation)}


def test_isolated_generation_request_contains_no_tools_gold_or_environment(monkeypatch):
    context, registry = approved_context()
    monkeypatch.setenv("SYNTHETIC_SECRET", "ENV_SYNTHETIC_CANARY")
    request = prepare_generation_request(context, approved_evidence=registry,
        forbidden_markers=("ENV_SYNTHETIC_CANARY", "SEALED_SYNTHETIC_CANARY", "fixtures/owned_ledger/reference.py"))
    assert request["stage"] == "synthesize" and "tools" not in request
    assert "JSON Schema:" in request["messages"][0]["content"]
    assert len(request["messages"]) == 3
    assert "hypothesis" in json.dumps(request)


@pytest.mark.parametrize("kind", ["unknown_evidence", "changed_observation", "injected_root", "forged_hypothesis"])
def test_generation_context_contamination_is_rejected(kind):
    context, registry = approved_context()
    if kind == "unknown_evidence":
        context["evidence"][0]["digest"] = "0" * 64
    elif kind == "changed_observation":
        context["evidence"][0]["observation"]["output"]["source"] = "SOURCE_SYNTHETIC_CANARY"
    elif kind == "injected_root":
        context["reference_source"] = "SOURCE_SYNTHETIC_CANARY"
    else:
        context["hypotheses"][0]["evidence_ids"] = ["0" * 64]
    with pytest.raises(EvaluationBlocked):
        prepare_generation_request(context, approved_evidence=registry)


def test_canary_scan_covers_approved_fields_and_final_gateway_schema():
    context, registry = approved_context()
    context["scope"]["goal"] = "Reconstruct behavior GOLD_SYNTHETIC_CANARY"
    with pytest.raises(EvaluationBlocked, match="Protected material"):
        prepare_generation_request(context, approved_evidence=registry, forbidden_markers=("GOLD_SYNTHETIC_CANARY",))
    context, registry = approved_context()
    with pytest.raises(EvaluationBlocked, match="Protected material"):
        prepare_generation_request(context, approved_evidence=registry, forbidden_markers=("JSON Schema:",))


def test_private_suite_identifiers_do_not_enter_model_request(cli_scope, tmp_path):
    path, digest = seal_owned_ledger_suite(tmp_path / "evaluator", cli_scope)
    suite = load_sealed_suite(path, digest, cli_scope)
    context, registry = approved_context()
    request = prepare_generation_request(context, approved_evidence=registry,
        forbidden_markers=tuple(case.case_id for case in suite.cases()))
    assert str(path) not in json.dumps(request)


@pytest.mark.parametrize("mode", ["probe", "generation_probe"])
def test_both_workers_are_denied_actual_reference_source_and_external_gold(mode, tmp_path):
    gold = tmp_path / "gold-canary"
    gold.write_text("SYNTHETIC_GOLD_CANARY")
    for path in (ROOT / "fixtures/owned_ledger/reference.py", gold):
        response = _run_worker(mode, {"path": str(path)}, CandidateExecutionLimits())
        assert all(response["checks"].values()), response


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction probe")
def test_windows_junction_cannot_expose_evaluator_storage(cli_scope, tmp_path):
    target = tmp_path / "evaluator"
    path, digest = seal_owned_ledger_suite(target, cli_scope)
    alias = tmp_path / "alias"
    command = str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe")
    result = subprocess.run([command, "/d", "/c", "mklink", "/J", str(alias), str(target)], capture_output=True)
    assert result.returncode == 0
    with pytest.raises(EvaluationBlocked, match="links or junctions"):
        load_sealed_suite(alias / "suite.json", digest, cli_scope)
    response = _run_worker("probe", {"path": str(alias / "suite.json")}, CandidateExecutionLimits())
    assert response["checks"]["file"] is True


@pytest.fixture
def approved_run(cli_scope, tmp_path):
    ledger = EvidenceLedger(tmp_path / "observations")
    observation = Observation(observation_id="public-obs:0", sequence_id="public-obs",
        action_index=0, input_action={"command": "list"}, output={"ok": True, "items": []},
        exit_code=0, duration_ms=0, status="ok")
    digest = ledger.store(observation)["sha256"]
    store = HypothesisStore()
    store.add_batch(validate_batch({"hypotheses": [{"id": "public-hypothesis",
        "statement": "List returns items", "evidence_ids": [digest]}]}, frozenset({digest})))
    raw = _encode({"suite_version": "1", "scope_digest": _scope_digest(cli_scope), "cases": [
        {"case_id": "PRIVATE_PUBLIC_CONTROL_ID", "category": "empty", "actions": [{"command": "list"}]},
    ]})
    suite = _admit_suite(raw, _digest(raw), cli_scope)
    run = PinnedEvaluatorRun(suite, cli_scope, ledger=ledger,
        observation_digests=(digest,), hypotheses=store)
    return run, ledger, store, suite, digest


def control_provider():
    return MockProvider([{"content": json.loads(CONTROL.read_bytes())}])


def control_budget():
    return RunBudget(Budgets(max_estimated_model_spend_usd=0))


def test_pinned_control_receipt_exact_request_score_and_replay(approved_run):
    run, ledger, store, suite, digest = approved_run
    ticket = run.prepare()
    seen = []
    def responder(request):
        seen.append(request.model_dump(mode="json"))
        return {"content": json.loads(CONTROL.read_bytes())}
    budget = control_budget()
    origin = run.generate(ticket, MockProvider(responder=responder), budget)
    assert seen == [json.loads(ticket.payload)["wire"]]
    result = run.evaluate(origin)
    assert result["kind"] == "PINNED_TRUSTED_CONTROL_EVALUATION"
    assert result["evaluation"] == {"passed": 1, "failed": 0, "indeterminate": 0, "total": 1, "failure_categories": {}}
    assert result["origin"]["origin"] == "mock" and result["origin"]["real"] is False
    assert result["reference_digest"] == result["code_pins"]["reference"]
    assert result["reference_source_digest"] == result["code_pins"]["reference_identity"] == OWNED_REFERENCE_DIGEST
    assert result["suite_digest"] == suite.digest and result["plan_digest"] == run.plan_digest
    assert result["origin"]["request_digest"] == _digest(_encode(seen[0]))
    assert run.evaluate(origin) == result
    assert budget.estimated_cost_usd == budget.uncertain_cost_usd == 0
    assert budget.attempts == 1
    with pytest.raises(EvaluationBlocked, match="replay"):
        run.generate(ticket, control_provider(), budget)
    with pytest.raises(EvaluationBlocked, match="real-model"):
        run.evaluate(origin, claim="REAL_MODEL")
    wire = json.dumps(result)
    assert "PRIVATE_PUBLIC_CONTROL_ID" not in wire and "input_action" not in wire
    assert "List returns items" not in wire
    feedback = run.repair_feedback(origin)
    assert feedback == result["evaluation"]
    feedback["failure_categories"]["hidden"] = 1
    assert "hidden" not in run.repair_feedback(origin)["failure_categories"]


@pytest.mark.parametrize("field", ["scope", "public_commands", "evidence", "hypotheses"])
def test_caller_cannot_replace_approved_scope_manifest_observations_or_hypotheses(approved_run, field):
    run, *_ = approved_run
    context = json.loads(run._context_raw)
    if field == "hypotheses":
        # Valid citation, fabricated statement/status: Muse's registry gate misses this.
        context[field][0]["statement"] = "Forged rule GOLD_CANARY"
        context[field][0]["status"] = "supported"
    elif field == "evidence":
        context[field][0]["observation"]["output"] = {"ok": True, "source": "SOURCE_CANARY"}
    else:
        context[field]["description" if field == "public_commands" else "goal"] = "FORGED_CANARY"
    with pytest.raises(EvaluationBlocked, match="frozen"):
        run.prepare(context)


def test_mutable_registry_store_and_scope_aliases_do_not_change_approval(approved_run):
    run, ledger, store, _, digest = approved_run
    before = run._context_raw
    store.update_status("public-hypothesis", "contradicted")
    # Post-freeze disk corruption must not change frozen approved bytes.
    (ledger.root / (digest + ".json")).write_text("corrupted")
    run.prepare()
    assert run._context_raw == before


@pytest.mark.parametrize("kind", ["ticket", "candidate", "receipt", "wrong_run"])
def test_unsigned_tampered_or_cross_run_artifacts_are_rejected(approved_run, kind, cli_scope):
    run, ledger, store, suite, digest = approved_run
    ticket = run.prepare()
    if kind == "ticket":
        value = json.loads(ticket.payload)
        value["wire"]["messages"][-1]["content"] += "LEAK_CANARY"
        with pytest.raises(EvaluationBlocked, match="Unattested"):
            run.generate(replace(ticket, payload=_encode(value)), control_provider(), control_budget())
        return
    origin = run.generate(ticket, control_provider(), control_budget())
    if kind == "wrong_run":
        other = PinnedEvaluatorRun(suite, cli_scope, ledger=ledger, observation_digests=(digest,), hypotheses=store)
        with pytest.raises(EvaluationBlocked, match="Unattested"):
            other.evaluate(origin)
        return
    value = json.loads(origin.payload)
    if kind == "candidate":
        value["spec"] += " "
    else:
        value["receipt"].update(origin="real", real=True, response_id="fabricated")
    with pytest.raises(EvaluationBlocked, match="Unattested"):
        run.evaluate(replace(origin, payload=_encode(value)), claim="REAL_MODEL")


def test_release_path_rejects_reference_injection(approved_run):
    run, *_ = approved_run
    origin = run.generate(run.prepare(), control_provider(), control_budget())
    with pytest.raises(TypeError):
        run.evaluate(origin, reference=object())
    with pytest.raises(EvaluationBlocked):
        run.evaluate({"origin": "real", "reference_digest": OWNED_REFERENCE_DIGEST})


def test_changed_trusted_code_pin_blocks_before_model_or_score(approved_run, monkeypatch):
    from second_source import g3_verification as verifier
    run, *_ = approved_run
    origin = run.generate(run.prepare(), control_provider(), control_budget())
    original = verifier._code_pins
    def changed():
        return {**original(), "verifier": "sha256:" + "0" * 64}
    monkeypatch.setattr(verifier, "_code_pins", changed)
    with pytest.raises(EvaluationBlocked, match="changed after run freeze"):
        run.evaluate(origin)
    with pytest.raises(EvaluationBlocked, match="changed after run freeze"):
        run.prepare()


@pytest.mark.parametrize("field", ["messages", "json_schema", "max_output_tokens", "prompt_version"])
def test_final_wire_drift_is_blocked_before_provider(approved_run, monkeypatch, field):
    from second_source import candidate_generation
    run, *_ = approved_run
    ticket = run.prepare()
    build = candidate_generation.build_synthesize_request
    def changed(*args, **kwargs):
        request = build(*args, **kwargs)
        values = {
            "messages": (*request.messages, {"role": "user", "content": "UNAPPROVED"}),
            "json_schema": {"type": "object"}, "max_output_tokens": 1999,
            "prompt_version": "unapproved-version",
        }
        return request.model_copy(update={field: values[field]})
    monkeypatch.setattr(candidate_generation, "build_synthesize_request", changed)
    def never_send(request):
        pytest.fail("Changed inspected wire reached provider")
    budget = control_budget()
    with pytest.raises(EvaluationBlocked, match="Broker attempt failed"):
        run.generate(ticket, MockProvider(responder=never_send), budget)
    assert budget.attempts == 1 and budget.estimated_cost_usd == 0


def test_concurrent_request_replay_has_only_one_transport(approved_run):
    from concurrent.futures import ThreadPoolExecutor
    run, *_ = approved_run
    ticket = run.prepare()
    budget = control_budget()
    provider = control_provider()
    def attempt():
        try:
            return run.generate(ticket, provider, budget)
        except EvaluationBlocked:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(type(value) is BrokerArtifact for value in outcomes) == 1
    assert budget.attempts == 1


def test_modified_original_is_rejected_at_freeze(approved_run, monkeypatch, cli_scope):
    from second_source import g3_verification
    _, ledger, store, suite, digest = approved_run
    monkeypatch.setattr(g3_verification, "OWNED_REFERENCE_DIGEST", "sha256:" + "0" * 64)
    with pytest.raises(EvaluationBlocked, match="reviewed pinned fixture"):
        PinnedEvaluatorRun(suite, cli_scope, ledger=ledger, observation_digests=(digest,), hypotheses=store)


def test_reference_source_identity_accepts_checkout_newlines_and_pins_exact_worker_bytes():
    raw = (ROOT / "fixtures/owned_ledger/reference.py").read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    assert _reference_identity(lf) == _reference_identity(crlf) == OWNED_REFERENCE_DIGEST
    assert _digest(lf) != _digest(crlf)
    pins = _code_pins()
    assert pins["reference"] == _digest(raw)
    assert pins["reference_identity"] == OWNED_REFERENCE_DIGEST
    assert pins["reference_adapter"] == _digest((ROOT / "src/second_source/reference.py").read_bytes())
    assert _reference_identity(lf + b"# changed source\n") != OWNED_REFERENCE_DIGEST


def test_failed_attempt_consumes_ticket_and_does_not_issue_origin(approved_run):
    run, *_ = approved_run
    ticket = run.prepare()
    budget = control_budget()
    with pytest.raises(EvaluationBlocked, match="Broker attempt failed"):
        run.generate(ticket, MockProvider(), budget)
    assert budget.attempts == 1
    with pytest.raises(EvaluationBlocked, match="replay"):
        run.generate(ticket, control_provider(), budget)
    with pytest.raises(EvaluationBlocked):
        run.repair_feedback(ticket)


@pytest.mark.parametrize("phase", ["transport", "after_reported_usage"])
def test_interrupted_broker_preserves_uncertain_or_reported_usage_and_blocks_retry(
    approved_run, cli_scope, tmp_path, monkeypatch, phase
):
    """Synthetic transport only: no network, genuine provider output or spend."""
    from second_source import g3_verification as verification, reconstruct as operator
    from second_source.budgets import estimate_cost_usd
    from second_source.model_gateway import ModelResponse

    initial, ledger, store, suite, digest = approved_run
    run = PinnedEvaluatorRun(suite, cli_scope, ledger=ledger,
        observation_digests=(digest,), hypotheses=store,
        operator_approved_context_digest=initial.approved_context_digest)
    budget = RunBudget(cli_scope.budgets)
    provider = MetaProvider("SYNTHETIC_NON_CREDENTIAL")
    seen = []

    def forbidden_network(*args, **kwargs):
        pytest.fail("Synthetic interruption probe attempted network access")

    def simulated_transport(request):
        seen.append(budget._outstanding)
        if phase == "transport":
            raise KeyboardInterrupt
        return ModelResponse(provider=provider.provider_name, model=provider.model,
            real=True, response_id="NON_AI_SIMULATION_NOT_PROVIDER_EVIDENCE",
            content_text="", parsed=json.loads(CONTROL.read_bytes()), latency_ms=0,
            input_tokens=101, output_tokens=42, prompt_version=request.prompt_version)

    def interrupt_after_usage(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("urllib.request.urlopen", forbidden_network)
    monkeypatch.setattr(provider, "complete", simulated_transport)
    if phase == "after_reported_usage":
        monkeypatch.setattr(verification, "CandidateReferenceAdapter", interrupt_after_usage)
    ticket = run.prepare()
    with pytest.raises(KeyboardInterrupt):
        run.generate(ticket, provider, budget, spending_approved=True)
    assert len(seen) == 1 and seen[0] > 0
    assert budget.attempts == 1 and budget._outstanding == 0
    if phase == "transport":
        assert budget.uncertain_cost_usd == seen[0]
        assert budget.estimated_cost_usd == budget.input_tokens == budget.output_tokens == budget.model_calls == 0
    else:
        assert (budget.input_tokens, budget.output_tokens, budget.model_calls) == (101, 42, 1)
        assert budget.estimated_cost_usd == estimate_cost_usd(101, 42, provider.rates)
        assert budget.uncertain_cost_usd == 0
    before = budget.summary()
    with pytest.raises((EvaluationBlocked, KeyboardInterrupt)) as stopped:
        run.generate(run.prepare(), provider, budget, spending_approved=True)
    assert isinstance(stopped.value, EvaluationBlocked) and "fresh independent preflight" in str(stopped.value)
    assert budget.summary() == before and len(seen) == 1
    with pytest.raises(EvaluationBlocked, match="replay"):
        run.generate(ticket, provider, budget, spending_approved=True)
    directory = tmp_path / "NON_AI_SIMULATED_STOPPED_RECEIPT"
    directory.mkdir()
    report = operator._write_failure_report(run_dir=directory, mode="real", real=True,
        stage="broker", budget=budget, interrupted=True)
    saved = json.loads((directory / "G3_report.json").read_bytes())
    assert saved == report and saved["stop_reason"] == "interrupted_stopped"
    for key in ("attempts", "input_tokens", "output_tokens", "estimated_cost_usd", "uncertain_cost_usd"):
        assert saved["usage"][key] == getattr(budget, key)


def test_real_broker_is_blocked_before_transport_without_owner_approval(approved_run, monkeypatch):
    run, *_ = approved_run
    provider = MetaProvider("SYNTHETIC_NON_CREDENTIAL")
    monkeypatch.setattr(provider, "complete", lambda request: pytest.fail("Unapproved real transport reached"))
    with pytest.raises(EvaluationBlocked, match="owner spending approval"):
        run.generate(run.prepare(), provider, control_budget())


def test_local_registry_alone_cannot_authorize_real_generation(approved_run, monkeypatch):
    run, *_ = approved_run
    provider = MetaProvider("SYNTHETIC_NON_CREDENTIAL")
    monkeypatch.setattr(provider, "complete", lambda request: pytest.fail("Unattested real transport reached"))
    with pytest.raises(EvaluationBlocked, match="approved G2 context pin"):
        run.generate(run.prepare(), provider, RunBudget(Budgets()), spending_approved=True)


def test_wrong_operator_input_pin_is_rejected(approved_run, cli_scope):
    _, ledger, store, suite, digest = approved_run
    with pytest.raises(EvaluationBlocked, match="operator's approved G2"):
        PinnedEvaluatorRun(suite, cli_scope, ledger=ledger, observation_digests=(digest,),
            hypotheses=store, operator_approved_context_digest="sha256:" + "0" * 64)


def test_run_budget_cannot_be_reset_and_attempts_are_bounded(approved_run):
    run, *_ = approved_run
    budget = control_budget()
    first = run.generate(run.prepare(), control_provider(), budget)
    with pytest.raises(EvaluationBlocked, match="replaced or widened"):
        run.generate(run.prepare(), control_provider(), control_budget())
    run.generate(run.prepare(), control_provider(), budget)
    run.generate(run.prepare(), control_provider(), budget)
    with pytest.raises(EvaluationBlocked, match="attempt limit"):
        run.generate(run.prepare(), control_provider(), budget)
    assert budget.attempts == 3
    with pytest.raises(EvaluationBlocked, match="no independent evaluation"):
        run.repair_feedback(first)


@pytest.mark.parametrize("signature", ["", "not-ascii-\u0100", "0" * 64])
def test_malformed_artifact_signatures_fail_closed(approved_run, signature):
    run, *_ = approved_run
    with pytest.raises(EvaluationBlocked, match="Unattested"):
        run.generate(BrokerArtifact(b"{}", signature), control_provider(), control_budget())


def test_ledger_content_address_and_hypothesis_citations_are_authenticated(approved_run, cli_scope):
    run, ledger, store, suite, digest = approved_run
    (ledger.root / (digest + ".json")).write_text("tampered")
    with pytest.raises(EvaluationBlocked, match="registry admission"):
        PinnedEvaluatorRun(suite, cli_scope, ledger=ledger, observation_digests=(digest,), hypotheses=store)
    with pytest.raises(EvaluationBlocked, match="Trusted ledger"):
        PinnedEvaluatorRun(suite, cli_scope, ledger={}, observation_digests=(digest,), hypotheses=store)


def test_muse_direct_real_function_must_not_allow_omitting_all_pins(approved_run, monkeypatch):
    run, *_ = approved_run
    provider = MetaProvider("SYNTHETIC_NON_CREDENTIAL")
    called = []
    def never_send(request):
        called.append(True)
        raise RuntimeError("NONBILLABLE_TRANSPORT_SENTINEL")
    monkeypatch.setattr(provider, "complete", never_send)
    gateway = ModelGateway(provider, RunBudget(Budgets()))
    try:
        request_candidate_spec(json.loads(run._context_raw), gateway)
    except Exception:
        pass
    assert not called, "Muse direct real path reached transport with every provenance pin omitted"


def test_no_approved_case_details_or_tools_in_generation_ticket(approved_run, monkeypatch):
    run, *_ = approved_run
    monkeypatch.setenv("SYNTHETIC_SECRET", "ENV_CANARY")
    wire = json.loads(run.prepare().payload)["wire"]
    assert set(wire) == set(ModelRequest.model_fields)
    rendered = json.dumps(wire)
    for marker in ("ENV_CANARY", "PRIVATE_PUBLIC_CONTROL_ID", "reference.py", "g3_verification", "tools"):
        assert marker not in rendered
