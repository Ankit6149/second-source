"""Durable SQLite job/event store for orchestration (separate DB, WAL, FULL sync)."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from second_source.backend.contracts import BackendError
from second_source.backend.paths import checked_regular_file, safe_directory

SCHEMA = """
CREATE TABLE IF NOT EXISTS orch_investigations(
 investigation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, title TEXT NOT NULL,
 instruction TEXT NOT NULL, target_id TEXT NOT NULL, scope_json TEXT NOT NULL,
 scope_digest TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN('created','authorized')),
 revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orch_jobs(
 job_id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL REFERENCES orch_investigations(investigation_id),
 kind TEXT NOT NULL DEFAULT 'orchestration_mock',
 status TEXT NOT NULL CHECK(status IN('queued','running','completed','failed','cancelled','needs_reconciliation')),
 stage TEXT, attempt INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL,
 cancel_requested INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 error_code TEXT, result_report_id TEXT, worker_id TEXT, lease_token TEXT, lease_expires REAL,
 idempotency_key TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS orch_jobs_idem ON orch_jobs(investigation_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS orch_events(
 event_id INTEGER PRIMARY KEY AUTOINCREMENT, investigation_id TEXT NOT NULL,
 job_id TEXT, event_type TEXT NOT NULL, stage TEXT, revision INTEGER NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orch_idempotency(
 owner_id TEXT NOT NULL, operation TEXT NOT NULL, key TEXT NOT NULL,
 request_digest TEXT NOT NULL, resource_id TEXT NOT NULL, PRIMARY KEY(owner_id,operation,key));
CREATE TABLE IF NOT EXISTS orch_spend(
 investigation_id TEXT NOT NULL, seq INTEGER NOT NULL, amount_usd REAL NOT NULL,
 packet_id TEXT, created_at TEXT NOT NULL, PRIMARY KEY(investigation_id, seq));
"""

class OrchestrationStore:
    def __init__(self, database_path: str | Path):
        self.path = Path(database_path).absolute()
        if str(database_path) == ":memory:":
            raise ValueError("A durable database path is required")
        safe_directory(self.path.parent)
        checked_regular_file(self.path)
        with self.transaction() as c:
            c.executescript(SCHEMA)
        self.path.chmod(0o600)

    def _connect(self):
        safe_directory(self.path.parent)
        for p in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")):
            checked_regular_file(p)
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @contextmanager
    def transaction(self):
        conn = None
        try:
            conn = self._connect()
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            if conn is not None:
                conn.rollback()
            raise BackendError("STORAGE_UNAVAILABLE", "Durable state is unavailable", 503) from e
        except BaseException:
            if conn is not None:
                conn.rollback()
            raise
        finally:
            if conn is not None:
                conn.close()

    def readiness(self) -> bool:
        try:
            with self.transaction() as c:
                return c.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except BackendError:
            return False
