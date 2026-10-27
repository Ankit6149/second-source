"""Experiment planner: model-typed generation + deterministic ranking (G2).

The planner asks the model (through `ModelGateway`) for hypothesis batches and
discriminating experiments, validates every output against closed schemas,
scores candidates with the documented heuristic, and routes EACH proposed
action through `ScopeGuard.validate_action` BEFORE anything executes. Rejected
proposals return with machine-readable codes so the loop can revise or stop
honestly. Planner output is a list of `ProposedAction`: the runner's only input.

Security: the model schema contains NO approval field. Any `approval_granted`
smuggled into raw output is stripped and ignored — approvals must come from a
trusted operator-controlled grant path that does not exist in G2, so external
mutations are always denied here.

Semantics: one proposal = one ordered action list (at most 8 steps) executed
as ONE fresh-process adapter sequence with NO persisted state between
sequences. The proposal must declare this reset boundary explicitly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from .budgets import RunBudget
from .contracts import ProposedAction, ScopeContract, SideEffect
from .evidence import redact
from .hypotheses import Hypothesis, HypothesisBatch, HypothesisStore, validate_batch
from .model_gateway import (
    HYPOTHESIZE_SYSTEM,
    PROMPT_VERSION_HYPOTHESIZE,
    PROMPT_VERSION_PROPOSE,
    PROPOSE_SYSTEM,
    GatewayError,
    ModelGateway,
    ModelRequest,
)
from .scope_guard import ScopeGuard

MAX_SEQUENCE_ACTIONS = 8
RESET_BOUNDARY = "fresh_process_per_sequence"

HYPOTHESIZE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "hypotheses"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "hypotheses": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "statement", "evidence_ids", "status", "alternatives", "unresolved_questions"],
                "properties": {
                    "id": {"type": "string", "minLength": 1, "maxLength": 64},
                    "statement": {"type": "string", "minLength": 1, "maxLength": 500},
                    "evidence_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "status": {"type": "string", "enum": ["hypothesized"]},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                    "unresolved_questions": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

PREDICTION_SCHEMA: dict[str, Any] = {
    # Wire shape only: required keys present, no extras. Semantic strictness
    # (boolean expects_ok, reset_boundary const, known side_effect) is enforced
    # per proposal in _to_actions so one bad item rejects instead of killing
    # the whole batch.
    "type": "object",
    "additionalProperties": False,
    "required": ["hypothesis_id", "expects_ok"],
    "properties": {
        "hypothesis_id": {"type": "string", "minLength": 1},
        "expects_ok": {},
        "expects_contains": {"type": "string"},
    },
}

ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["command"],
    "properties": {
        "command": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "minLength": 1},
        "params": {"type": "object"},
    },
}

PROPOSE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "proposal_id", "requirement_id", "hypothesis_ids", "question",
                    "reset_boundary", "actions", "predictions",
                    "expected_information_gain", "side_effect", "role", "requires_auth",
                ],
                "properties": {
                    "proposal_id": {"type": "string", "minLength": 1, "maxLength": 64},
                    "requirement_id": {"type": "string", "minLength": 1},
                    "hypothesis_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "question": {"type": "string"},
                    "reset_boundary": {"type": "string", "minLength": 1},
                    "actions": {"type": "array", "minItems": 1, "maxItems": MAX_SEQUENCE_ACTIONS, "items": ACTION_SCHEMA},
                    "predictions": {"type": "array", "minItems": 1, "items": PREDICTION_SCHEMA},
                    "expected_information_gain": {"type": "string"},
                    "side_effect": {"type": "string", "minLength": 1},
                    "role": {"type": "string", "minLength": 1},
                    "requires_auth": {"type": "boolean"},
                    # Structurally tolerated so one smuggled field cannot kill
                    # the batch; _to_actions strips it and the guard denies.
                    "approval_granted": {},
                },
            },
        }
    },
}

MODEL_SIDE_EFFECTS = {
    "read_only": SideEffect.READ_ONLY,
    "owned_mutation": SideEffect.LOCAL_MUTATION,
    "external": SideEffect.EXTERNAL_MUTATION,
    "prohibited": SideEffect.SENSITIVE,
}


@dataclass(frozen=True)
class Prediction:
    hypothesis_id: str
    expects_ok: bool
    expects_contains: str | None


@dataclass(frozen=True)
class RankedProposal:
    actions: tuple[ProposedAction, ...]
    proposal_id: str
    utility: float
    decision_codes: tuple[str, ...]
    predictions: tuple[Prediction, ...]


@dataclass(frozen=True)
class PlanResult:
    ranked: tuple[RankedProposal, ...]
    rejected: tuple[tuple[str, str], ...]  # (proposal_id_or_raw, reason)


def score_utility(
    *,
    discrimination: float,
    scope_relevance: float,
    novelty: float,
    coverage_gain: float,
    normalized_cost: float,
    risk_penalty: float,
) -> float:
    """Playbook heuristic: 0.35*disc + 0.25*scope + 0.20*nov + 0.20*cov - cost - risk."""
    for name, value in (
        ("discrimination", discrimination),
        ("scope_relevance", scope_relevance),
        ("novelty", novelty),
        ("coverage_gain", coverage_gain),
        ("normalized_cost", normalized_cost),
        ("risk_penalty", risk_penalty),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"utility feature {name}={value} outside 0..1")
    return (
        0.35 * discrimination
        + 0.25 * scope_relevance
        + 0.20 * novelty
        + 0.20 * coverage_gain
        - normalized_cost
        - risk_penalty
    )


def reconcile_predictions(
    predictions: Sequence[Prediction],
    final_output: Any,
    final_status: str,
) -> dict[str, str]:
    """Compare checkable predictions against the observed final-step output.

    Returns {hypothesis_id: supported|contradicted|unresolved}. Harness-level
    failures (timeout/protocol) leave hypotheses unresolved rather than
    punishing them for inconclusive evidence.
    """
    if final_status not in ("ok", "target_error"):
        return {p.hypothesis_id: "unresolved" for p in predictions}
    actual_ok = final_status == "ok"
    try:
        canonical = json.dumps(final_output, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = str(final_output)
    verdicts: dict[str, str] = {}
    for pred in predictions:
        if pred.expects_ok != actual_ok:
            verdicts[pred.hypothesis_id] = "contradicted"
        elif pred.expects_contains is not None and pred.expects_contains not in canonical:
            verdicts[pred.hypothesis_id] = "contradicted"
        else:
            verdicts[pred.hypothesis_id] = "supported"
    return verdicts


class ExperimentPlanner:
    def __init__(
        self,
        gateway: ModelGateway,
        guard: ScopeGuard,
        hypotheses: HypothesisStore,
        budget: RunBudget,
        contract: ScopeContract,
        public_contract: dict[str, Any] | None = None,
    ) -> None:
        self._gateway = gateway
        self._guard = guard
        self._hypotheses = hypotheses
        self._budget = budget
        self._contract = contract
        # Operator-authored public action signatures, NEVER reference source.
        self._public_contract = public_contract or {}
        self._executed_signatures: set[str] = set()

    @property
    def receipts(self):  # type: ignore[no-untyped-def]
        return self._gateway.receipts

    def _model_context(self, evidence: Sequence[dict[str, Any]], extra: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "scope_goal": self._contract.goal,
            "mode": self._contract.mode.value,
            "requirement_ids": sorted(self._contract.implementation.requirements),
            "allowed_commands": sorted(self._contract.observation.allowed_commands),
            "excluded_subsystems": sorted(self._contract.exclusions.subsystems),
            "reset_boundary": RESET_BOUNDARY,
            "public_command_contract": redact(self._public_contract),
            "evidence": [redact(dict(item)) for item in evidence],
            "budget_remaining": {
                "model_calls": self._budget.model_calls_remaining,
            },
        }
        if extra:
            payload["extra"] = redact(extra)
        return json.dumps(payload, sort_keys=True, default=str)

    def hypothesize(
        self, evidence: Sequence[dict[str, Any]], known_ids: frozenset[str]
    ) -> HypothesisBatch:
        if not evidence:
            raise GatewayError("hypothesize requires at least one evidence item")
        response = self._gateway.generate(
            ModelRequest(
                stage="hypothesize",
                messages=(
                    {"role": "system", "content": HYPOTHESIZE_SYSTEM},
                    {"role": "user", "content": self._model_context(evidence)},
                ),
                json_schema=HYPOTHESIZE_JSON_SCHEMA,
                max_output_tokens=2400,
                prompt_version=PROMPT_VERSION_HYPOTHESIZE,
            )
        )
        if response.parsed is None:
            raise GatewayError("hypothesize: model returned no parsed object")
        return validate_batch(response.parsed, known_ids)

    def propose(
        self,
        evidence: Sequence[dict[str, Any]],
        hypotheses: Sequence[Hypothesis],
        requirement_id: str,
        *,
        reference_remaining: int,
        model_remaining: int,
        rejection_codes: Sequence[str] = (),
    ) -> PlanResult:
        if not hypotheses:
            raise GatewayError("propose requires at least one hypothesis")
        competing = {
            "hypotheses": [
                {"id": h.id, "statement": h.statement, "alternatives": list(h.alternatives)}
                for h in hypotheses
            ],
            "requirement_id": requirement_id,
            "operator_guidance": (
                "This is an owned, synthetic CLI, not a production account. "
                "Commands add/remove mutate only local in-process fixture state; "
                "total/list read local state. Use exactly requirement_id as given, "
                "role guest, requires_auth false, reset_boundary fresh_process_per_sequence, "
                "side_effect owned_mutation when proposing add/remove or read_only "
                "for total/list. Actions must contain CLI command labels, not shell commands. "
                "Propose a test that gives distinguishable predicted outcomes, "
                "and fill all required JSON schema properties."
            ),
        }
        if rejection_codes:
            # Feedback is from *trusted deterministic validation*, never raw
            # target text or model-provided prose. It cannot authorize actions.
            safe_codes = sorted({code for code in rejection_codes if code in {
                "COMMAND_NOT_ALLOWED", "ACTION_NOT_ALLOWED", "ROLE_NOT_ALLOWED",
                "HUMAN_APPROVAL_REQUIRED", "SENSITIVE_ACTION_BLOCKED",
                "AUTH_OUT_OF_SCOPE", "SCHEMA_ERROR", "RESET_BOUNDARY",
                "OVER_BUDGET", "REQUIREMENT_NOT_IN_SCOPE", "SIDE_EFFECT",
                "NO_PROPOSALS", "PREDICTION_INVALID",
            }})
            competing["prior_rejection_codes"] = safe_codes
            competing["correction_instruction"] = (
                "The previous proposal did not pass deterministic validation. "
                "Choose a NEW permitted CLI action sequence, do not reuse blocked "
                "commands or claim human approval. The scope guard remains authoritative."
            )
        response = self._gateway.generate(
            ModelRequest(
                stage="propose",
                messages=(
                    {"role": "system", "content": PROPOSE_SYSTEM},
                    {"role": "user", "content": self._model_context(evidence, competing)},
                ),
                json_schema=PROPOSE_JSON_SCHEMA,
                max_output_tokens=2800,
                prompt_version=PROMPT_VERSION_PROPOSE,
            )
        )
        if response.parsed is None:
            raise GatewayError("propose: model returned no parsed object")
        raw_list = response.parsed.get("proposals", [])
        if not isinstance(raw_list, list):
            raise GatewayError("propose: 'proposals' is not a list")

        ranked: list[RankedProposal] = []
        rejected: list[tuple[str, str]] = []
        for raw in raw_list:
            label = raw.get("proposal_id", "?") if isinstance(raw, dict) else "?"
            try:
                actions, proposal_id, predictions = self._to_actions(raw, requirement_id)
            except (ValueError, TypeError, AttributeError) as exc:
                rejected.append((str(label), f"schema: {exc}"))
                continue
            decisions: list[str] = []
            denied: str | None = None
            for action in actions:
                decision = self._guard.validate_action(action)
                decisions.append(decision.code)
                if not decision.allowed:
                    denied = f"{decision.code}: {decision.reason}"
                    break
            if denied is not None:
                rejected.append((proposal_id, denied))
                continue
            if reference_remaining < 1 or model_remaining < 1:
                rejected.append((proposal_id, "OVER_BUDGET: no reference/model budget remains"))
                continue
            utility = self._score(actions, predictions, hypotheses)
            ranked.append(RankedProposal(tuple(actions), proposal_id, utility, tuple(decisions), tuple(predictions)))
        ranked.sort(key=lambda r: r.utility, reverse=True)
        return PlanResult(ranked=tuple(ranked), rejected=tuple(rejected))

    def _to_actions(
        self, raw: Any, requirement_id: str
    ) -> tuple[list[ProposedAction], str, list[Prediction]]:
        if not isinstance(raw, dict):
            raise ValueError("proposal must be an object")
        # Defense in depth: approvals are NEVER model-supplied. Strip silently;
        # the guard denies anything needing approval without a trusted grant.
        raw = {k: v for k, v in raw.items() if k != "approval_granted"}
        try:
            proposal_id = str(raw["proposal_id"])
            hyp_ids = raw["hypothesis_ids"]
            raw_actions = raw["actions"]
            raw_predictions = raw["predictions"]
        except KeyError as exc:
            raise ValueError(f"missing field {exc}") from exc
        if raw.get("reset_boundary", RESET_BOUNDARY) != RESET_BOUNDARY:
            raise ValueError(f"reset_boundary must be {RESET_BOUNDARY!r}")
        if not isinstance(hyp_ids, list) or not hyp_ids or not all(isinstance(h, str) for h in hyp_ids):
            raise ValueError("hypothesis_ids must be a non-empty string list")
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ValueError("actions must be a non-empty list")
        if len(raw_actions) > MAX_SEQUENCE_ACTIONS:
            raise ValueError(f"actions exceed bound of {MAX_SEQUENCE_ACTIONS}")
        if not isinstance(raw_predictions, list) or not raw_predictions:
            raise ValueError("predictions must be a non-empty list")
        side_effect = MODEL_SIDE_EFFECTS.get(str(raw.get("side_effect", "read_only")))
        if side_effect is None:
            raise ValueError(f"unknown side_effect {raw.get('side_effect')!r}")
        requirement = str(raw.get("requirement_id", requirement_id))
        role = str(raw.get("role", "guest"))
        requires_auth = bool(raw.get("requires_auth", False))
        actions: list[ProposedAction] = []
        for step in raw_actions:
            if not isinstance(step, dict):
                raise ValueError("each action must be an object")
            command = step.get("command")
            if not isinstance(command, str) or not command:
                raise ValueError("each action needs a non-empty command")
            params = step.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("action params must be an object")
            if "command" in params:
                raise ValueError("params cannot override the approved command label")
            actions.append(
                ProposedAction(
                    kind=str(step.get("kind", "cli")),
                    target=command,
                    requirement_id=requirement,
                    role=role,
                    requires_auth=requires_auth,
                    side_effect=side_effect,
                    approval_granted=False,
                    payload=dict(params),
                )
            )
        predictions: list[Prediction] = []
        for item in raw_predictions:
            if not isinstance(item, dict):
                raise ValueError("each prediction must be an object")
            hid = item.get("hypothesis_id")
            ok = item.get("expects_ok")
            contains = item.get("expects_contains")
            if not isinstance(hid, str) or not hid:
                raise ValueError("prediction needs a hypothesis_id")
            if not isinstance(ok, bool):
                raise ValueError("prediction expects_ok must be boolean")
            if contains is not None and (not isinstance(contains, str) or not contains):
                raise ValueError("prediction expects_contains must be a non-empty string")
            predictions.append(Prediction(hid, ok, contains))
        return actions, proposal_id, predictions

    def _score(
        self,
        actions: Sequence[ProposedAction],
        predictions: Sequence[Prediction],
        hypotheses: Sequence[Hypothesis],
    ) -> float:
        predicted = {p.hypothesis_id for p in predictions}
        discrimination = len([h for h in hypotheses if h.id in predicted]) / max(
            1, len(hypotheses)
        )
        scope_relevance = (
            1.0
            if all(a.requirement_id in self._contract.implementation.requirements for a in actions)
            else 0.0
        )
        signature = "|".join(
            a.target + ":" + json.dumps(a.payload, sort_keys=True) for a in actions
        )
        novelty = 0.0 if signature in self._executed_signatures else 1.0
        coverage_gain = min(1.0, len(actions) / 4.0)
        normalized_cost = min(
            1.0, len(actions) / max(1, self._contract.budgets.max_reference_experiments)
        )
        risk_penalty = (
            0.0
            if all(a.side_effect == SideEffect.READ_ONLY for a in actions)
            else 0.5
        )
        return score_utility(
            discrimination=discrimination,
            scope_relevance=scope_relevance,
            novelty=novelty,
            coverage_gain=coverage_gain,
            normalized_cost=normalized_cost,
            risk_penalty=risk_penalty,
        )

    def mark_executed(self, actions: Sequence[ProposedAction]) -> None:
        self._executed_signatures.add(
            "|".join(a.target + ":" + json.dumps(a.payload, sort_keys=True) for a in actions)
        )
