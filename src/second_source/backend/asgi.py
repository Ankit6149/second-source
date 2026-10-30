"""Cloud-only ASGI factory. No deployment, migrations or secret reads on import."""
from __future__ import annotations

import os
import json
import logging
import uuid
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from .api import create_app
from .auth import SupabaseIdentity
from .cloud_artifacts import SupabaseArtifactStore, SupabaseHTTPTransport
from .on_demand import OnDemandMockExecutor
from .postgres import PostgresStore
from .service import BackendService
from .settings import CloudSettings


class _SanitizedCloudErrors:
    """Prevent the server from logging raw unexpected request exceptions."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def guarded_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, guarded_send)
        except Exception:
            correlation = scope.get("state", {}).get("correlation_id") or uuid.uuid4().hex
            logging.getLogger("second_source.backend.cloud").error(json.dumps({
                "event": "REQUEST_FAILED", "correlation_id": correlation}))
            if not started:
                response = JSONResponse({"code": "INTERNAL_ERROR", "message": "The operation could not be completed.",
                    "correlation_id": correlation}, status_code=500,
                    headers={"X-Correlation-ID": correlation, "Cache-Control": "no-store"})
                await response(scope, receive, send)


def build_cloud_app(settings: CloudSettings, *, store=None, transport=None, identity=None,
                    executor=None):
    """Inject fakes in tests; configured deployment uses durable PG+private Storage."""
    store = store if store is not None else PostgresStore(
        settings.database_url.get_secret_value(), project_ref=settings.project_ref)
    service = BackendService(store=store)
    transport = transport if transport is not None else SupabaseHTTPTransport(
        access_token=settings.storage_key.get_secret_value(), api_key=settings.storage_key.get_secret_value())
    artifacts = SupabaseArtifactStore(transport, authorize_run=service.get_run, timeout_seconds=3)
    identity = identity if identity is not None else SupabaseIdentity(
        settings.project_ref, settings.publishable_key.get_secret_value())
    if settings.enable_mock_execution and executor is None:
        record = getattr(store, "record_artifact_ref", None)
        if not callable(record):
            raise ValueError("Durable artifact indexing is required before worker activation")
        executor = OnDemandMockExecutor(service, artifacts, record_artifact=record)
    if not settings.enable_mock_execution:
        executor = None
    app = create_app(service, artifact_store=artifacts, identity_resolver=identity,
        max_concurrent_requests=settings.max_concurrent_requests,
        requests_per_minute=settings.requests_per_minute, body_timeout_seconds=15,
        run_executor=executor)
    app.add_middleware(_SanitizedCloudErrors)
    # Outer middleware handles exact-origin preflight without authentication.
    # API mutations still require a bearer identity; credentials/cookies disabled.
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
            allow_credentials=False, allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
            expose_headers=["X-Correlation-ID", "Content-Disposition"], max_age=300)
    return app


def create_application():
    try:
        return build_cloud_app(CloudSettings.from_environment(os.environ))
    except Exception:
        raise RuntimeError("Cloud startup configuration is invalid or unavailable") from None
