# Backend API v1

**Backend integration branch, 30 October:** existing routes remain compatible.
The cloud factory is `second_source.backend.asgi:create_application`; it requires
explicit private PostgreSQL/Auth/Storage configuration and never falls back to
ephemeral SQLite. New typed session, exact-run execute, reconciliation, run-event
and verification routes are described in [the frontend contract](FRONTEND_BACKEND_CONTRACT.md).
On-demand mock execution is disabled by default. Its existence is not deployment
or genuine engine acceptance. See [cloud operations](CLOUD_BACKEND_OPERATIONS.md).

This is a local, durable control-plane slice around the existing G3 mock engine.
It does not enable paid inference, authorize Meta spending, or demonstrate real
model reconstruction. The authentic G2 archive and two consumed real G3 attempts
remain separate historical evidence; this service does not replace them.

## Construction and authority

Install the project with `python -m pip install -e ".[dev]"`. Runtime additions
are FastAPI 0.162.0, Starlette 1.10.0 and Uvicorn 0.54.0;
HTTPX 0.28.1 is a test dependency.
The existing Pydantic and pytest ranges are retained. SQLite migrations are
included in the installed package.

The shared service has no HTTP dependency. CLI/worker clients and the HTTP
adapter use the same transactions and typed contracts:

```python
from second_source.backend.api import create_app
from second_source.backend.artifacts import ArtifactStore
from second_source.backend.service import BackendService

service = BackendService("/private/operator/state.sqlite")
artifacts = ArtifactStore("/private/operator/artifacts")
app = create_app(service, token_hashes={
    # Inject an actual lowercase SHA-256 token digest and its assigned owner ID.
    # Plaintext bearer tokens are not configuration keys.
    "<64 lowercase hexadecimal characters>": "owner",
}, artifact_store=artifacts)
```

The example digest is a placeholder and intentionally fails validation. Configure
an unguessable bearer token of at least 32 ASCII token characters through the
operator's secure local setup. Keep its plaintext outside source control,
logs, command history, reports and generated evidence packages. The app factory
never reads environment variables or provider credentials. It accepts 1–256
digest-to-owner mappings and validates owner identifiers. Only the token mapping
assigns authority; request bodies cannot assign an owner. Tokens cannot be issued
or escalated through this API. TLS, secure token provisioning, rotation, external
network exposure and deployment authorization remain operator responsibilities.

Every `/v1` request requires exactly one `Authorization: Bearer <token>` header.
Authentication compares SHA-256 digests using constant-time comparisons across
all configured digests. Missing, malformed and unknown tokens return 401. Resource
reads and mutations return the same 404 for absent and other-owner resources.
No permissive CORS policy or browser cookie authentication is installed.

## One continuous zero-cost workflow

1. `POST /v1/investigations` creates durable scope and lifecycle state. Send
   `Idempotency-Key` and a `CreateInvestigation` JSON body: `title` and the existing
   `ScopeContract`. A replay with the same owner/key/body returns the same object;
   a changed body conflicts.
2. Inspect the returned `scope_digest` and `revision`. Submit
   `POST /v1/investigations/{id}/authorize` with `expected_revision`,
   `scope_digest`, `mode: "mock"` and `maximum_model_spend_usd: 0`. This records
   approval for this nonbillable slice only. Real mode/nonzero spend is rejected.
3. `POST /v1/investigations/{id}/runs` with `Idempotency-Key` and
   `{"kind":"g3_mock"}` queues a bounded durable run. The HTTP handler does not
   launch a worker, run a provider, or bypass scope validation.
4. A separately configured local worker claims durable work and invokes the
   existing zero-cost engine. Poll the run and lifecycle events to follow actual
   committed progress. A queued response is not completion or quality evidence.
5. Inspect completed results, or explicit failed/cancelled/reconciliation state.
   Retrieve the sanitized report and checksum-verifiable proof bundle when an
   immutable report reference is available. Mock results remain `real: false`.

No arbitrary commands, code, private suite paths, model credentials or paid mode
can be submitted through these routes. A stale revision produces 409 instead of
overwriting concurrent state. Cancellation is durable; a running worker must
observe the request and stop. Expired execution leases are reconciled rather
than silently replaying possibly consumed operations.

## HTTP contracts

`GET /openapi.json` publishes generated typed request/response contracts and
bearer security requirements. Interactive documentation is disabled. Health and
the schema are anonymous; investigation state is authenticated.

| Method and path | Result |
| --- | --- |
| `GET /health/live` | Process is accepting application requests; no provider call |
| `GET /health/ready` | SQLite connectivity, schema version and quick integrity check; 503 when unavailable |
| `GET /v1/capabilities` | Explicitly `real: false`, paid authorization disabled, `g3_mock` only |
| `POST /v1/investigations` | 201 typed investigation; idempotent creation |
| `GET /v1/investigations` | Owner-filtered investigation page |
| `GET /v1/investigations/{id}` | Owner-authorized investigation |
| `POST /v1/investigations/{id}/authorize` | Revision/scope-pinned mock-only approval |
| `POST /v1/investigations/{id}/runs` | 201 typed queued run; idempotent creation |
| `GET /v1/investigations/{id}/runs` | Owner-authorized run page |
| `GET /v1/investigations/{id}/events` | Committed lifecycle event page |
| `GET /v1/runs/{id}` | Current durable run, result and error code |
| `POST /v1/runs/{id}/cancel` | Revision-checked cancellation request |
| `GET /v1/runs/{id}/report` | Checksum-verified sanitized JSON report |
| `GET /v1/runs/{id}/export.zip` | Sanitized proof bundle; no raw model content or private suite |

Investigation/run pages accept `limit=1..100` (default 50) and optional `after`
resource ID, returning `items` and `next_after`. IDs sort lexically, not by
creation time. A full page may advertise a cursor whose next page is empty.
Events accept `limit=1..500` (default 100) and integer `after>=0`, returning
the last included event ID or the supplied cursor when empty. Treat cursors
as opaque per collection. HTTP exports include a complete bounded event snapshot:
more than 1000 investigation events returns `EXPORT_LIMIT` rather than silently
truncating evidence. Exports provide checksum integrity, not provider signatures.

IDs/cursors use at most 80 ASCII letters, digits, underscores and hyphens.
Idempotency keys are required for both creation endpoints, with the same
character set and 1–80 characters. JSON models forbid unknown fields. Authorizing
a scope never authorizes arbitrary inputs, model spending or retry allowances.

## Bounded ingress and safe errors

Defaults are 64 KiB per body, a 30-second total receive deadline, 16 concurrent
requests and 120 authenticated requests per owner per rolling minute. Bounds are
configurable through the app factory. Both declared and streamed request bodies
are limited before JSON parsing. Mutations require uncompressed
`application/json`; ambiguous framing and repeated critical headers are rejected.
Rate limits are process-local and owner-based. Concurrency is also process-local;
neither replaces a reverse proxy, deployment-wide limits or worker bounds.

Each response carries a server-generated `X-Correlation-ID` and `Cache-Control:
no-store`. Incoming correlation IDs are not trusted. Errors use a stable shape:

```json
{"code":"VALIDATION_ERROR","message":"Request validation failed.","correlation_id":"<server-generated ID>"}
```

Common statuses are 401 authentication, 404 absent/inaccessible resource,
409 conflict, 413 body limit, 415 unsupported content, 422 validation, 429 rate
limit, and 503 storage/concurrency unavailability. Raw Pydantic errors, request
inputs, SQLite/OS exceptions and private paths are not returned. Unexpected-error
logs contain only the fixed error code and generated correlation ID.
Readiness failure is the intentionally small `{"status":"not_ready"}` health
contract, not a detailed storage diagnostic. Readiness does not assert provider
availability or that a worker is running.

## Acceptance and remaining limits

`python -m pytest tests/test_backend_api.py` exercises actual SQLite-backed HTTP
state, scope approval, restart reads, idempotency, owner isolation, revisions,
cancellation, progress cursors, typed OpenAPI, body/rate/concurrency bounds,
receive timeout, redaction, artifact tampering and checksum export verification.
Tests use synthetic tokens and NON_AI fixtures, with no provider transport.
Current Starlette TestClient emits an HTTPX deprecation warning; it is visible
and does not alter assertions.

This slice is not production certification. It does not expose paid real runs,
live credential management, distributed queues/rate limits, account provisioning,
or arbitrary artifact access. Authentic reconstruction and real-run authorization
still require the existing independent G2/G3 process. Further API resources must
reuse that evidence and engine instead of creating a second receipt/scoring
system. Clean-install and Linux/Windows results must be cited at the final
combined commit, not inferred from these local tests.
