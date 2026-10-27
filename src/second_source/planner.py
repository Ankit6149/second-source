"""Experiment planner: model-typed generation + deterministic ranking (G2).

The planner asks the model (through `ModelGateway`) for hypothesis batches and
discriminating experiments, validates every output against closed schemas,
scores candidates with the documented heuristic, and routes each proposal
through `ScopeGuard.validate_action` BEFORE anything executes. Rejected
proposals return with machine-readable codes so the loop can revise or stop
honestly. Planner output is always `ProposedAction`: the runner's only input.
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
                "required": ["id", "statement", "evidence_ids"],
                "properties": {
                    "id": {"type": "string", "minLength": 1, "maxLength": 64},
                    "statement": {"type": "string", "minLength": 1, "maxLength": 500},
                    "evidence_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "status": {"type": "string", "default": "hypothesized"},
                    "alternatives": {"type": "array", "items": {"type": "string"}, "default": []},
                    "unresolved_questions": {"type": "array", "items": {"type": "string"}, "default": []},
                },
            },
        },
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
                "required": ["proposal_id", "requirement_id", "hypothesis_ids", "command", "predictions", "side_effect"],
                "properties": {
                    "proposal_id": {"type": "string", "minLength": 1, "maxLength": 64},
                    "requirement_id": {"type": "string", "minLength": 1},
                    "hypothesis_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "question": {"type": "string", "default": ""},
                    "command": {"type": "string", "minLength": 1},
                    "kind": {"type": "string", "default": "cli"},
                    "params": {"type": "object", "default": {}},
                    "role": {"type": "string", "default": "guest"},
                    "requires_auth": {"type": "boolean", "default": False},
                    "predictions": {"type": "object", "minProperties": 1},
                    "expected_information_gain": {"type": "string", "default": ""},
                    "estimated_reference_calls": {"type": "integer", "minimum": 1, "default": 1},
                    "side_effect": {"type": "string", "default": "read_only"},
                    "approval_granted": {"type": "boolean", "default": False},
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
class RankedProposal:
    action: ProposedAction
    proposal_id: str
    utility: float
    decision_code: str
    predictions: tuple[tuple[str, str], ...]


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


class ExperimentPlanner:
    def __init__(
        self,
        gateway: ModelGateway,
        guard: ScopeGuard,
        hypotheses: HypothesisStore,
        budget: RunBudget,
        contract: ScopeContract,
    ) -> None:
        self._gateway = gateway
        self._guard = guard
        self._hypotheses = hypotheses
        self._budget = budget
        self._contract = contract
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
                max_output_tokens=1200,
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
    ) -> PlanResult:
        if not hypotheses:
            raise GatewayError("propose requires at least one hypothesis")
        competing = {
            "hypotheses": [
                {"id": h.id, "statement": h.statement, "alternatives": list(h.alternatives)}
                for h in hypotheses
            ],
            "requirement_id": requirement_id,
        }
        response = self._gateway.generate(
            ModelRequest(
                stage="propose",
                messages=(
                    {"role": "system", "content": PROPOSE_SYSTEM},
                    {"role": "user", "content": self._model_context(evidence, competing)},
                ),
                json_schema=PROPOSE_JSON_SCHEMA,
                max_output_tokens=1200,
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
                action, proposal_id, predictions = self._to_action(raw, requirement_id)
            except (ValueError, TypeError, AttributeError) as exc:
                rejected.append((str(label), f"schema: {exc}"))
                continue
            decision = self._guard.validate_action(action)
            if not decision.allowed:
                rejected.append((proposal_id, f"{decision.code}: {decision.reason}"))
                continue
            if reference_remaining < 1 or model_remaining < 1:
                rejected.append((proposal_id, "OVER_BUDGET: no reference/model budget remains"))
                continue
            utility = self._score(action, predictions, hypotheses)
            ranked.append(RankedProposal(action, proposal_id, utility, decision.code, predictions))
        ranked.sort(key=lambda r: r.utility, reverse=True)
        return PlanResult(ranked=tuple(ranked), rejected=tuple(rejected))

    def _to_action(
        self, raw: Any, requirement_id: str
    ) -> tuple[ProposedAction, str, tuple[tuple[str, str], ...]]:
        if not isinstance(raw, dict):
            raise ValueError("proposal must be an object")
        try:
            proposal_id = str(raw["proposal_id"])
            command = str(raw["command"])
            hyp_ids = raw["hypothesis_ids"]
            predictions = raw["predictions"]
            params = raw.get("params", {})
        except KeyError as exc:
            raise ValueError(f"missing field {exc}") from exc
        if not isinstance(hyp_ids, list) or not hyp_ids or not all(isinstance(h, str) for h in hyp_ids):
            raise ValueError("hypothesis_ids must be a non-empty string list")
        if not isinstance(predictions, dict) or not predictions:
            raise ValueError("predictions must be a non-empty object")
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        if "command" in params:
            raise ValueError("params cannot override the approved command label")
        side_effect = MODEL_SIDE_EFFECTS.get(str(raw.get("side_effect", "read_only")))
        if side_effect is None:
            raise ValueError(f"unknown side_effect {raw.get('side_effect')!r}")
        kind = str(raw.get("kind", "cli"))
        action = ProposedAction(
            kind=kind,
            target=command,
            requirement_id=str(raw.get("requirement_id", requirement_id)),
            role=str(raw.get("role", "guest")),
            requires_auth=bool(raw.get("requires_auth", False)),
            side_effect=side_effect,
            approval_granted=bool(raw.get("approval_granted", False)),
            payload=dict(params),
        )
        return action, proposal_id, tuple((str(k), str(v)) for k, v in predictions.items())

    def _score(
        self,
        action: ProposedAction,
        predictions: Sequence[tuple[str, str]],
        hypotheses: Sequence[Hypothesis],
    ) -> float:
        predicted = {k for k, _ in predictions}
        discrimination = len([h for h in hypotheses if h.id in predicted]) / max(
            1, len(hypotheses)
        )
        scope_relevance = (
            1.0 if action.requirement_id in self._contract.implementation.requirements else 0.0
        )
        signature = action.target + ":" + json.dumps(action.payload, sort_keys=True)
        novelty = 0.0 if signature in self._executed_signatures else 1.0
        coverage_gain = min(1.0, (1 + len(action.payload)) / 4.0)
        normalized_cost = min(
            1.0, 1 / max(1, self._contract.budgets.max_reference_experiments)
        )
        risk_penalty = 0.0 if action.side_effect == SideEffect.READ_ONLY else 0.5
        return score_utility(
            discrimination=discrimination,
            scope_relevance=scope_relevance,
            novelty=novelty,
            coverage_gain=coverage_gain,
            normalized_cost=normalized_cost,
            risk_penalty=risk_penalty,
        )

    def mark_executed(self, action: ProposedAction) -> None:
        self._executed_signatures.add(
            action.target + ":" + json.dumps(action.payload, sort_keys=True)
        )
