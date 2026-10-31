"""Zero-call genuine-G3 readiness rehearsal through the real broker seam.

Every test drives PinnedEvaluatorRun.generate with a synthetic stand-in for
a model response. Nothing here measures model quality; the suite proves the
admission gate fails closed on malformed, truncated, incompatible, and
cross-protocol outputs, that guided synthesis matches full-spec
expressiveness for the ledger DSL at lower wire cost, and that generation
wires carry no sealed material. No credentials, network, or paid calls:
genuine transport is monkeypatched to raise.
"""
import json
import urllib.request
from pathlib import Path

import pytest

from second_source.budgets import RunBudget
from second_source.candidate_generation import build_spec_skeleton, merge_skeleton_fill
from second_source.contracts import Observation
from second_source.evidence import EvidenceLedger
from second_source.g3_verification import (
    EvaluationBlocked,
    PinnedEvaluatorRun,
    load_sealed_suite,
    seal_owned_ledger_suite,
)
from second_source.hypotheses import HypothesisStore, validate_batch
from second_source.model_gateway import MetaProvider, MockProvider
from second_source.reconstruct import create_scope
from test_g3_guided_synthesis import PUBLIC, correct_fill

ROOT = Path(__file__).resolve().parents[1]
CONTROL = json.loads((ROOT / "tests/g3_fixtures/valid_candidate.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_genuine_transport(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("SECOND_SOURCE_MAX_RUN_USD", "0")

    def forbidden(*args, **kwargs):
        raise AssertionError("Readiness rehearsal authorizes no genuine provider transport")

    monkeypatch.setattr(MetaProvider, "complete", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


@pytest.fixture(scope="module")
def ready_inputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("g3-readiness")
    scope = create_scope(0)
    ledger = EvidenceLedger(root / "observations")
    digest = ledger.store(Observation(
        observation_id="READINESS:0", sequence_id="READINESS", action_index=0,
        input_action={"command": "list"}, output={"ok": True, "items": []},
        exit_code=0, duration_ms=0, status="ok",
    ))["sha256"]
    store = HypothesisStore()
    store.add_batch(validate_batch({"hypotheses": [{
        "id": "READINESS_EMPTY_LIST", "statement": "Synthetic empty list control",
        "evidence_ids": [digest],
    }]}, frozenset({digest})))
    suite_path, suite_digest = seal_owned_ledger_suite(root / "sealed", scope)
    suite = load_sealed_suite(suite_path, suite_digest, scope)
    return scope, ledger, digest, store, suite


def _run(inputs, synthesis="full"):
    scope, ledger, digest, hypotheses, suite = inputs
    return PinnedEvaluatorRun(suite, scope, ledger=ledger,
        observation_digests=(digest,), hypotheses=hypotheses, synthesis=synthesis)


def _attempt(run, scope, content):
    ticket = run.prepare()
    budget = RunBudget(scope.budgets)
    return ticket, budget


def test_truncated_model_output_fails_before_admission(ready_inputs):
    scope = ready_inputs[0]
    run = _run(ready_inputs)
    ticket, budget = _attempt(run, scope, None)
    calls = {"n": 0}
    def responder(request):
        calls["n"] += 1
        return {"content": json.dumps(CONTROL)[:600]}
    with pytest.raises(EvaluationBlocked):
        run.generate(ticket, MockProvider(responder=responder), budget)
    # Rejected before response accounting: zero spend recorded, but the
    # attempt is consumed from the shared immutable attempt budget.
    assert calls["n"] == 1 and budget.model_calls == 0
    assert budget.estimated_cost_usd == 0
    for _ in range(2):
        with pytest.raises(EvaluationBlocked):
            run.generate(run.prepare(),
                         MockProvider(responder=responder), budget)
    assert calls["n"] == 3
    with pytest.raises(EvaluationBlocked):
        run.generate(run.prepare(),
                     MockProvider(script=[{"content": CONTROL}]), budget)


def test_non_json_output_fails_before_admission(ready_inputs):
    scope = ready_inputs[0]
    run = _run(ready_inputs)
    ticket = run.prepare()
    with pytest.raises(EvaluationBlocked):
        run.generate(ticket, MockProvider(script=[{"content": "not json{{{ TrUnCaTeD"}]),
                         RunBudget(scope.budgets))


def test_schema_incompatible_output_fails_before_admission(ready_inputs):
    scope = ready_inputs[0]
    run = _run(ready_inputs)
    ticket = run.prepare()
    bad = {"kind": "CANDIDATE_ORIGIN",
           "spec": {"spec_version": "1", "subsystem": "cli_ledger"}}
    with pytest.raises(EvaluationBlocked):
        run.generate(ticket, MockProvider(script=[{"content": bad}]),
                         RunBudget(scope.budgets))


def test_cross_protocol_content_rejected_on_both_tickets(ready_inputs):
    scope = ready_inputs[0]
    full = _run(ready_inputs, "full")
    with pytest.raises(EvaluationBlocked):
        full.generate(full.prepare(),
                      MockProvider(script=[{"content": correct_fill()}]),
                      RunBudget(scope.budgets))
    guided = _run(ready_inputs, "guided")
    with pytest.raises(EvaluationBlocked):
        guided.generate(guided.prepare(),
                        MockProvider(script=[{"content": CONTROL}]),
                        RunBudget(scope.budgets))


def test_guided_expressiveness_matches_full_control(ready_inputs):
    """Guided skeleton + fill reaches the exact full-spec control candidate."""
    merged = merge_skeleton_fill(build_spec_skeleton(PUBLIC), correct_fill())
    assert merged == CONTROL
    fill_chars, full_chars = len(json.dumps(correct_fill())), len(json.dumps(CONTROL))
    assert fill_chars < full_chars
    scope = ready_inputs[0]
    full = _run(ready_inputs, "full")
    full_artifact = full.generate(full.prepare(),
                                 MockProvider(script=[{"content": CONTROL}]),
                                 RunBudget(scope.budgets))
    guided = _run(ready_inputs, "guided")
    guided_artifact = guided.generate(guided.prepare(),
                                      MockProvider(script=[{"content": correct_fill()}]),
                                      RunBudget(scope.budgets))
    assert (json.loads(json.loads(full_artifact.payload)["spec"])
            == json.loads(json.loads(guided_artifact.payload)["spec"]))


def test_generation_wires_carry_no_sealed_material(ready_inputs):
    scope = ready_inputs[0]
    seen = {}
    def responder(protocol):
        def respond(request):
            seen[protocol] = json.dumps(request.model_dump(mode="json"), sort_keys=True)
            return {"content": CONTROL if protocol == "full" else correct_fill()}
        return respond
    full = _run(ready_inputs, "full")
    full.generate(full.prepare(), MockProvider(responder=responder("full")),
                  RunBudget(scope.budgets))
    guided = _run(ready_inputs, "guided")
    guided.generate(guided.prepare(), MockProvider(responder=responder("guided")),
                    RunBudget(scope.budgets))
    cases = [case.case_id for case in ready_inputs[-1].cases()]
    for protocol, wire in seen.items():
        assert cases, "sealed suite must be nonempty for this proof"
        for case_id in cases:
            assert case_id not in wire, (protocol, case_id)
        for marker in ("reference.py", "gold", ".runs", "AppData"):
            assert marker not in wire, (protocol, marker)
    assert len(seen["guided"]) < len(seen["full"])


def test_staged_generation_modules_import_without_stderr():
    """The isolated worker treats ANY subprocess stderr output as failure, so
    staged generation modules must import warning-free (a SyntaxWarning once
    broke guided preflight with an empty-looking rejection)."""
    import subprocess
    import sys
    modules = ("contracts", "scope_guard", "candidate_spec", "candidate_runtime",
               "candidate_adapter", "candidate_generation", "model_gateway",
               "budgets", "runner", "reference", "evidence", "schema_validate")
    completed = subprocess.run(
        [sys.executable, "-W", "error::SyntaxWarning", "-B", "-c",
         "import " + ", ".join("second_source." + name for name in modules)],
        capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert completed.stderr == "", completed.stderr[-2000:]


def test_guided_wire_carries_raised_cap_and_low_reasoning(ready_inputs):
    """The fake transport must observe the remediated 4096 cap (not the
    failed 800) with reasoning_effort low: 798 measured reasoning tokens
    plus fill content must fit."""
    from second_source.model_gateway import MockProvider
    scope = ready_inputs[0]
    seen = []

    def respond(request):
        seen.append(request.model_dump(mode="json"))
        return {"content": correct_fill()}

    guided = _run(ready_inputs, "guided")
    guided.generate(guided.prepare(), MockProvider(responder=respond),
                    RunBudget(scope.budgets))
    assert len(seen) == 1
    assert seen[0]["max_output_tokens"] == 4096
    assert seen[0]["reasoning_effort"] == "low"
