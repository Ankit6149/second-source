# Cloud backend operation — prepared, not deployed

The reviewed target is one Render Free API with Supabase private PostgreSQL,
Auth and Storage. Railway is an alternative, never a concurrent authoritative
worker. No account, resource, key, migration or deployed URL was created here.
Applying the configuration and live migrations requires explicit owner approval.

## Reproducible startup

Use Python 3.12 and the exact approved commit:

```sh
python -m venv .venv
python -m pip install -r requirements-deploy.txt
python -m second_source.backend.serve_cloud
```

Activate the venv first (PowerShell: `.\.venv\Scripts\Activate.ps1`). Runtime
constraints are pinned; build-tool/wheel binary reproducibility is not claimed.
The install is editable intentionally: the existing owned-fixture engine resolves
trusted assets relative to the checked-out repository. Retain the checkout in the
runtime image; a wheel-only deployment without fixtures is unsupported.
The Render proposal pins Python3.12.16, the current security patch listed by
[Python.org](https://www.python.org/downloads/), rather than the authoring host's
older3.12.4 interpreter. Host availability/build and actual TLS acceptance still
must be verified before activation; local unit results do not establish those.
`PORT` defaults to 8000 and accepts 1024..65535. Uvicorn uses one process, bounded
concurrency, no access-token request logs and a 110-second shutdown grace period.
The factory reads server configuration only when explicitly started. It performs
no migration, worker provisioning, sandbox creation, inference or .env discovery.

Required private server settings:

| Variable | Meaning |
|---|---|
| `SECOND_SOURCE_DATABASE_URL` | Dedicated `second_source_backend` direct/pooler login, explicit password, TLS verify-full; never postgres/service-role login |
| `SECOND_SOURCE_SUPABASE_PROJECT_REF` | Exactly `jpqcqqbzriizxhigvjki` |
| `SECOND_SOURCE_SUPABASE_PUBLISHABLE_KEY` | Public Auth project key, server configured |
| `SECOND_SOURCE_STORAGE_SERVER_KEY` | Trusted private Storage credential; never browser configuration |
| `SECOND_SOURCE_CORS_ORIGINS` | JSON array of at most eight exact HTTPS origins; default [] denies browser cross-origin use |
| `SECOND_SOURCE_ENABLE_MOCK_EXECUTION` | Exact `true`/`false`; defaults false and must remain false until worker acceptance |

Never paste secrets into chat, commits, URLs, CLI arguments or public build
variables. Do not inherit libpq PG* configuration. See [PostgreSQL role/migration
operations](POSTGRES_BACKEND.md), [Auth limits](SUPABASE_AUTH.md) and [Storage](CLOUD_ARTIFACTS.md).

`/health/live` is process liveness. `/health/ready` checks durable schema/role
readiness and returns503 safely when unavailable; it is not proof of Auth/Storage
availability. `/v1/capabilities` requires an authenticated user and truthfully
advertises only mock runs. `/v1/session` returns the immutable verified owner ID.
Local token/SQLite construction remains available through the existing CLI/API;
the cloud factory never substitutes ephemeral SQLite for unavailable PostgreSQL.

## Worker lifecycle without a free permanent worker

An authorized user queues a run, then explicitly requests
`POST /v1/runs/{id}/execute` with `{"expected_revision":1}` (use the actual
revision). Execution is synchronous, process-concurrency1, exactly that owned
run, existing zero-cost engine, 90-second engine bound and100-second publication
deadline. No arbitrary command, model key, repair, source or suite path is
accepted. Temporary processing is outside the checkout and is not durable state.

The worker renews/checks its fenced lease and cancellation before report/private
publication; metadata writes require the same active lease token. All retained
private objects use the strict existing-engine JSON allowlist, never sealed
suite files or logs. Uploads/readbacks are bounded to3seconds per request in the
cloud factory. Successful private bytes/hash metadata and the sanitized report
are remote before completion. A failed/ambiguous publication becomes
`needs_reconciliation`; no upload/regeneration/paid operation retries are hidden.
Completed mock runs require all five mandatory original JSON artifacts; only
G3_input_provenance is optional. The immutable runtime_artifact_refs rows are
the authoritative private hash manifest, rather than a second mutable file.

Repeated execute requests for active or terminal runs return their durable
state. Queued is never completed. After an interrupted process, an owner can
request `POST /v1/runs/{id}/reconcile` with its actual revision: an expired lease
is quarantined, never requeued. This endpoint does not claim that an uncertain
external effect did not happen. Private partial uploads may require manual
reconciliation; failed publication is not a successful evidence archive.

Reports and exports enforce service ownership and bind Storage access per
principal. Public ZIPs contain only the existing sanitized integrity package;
original responses/candidates remain private and sealed material never uploads.
See `/openapi.json` for authoritative typed request/response/error contracts.
Candidate/repair-history acceptance remains Muse's PR #18; no new real-engine
or repair claim is introduced by this infrastructure.

## Free-tier limits and deployment

[Render Free](https://render.com/docs/free) currently sleeps after15 idle minutes,
may take about one minute to cold-start, loses local files on restart and grants
750 workspace instance-hours/month. No free permanent/background worker or
persistent disk is assumed. Quota exhaustion can suspend services/builds; do not
add a payment method or upgrade to conceal this. Excess outbound DB/Storage/API
traffic can also lead to suspension. The chosen service must remain a bounded
hackathon demo, not a claimed always-on production system.

[Railway Free](https://docs.railway.com/pricing/free-trial) documents a limited
trial and then $1/month free credit; entitlement, no-card eligibility and hard
capacity for this account remain unverified. `railway.toml` is configuration
only. Do not activate it as fallback automatically or run both workers.

After explicit owner approval: verify account free/no-card eligibility; review
the additive migrations and backups; apply them through the owner-controlled
privileged path; provision the dedicated runtime password privately; configure
Auth/OAuth/Storage and exact frontend origin; deploy `render.yaml` manually
(`autoDeployTrigger: off`). Keep mock execution disabled until actual signed-in
two-owner persistence/report/export/restart acceptance succeeds. A cold-start
loading response must be retried as a status read, never replay a paid action.

Rollback: stop new execution, quarantine expired/uncertain work, restore the
previous reviewed API build/config. Do not drop ss/ss_runtime, rewind events,
delete witnessed objects or reverse migrations blindly. Schema changes are
additive; use the migration's documented verified rollback limits.
