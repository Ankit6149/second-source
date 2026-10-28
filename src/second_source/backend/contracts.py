"""Versioned control-plane contracts; engine evidence/scopes are reused, not copied."""
from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import Field, model_validator

from second_source.contracts import ScopeContract, StrictModel


class InvestigationStatus(str, Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_RECONCILIATION = "needs_reconciliation"


class CodeStage(str, Enum):
    CAPTURE = "capture"
    ORGANIZE = "organize"
    DISTILL = "distill"
    EXECUTE = "execute"


class Principal(StrictModel):
    owner_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class CreateInvestigation(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    scope: ScopeContract


class AuthorizeInvestigation(StrictModel):
    expected_revision: int = Field(ge=1)
    scope_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    # This initial slice authorizes only the existing zero-cost mock engine.
    mode: Literal["mock"] = "mock"
    maximum_model_spend_usd: Literal[0] = 0


class CreateRun(StrictModel):
    kind: Literal["g3_mock"] = "g3_mock"


class CancelRun(StrictModel):
    expected_revision: int = Field(ge=1)


class UsageSummary(StrictModel):
    attempts: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    uncertain_cost_usd: float = Field(default=0, ge=0, allow_inf_nan=False)


class EvaluationSummary(StrictModel):
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    indeterminate: int = Field(ge=0)
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_agree(self):
        if self.passed + self.failed + self.indeterminate != self.total:
            raise ValueError("Evaluation counts must sum to total")
        return self


class ArtifactReference(StrictModel):
    artifact_id: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    media_type: str


class EngineResult(StrictModel):
    origin: Literal["mock"] = "mock"
    real: Literal[False] = False
    stop_reason: str = Field(min_length=1, max_length=80)
    usage: UsageSummary = Field(default_factory=UsageSummary)
    evaluation: EvaluationSummary | None = None
    report: ArtifactReference | None = None


class Investigation(StrictModel):
    investigation_id: str
    owner_id: str
    title: str
    scope: ScopeContract
    scope_digest: str
    status: InvestigationStatus
    revision: int
    created_at: str
    updated_at: str


class Run(StrictModel):
    run_id: str
    investigation_id: str
    kind: Literal["g3_mock"]
    status: RunStatus
    stage: CodeStage | None = None
    revision: int
    cancel_requested: bool
    created_at: str
    updated_at: str
    result: EngineResult | None = None
    error_code: str | None = None


class LifecycleEvent(StrictModel):
    event_id: int
    investigation_id: str
    run_id: str | None
    event_type: str
    stage: CodeStage | None = None
    created_at: str
    revision: int


class Lease(StrictModel):
    run: Run
    scope: ScopeContract
    token: str
    worker_id: str
    expires_at: float


class ErrorBody(StrictModel):
    code: str
    message: str
    correlation_id: str


class BackendError(RuntimeError):
    """Safe fixed messages only; never pass model/SQLite/OS exception text here."""
    def __init__(self, code: str, message: str, status_code: int = 409):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)
