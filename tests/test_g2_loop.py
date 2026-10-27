"""G2 end-to-end mock discovery loop on the owned fixture."""

import pytest

from g2_helpers import add_action, pred, responder, wiring
from second_source.loop import STOP_REASONS

SEED = ({"command": "add", "label": "Seed", "amount": 7}, {"command": "total"})


def test_mock_loop_resolves_hypotheses(cli_scope, reference, tmp_path):
    """One hypothesis supported, one contradicted, from real observations."""
    steps = [add_action("Dup", 3), add_action("Dup", 3)]
    preds = [pred("hyp-a", False, "duplicate_label"), pred("hyp-b", True)]
    loop, ledger, _, _, _ = wiring(
        cli_scope, reference, tmp_path,
        responder(hyp_ids=("hyp-a", "hyp-b"), actions=steps, predictions=preds),
        max_rounds=1,
    )
    report = loop.run(list(SEED))
    assert len(report.rounds) == 1
    assert report.real_model_calls == 0
    assert report.mock_model_calls == 2
    assert report.resolution_counts == {
        "hypothesized": 0, "supported": 1, "contradicted": 1, "unresolved": 0,
    }
    assert report.rounds[0].actions_executed == 2
    assert report.rounds[0].reset_boundary == "fresh_process_per_sequence"


def test_stateful_sequence_vs_fresh_reset(cli_scope, reference, tmp_path):
    """add A -> add A -> total in ONE sequence shows burst state; a fresh
    sequence shows the reset boundary. This is the G2 discrimination demo."""
    from second_source.contracts import ProposedAction
    from second_source.runner import SafeCLIExperimentRunner
    from second_source.evidence import EvidenceLedger

    ledger = EvidenceLedger(tmp_path / "ev")
    runner = SafeCLIExperimentRunner(cli_scope, reference, ledger)
    seq = runner.run([
        ProposedAction(kind="cli", target="add", requirement_id="REQ-LEDGER",
                       payload={"label": "A", "amount": 1}),
        ProposedAction(kind="cli", target="add", requirement_id="REQ-LEDGER",
                       payload={"label": "A", "amount": 1}),
        ProposedAction(kind="cli", target="total", requirement_id="REQ-LEDGER"),
    ])
    assert seq.observations[0].output == {"ok": True, "id": "1"}
    assert seq.observations[1].output == {"ok": False, "error": "duplicate_label"}
    assert seq.observations[2].output["count"] == 1
    fresh = runner.run([
        ProposedAction(kind="cli", target="add", requirement_id="REQ-LEDGER",
                       payload={"label": "A", "amount": 1}),
    ])
    assert fresh.observations[0].output == {"ok": True, "id": "1"}


def test_conclusive_error_contradicts(cli_scope, reference, tmp_path):
    """A target_error is conclusive evidence, not an inconclusive harness fault."""
    steps = [{"command": "add", "params": {"label": "Bad", "amount": -1}}]
    preds = [pred("hyp-a", True)]
    loop, _, _, _, _ = wiring(
        cli_scope, reference, tmp_path,
        responder(hyp_ids=("hyp-a",), actions=steps, predictions=preds),
        max_rounds=1,
    )
    report = loop.run(list(SEED))
    assert report.resolution_counts["contradicted"] == 1


def test_timeout_leaves_hypotheses_unresolved(cli_scope, tmp_path):
    """A harness timeout yields no evidence: statuses stay hypothesized."""
    from second_source.contracts import Observation, SequenceResult
    from second_source.evidence import EvidenceLedger
    from second_source.budgets import RunBudget
    from second_source.hypotheses import HypothesisStore
    from second_source.loop import DiscoveryLoop
    from second_source.model_gateway import MockProvider, ModelGateway
    from second_source.planner import ExperimentPlanner
    from second_source.scope_guard import ScopeGuard
    from g2_helpers import responder

    class FlakyRunner:
        def __init__(self):
            self.count = 0

        def run(self, actions):
            self.count += 1
            if self.count == 1:
                obs = Observation(
                    observation_id="seed:0", sequence_id="seed", action_index=0,
                    input_action={"command": "total"}, output={"ok": True},
                    exit_code=0, duration_ms=1, status="ok",
                )
                return SequenceResult(sequence_id="seed", observations=(obs,), status="ok", stderr="")
            return SequenceResult(sequence_id="r1", observations=(), status="timeout", stderr="boom")

    ledger = EvidenceLedger(tmp_path / "ev")
    budget = RunBudget(cli_scope.budgets)
    gateway = ModelGateway(
        MockProvider(responder=responder(hyp_ids=("hyp-a", "hyp-b"))), budget
    )
    store = HypothesisStore()
    plan = ExperimentPlanner(gateway, ScopeGuard(cli_scope), store, budget, cli_scope)
    loop = DiscoveryLoop(
        run_id="run_t", requirement_id="REQ-LEDGER", contract=cli_scope,
        runner=FlakyRunner(), ledger=ledger, hypotheses=store,
        planner=plan, budget=budget, max_rounds=1,
    )
    report = loop.run([{"command": "total"}])
    assert report.resolution_counts == {
        "hypothesized": 2, "supported": 0, "contradicted": 0, "unresolved": 0,
    }


def test_model_budget_stop_is_clean(cli_scope, reference, tmp_path):
    tight = cli_scope.budgets.model_copy(update={"max_model_calls": 0})
    loop, _, _, _, _ = wiring(cli_scope, reference, tmp_path, responder(), budgets=tight)
    report = loop.run(list(SEED))
    assert report.stop_reason == "budget"
    assert report.real_model_calls == 0


def test_guard_blocked_when_nothing_allowed(cli_scope, reference, tmp_path):
    loop, ledger, _, _, _ = wiring(
        cli_scope, reference, tmp_path, responder(actions=[{"command": "nope", "params": {}}])
    )
    report = loop.run(list(SEED))
    assert report.stop_reason == "guard_blocked"
    assert "COMMAND_NOT_ALLOWED" in report.rejection_codes
    assert len(list(ledger.root.glob("*.json"))) == 2  # seed only


def test_failed_model_request_is_not_reported_as_scope_guard_rejection(cli_scope, reference, tmp_path):
    def invalid_hypothesis(_request):
        # Mock provider fails schema validation on the first model call.
        return {"content": {"unexpected": "bad"}}

    loop, ledger, _, _, _ = wiring(
        cli_scope, reference, tmp_path, invalid_hypothesis, max_rounds=1
    )
    report = loop.run(list(SEED))
    assert report.stop_reason == "model_error"
    assert report.real_model_calls == 0
    assert report.rounds[-1].note.startswith("model stop:")
    assert len(list(ledger.root.glob("*.json"))) == 2  # seed only


def test_live_pattern_corrects_denied_first_proposal_with_one_model_retry(cli_scope, reference, tmp_path):
    """First Muse proposal is valid JSON but disallowed; second is model-selected."""
    import json
    from g2_helpers import hyp_doc, propose_doc

    stages = []

    def adaptive(request):
        stages.append(request.stage)
        context = json.loads(next(m["content"] for m in request.messages if m["role"] == "user"))
        if request.stage == "hypothesize":
            return {"content": hyp_doc(("hyp-a", "hyp-b"), context["evidence"][0]["digest"])}
        ids = [h["id"] for h in context["extra"]["hypotheses"]]
        if "prior_rejection_codes" not in context["extra"]:
            bad = propose_doc(
                "first-denied", ids, [add_action("X", 5)],
                [pred("hyp-a", True), pred("hyp-b", False)], side_effect="external",
            )
            return {"content": {"proposals": [bad]}}
        assert context["extra"]["prior_rejection_codes"] == ["HUMAN_APPROVAL_REQUIRED"]
        good = propose_doc(
            "model-corrected", ids,
            [add_action("A", 5), add_action("A", 5)],
            [pred("hyp-a", False, "duplicate_label"), pred("hyp-b", True)],
            side_effect="owned_mutation",
        )
        return {"content": {"proposals": [good]}}

    loop, ledger, budget, _, store = wiring(
        cli_scope, reference, tmp_path, adaptive, max_rounds=1,
    )
    report = loop.run(list(SEED))
    assert stages == ["hypothesize", "propose", "propose"]
    assert report.stop_reason == "stalled"
    assert report.mock_model_calls == 3
    assert budget.attempts == 3
    assert report.rounds[0].proposal_id == "model-corrected"
    assert report.rounds[0].actions_executed == 2
    assert report.resolution_counts["supported"] == 1
    assert report.resolution_counts["contradicted"] == 1
    assert len(list(ledger.root.glob("*.json"))) >= 4


def test_retry_respects_model_budget_and_does_not_execute_denied_proposal(cli_scope, reference, tmp_path):
    from second_source.budgets import RunBudget

    loop, ledger, budget, _, _ = wiring(
        cli_scope, reference, tmp_path,
        responder(actions=[{"command": "unapproved", "params": {}}]),
        budgets=cli_scope.budgets.model_copy(update={"max_model_calls": 2}),
        max_rounds=1,
    )
    report = loop.run(list(SEED))
    assert report.stop_reason == "guard_blocked"
    assert report.mock_model_calls == 2
    assert budget.attempts == 2
    assert len(list(ledger.root.glob("*.json"))) == 2



def test_real_muse_side_effect_phrase_runs_allowed_owned_experiment(cli_scope, reference, tmp_path):
    """Real failure reproduction: verbose 'mutating:' is classified only by trusted manifest."""
    import json
    from pathlib import Path

    manifest = json.loads(
        (Path(__file__).resolve().parents[1] / "fixtures/owned_ledger/public_contract.json").read_text()
    )
    steps = [add_action("A", 5), add_action("A", 5)]
    predictions = [pred("hyp-a", False, "duplicate_label"), pred("hyp-b", True)]
    loop, ledger, budget, _, _ = wiring(
        cli_scope, reference, tmp_path,
        responder(hyp_ids=("hyp-a", "hyp-b"), actions=steps,
                  predictions=predictions,
                  side_effect="mutating: creates two ledger records within isolated session"),
        max_rounds=1,
        public_contract=manifest,
    )
    result = loop.run(list(SEED))
    assert result.stop_reason == "stalled"
    assert result.mock_model_calls == 2
    assert result.rounds[0].actions_executed == 2
    assert result.resolution_counts["supported"] == 1
    assert result.resolution_counts["contradicted"] == 1
    assert len(list(ledger.root.glob("*.json"))) == 4
