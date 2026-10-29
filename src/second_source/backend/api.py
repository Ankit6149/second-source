"""Typed v1 HTTP adapter for the shared durable service, without inference authority.

No environment or credential access occurs on import or app creation. The caller
injects SHA-256 bearer-token digests; only the service owns business transactions.
"""
from __future__ import annotations

import asyncio
from collections import deque
import hashlib
import logging
import re
import secrets
import threading
import time
from typing import Annotated, Any, Callable, Literal, Mapping, TYPE_CHECKING
import uuid

from fastapi import Depends, FastAPI, Header, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from second_source.contracts import StrictModel
from .contracts import (
    AuthorizeInvestigation, BackendError, CancelRun, CreateInvestigation,
    CreateRun, ErrorBody, Investigation, LifecycleEvent, Principal, Run,
)

if TYPE_CHECKING:
    from .service import BackendService

_LOG = logging.getLogger(__name__)
_TOKEN = re.compile(r"[A-Za-z0-9\-._~+/]{32,256}={0,2}\Z", re.ASCII)
_DIGEST = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_IDENTIFIER = r"^[A-Za-z0-9_-]{1,80}$"
_BEARER = HTTPBearer(auto_error=False, scheme_name="OwnerToken")


class InvestigationPage(StrictModel):
    items: list[Investigation]
    next_after: str | None = None


class RunPage(StrictModel):
    items: list[Run]
    next_after: str | None = None


class EventPage(StrictModel):
    items: list[LifecycleEvent]
    next_after: int = Field(ge=0)


class Health(StrictModel):
    status: Literal["ok", "not_ready"]


class Capabilities(StrictModel):
    api_version: Literal["v1"] = "v1"
    enabled_run_kinds: tuple[Literal["g3_mock"], ...] = ("g3_mock",)
    real: Literal[False] = False
    real_inference_enabled: Literal[False] = False
    paid_authorization_enabled: Literal[False] = False


def _error(code: str, message: str, status: int, correlation: str) -> JSONResponse:
    headers = {"X-Correlation-ID": correlation, "Cache-Control": "no-store"}
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if status == 429:
        headers["Retry-After"] = "60"
    return JSONResponse(
        ErrorBody(code=code, message=message, correlation_id=correlation).model_dump(),
        status_code=status, headers=headers,
    )


class _Boundary:
    """Bounded ASGI ingress; limits also apply to chunked bodies before parsing."""

    def __init__(self, app: ASGIApp, *, token_hashes: Mapping[str, Principal],
                 identity_resolver: Callable[[str], Principal | None] | None = None,
                 max_body_bytes: int, max_concurrent_requests: int,
                 requests_per_minute: int, body_timeout_seconds: float):
        self.app = app
        self.tokens = tuple(token_hashes.items())
        self.identity_resolver = identity_resolver
        self.max_body = max_body_bytes
        self.slots = threading.BoundedSemaphore(max_concurrent_requests)
        self.rate = requests_per_minute
        self.buckets: dict[str, deque[float]] = {}
        self.lock = threading.Lock()
        self.body_timeout = body_timeout_seconds

    def _principal(self, headers: list[tuple[bytes, bytes]]) -> Principal | None:
        values = [value for key, value in headers if key.lower() == b"authorization"]
        if len(values) != 1:
            return None
        try:
            value = values[0].decode("ascii")
        except UnicodeError:
            return None
        if not value.startswith("Bearer "):
            return None
        token = value[7:]
        if self.identity_resolver is not None:
            if len(token) > 8192 or not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2}", token):
                return None
            try:
                return self.identity_resolver(token)
            except Exception:
                # Never log bearer tokens or external provider response bodies.
                return None
        if not _TOKEN.fullmatch(token):
            return None
        supplied = hashlib.sha256(token.encode("ascii")).hexdigest()
        matched = None
        # Compare every configured digest; never use a plaintext token as a key.
        for digest, principal in self.tokens:
            if secrets.compare_digest(supplied, digest):
                matched = principal
        return matched

    def _rate_allowed(self, owner: str) -> bool:
        now = time.monotonic()
        with self.lock:
            bucket = self.buckets.setdefault(owner, deque())
            while bucket and bucket[0] <= now - 60:
                bucket.popleft()
            if len(bucket) >= self.rate:
                return False
            bucket.append(now)
            return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        correlation = uuid.uuid4().hex
        scope.setdefault("state", {})["correlation_id"] = correlation
        headers = scope.get("headers", [])

        async def reject(code: str, message: str, status: int) -> None:
            await _error(code, message, status, correlation)(scope, receive, send)

        protected = scope["path"].startswith("/v1")
        if protected:
            principal = await asyncio.to_thread(self._principal, headers)
            if principal is None:
                await reject("UNAUTHENTICATED", "A valid bearer token is required.", 401)
                return
            scope["state"]["principal"] = principal
            if not self._rate_allowed(principal.owner_id):
                await reject("RATE_LIMITED", "Request rate limit exceeded.", 429)
                return
        if not self.slots.acquire(blocking=False):
            await reject("BUSY", "Request concurrency limit exceeded.", 503)
            return
        try:
            # Reject ambiguous framing and repeated idempotency keys.
            for name in (b"content-length", b"content-type", b"idempotency-key"):
                if sum(key.lower() == name for key, _ in headers) > 1:
                    await reject("INVALID_REQUEST", "Repeated request headers are not supported.", 400)
                    return
            values = {key.lower(): value for key, value in headers}
            if b"content-length" in values:
                raw_length = values[b"content-length"]
                if not re.fullmatch(rb"[0-9]{1,10}", raw_length):
                    await reject("INVALID_REQUEST", "Invalid request framing.", 400)
                    return
                if int(raw_length) > self.max_body:
                    await reject("BODY_TOO_LARGE", "Request body limit exceeded.", 413)
                    return
                if b"transfer-encoding" in values:
                    await reject("INVALID_REQUEST", "Ambiguous request framing.", 400)
                    return
            if protected and scope["method"] in {"POST", "PUT", "PATCH"}:
                media = values.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
                if media != b"application/json" or values.get(b"content-encoding", b"identity") != b"identity":
                    await reject("UNSUPPORTED_MEDIA_TYPE", "An uncompressed JSON body is required.", 415)
                    return
            body = bytearray()
            deadline = time.monotonic() + self.body_timeout
            while True:
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    await reject("REQUEST_TIMEOUT", "Request body deadline exceeded.", 408)
                    return
                try:
                    message = await asyncio.wait_for(receive(), remaining_seconds)
                except TimeoutError:
                    await reject("REQUEST_TIMEOUT", "Request body deadline exceeded.", 408)
                    return
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.max_body:
                    await reject("BODY_TOO_LARGE", "Request body limit exceeded.", 413)
                    return
                if not message.get("more_body", False):
                    break
            consumed = False

            async def replay() -> Message:
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            async def response_send(message: Message) -> None:
                if message["type"] == "http.response.start":
                    outgoing = [(key, value) for key, value in message.get("headers", [])
                                if key.lower() not in {b"x-correlation-id", b"cache-control"}]
                    outgoing.extend([(b"x-correlation-id", correlation.encode("ascii")),
                                     (b"cache-control", b"no-store"),
                                     (b"x-content-type-options", b"nosniff")])
                    message = {**message, "headers": outgoing}
                await send(message)

            await self.app(scope, replay, response_send)
        finally:
            self.slots.release()


def create_app(service: BackendService, token_hashes: Mapping[str, str] | None = None,
               artifact_store: Any | None = None, *, max_body_bytes: int = 65_536,
               max_concurrent_requests: int = 16, requests_per_minute: int = 120,
               body_timeout_seconds: float = 30,
               identity_resolver: Callable[[str], Principal | None] | None = None) -> FastAPI:
    """Construct a local HTTP adapter using injected service and hashed tokens.

    An optional shared artifact store enables verified report and bundle reads.
    No arbitrary filesystem paths or private evaluator files are exposed.
    """
    if identity_resolver is None:
        if not isinstance(token_hashes, Mapping) or not 1 <= len(token_hashes) <= 256:
            raise ValueError("Configure between one and 256 token hashes.")
    else:
        if token_hashes is not None or not callable(identity_resolver):
            raise ValueError("Configure exactly one authentication authority.")
    principals = {}
    for digest, owner in (token_hashes or {}).items():
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise ValueError("Token configuration requires lowercase SHA-256 digests.")
        principals[digest] = Principal(owner_id=owner)
    if not (1024 <= max_body_bytes <= 1_048_576 and 1 <= max_concurrent_requests <= 128
            and 1 <= requests_per_minute <= 100_000 and 0 < body_timeout_seconds <= 120):
        raise ValueError("API boundary limits are outside supported bounds.")
    errors = {status: {"model": ErrorBody} for status in (400, 401, 404, 405, 408, 409, 413, 415, 422, 429, 500, 503)}
    app = FastAPI(title="Second Source backend", version="1.0.0", docs_url=None,
                  redoc_url=None, responses=errors)
    app.add_middleware(_Boundary, token_hashes=principals, identity_resolver=identity_resolver,
                       max_body_bytes=max_body_bytes,
                       max_concurrent_requests=max_concurrent_requests,
                       requests_per_minute=requests_per_minute,
                       body_timeout_seconds=body_timeout_seconds)

    def owner(request: Request, supplied: HTTPAuthorizationCredentials | None = Depends(_BEARER)) -> Principal:
        return request.state.principal

    def key(value: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=80,
                                       pattern=r"^[A-Za-z0-9_-]+$")]) -> str:
        return value

    @app.exception_handler(BackendError)
    async def backend_error(request: Request, error: BackendError) -> JSONResponse:
        return _error(error.code, error.message, error.status_code, request.state.correlation_id)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        # Pydantic errors can include raw bodies, secrets and exception contexts.
        return _error("VALIDATION_ERROR", "Request validation failed.", 422, request.state.correlation_id)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        code = "NOT_FOUND" if error.status_code == 404 else "HTTP_ERROR"
        return _error(code, "The requested operation is unavailable.", error.status_code,
                      request.state.correlation_id)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        _LOG.error("backend_request_failed correlation_id=%s code=INTERNAL_ERROR", request.state.correlation_id)
        return _error("INTERNAL_ERROR", "The operation could not be completed.", 500, request.state.correlation_id)

    @app.get("/health/live", response_model=Health, tags=["health"])
    def live() -> Health:
        return Health(status="ok")

    @app.get("/health/ready", response_model=Health, responses={503: {"model": Health}}, tags=["health"])
    def ready() -> Health | JSONResponse:
        try:
            healthy = service.readiness()
        except Exception:
            healthy = False
        if not healthy:
            return JSONResponse(Health(status="not_ready").model_dump(), status_code=503)
        return Health(status="ok")

    @app.get("/v1/capabilities", response_model=Capabilities, tags=["capabilities"])
    def capabilities(principal: Principal = Depends(owner)) -> Capabilities:
        return Capabilities()

    @app.post("/v1/investigations", response_model=Investigation, status_code=201, tags=["investigations"])
    def create_investigation(body: CreateInvestigation, principal: Principal = Depends(owner),
                             idempotency_key: str = Depends(key)) -> Investigation:
        return service.create_investigation(principal, body, idempotency_key)

    @app.get("/v1/investigations", response_model=InvestigationPage, tags=["investigations"])
    def list_investigations(principal: Principal = Depends(owner),
                            after: Annotated[str | None, Query(pattern=_IDENTIFIER)] = None,
                            limit: Annotated[int, Query(ge=1, le=100)] = 50) -> InvestigationPage:
        items = service.list_investigations(principal, after=after, limit=limit)
        return InvestigationPage(items=items, next_after=items[-1].investigation_id if len(items) == limit else None)

    @app.get("/v1/investigations/{investigation_id}", response_model=Investigation, tags=["investigations"])
    def get_investigation(investigation_id: Annotated[str, Path(pattern=_IDENTIFIER)],
                          principal: Principal = Depends(owner)) -> Investigation:
        return service.get_investigation(principal, investigation_id)

    @app.post("/v1/investigations/{investigation_id}/authorize", response_model=Investigation, tags=["approvals"])
    def authorize_investigation(investigation_id: Annotated[str, Path(pattern=_IDENTIFIER)],
                                body: AuthorizeInvestigation, principal: Principal = Depends(owner)) -> Investigation:
        return service.authorize_investigation(principal, investigation_id, body)

    @app.post("/v1/investigations/{investigation_id}/runs", response_model=Run, status_code=201, tags=["runs"])
    def create_run(investigation_id: Annotated[str, Path(pattern=_IDENTIFIER)], body: CreateRun,
                   principal: Principal = Depends(owner), idempotency_key: str = Depends(key)) -> Run:
        return service.create_run(principal, investigation_id, body, idempotency_key)

    @app.get("/v1/investigations/{investigation_id}/runs", response_model=RunPage, tags=["runs"])
    def list_runs(investigation_id: Annotated[str, Path(pattern=_IDENTIFIER)],
                  principal: Principal = Depends(owner),
                  after: Annotated[str | None, Query(pattern=_IDENTIFIER)] = None,
                  limit: Annotated[int, Query(ge=1, le=100)] = 50) -> RunPage:
        items = service.list_runs(principal, investigation_id, after=after, limit=limit)
        return RunPage(items=items, next_after=items[-1].run_id if len(items) == limit else None)

    @app.get("/v1/runs/{run_id}", response_model=Run, tags=["runs"])
    def get_run(run_id: Annotated[str, Path(pattern=_IDENTIFIER)],
                 principal: Principal = Depends(owner)) -> Run:
        return service.get_run(principal, run_id)

    @app.post("/v1/runs/{run_id}/cancel", response_model=Run, tags=["runs"])
    def cancel_run(run_id: Annotated[str, Path(pattern=_IDENTIFIER)], body: CancelRun,
                    principal: Principal = Depends(owner)) -> Run:
        return service.cancel_run(principal, run_id, body.expected_revision)

    @app.get("/v1/investigations/{investigation_id}/events", response_model=EventPage, tags=["progress"])
    def events(investigation_id: Annotated[str, Path(pattern=_IDENTIFIER)],
               principal: Principal = Depends(owner), after: Annotated[int, Query(ge=0)] = 0,
               limit: Annotated[int, Query(ge=1, le=500)] = 100) -> EventPage:
        items = service.events(principal, investigation_id, after=after, limit=limit)
        return EventPage(items=items, next_after=items[-1].event_id if items else after)

    @app.get("/v1/runs/{run_id}/report", response_class=Response,
             responses={200: {"content": {"application/json": {"schema": {"type": "object"}}}}}, tags=["artifacts"])
    def report(run_id: Annotated[str, Path(pattern=_IDENTIFIER)],
               principal: Principal = Depends(owner)) -> Response:
        run = service.get_run(principal, run_id)
        if artifact_store is None or run.result is None or run.result.report is None:
            raise BackendError("NOT_FOUND", "Report is not available.", 404)
        raw = artifact_store.read(run.run_id, run.result.report)
        return Response(raw, media_type="application/json")

    @app.get("/v1/runs/{run_id}/export.zip", response_class=Response,
             responses={200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}}},
             tags=["artifacts"])
    def export(run_id: Annotated[str, Path(pattern=_IDENTIFIER)],
               principal: Principal = Depends(owner)) -> Response:
        run = service.get_run(principal, run_id)
        if artifact_store is None or run.result is None or run.result.report is None:
            raise BackendError("NOT_FOUND", "Export is not available.", 404)
        investigation = service.get_investigation(principal, run.investigation_id)
        all_events: list[LifecycleEvent] = []
        cursor = 0
        while True:
            page = service.events(principal, run.investigation_id, after=cursor, limit=500)
            if not page:
                break
            all_events.extend(page)
            if len(all_events) > 1000:
                raise BackendError("EXPORT_LIMIT", "Investigation exceeds the bounded HTTP export limit.", 409)
            cursor = page[-1].event_id
        raw = artifact_store.export_bundle(investigation, run, all_events)
        return Response(raw, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="{run.run_id}.zip"',
        })

    return app
