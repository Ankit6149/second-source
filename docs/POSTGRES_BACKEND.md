# Postgres backend implementation (no cloud deployment yet)

The existing backend service can accept a PostgresStore instance in place of its
SQLiteStore. Local SQLite is still the default. The separate additive
ss_runtime SQL migration preserves the 12 already-applied ss evidence tables.

Configure the private server-only connection from SECOND_SOURCE_DATABASE_URL.
Do not commit passwords or expose connection strings in the browser.
Install pip install -e '.[cloud]' for psycopg 3. Instantiate:

    service = BackendService(store=PostgresStore(
        os.environ["SECOND_SOURCE_DATABASE_URL"],
        project_ref="jpqcqqbzriizxhigvjki"))

The project-pinned DSN requires TLS and an exact Supabase direct/pooler identity.
Transactions use SERIALIZABLE isolation, tenant-aware owner checks already in
BackendService, plus FOR UPDATE SKIP LOCKED on work claims. No automatic retries.

This is not production acceptance: schema and permissions require an
independent native Postgres integration test, a dedicated least-privilege
database role, Cloud artifact storage, worker deployment, and a mapping between
ss_runtime control-plane run identities and ss evidence records. The migration
is NOT applied to the live project. No paid inference or Google OAuth setup.


## Reviewed security amendments

Connections reject libpq hostaddr/service overrides and require verified
server identity with sslmode=verify-full. The service uses the PostgreSQL
server clock for lease grants, fencing, heartbeats and expired-run quarantine,
not client machine time; SQLite retains local time. Both generic and
run-filtered queued claims use FOR UPDATE SKIP LOCKED. The added native test
probes skewed host-clock behavior in an isolated PostgreSQL cluster.

Do not deploy or merge without independent concurrency and provider-identity
review. The ss_runtime and ss schemas remain intentionally unsynchronized.

## Native concurrency and process-loss acceptance

The disposable Linux PostgreSQL lifecycle suite additionally launches two
concurrent independent worker claims for one queued run, requires exactly one
lease and a single durable claim event, simulates abrupt worker disappearance
by expiring the lease according to the database clock, and verifies that
recovery transitions the run to `needs_reconciliation` without auto-requeue
or accepting a stale worker's stage update. A serialization error is allowed
only as a sanitized failed claim, never as a second lease.

This remains a test of the current trusted local DB semantics, **not** a
cloud-hosted worker acceptance test, a proof of billing idempotency, or a
substitute for a least-privilege Postgres role and live project credentials.
