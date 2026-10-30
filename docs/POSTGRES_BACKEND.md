# Private PostgreSQL control plane

SQLite remains the default local store, including bounded local owner labels.
`BackendService(store=PostgresStore(...))` reuses the same lifecycle, validation,
mock-only authorization, idempotency, events, worker and public contracts. The
adapter neither applies migrations nor reads credentials on import/construction.
No cloud activation, live database acceptance or paid execution follows from
these implementation checks.

## Reviewed additive schema

Apply nothing to the hosted project as part of normal startup. An authorized
operator must separately review and apply, in order:

1. The retained **already-applied** `20261028193413` ss baseline. Do not reapply
   this to `jpqcqqbzriizxhigvjki` or change its frozen byte witness.
2. `20261029_backend_runtime_schema.sql`, the private local-contract-compatible
   `ss_runtime` baseline proposed in PR #14.
3. `20261030180237_runtime_private_role_and_bindings.sql`, the additive identity,
   role and binding migration prepared from the backend completion proposal.

The new migration was generated with the Supabase CLI and remains unapproved for
live application. No linked target, history repair, reset or live DDL was used.
The native acceptance tests replay all three in disposable clusters; the newly
generated file requires a fresh CI run before approval. The new migration fails
on invalid existing runtime owners or a
pre-existing conflicting role instead of deleting/reassigning records.

`ss_runtime` preserves the existing service's revision checks, immutable scope,
mock approval receipt, request-body-bound idempotency, ordered CODE events and
terminal result. It does not create another engine, evaluator or spending grant.
There is no automatic synchronization or fabricated evidence in `ss`.

Runtime investigations carry a generated canonical owner UUID with an FK to
`auth.users`. Runtime approvals/events also have composite investigation/run
ownership constraints. Local SQLite labels are unaffected. A verified Auth
principal UUID and an existing user row are both required for PostgreSQL work;
the database constraint does not itself authenticate an HTTP caller.

## Dedicated server role

`second_source_backend` is a non-owner LOGIN role with no password in the
migration. It is explicitly NOSUPERUSER, NOINHERIT, NOBYPASSRLS, NOCREATEDB,
NOCREATEROLE and NOREPLICATION. Setting its secret through authorized server-side
provisioning is a separate owner action; never paste or commit a password.

The role receives schema usage and SELECT on runtime tables; INSERT for the
service's create-once records; and UPDATE only on mutable investigation/run
columns. It cannot delete/truncate runtime state, change owners/scopes, rewrite
events/approvals/idempotency/bindings, modify schema version, or create objects
in `ss_runtime`. The role has no `ss` or `auth` schema usage or row grants.
Role-specific runtime RLS policies authorize this private server role only.
They are not per-user RLS: the trusted server can service multiple owners, so
all application reads/mutations retain the service's owner predicates. No
browser, `anon`, `authenticated` or `service_role` runtime access is granted.

Each transaction verifies the actual database/session role, absence of elevated
role attributes/memberships, runtime schema ownership and `ss` access. Drift
fails closed. Explicit `pg_temp` ordering prevents temporary objects from
shadowing unqualified runtime relations. No SECURITY DEFINER function or
permissive policy is added to `ss`.

The adapter accepts only an explicit password-bearing, project-pinned DSN:

- Direct: `second_source_backend` at `db.<project>.supabase.co:5432`.
- Pooler: `second_source_backend.<project>` at the Supabase pooler, port
  `5432` or `6543`.
- Database `postgres`; TLS `sslmode=verify-full` is required.

The allowlist rejects hostaddr, service, options, password-file and client-key
overrides. Before connecting it rejects inherited `PG*` option names without
reading their values, and explicitly disables implicit password-file fallback.
Use a server configuration process that supplies only the reviewed explicit
DSN/trust settings. The store keeps secrets private and returns fixed errors.
Install the existing pinned optional dependency with `pip install -e '.[cloud]'`.

## Explicit evidence identities

Bindings connect existing records and never create `ss` observations, candidates,
model calls, evaluations or artifacts:

```python
store.bind_investigation(principal, runtime_investigation_id, existing_ss_investigation_id)
store.bind_run(principal, runtime_run_id, existing_ss_run_id)
store.bind_artifact(principal, runtime_run_id, existing_ss_artifact_id)
bindings = store.evidence_bindings(principal, runtime_investigation_id)
```

The immutable binding tables enforce the canonical owner, runtime investigation,
runtime run, existing `ss` investigation/run and frozen scope digest through
composite FKs. The one additive unique key on `ss.runs` enables that full identity
FK; it changes no `ss` rows, policies, permissions or lifecycle. An artifact FK
requires its exact existing evidence run and owner. Identical calls are
idempotent; conflicting bindings fail. Cross-owner resources retain NOT_FOUND
and inconsistent existing evidence references fail with a fixed diagnostic.
Unbound runtime records stay explicitly unbound. Binding is not provider
attestation, behavioral equivalence, or proof that object bytes match metadata.

`record_artifact_ref(principal, run_id, reference, lease_token=lease.token)` and
`artifact_refs(principal, run_id)` separately retain immutable owner/run-bound
hash, length and media type references for private execution artifacts. No
private bytes or storage credentials enter these tables. These references do
not fabricate `ss.artifacts`; actual private object publication and checksum
verification remain the artifact adapter's responsibility. Public report/export
routes must not expose the private reference list.
Recording requires the current exact-run worker lease, locks that run, checks
owner/token/status and the DB clock before and after the immutable insert, and
rolls back on expiry. No unfenced administrator-recovery shortcut is installed.

## Fencing, recovery and transaction failure

Transactions use SERIALIZABLE isolation and never automatically retry. Both
generic and exact-run claims use `FOR UPDATE SKIP LOCKED`. PostgreSQL's server
clock controls lease grants, heartbeats, fence checks and recovery. Every worker
run mutation first locks the row, validates the secret lease, then checks status,
token and DB-clock expiry again in the UPDATE itself. A timeout or serialization
failure cannot silently become a successful dispatch.

Queued cancellation is terminal; active cancellation is durable and prevents
the next stage. Expired runs move to `needs_reconciliation` with lease cleared,
never to the queue. `recover_expired(run_id=...)` supports an exact-run operation
after the caller's owner check; the global CLI default remains available.
`ARTIFACT_PUBLICATION_UNCERTAIN` also terminates in `needs_reconciliation` because
an unknown remote publication outcome cannot authorize replay. Results/state
and lifecycle events commit atomically; event failures roll back the transition.

## Credential-free verification

```sh
python -m pytest tests/test_backend_postgres.py tests/test_backend_postgres_native.py tests/test_backend_store.py
```

Native acceptance requires Linux PostgreSQL server tools. Each test creates a
private fresh cluster with no TCP listener and only its generated Unix socket,
minimal fake Auth users and synthetic NON_AI evidence. It applies all migrations
and executes the production transaction code as `second_source_backend`, not
as the owner. Cleanup stops only that generated cluster even after failure.

Cases cover six competing exact claims and an unrelated queue; host clock skew;
cancel-before/after-claim; scoped/global expiry quarantine; all stale worker
mutations; expiry between validation and UPDATE; transition/event rollback;
restart; owner isolation; Auth FK rejection; immutable evidence/ref replay and
conflicts; denied evidence/Auth reads and DDL/deletes; and privilege-drift failure.
Other platforms report native skips rather than claim PostgreSQL acceptance.

Local Windows targeted result at implementation time: **26 passed / 6 native
Linux skips**. No hosted project, Google OAuth, real Meta, billing or production
deployment was accessed. Linux native results and exact-head CI must be recorded
before treating this milestone as independently accepted.
