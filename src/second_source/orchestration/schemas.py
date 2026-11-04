"""Versioned Gate A orchestration schemas (v1). Any field change bumps .vN."""
from __future__ import annotations
from enum import Enum
from typing import Literal
from pydantic import Field, model_validator
from second_source.contracts import Observation, ScopeContract, StrictModel

SCHEMA_VERSION = Literal["1"]

class ProvenanceLabel(str, Enum):
    NON_AI = "NON_AI"
    REAL_MODEL = "REAL_MODEL"
    GEMMA_TEST = "GEMMA_TEST"

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_RECONCILIATION = "needs_reconciliation"

class JobStage(str, Enum):
    CAPTURE = "capture"
    ORGANIZE = "organize"
    DISTILL = "distill"
    EXECUTE = "execute"

# Scope.v1 is the existing strict ScopeContract (no copy, reuse).
ScopeV1 = ScopeContract

class InvestigationV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    investigation_id: str
    owner_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=4000)
    target_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    scope: ScopeContract
    scope_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["created", "authorized"] = "created"
    revision: int = Field(ge=1)
    created_at: str
    updated_at: str

class CreateInvestigationV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    title: str = Field(min_length=1, max_length=120)
    instruction: str = Field(min_length=1, max_length=4000)
    target_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    scope: ScopeContract

class AuthorizeInvestigationV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    expected_revision: int = Field(ge=1)
    scope_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    mode: Literal["mock"] = "mock"
    maximum_model_spend_usd: Literal[0] = 0

class EvidenceV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    observation: Observation
    provenance: ProvenanceLabel = ProvenanceLabel.NON_AI
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

class CandidateRouteV1(StrictModel):
    method: str = Field(min_length=1, max_length=10)
    path_template: str = Field(min_length=1, max_length=500)
    kind: str = Field(min_length=1, max_length=80)
    provenance_per_field: dict[str, str] = Field(default_factory=dict)

class CandidateV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    ir_version: Literal[2] = 2
    candidate_id: str
    investigation_id: str
    provenance: ProvenanceLabel = ProvenanceLabel.NON_AI
    source_observations_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    routes: tuple[CandidateRouteV1, ...] = ()
    frozen_fields: tuple[str, ...] = ("template", "method", "path")

class VerificationV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    indeterminate: int = Field(ge=0)
    total: int = Field(ge=0)
    origin: Literal["mock"] = "mock"
    real: Literal[False] = False
    claim: Literal["TRUSTED_CONTROL", "NON_AI"] = "NON_AI"

    @model_validator(mode="after")
    def counts_agree(self):
        if self.passed + self.failed + self.indeterminate != self.total:
            raise ValueError("Verification counts must sum to total")
        return self

class ArtifactRefV1(StrictModel):
    artifact_id: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    media_type: str

class ReportV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    report_id: str
    investigation_id: str
    job_id: str
    provenance: ProvenanceLabel = ProvenanceLabel.NON_AI
    evaluation: VerificationV1 | None = None
    report: ArtifactRefV1 | None = None
    stop_reason: str = Field(min_length=1, max_length=80)

class ExportV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    bundle: ArtifactRefV1
    deterministic: Literal[True] = True
    contains_sealed: Literal[False] = False
    contains_raw_model: Literal[False] = False

class JobV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    job_id: str
    investigation_id: str
    kind: Literal["orchestration_mock"] = "orchestration_mock"
    status: JobStatus = JobStatus.QUEUED
    stage: JobStage | None = None
    attempt: int = Field(default=1, ge=1)
    revision: int = Field(ge=1)
    cancel_requested: bool = False
    created_at: str
    updated_at: str
    error_code: str | None = None
    result_report_id: str | None = None

EventStatus = Literal["RUNNING", "FAILED", "CANNOT_VERIFY", "COMPLETED", "CANCELLED"]

class OrchestrationEventV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    event_id: int
    investigation_id: str
    job_id: str | None = None
    event_type: str
    stage: JobStage | None = None
    revision: int
    created_at: str
    status: EventStatus = "COMPLETED"
    provenance: ProvenanceLabel = ProvenanceLabel.NON_AI
    artifact_refs: tuple[str, ...] = ()
    detail: str | None = Field(default=None, max_length=200)

class ArtifactListItemV1(ArtifactRefV1):
    kind: str
    name: str
    created_at: str

class WorkspaceV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    investigation_id: str
    candidate: CandidateV1 | None = None
    verification: VerificationV1 | None = None
    report: ReportV1 | None = None
    artifacts: list[ArtifactListItemV1] = Field(default_factory=list)

class TargetRegistrationV1(StrictModel):
    schema_version: SCHEMA_VERSION = "1"
    target_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    label: str = Field(min_length=1, max_length=120)
    adapter_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    scope: ScopeContract
    scope_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_enabled: bool = False
    provenance: ProvenanceLabel = ProvenanceLabel.NON_AI
