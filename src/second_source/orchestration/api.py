"""HTTP adapter for orchestration. NL instruction enters here, reaches service."""
from __future__ import annotations
from typing import Annotated, Callable
from fastapi import APIRouter, Depends, Header, Path, Response
from pydantic import Field
from second_source.contracts import StrictModel
from second_source.backend.contracts import Principal
from .schemas import (
    ArtifactListItemV1, AuthorizeInvestigationV1, CandidateV1, CreateInvestigationV1,
    ExportV1, InvestigationV1, JobV1, OrchestrationEventV1, TargetRegistrationV1,
    VerificationV1, WorkspaceV1,
)
from .service import OrchestrationService

_ID = r"^[A-Za-z0-9_-]{1,80}$"

class EnqueueJobV1(StrictModel):
    schema_version: str = "1"

class CancelJobV1(StrictModel):
    expected_revision: int = Field(ge=1)

class RetryJobV1(StrictModel):
    expected_revision: int = Field(ge=1)

class EventPageV1(StrictModel):
    items: list[OrchestrationEventV1]
    next_after: int = Field(ge=0)

def create_orchestration_router(service: OrchestrationService,
                                get_principal: Callable) -> APIRouter:
    router = APIRouter(prefix="/v1/orchestration", tags=["orchestration"])

    def key(value: Annotated[str, Header(alias="Idempotency-Key", min_length=1,
                                          max_length=80, pattern=r"^[A-Za-z0-9_-]+$")]) -> str:
        return value

    @router.get("/targets", response_model=list[TargetRegistrationV1])
    def targets(principal: Principal = Depends(get_principal)):
        return service.registry.list()

    @router.post("/investigations", response_model=InvestigationV1, status_code=201)
    def create(body: CreateInvestigationV1, principal: Principal = Depends(get_principal),
               idempotency_key: str = Depends(key)):
        # body.instruction (natural language) is forwarded verbatim to the service
        # and persisted; tests assert it round-trips via GET.
        return service.create_investigation(principal, body, idempotency_key)

    @router.get("/investigations/{investigation_id}", response_model=InvestigationV1)
    def get_inv(investigation_id: Annotated[str, Path(pattern=_ID)],
                principal: Principal = Depends(get_principal)):
        return service.get_investigation(principal, investigation_id)

    @router.post("/investigations/{investigation_id}/authorize", response_model=InvestigationV1)
    def authorize(investigation_id: Annotated[str, Path(pattern=_ID)],
                  body: AuthorizeInvestigationV1, principal: Principal = Depends(get_principal)):
        return service.authorize(principal, investigation_id, body)

    @router.post("/investigations/{investigation_id}/jobs", response_model=JobV1, status_code=201)
    def enqueue(investigation_id: Annotated[str, Path(pattern=_ID)], body: EnqueueJobV1,
                principal: Principal = Depends(get_principal), idempotency_key: str = Depends(key)):
        return service.enqueue(principal, investigation_id, idempotency_key)

    @router.get("/jobs/{job_id}", response_model=JobV1)
    def get_job(job_id: Annotated[str, Path(pattern=_ID)], principal: Principal = Depends(get_principal)):
        return service.get_job(principal, job_id)

    @router.post("/jobs/{job_id}/cancel", response_model=JobV1)
    def cancel(job_id: Annotated[str, Path(pattern=_ID)], body: CancelJobV1,
               principal: Principal = Depends(get_principal)):
        return service.cancel(principal, job_id, body.expected_revision)

    @router.post("/jobs/{job_id}/retry", response_model=JobV1)
    def retry(job_id: Annotated[str, Path(pattern=_ID)], body: RetryJobV1,
              principal: Principal = Depends(get_principal)):
        return service.retry(principal, job_id, body.expected_revision)

    @router.post("/jobs/{job_id}/execute", response_model=JobV1)
    def execute(job_id: Annotated[str, Path(pattern=_ID)],
                principal: Principal = Depends(get_principal)):
        return service.execute_job(principal, job_id)

    @router.get("/investigations/{investigation_id}/events", response_model=EventPageV1)
    def events(investigation_id: Annotated[str, Path(pattern=_ID)],
               principal: Principal = Depends(get_principal), after: int = 0, limit: int = 100):
        items = service.list_events(principal, investigation_id, after=after, limit=limit)
        return EventPageV1(items=items, next_after=items[-1].event_id if items else after)

    @router.get("/investigations/{investigation_id}/workspace", response_model=WorkspaceV1)
    def workspace(investigation_id: Annotated[str, Path(pattern=_ID)],
                  principal: Principal = Depends(get_principal)):
        return service.get_workspace(principal, investigation_id)

    @router.get("/investigations/{investigation_id}/candidate", response_model=CandidateV1)
    def candidate(investigation_id: Annotated[str, Path(pattern=_ID)],
                  principal: Principal = Depends(get_principal)):
        return service.get_workspace(principal, investigation_id).candidate

    @router.get("/investigations/{investigation_id}/verification", response_model=VerificationV1)
    def verification(investigation_id: Annotated[str, Path(pattern=_ID)],
                     principal: Principal = Depends(get_principal)):
        return service.get_verification(principal, investigation_id)

    @router.get("/investigations/{investigation_id}/export", response_model=ExportV1)
    def export(investigation_id: Annotated[str, Path(pattern=_ID)],
               principal: Principal = Depends(get_principal)):
        return service.get_export(principal, investigation_id)

    @router.get("/investigations/{investigation_id}/artifacts", response_model=list[ArtifactListItemV1])
    def artifacts(investigation_id: Annotated[str, Path(pattern=_ID)],
                  principal: Principal = Depends(get_principal)):
        return service.list_artifacts(principal, investigation_id)

    @router.get("/investigations/{investigation_id}/artifacts/{artifact_id}/content")
    def artifact_content(investigation_id: Annotated[str, Path(pattern=_ID)],
                         artifact_id: Annotated[str, Path(pattern=r"^art-[a-f0-9]{16}$")],
                         principal: Principal = Depends(get_principal)):
        content, media_type, name = service.artifact_content(principal, investigation_id, artifact_id)
        return Response(content=content, media_type=media_type,
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return router
