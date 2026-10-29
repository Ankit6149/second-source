# Recovered Supabase baseline

`migrations/20261028193413_initial_second_source_private_schema.sql` is the
**already-applied** baseline for the dedicated Second Source project
`jpqcqqbzriizxhigvjki`. It is not a proposed migration or a deployment instruction.
Do not reapply it to that project, edit it, repair remote history or replace it
with the earlier unavailable draft. Future changes must be additive and reviewed.

The [provisioning record](https://github.com/Ankit6149/second-source/issues/2#issuecomment-6478716360)
and [recovery handoff](https://github.com/Ankit6149/second-source/issues/2#issuecomment-6492821865)
identify the source. The retained connector response contains one original
statement string from `supabase_migrations.schema_migrations`. Its exact UTF-8
export is **10,244 bytes**, SHA-256
`8a89975315fd8b9e1287bace3073e5fe7a3a185eb673c4341038234157d5aac2`.
`.gitattributes` disables newline conversion for this file. No comments or
formatting were inserted into the recovered SQL.

The 29 October read-only catalog snapshot recorded 12 tables / 104 constraints,
all RLS enabled, no policies, application routines or noninternal triggers.
`anon` and `authenticated` had no schema usage or table access; `service_role`
could select/insert events but not update/delete/truncate them. These are
snapshot facts, not a fresh live-state check. Raw connector/catalog receipts
remain in the ignored verifier archive `.runs/supabase-baseline-review-20261029/`;
they are not required for a clean-checkout replay and are not provider signatures.

## Offline verification

From the repository root, without credentials or a database:

```sh
python scripts/verify_supabase_baseline.py
```

This checks the retained byte witness only. It does not query Supabase, inspect
application rows or assert that the live schema still matches the snapshot.

The existing Python CI workflow discovers `tests/test_postgres_baseline.py`.
Its Linux test creates a disposable private PostgreSQL cluster using the runner's
server tools, disables TCP, and connects only to its own Unix socket. It never
accepts a DSN or inherits `PG*` settings. Minimal placeholder Auth roles/table
allow the exact migration to replay. The SQL exercises constraints/ACLs and
rolls back all DDL, roles and synthetic rows; the cluster is stopped and removed
even on failure. This uses no secrets or hosted connection and tests no Supabase
Auth/Storage runtime. Linux GitHub CI fails if server tools are absent. Other
platforms skip native replay and still verify exact baseline bytes.

```sh
python -m pytest tests/test_postgres_baseline.py
```

The SQL is in `tests/postgres/` and is intentionally for a fresh disposable
database only. The placeholder roles/table fail on reuse. The test does not
implement an adapter, measure concurrency or prove paid-call enforcement.
The first local SQL validation used an ignored PGlite 0.3.14 / embedded
PostgreSQL 17.5 installation, with no Python runtime dependency added. Native
Linux PostgreSQL replay and ordinary Linux/Windows CI are separate evidence.

## Map the existing service before implementing an adapter

Keep [backend contracts](../src/second_source/backend/contracts.py), the existing
G2/G3 engine, verifier and receipts authoritative. Do not add a second lifecycle,
scorer, approval system or schema solely to bypass these differences.

| Existing local contract | Recovered baseline | Required adapter decision / missing primitive |
|---|---|---|
| Owner-scoped investigation with immutable scope/digest | `targets.scope` plus `investigations.target_id`; scope hash on `runs` | Freeze and verify the same canonical scope at target/investigation/run boundaries; no mutable target lookup may widen an approved run |
| `Principal.owner_id` accepts bounded local IDs | Owners are UUID foreign keys to `auth.users` | Use verified server-side identity; never cast a local token label or trust user-editable JWT metadata |
| `created` / `authorized`, revision-checked mutation | Investigation starts `draft`; no revision columns | Explicit status mapping and additive optimistic revision support; never drop `expected_revision` checks |
| Idempotent investigation AND run creation, request-body digest | Unique `(owner_id,idempotency_key)` on runs only; key length 16..160 | Durable body-digest binding and investigation idempotency; preserve current service's accepted keys rather than truncate/pad or silently change semantics |
| Investigation events may have no run ID | `run_events.run_id` required; no lifecycle revision field | Preserve investigation events and revisions through a reviewed additive representation; do not invent a run to store an authorization event |
| Mock-only scope approval, exactly zero spend | Run-specific action approvals, including `model_call` and `repair` | A local mock approval cannot be translated to a paid action grant; cloud real mode stays disabled |
| Ordered CODE stages and truthful terminal result | Extra stage/status values; result scattered across tables | Explicit lossless mappings, durable result/error fields; quarantine unsupported states instead of reporting completion |
| Queued / running / needs_reconciliation; fenced token and expiry | Separate jobs, epoch/owner/until; run `uncertain`, job `blocked` available | Atomic claim with `FOR UPDATE SKIP LOCKED`, run+job+event transaction, fencing on EVERY worker mutation, DB-clock expiry and quarantine on expired execution |
| No automatic replay after lease expiry | `jobs.max_attempts` defaults to **3** | Adapter must explicitly restrict each submitted run to one attempt; schema default grants no retry or inference authority |
| Append-only events in the same state transaction | ACL denies service-role update/delete, hash columns only | Serialize append with run lock, bind canonical event content/previous hash, verify chain; database owner can still alter records |
| Existing immutable model receipts and explicit uncertainty | Unique model operation key; nullable approval and optional request/response fields | Atomic permission consumption/reservation/dispatch journal; ambiguous transport quarantines with uncertainty, never automatic retry. A row or FK is not authentic provider provenance |
| Evaluation passed+failed+indeterminate=total | Adds `skipped` and a total count constraint | Preserve original raw counts; refuse unsupported nonzero skipped counts rather than silently relabel them. Never regenerate the frozen evaluator |
| Private hashed artifact references and sanitized exports | Bucket/object-key metadata; no object content verification | Verify stored bytes/checksums and owner/run binding with the existing artifact contract; no public bucket or raw-response export |

The schema alone does **not** enforce atomic claim/approval consumption, event
hash-chain authenticity, exactly-once execution, immutable scope or safe paid
transport. Composite FKs prevent several cross-owner references but do not
authorize service-role requests; all application reads/writes still need tenant
filters. Evaluation ownership must be checked through candidate -> run because
`evaluations` has no direct owner column. Keep all tables private and leave the
intentional policy-free RLS boundary intact.

The next adapter slice should first add/review only the transaction primitives
needed to retain these contracts, then run the shared service acceptance cases
against disposable native PostgreSQL, including competing claims, stale fences,
rollback and process loss. Do not enable hosted connections, migrations, auth,
workers or paid operations as a side effect of importing an adapter.

Supabase's [local workflow](https://supabase.com/docs/guides/local-development/cli-workflows)
documents versioned migrations and distinguishes local from linked targets.
No CLI linking, credentials, remote history repair, `db push`, reset, new project,
deployment or live write was used for this repository recovery.
