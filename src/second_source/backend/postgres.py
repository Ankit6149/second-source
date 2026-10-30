"""PostgreSQL transactional adapter for the existing backend service.

Requires the separately reviewed ss_runtime schema; never migrates on startup.
Trusted server-only DSN, project-pinned and TLS required. No paid operations.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import os
import re
from typing import Any
import uuid

from .contracts import ArtifactReference, BackendError, Principal


RUNTIME_ROLE = 'second_source_backend'


class _Row(Mapping):
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.positional = tuple(data.values())

    def __getitem__(self, item):
        return self.positional[item] if type(item) is int else self.data[item]

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)


class _Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        return _Row(row) if row is not None else None

    def fetchall(self):
        return [_Row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        for row in self.cursor:
            yield _Row(row)


def _translate(query: str) -> str:
    # Fixed backend statements use SQLite qmark syntax, with no literal
    # question-mark operators or SQL interpolation. Bound parameters remain
    # bound parameters in psycopg, not concatenated strings.
    if not isinstance(query, str) or not query or ";" in query or "%" in query:
        raise BackendError("STORAGE_QUERY", "Unsupported storage statement", 503)
    if query.strip().upper().startswith(("PRAGMA", "ATTACH", "COPY", "SET ")):
        raise BackendError("STORAGE_QUERY", "Unsupported storage statement", 503)
    sql = query.replace("?", "%s")
    # Concurrent worker claims must never select one row without a lock.
    if sql in ("SELECT * FROM runs WHERE status='queued' ORDER BY created_at,run_id LIMIT 1",
                  "SELECT * FROM runs WHERE status='queued' AND run_id=%s ORDER BY created_at,run_id LIMIT 1"):
        sql += " FOR UPDATE SKIP LOCKED"
    elif sql in ("SELECT * FROM runs WHERE status='running' AND lease_expires<=%s",
                 "SELECT * FROM runs WHERE status='running' AND lease_expires<=%s AND run_id=%s"):
        sql += " FOR UPDATE SKIP LOCKED"
    return sql


class _Connection:
    def __init__(self, raw):
        self.raw = raw
        self._fence = None

    def execute(self, query: str, params=()):
        sql = _translate(query)
        if self._fence is not None and query.startswith('UPDATE runs SET '):
            run_id, token = self._fence
            if not query.endswith(' WHERE run_id=?') or not params or params[-1] != run_id:
                raise BackendError('STORAGE_QUERY', 'Unsupported fenced mutation', 503)
            # Recheck expiry at the actual mutation, after obtaining the row lock.
            # A lease that expires during validation may not commit a result/event.
            sql += " AND status='running' AND lease_token=%s AND lease_expires>EXTRACT(EPOCH FROM clock_timestamp())"
            cursor = self.raw.execute(sql, (*params, token))
            if cursor.rowcount != 1:
                raise BackendError('LEASE_LOST', 'Execution lease is no longer valid')
            return _Cursor(cursor)
        return _Cursor(self.raw.execute(sql, params))

    def lock_run(self, run_id):
        return _Cursor(self.raw.execute('SELECT * FROM runs WHERE run_id=%s FOR UPDATE', (run_id,))).fetchone()

    def set_fence(self, run_id, token):
        self._fence = (run_id, token)

    def database_epoch(self) -> float:
        row = self.raw.execute("SELECT EXTRACT(EPOCH FROM clock_timestamp()) AS epoch").fetchone()
        return float(row["epoch"])

    def database_timestamp(self) -> str:
        return self.raw.execute('SELECT clock_timestamp() AS timestamp').fetchone()['timestamp'].isoformat()


class PostgresStore:
    SCHEMA_VERSION = 2

    def __init__(self, dsn: str, *, project_ref: str):
        if not isinstance(project_ref, str) or not re.fullmatch(r"[a-z0-9]{20}", project_ref):
            raise ValueError("Invalid Supabase project reference")
        if not isinstance(dsn, str) or len(dsn) > 4096:
            raise ValueError("Invalid Postgres configuration")
        try:
            from psycopg.conninfo import conninfo_to_dict
            config = conninfo_to_dict(dsn)
        except Exception as exc:
            raise ValueError("Invalid Postgres configuration") from exc
        host, user = config.get("host", ""), config.get("user", "")
        direct = host == f"db.{project_ref}.supabase.co" and user == RUNTIME_ROLE
        pool = bool(re.fullmatch(r"aws-[a-z0-9-]+\.pooler\.supabase\.com", host)) and user == f"{RUNTIME_ROLE}.{project_ref}"
        allowed = {'host', 'port', 'user', 'password', 'dbname', 'sslmode', 'sslrootcert', 'application_name'}
        if (set(config) - allowed or not config.get('password')
                or not (direct or pool) or config.get("dbname") != "postgres"
                or config.get("sslmode") != "verify-full"
                or (direct and config.get("port", "5432") != "5432")
                or (pool and config.get("port", "5432") not in ("5432", "6543"))):
            raise ValueError("Database identity, TLS or routing configuration is not permitted")
        self._dsn = dsn

    def _open_connection(self):
        import psycopg
        from psycopg.rows import dict_row
        # libpq fills missing settings from PG* environment variables. Reject
        # their names without reading any credential values, and disable its
        # implicit password-file fallback. The DSN is explicit server config.
        if any(name.upper().startswith('PG') for name in os.environ):
            raise BackendError('STORAGE_CONFIGURATION', 'Implicit database configuration is not permitted', 503)
        return psycopg.connect(self._dsn, autocommit=False, connect_timeout=5,
                               prepare_threshold=None, row_factory=dict_row, passfile=os.devnull)

    @contextmanager
    def transaction(self):
        try:
            with self._open_connection() as raw:
                raw.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                raw.execute("SET LOCAL statement_timeout TO '10000ms'")
                raw.execute("SET LOCAL lock_timeout TO '4000ms'")
                raw.execute("SET LOCAL search_path TO pg_catalog, pg_temp")
                role = raw.execute("""SELECT current_user AS name, session_user AS session_name,
                    rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication, rolinherit,
                    EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid) AS has_membership,
                    has_schema_privilege(current_user,'ss','USAGE') AS evidence_access
                    ,EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='ss_runtime' AND nspowner=pg_roles.oid) AS runtime_owner
                    ,has_schema_privilege(current_user,'ss_runtime','CREATE') AS runtime_ddl
                    ,EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                            WHERE n.nspname='ss_runtime' AND c.relowner=pg_roles.oid) AS runtime_relation_owner
                    FROM pg_roles WHERE rolname=current_user""").fetchone()
                if (not role or role['name'] != RUNTIME_ROLE or role['session_name'] != RUNTIME_ROLE
                        or any(role[key] for key in ('rolsuper', 'rolbypassrls', 'rolcreatedb',
                            'rolcreaterole', 'rolreplication', 'rolinherit', 'has_membership',
                            'evidence_access', 'runtime_owner', 'runtime_ddl', 'runtime_relation_owner'))):
                    raise BackendError('STORAGE_ROLE', 'Dedicated private database role is required', 503)
                raw.execute("SET LOCAL search_path TO ss_runtime, pg_catalog, pg_temp")
                yield _Connection(raw)
        except BackendError:
            raise
        except Exception as exc:
            # PostgreSQL serialization conflicts must never silently retry
            # reference mutations or already-dispatched paid model calls.
            raise BackendError("STORAGE_UNAVAILABLE", "Cloud state is unavailable", 503) from exc

    def readiness(self) -> bool:
        try:
            with self.transaction() as db:
                row = db.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
                return bool(row and row[0] == self.SCHEMA_VERSION)
        except BackendError:
            return False

    @staticmethod
    def _uuid(value):
        try:
            parsed = uuid.UUID(value)
            if str(parsed) != value:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise BackendError('INVALID_ID', 'Canonical UUID identity is required', 422) from None
        return value

    @staticmethod
    def _owned_investigation(db, principal, investigation_id):
        row = db.execute('SELECT * FROM investigations WHERE investigation_id=? AND owner_id=?',
                         (investigation_id, principal.owner_id)).fetchone()
        if row is None:
            raise BackendError('NOT_FOUND', 'Resource not found', 404)
        return row

    @staticmethod
    def _insert_binding(db, table, values):
        # Identifiers come exclusively from the fixed dictionaries below;
        # all caller-supplied identities stay bound parameters.
        columns = ','.join(values)
        marks = ','.join('?' for _ in values)
        db.execute(f'INSERT INTO {table}({columns}) VALUES({marks}) ON CONFLICT DO NOTHING', tuple(values.values()))
        predicate = ' AND '.join(name + '=?' for name in values)
        if db.execute(f'SELECT 1 FROM {table} WHERE {predicate}', tuple(values.values())).fetchone() is None:
            raise BackendError('BINDING_CONFLICT', 'An immutable evidence binding already exists')

    @contextmanager
    def _binding_transaction(self):
        try:
            with self.transaction() as db:
                yield db
        except BackendError as error:
            if getattr(error.__cause__, 'sqlstate', None) in {'23503', '23514', '22P02'}:
                raise BackendError('INVALID_EVIDENCE_BINDING', 'Existing evidence identities do not match the owner, run or scope') from None
            raise

    def bind_investigation(self, principal: Principal, investigation_id: str, evidence_investigation_id: str) -> None:
        self._uuid(principal.owner_id)
        self._uuid(evidence_investigation_id)
        with self._binding_transaction() as db:
            row = self._owned_investigation(db, principal, investigation_id)
            self._insert_binding(db, 'investigation_bindings', {
                'investigation_id': investigation_id, 'owner_id': principal.owner_id,
                'evidence_investigation_id': evidence_investigation_id, 'scope_digest': row['scope_digest']})

    def bind_run(self, principal: Principal, run_id: str, evidence_run_id: str) -> None:
        self._uuid(principal.owner_id)
        self._uuid(evidence_run_id)
        with self._binding_transaction() as db:
            row = db.execute('SELECT r.investigation_id,b.evidence_investigation_id,b.scope_digest FROM runs r JOIN investigation_bindings b USING(investigation_id) WHERE r.run_id=? AND b.owner_id=?',
                             (run_id, principal.owner_id)).fetchone()
            if row is None:
                raise BackendError('NOT_FOUND', 'Resource or investigation binding not found', 404)
            self._insert_binding(db, 'run_bindings', {
                'run_id': run_id, 'investigation_id': row['investigation_id'], 'owner_id': principal.owner_id,
                'evidence_investigation_id': row['evidence_investigation_id'],
                'scope_digest': row['scope_digest'], 'evidence_run_id': evidence_run_id})

    def bind_artifact(self, principal: Principal, run_id: str, evidence_artifact_id: str) -> None:
        self._uuid(principal.owner_id)
        self._uuid(evidence_artifact_id)
        with self._binding_transaction() as db:
            row = db.execute('SELECT evidence_run_id FROM run_bindings WHERE run_id=? AND owner_id=?',
                             (run_id, principal.owner_id)).fetchone()
            if row is None:
                raise BackendError('NOT_FOUND', 'Resource or run binding not found', 404)
            self._insert_binding(db, 'artifact_bindings', {
                'run_id': run_id, 'owner_id': principal.owner_id,
                'evidence_run_id': row['evidence_run_id'], 'evidence_artifact_id': evidence_artifact_id})

    def evidence_bindings(self, principal: Principal, investigation_id: str) -> dict:
        self._uuid(principal.owner_id)
        with self.transaction() as db:
            self._owned_investigation(db, principal, investigation_id)
            investigation = db.execute('SELECT evidence_investigation_id FROM investigation_bindings WHERE investigation_id=? AND owner_id=?',
                                      (investigation_id, principal.owner_id)).fetchone()
            runs = db.execute('SELECT run_id,evidence_run_id FROM run_bindings WHERE investigation_id=? AND owner_id=? ORDER BY run_id',
                              (investigation_id, principal.owner_id)).fetchall()
            artifacts = db.execute('SELECT a.run_id,a.evidence_artifact_id FROM artifact_bindings a JOIN run_bindings b ON a.run_id=b.run_id AND a.owner_id=b.owner_id WHERE b.investigation_id=? AND a.owner_id=? ORDER BY a.run_id,a.evidence_artifact_id',
                                   (investigation_id, principal.owner_id)).fetchall()
            return {'investigation_id': investigation_id,
                    'evidence_investigation_id': str(investigation[0]) if investigation else None,
                    'runs': [{'run_id': row['run_id'], 'evidence_run_id': str(row['evidence_run_id'])} for row in runs],
                    'artifacts': [{'run_id': row['run_id'], 'evidence_artifact_id': str(row['evidence_artifact_id'])} for row in artifacts]}

    @staticmethod
    def _owned_run(db, principal, run_id):
        row = db.execute('SELECT r.* FROM runs r JOIN investigations i USING(investigation_id) WHERE r.run_id=? AND i.owner_id=?',
                         (run_id, principal.owner_id)).fetchone()
        if row is None:
            raise BackendError('NOT_FOUND', 'Resource not found', 404)
        return row

    def record_artifact_ref(self, principal: Principal, run_id: str, reference: ArtifactReference, *, lease_token: str) -> None:
        from .service import BackendService
        self._uuid(principal.owner_id)
        reference = ArtifactReference.model_validate(reference.model_dump() if isinstance(reference, ArtifactReference) else reference)
        if (not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', reference.artifact_id)
                or len(reference.media_type) > 120 or not reference.media_type
                or reference.size_bytes > 104_857_600):
            raise BackendError('INVALID_ARTIFACT_REFERENCE', 'Bounded artifact metadata is required', 422)
        with self.transaction() as db:
            row = self._owned_run(db, principal, run_id)
            BackendService._fenced(db, run_id, lease_token)
            self._insert_binding(db, 'runtime_artifact_refs', {
                'run_id': run_id, 'investigation_id': row['investigation_id'], 'owner_id': principal.owner_id,
                'artifact_id': reference.artifact_id, 'sha256': reference.sha256,
                'size_bytes': reference.size_bytes, 'media_type': reference.media_type})
            # Holding the run lock prevents concurrent cancellation/recovery;
            # this second DB-clock check also rolls back an insert if the lease
            # expired during metadata validation/publication of this transaction.
            BackendService._fenced(db, run_id, lease_token)

    def artifact_refs(self, principal: Principal, run_id: str) -> list[ArtifactReference]:
        self._uuid(principal.owner_id)
        with self.transaction() as db:
            self._owned_run(db, principal, run_id)
            rows = db.execute('SELECT artifact_id,sha256,size_bytes,media_type FROM runtime_artifact_refs WHERE run_id=? AND owner_id=? ORDER BY artifact_id',
                              (run_id, principal.owner_id)).fetchall()
            return [ArtifactReference.model_validate(dict(row)) for row in rows]
