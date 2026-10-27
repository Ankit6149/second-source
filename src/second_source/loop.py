"""Bounded observe -> hypothesize -> experiment -> update loop (G2).

Separation, enforced in code:
- `model zone`: redacted ledger views (`EvidenceLedger.model_view`) plus the
  public scope summary. This is ALL the model gateway ever receives.
- `restricted zone`: raw observation artifacts, the reference process, and
  sealed evaluation cases. Only the adapter, ledger, runner, and verifier
  touch these; they are never serialized into a `ModelRequest`.

One proposal = one ordered action list executed as ONE fresh-process adapter
sequence: state accumulates WITHIN the sequence and resets BETWEEN sequences
(the fixture starts empty on each process launch). The loop records this
boundary on every round; cross-sequence persistence claims are never made.

Reference and wall-clock budgets stay enforced by `SafeCLIExperimentRunner`;
model budgets by `RunBudget`. Exhaustion stops the run with an explicit
`budget` reason, never false success. Stop reasons: `stalled` (rounds
exhausted with hypotheses still open), `budget`, `guard_blocked` (no allowed
proposal).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .budgets import RunBudget
from .contracts import ProposedAction, ScopeContract
from .evidence import EvidenceLedger
from .hypotheses import HypothesisStore
from .model_gateway import GatewayError
from .planner import ExperimentPlanner, reconcile_predictions
from .runner import BudgetExhausted, PolicyViolation, SafeCLIExperimentRunner

STOP_REASONS = ("stalled", "budget", "guard_blocked", "model_error")


def _trusted_rejection_codes(rejected: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    """Return only scope/shape codes, not untrusted model text."""
    known = {
        "COMMAND_NOT_ALLOWED", "ACTION_NOT_ALLOWED", "ROLE_NOT_ALLOWED",
        "HUMAN_APPROVAL_REQUIRED", "SENSITIVE_ACTION_BLOCKED",
        "AUTH_OUT_OF_SCOPE", "REQUIREMENT_NOT_IN_SCOPE", "OVER_BUDGET",
    }
    codes: set[str] = set()
    if not rejected:
        return ("NO_PROPOSALS",)
    for _label, reason in rejected:
        prefix = reason.split(":", 1)[0]
        if prefix in known:
            codes.add(prefix)
        elif "reset_boundary" in reason:
            codes.add("RESET_BOUNDARY")
        elif "side_effect" in reason:
            codes.add("SIDE_EFFECT")
        elif "prediction" in reason:
            codes.add("PREDICTION_INVALID")
        else:
            codes.add("SCHEMA_ERROR")
    return tuple(sorted(codes))



@dataclass(frozen=True)
class LoopRound:
    round_no: int
    hypothesis_ids: tuple[str, ...]
    proposal_id: str | None
    actions_executed: int
    observation_ids: tuple[str, ...]
    reset_boundary: str
    resolution: dict[str, int]
    note: str


@dataclass(frozen=True)
class LoopReport:
    run_id: str
    rounds: tuple[LoopRound, ...]
    stop_reason: str
    real_model_calls: int
    mock_model_calls: int
    budget_summary: dict[str, Any]
    resolution_counts: dict[str, int]


class DiscoveryLoop:
    """One bounded discovery run over a single requirement id."""

    def __init__(
        self,
        *,
        run_id: str,
        requirement_id: str,
        contract: ScopeContract,
        runner: SafeCLIExperimentRunner,
        ledger: EvidenceLedger,
        hypotheses: HypothesisStore,
        planner: ExperimentPlanner,
        budget: RunBudget,
        max_rounds: int = 6,
    ) -> None:
        self._run_id = run_id
        self._requirement_id = requirement_id
        self._contract = contract
        self._runner = runner
        self._ledger = ledger
        self._hypotheses = hypotheses
        self._planner = planner
        self._budget = budget
        self._max_rounds = max_rounds
        self._digests: list[str] = []

    def _views(self) -> list[dict[str, Any]]:
        # Digest-keyed redacted views: the mock/real model cites digests, and
        # the planner resolves them against exactly this known set.
        return [
            {"digest": digest, "observation": self._ledger.model_view(digest)}
            for digest in self._digests
        ]

    def _known_ids(self) -> frozenset[str]:
        return frozenset(self._digests)

    def _execute(
        self, actions: Sequence[ProposedAction]
    ) -> tuple[list[str], Any | None]:
        """Run ONE guard-validated sequence.

        Returns (observation ids, final observation or None). A sequence with
        zero observations (timeout/protocol) yields None so reconciliation
        marks hypotheses unresolved instead of reusing stale evidence.
        """
        result = self._runner.run(list(actions))
        obs_ids: list[str] = []
        for observation in result.observations:
            receipt = self._ledger.store(observation)
            self._digests.append(receipt["sha256"])
            obs_ids.append(observation.observation_id)
        final = result.observations[-1] if result.observations else None
        return obs_ids, final

    def _seed(self, seed_actions: Sequence[dict[str, Any]]) -> None:
        """Baseline observations through the guarded runner (budget-counted)."""
        if not seed_actions:
            raise GatewayError("loop requires at least one seed action")
        self._execute([
            ProposedAction(
                kind="cli",
                target=str(item["command"]),
                requirement_id=self._requirement_id,
                payload={k: v for k, v in item.items() if k != "command"},
            )
            for item in seed_actions
        ])

    def _reference_remaining(self) -> int:
        return max(
            0,
            self._contract.budgets.max_reference_experiments - self._runner.count,
        )

    def run(self, seed_actions: Sequence[dict[str, Any]]) -> LoopReport:
        rounds: list[LoopRound] = []
        stop_reason = "stalled"
        try:
            self._seed(seed_actions)
            for round_no in range(1, self._max_rounds + 1):
                batch = self._planner.hypothesize(self._views(), self._known_ids())
                for hyp in batch.hypotheses:
                    if hyp.id not in self._hypotheses.ids():
                        self._hypotheses.add_batch(
                            batch.model_copy(update={"hypotheses": (hyp,)})
                        )
                plan = self._planner.propose(
                    self._views(),
                    self._hypotheses.competing(),
                    self._requirement_id,
                    reference_remaining=self._reference_remaining(),
                    model_remaining=self._budget.model_calls_remaining,
                )
                first_denials = _trusted_rejection_codes(plan.rejected) if not plan.ranked else ()
                # One corrective MODEL-chosen proposal, not a deterministic
                # fallback. No extra call for API/schema failures; only after a
                # successful but guard-rejected model proposal.
                if not plan.ranked and self._budget.model_calls_remaining > 0 and self._reference_remaining() > 0:
                    plan = self._planner.propose(
                        self._views(),
                        self._hypotheses.competing(),
                        self._requirement_id,
                        reference_remaining=self._reference_remaining(),
                        model_remaining=self._budget.model_calls_remaining,
                        rejection_codes=first_denials,
                    )
                if not plan.ranked:
                    reasons = "; ".join(r for _, r in plan.rejected[:3])
                    reasons = (
                        f"first_denials={','.join(first_denials)}; "
                        f"correction_denials={','.join(_trusted_rejection_codes(plan.rejected))}; "
                        + (reasons or 'empty proposal list')
                    )
                    rounds.append(
                        LoopRound(
                            round_no,
                            tuple(h.id for h in batch.hypotheses),
                            None,
                            0,
                            (),
                            "fresh_process_per_sequence",
                            self._hypotheses.resolution_counts(),
                            f"no allowed experiment: {reasons}",
                        )
                    )
                    stop_reason = "guard_blocked"
                    break
                top = plan.ranked[0]
                try:
                    obs_ids, final = self._execute(top.actions)
                except PolicyViolation as exc:
                    rounds.append(
                        LoopRound(
                            round_no,
                            tuple(h.id for h in batch.hypotheses),
                            top.proposal_id,
                            0,
                            (),
                            "fresh_process_per_sequence",
                            self._hypotheses.resolution_counts(),
                            f"runner refused: {exc}",
                        )
                    )
                    stop_reason = "guard_blocked"
                    break
                self._planner.mark_executed(top.actions)
                # UPDATE: reconcile checkable predictions against the observed
                # FINAL step output; harness failures leave hypotheses open.
                if final is None:
                    verdicts = {p.hypothesis_id: "unresolved" for p in top.predictions}
                else:
                    last_view = self._ledger.model_view(self._digests[-1])
                    verdicts = reconcile_predictions(
                        top.predictions,
                        last_view.get("output"),
                        str(last_view.get("status", "")),
                    )
                for hyp_id, verdict in verdicts.items():
                    if verdict in ("supported", "contradicted"):
                        try:
                            self._hypotheses.update_status(hyp_id, verdict)
                        except KeyError:
                            pass
                rounds.append(
                    LoopRound(
                        round_no,
                        tuple(h.id for h in batch.hypotheses),
                        top.proposal_id,
                        len(top.actions),
                        tuple(obs_ids),
                        "fresh_process_per_sequence",
                        self._hypotheses.resolution_counts(),
                        f"executed {top.proposal_id} utility={top.utility:.3f} "
                        f"steps={len(top.actions)} verdicts={verdicts}",
                    )
                )
        except BudgetExhausted as exc:
            rounds.append(
                LoopRound(
                    0, (), None, 0, (), "fresh_process_per_sequence",
                    self._hypotheses.resolution_counts(), f"budget stop: {exc}",
                )
            )
            stop_reason = "budget"
        except GatewayError as exc:
            rounds.append(
                LoopRound(
                    0, (), None, 0, (), "fresh_process_per_sequence",
                    self._hypotheses.resolution_counts(), f"model stop: {exc}",
                )
            )
            stop_reason = "model_error"

        receipts = self._planner.receipts
        return LoopReport(
            run_id=self._run_id,
            rounds=tuple(rounds),
            stop_reason=stop_reason,
            real_model_calls=sum(1 for r in receipts if r.real),
            mock_model_calls=sum(1 for r in receipts if not r.real),
            budget_summary=self._budget.summary(),
            resolution_counts=self._hypotheses.resolution_counts(),
        )
