"""SQLite persistence boundary. One connection/transaction per operation.

The database and WAL are private local operator state, not a cryptographically
authenticated evidence store. Existing engine receipts retain that role.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from .contracts import BackendError
from .paths import checked_regular_file, safe_directory


class SQLiteStore:
    SCHEMA_VERSION = 1

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path).absolute()
        if str(database_path) == ':memory:':
            raise ValueError('A durable database path is required')
        safe_directory(self.path.parent)
        checked_regular_file(self.path)
        with self.transaction() as connection:
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version > self.SCHEMA_VERSION:
                raise BackendError('SCHEMA_VERSION', 'Database schema is newer than this service', 503)
            if version < 1:
                migration = (Path(__file__).parent / 'migrations' / '001_control_plane.sql').read_text(encoding='utf-8')
                # executescript commits implicitly; execute complete statements ourselves
                # so schema, triggers and user_version commit as one atomic migration.
                statement = ''
                for line in migration.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        connection.execute(statement)
                        statement = ''
                if statement.strip():
                    raise BackendError('SCHEMA_VERSION', 'Incomplete database migration', 503)
                connection.execute('PRAGMA user_version=1')
        self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        # Aliased database names must never create independent WAL namespaces.
        # Sidecars receive the same checks as the database before every connect.
        safe_directory(self.path.parent)
        for path in (self.path, Path(str(self.path) + '-wal'), Path(str(self.path) + '-shm')):
            checked_regular_file(path)
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=10000')
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=FULL')
        return connection

    @contextmanager
    def transaction(self):
        connection = None
        try:
            connection = self._connect()
            connection.execute('BEGIN IMMEDIATE')
            yield connection
            connection.commit()
        except sqlite3.Error as error:
            if connection is not None:
                connection.rollback()
            raise BackendError('STORAGE_UNAVAILABLE', 'Durable state is unavailable', 503) from error
        except BaseException:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def readiness(self) -> bool:
        try:
            with self.transaction() as connection:
                return (connection.execute('PRAGMA user_version').fetchone()[0] == self.SCHEMA_VERSION
                        and connection.execute('PRAGMA quick_check').fetchone()[0] == 'ok')
        except BackendError:
            return False
