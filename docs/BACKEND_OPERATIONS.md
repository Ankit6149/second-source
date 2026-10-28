# Durable backend operator workflow

This slice provides a local, modular control plane around the existing **NON_AI G3 engine**. It does not enable Meta inference, credential retrieval, candidate repair or deployment. See [API contracts](BACKEND_API.md) and the [current board](G3_DELIVERY_BOARD.md) for acceptance state; implemented code is not a production-readiness certification.

## Install and provision

Use Python 3.11+ from the exact reviewed checkout:

```sh
python -m venv .venv
# Linux: . .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m second_source.backend --data-dir <private-external-directory> init
```

The data directory must be outside the checkout, local to a trusted operator, and backed up using SQLite's supported backup mechanism while writers are active. Protect it with OS permissions; application file modes alone do not configure Windows ACLs or encryption. Never use shared network storage or manually copy a live database without its WAL. No automatic retention cleanup deletes witnessed evidence.

SQLite migration `001_control_plane.sql` initializes schema version 1 transactionally. Future-schema databases fail closed. No destructive automatic downgrade exists: stop API/workers, back up state, migrate only with the corresponding reviewed service version; restore an intact pre-migration backup to roll back. Database/WAL/SHM hardlinks, symbolic links and reparse ancestors are rejected. Concurrent connections use WAL, FULL synchronization, foreign keys, a bounded busy timeout and per-operation transactions. Power-loss guarantees still depend on the underlying filesystem.

## One nonbillable journey

```sh
python -m second_source.backend --data-dir <private-external-directory> mock
```

This creates an investigation with the exact published zero-cost owned-ledger scope, records mock-only scope approval, queues an idempotent run, claims a fenced lease, then invokes the **existing** G3 command in a separate process. Only safe process-environment variables are inherited; model keys and nonzero spending settings are excluded. Ordered durable CODE stage events follow actual engine notifications. Original engine report, candidate, broker envelope and private sealed suite stay in private engine storage; the API receives only an allowlisted report projection.

The expected existing scripted score is **22 passed / 3 failed / 0 indeterminate / 25, NON_AI**. It demonstrates integration and verifier sensitivity, not a genuine reconstruction. Reusing the command's default idempotency key returns its existing run; it never grants a new paid attempt. Use a new explicit `--idempotency-key` only for a deliberately new nonbillable run. Scope changes are not silently mapped to the owned fixture: unsupported scopes stop before subprocess dispatch.

## API and workers

```sh
python -m second_source.backend --data-dir <private-external-directory> serve --token-hashes <hash-only-owner-map.json>
python -m second_source.backend --data-dir <same-directory> worker
python -m second_source.backend --data-dir <same-directory> status --owner <owner-id> --run-id <run-id>
```

Serving is an explicit local operator action, not something performed by documentation or acceptance tests. The service binds `127.0.0.1` only. The token file maps SHA-256 digests of independently provisioned high-entropy backend bearer tokens to owner IDs; it contains neither model keys nor plaintext tokens. CLI administrative access relies on the local OS account; it is not a multi-tenant remote authentication mechanism. See the API document for bounded ingress, pagination, errors and exact routes. HTTP requests persist jobs rather than executing inference in the request thread.

The queue defaults to 32 outstanding jobs. Workers claim once, heartbeat and fence every mutation; stale/expired workers cannot publish a new result. Cancel requests use expected revisions. A queued cancellation is terminal; a running cancellation stops further dispatch and retains an honest terminal outcome. SIGINT/SIGTERM stops claiming new jobs and requests cancellation of active work. A mock subprocess is time-bounded, with bounded output. POSIX termination covers the wrapper's process group, but staged candidate workers start independent sessions and may outlive that wrapper until their existing bounds stop them. Complete descendant termination is **best effort on both platforms**, not certified through Job Objects or a full process-tree boundary. Existing candidate/reference worker bounds remain required; this is not an arbitrary-code sandbox.

At worker startup expired running leases become `needs_reconciliation`, never silently requeued. This intentionally does not resume a possibly executed reference or model operation. There is no paid engine adapter or generic HTTP paid-approval endpoint. Enabling one later requires integration with the existing exact-input approval/budget/receipt boundary and explicit operation-specific owner authorization.

## Reports and independently checked export

Authenticated owners may retrieve their report and `export.zip` through API v1. The ZIP contains an allowlisted report, public run metadata, ordered scoped lifecycle events and a checksum manifest. It excludes raw model text, hypotheses, observation contents, credentials, local paths, signing keys and sealed cases. The original private engine artifacts are retained separately; this public projection is not the complete private archive or a provider signature.

```sh
python -m second_source.backend --data-dir <private-external-directory> verify-bundle <export.zip> --expected-sha256 <externally-retained-bundle-hash>
```

Verification is bounded and in-memory, without extracting or executing ZIP entries. It checks member names, sizes, checksums, report/result linkage, origin/accounting and event scope/order. Without an external expected hash it proves internal integrity only. Retain the bundle hash through a separate trusted channel. Private candidate/suite replay remains an evaluator operation under the existing G3 contract; the ZIP contains no hidden test material and cannot reproduce a sealed score by itself.

## Operational acceptance and limits

Targeted acceptance covers transactional restart, an actual process death mid-transaction, duplicate requests, competing claims, scope approvals, stale fences, cancellation, malformed HTTP/bundles, owner isolation, storage aliases, sanitized errors and the service-to-existing-G3 mock path. Exact Linux/Windows CI and independent review must pass at the published checkpoint before merge.

Implemented observability: durable timestamped events with investigation/run IDs, revisions and stages; request correlation IDs and safe error codes; structured worker outcome logs; persisted usage/evaluation summaries; liveness and storage/schema readiness. Not implemented: distributed tracing, stage-latency dashboards, alerting, provider health probes, certified horizontal scaling or Windows Job Object cancellation. Health does not imply provider availability or successful real reconstruction. Runtime API pins are explicit; the repository's older Pydantic/test/build ranges are not a complete transitive dependency lock.
