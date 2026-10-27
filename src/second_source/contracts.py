"""Strict v1 scope and experimental evidence contracts.

No permissive fallback: input outside the declared scope is not silently widened.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TargetKind(str, Enum):
    CLI = "cli"
    HTTP = "http"
    BROWSER = "browser"


class ScopeMode(str, Enum):
    PUBLIC_ONLY = "public_only"
    SELECTED_SURFACES = "selected_surfaces"
    SELECTED_FLOWS = "selected_flows"
    FULL_AUTHORIZED = "full_authorized_surface"
    ANALYSIS_ONLY = "analysis_only"


class SideEffect(str, Enum):
    READ_ONLY = "read_only"
    LOCAL_MUTATION = "local_mutation"
    EXTERNAL_MUTATION = "external_mutation"
    SENSITIVE = "sensitive"


class TargetSpec(StrictModel):
    kind: TargetKind
    permission_ref: str = Field(min_length=3)
    reference_url: HttpUrl | None = None
    reference_command_id: str | None = None

    @model_validator(mode="after")
    def require_locator(self) -> "TargetSpec":
        if self.kind == TargetKind.CLI:
            if not self.reference_command_id or self.reference_url:
                raise ValueError("CLI requires a trusted reference_command_id only")
        elif not self.reference_url or self.reference_command_id:
            raise ValueError("Browser/HTTP target requires a reference_url only")
        return self


class ObservationScope(StrictModel):
    allowed_url_patterns: tuple[str, ...] = ()
    allowed_roles: frozenset[str] = Field(default_factory=lambda: frozenset({"guest"}))
    permitted_actions: frozenset[str] = Field(default_factory=frozenset)
    allowed_commands: frozenset[str] = Field(default_factory=frozenset)
    authenticated_access: Literal["not_required", "authorized_test_account", "human_required"] = "not_required"


class ImplementationScope(StrictModel):
    route_patterns: tuple[str, ...] = ()
    required_flows: tuple[str, ...] = ()
    requirements: frozenset[str] = Field(min_length=1)
    allowed_subsystems: frozenset[str] = Field(min_length=1)
    fidelity: frozenset[Literal["visual", "interaction", "behavioral", "full_stack"]] = Field(default_factory=lambda: frozenset({"behavioral"}))


class ExclusionScope(StrictModel):
    url_patterns: tuple[str, ...] = ()
    subsystems: frozenset[str] = Field(default_factory=frozenset)
    external_side_effects: frozenset[str] = Field(default_factory=frozenset)


class Budgets(StrictModel):
    max_reference_experiments: int = Field(default=30, ge=1, le=1000)
    max_model_calls: int = Field(default=40, ge=0, le=10000)
    max_repair_rounds: int = Field(default=3, ge=0, le=50)
    max_wall_seconds: int = Field(default=1800, ge=1, le=86400)
    max_estimated_model_spend_usd: float = Field(default=2.0, ge=0, le=1000)


class ScopeContract(StrictModel):
    scope_version: Literal["1"] = "1"
    target: TargetSpec
    goal: str = Field(min_length=8, max_length=1000)
    mode: ScopeMode
    observation: ObservationScope
    implementation: ImplementationScope
    exclusions: ExclusionScope = Field(default_factory=ExclusionScope)
    budgets: Budgets = Field(default_factory=Budgets)

    @model_validator(mode="after")
    def check_boundaries(self) -> "ScopeContract":
        if not self.observation.permitted_actions:
            raise ValueError("Must explicitly allow at least one observation action")
        if self.mode == ScopeMode.PUBLIC_ONLY and (self.observation.authenticated_access != "not_required" or self.observation.allowed_roles != frozenset({"guest"})):
            raise ValueError("public_only cannot request authenticated actors")
        if self.implementation.allowed_subsystems & self.exclusions.subsystems:
            raise ValueError("Implementation and exclusions overlap")
        if self.target.kind != TargetKind.CLI and not self.observation.allowed_url_patterns:
            raise ValueError("Network targets require explicit allowed URL paths")
        if self.target.kind == TargetKind.CLI and not self.observation.allowed_commands:
            raise ValueError("CLI target requires explicit trusted command labels")
        for group in (self.observation.allowed_url_patterns, self.implementation.route_patterns, self.exclusions.url_patterns):
            for pattern in group:
                if not pattern.startswith("/") or ".." in pattern or "?" in pattern or "#" in pattern:
                    raise ValueError("URL scope patterns must be absolute paths without traversal, query or fragment")
        return self


class ProposedAction(StrictModel):
    kind: str = Field(min_length=1)
    target: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    role: str = "guest"
    requires_auth: bool = False
    side_effect: SideEffect = SideEffect.READ_ONLY
    external_effect_name: str | None = None
    approval_granted: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class ProposedFile(StrictModel):
    path: str = Field(min_length=1)
    subsystem: str = Field(min_length=1)
    requirement_ids: frozenset[str] = Field(min_length=1)


class PolicyDecision(StrictModel):
    allowed: bool
    code: str
    reason: str


class Observation(StrictModel):
    observation_id: str = Field(min_length=1)
    sequence_id: str = Field(min_length=1)
    action_index: int = Field(ge=0)
    input_action: dict[str, Any]
    output: Any
    exit_code: int
    duration_ms: int = Field(ge=0)
    status: Literal["ok", "target_error", "timeout", "protocol_error"]


class SequenceResult(StrictModel):
    sequence_id: str
    observations: tuple[Observation, ...]
    status: Literal["ok", "timeout", "protocol_error"]
    stderr: str = ""
