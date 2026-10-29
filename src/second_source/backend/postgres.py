"""PostgreSQL transactional adapter for the existing backend service.

Requires the separately reviewed ss_runtime schema; never migrates on startup.
Trusted server-only DSN, project-pinned and TLS required. No paid operations.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import re
from typing import Any

from .contracts import BackendError


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
    if sql == "SELECT * FROM runs WHERE status='queued' ORDER BY created_at,run_id LIMIT 1":
        sql += " FOR UPDATE SKIP LOCKED"
    return sql


class _Connection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, query: str, params=()):
        return _Cursor(self.raw.execute(_translate(query), params))


class PostgresStore:
    SCHEMA_VERSION = 1

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
        direct = host == f"db.{project_ref}.supabase.co" and user == "postgres"
        pool = bool(re.fullmatch(r"aws-[a-z0-9-]+\.pooler\.supabase\.com", host)) and user == f"postgres.{project_ref}"
        if (not (direct or pool) or config.get("dbname") != "postgres"
                or config.get("sslmode") not in ("verify-full", "verify-ca", "require")):
            raise ValueError("Database TLS, host or tenant identity is not permitted")
        self._dsn = dsn

    @contextmanager
    def transaction(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
            with psycopg.connect(self._dsn, autocommit=False, connect_timeout=5,
                                 prepare_threshold=None, row_factory=dict_row) as raw:
                raw.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                raw.execute("SET LOCAL search_path TO ss_runtime, pg_catalog")
                raw.execute("SET LOCAL statement_timeout TO '10000ms'")
                raw.execute("SET LOCAL lock_timeout TO '4000ms'")
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
