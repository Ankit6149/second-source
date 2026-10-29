"""Durable owner-isolated control plane for the existing zero-cost G3 engine.

No provider, credential, engine execution or HTTP dependency belongs here.
Lease expiry deliberately requires reconciliation, never automatic replay.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re
import secrets
import time
import uuid
from pathlib import Path

from second_source.g2_persistence import canonical, scope_digest_of
from .contracts import (
    AuthorizeInvestigation, BackendError, CodeStage, CreateInvestigation,
    CreateRun, EngineResult, Investigation, Lease, LifecycleEvent, Principal, Run,
)
from .store import SQLiteStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value) -> str:
    return canonical(value).decode('utf-8')


def _error(code: str, message: str, status: int = 409):
    raise BackendError(code, message, status)


class BackendService:
    def __init__(self, database_path: str | Path | None = None, *,
                 store=None, max_queued_runs: int = 32):
        if type(max_queued_runs) is not int or not 1 <= max_queued_runs <= 10000:
            raise ValueError('Invalid queue limit')
        if store is None:
            if database_path is None:
                raise ValueError('A durable database path is required')
            self.store = SQLiteStore(database_path)
        else:
            if database_path is not None or not callable(getattr(store, 'transaction', None)) or not callable(getattr(store, 'readiness', None)):
                raise ValueError('An exclusive durable store is required')
            self.store = store
        self.max_queued_runs = max_queued_runs

    def readiness(self) -> bool:
        return self.store.readiness()

    @staticmethod
    def _investigation(row) -> Investigation:
        data = {key: row[key] for key in Investigation.model_fields if key != 'scope'}
        data['scope'] = json.loads(row['scope_json'])
        return Investigation.model_validate(data)

    @staticmethod
    def _run(row) -> Run:
        data = {key: row[key] for key in Run.model_fields if key != 'result'}
        data['result'] = json.loads(row['result_json']) if row['result_json'] else None
        return Run.model_validate(data)

    @staticmethod
    def _owned(connection, principal: Principal, investigation_id: str):
        row = connection.execute('SELECT * FROM investigations WHERE investigation_id=? AND owner_id=?',
                                 (investigation_id, principal.owner_id)).fetchone()
        if row is None:
            _error('NOT_FOUND', 'Resource not found', 404)
        return row

    def _owned_run(self, connection, principal, run_id):
        row = connection.execute('SELECT r.* FROM runs r JOIN investigations i USING(investigation_id) WHERE r.run_id=? AND i.owner_id=?',
                                 (run_id, principal.owner_id)).fetchone()
        if row is None:
            _error('NOT_FOUND', 'Resource not found', 404)
        return row

    @staticmethod
    def _event(connection, investigation_id, run_id, event_type, revision, stage=None):
        connection.execute('INSERT INTO events(investigation_id,run_id,event_type,stage,created_at,revision) VALUES(?,?,?,?,?,?)',
                           (investigation_id, run_id, event_type, stage, _now(), revision))

    @staticmethod
    def _key(key):
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', key):
            _error('INVALID_IDEMPOTENCY_KEY', 'A bounded idempotency key is required', 422)

    @staticmethod
    def _existing(connection, owner, operation, key, body):
        digest = hashlib.sha256(canonical(body)).hexdigest()
        old = connection.execute('SELECT * FROM idempotency WHERE owner_id=? AND operation=? AND key=?',
                                 (owner, operation, key)).fetchone()
        if old and old['request_digest'] != digest:
            _error('IDEMPOTENCY_CONFLICT', 'Idempotency key already binds a different request')
        return (old['resource_id'] if old else None), digest

    @staticmethod
    def _remember(connection, owner, operation, key, digest, resource_id):
        connection.execute('INSERT INTO idempotency VALUES(?,?,?,?,?)', (owner, operation, key, digest, resource_id))

    def create_investigation(self, principal: Principal, request: CreateInvestigation, idempotency_key: str) -> Investigation:
        self._key(idempotency_key)
        with self.store.transaction() as connection:
            old, digest = self._existing(connection, principal.owner_id, 'create_investigation', idempotency_key, request.model_dump(mode='python'))
            if old:
                return self._investigation(self._owned(connection, principal, old))
            identity, now = str(uuid.uuid4()), _now()
            scope_digest = scope_digest_of(request.scope).removeprefix('sha256:')
            connection.execute('INSERT INTO investigations VALUES(?,?,?,?,?,?,?,?,?)',
                               (identity, principal.owner_id, request.title, _json(request.scope.model_dump(mode='python')), scope_digest, 'created', 1, now, now))
            self._remember(connection, principal.owner_id, 'create_investigation', idempotency_key, digest, identity)
            self._event(connection, identity, None, 'investigation_created', 1)
            return self._investigation(self._owned(connection, principal, identity))

    def get_investigation(self, principal: Principal, investigation_id: str) -> Investigation:
        with self.store.transaction() as connection:
            return self._investigation(self._owned(connection, principal, investigation_id))

    @staticmethod
    def _limit(limit, maximum):
        if type(limit) is not int or not 1 <= limit <= maximum:
            _error('INVALID_PAGE', 'Invalid page limit', 422)

    def list_investigations(self, principal: Principal, after=None, limit=50) -> list[Investigation]:
        self._limit(limit, 100)
        with self.store.transaction() as connection:
            return [self._investigation(row) for row in connection.execute('SELECT * FROM investigations WHERE owner_id=? AND investigation_id>? ORDER BY investigation_id LIMIT ?', (principal.owner_id, after or '', limit))]

    def authorize_investigation(self, principal: Principal, investigation_id: str, request: AuthorizeInvestigation) -> Investigation:
        with self.store.transaction() as connection:
            row = self._owned(connection, principal, investigation_id)
            if row['revision'] != request.expected_revision:
                _error('REVISION_CONFLICT', 'Resource revision changed')
            if row['status'] != 'created':
                _error('INVALID_STATE', 'Investigation is already authorized')
            if request.scope_digest != row['scope_digest']:
                _error('SCOPE_MISMATCH', 'Approval does not match the immutable scope')
            connection.execute('INSERT INTO approvals VALUES(?,?,?,?,?)', (investigation_id, principal.owner_id, row['scope_digest'], _json(request.model_dump(mode='python')), _now()))
            connection.execute("UPDATE investigations SET status='authorized',revision=revision+1,updated_at=? WHERE investigation_id=?", (_now(), investigation_id))
            self._event(connection, investigation_id, None, 'investigation_authorized_mock_only', row['revision'] + 1)
            return self._investigation(self._owned(connection, principal, investigation_id))

    def create_run(self, principal: Principal, investigation_id: str, request: CreateRun, idempotency_key: str) -> Run:
        self._key(idempotency_key)
        with self.store.transaction() as connection:
            investigation = self._owned(connection, principal, investigation_id)
            old, digest = self._existing(connection, principal.owner_id, 'create_run', idempotency_key, {'investigation_id': investigation_id, **request.model_dump(mode='python')})
            if old:
                return self._run(self._owned_run(connection, principal, old))
            if investigation['status'] != 'authorized':
                _error('APPROVAL_REQUIRED', 'Mock-only scope approval is required')
            if connection.execute("SELECT COUNT(*) FROM runs WHERE status IN('queued','running')").fetchone()[0] >= self.max_queued_runs:
                _error('QUEUE_FULL', 'The bounded execution queue is full', 429)
            identity, now = str(uuid.uuid4()), _now()
            connection.execute('INSERT INTO runs(run_id,investigation_id,kind,status,revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?)', (identity, investigation_id, request.kind, 'queued', 1, now, now))
            self._remember(connection, principal.owner_id, 'create_run', idempotency_key, digest, identity)
            self._event(connection, investigation_id, identity, 'run_queued', 1)
            return self._run(self._owned_run(connection, principal, identity))

    def get_run(self, principal: Principal, run_id: str) -> Run:
        with self.store.transaction() as connection:
            return self._run(self._owned_run(connection, principal, run_id))

    def list_runs(self, principal: Principal, investigation_id: str, after=None, limit=50) -> list[Run]:
        self._limit(limit, 100)
        with self.store.transaction() as connection:
            self._owned(connection, principal, investigation_id)
            return [self._run(row) for row in connection.execute('SELECT * FROM runs WHERE investigation_id=? AND run_id>? ORDER BY run_id LIMIT ?', (investigation_id, after or '', limit))]

    def events(self, principal: Principal, investigation_id: str, after=0, limit=100) -> list[LifecycleEvent]:
        self._limit(limit, 500)
        if type(after) is not int or after < 0:
            _error('INVALID_PAGE', 'Invalid event cursor', 422)
        with self.store.transaction() as connection:
            self._owned(connection, principal, investigation_id)
            return [LifecycleEvent.model_validate(dict(row)) for row in connection.execute('SELECT * FROM events WHERE investigation_id=? AND event_id>? ORDER BY event_id LIMIT ?', (investigation_id, after, limit))]

    def cancel_run(self, principal: Principal, run_id: str, expected_revision: int) -> Run:
        with self.store.transaction() as connection:
            row = self._owned_run(connection, principal, run_id)
            if row['revision'] != expected_revision:
                _error('REVISION_CONFLICT', 'Resource revision changed')
            if row['status'] not in ('queued', 'running') or row['cancel_requested']:
                _error('INVALID_STATE', 'Run cannot be cancelled in this state')
            status = 'cancelled' if row['status'] == 'queued' else 'running'
            connection.execute('UPDATE runs SET status=?,cancel_requested=1,revision=revision+1,updated_at=? WHERE run_id=?', (status, _now(), run_id))
            self._event(connection, row['investigation_id'], run_id, 'run_cancelled' if status == 'cancelled' else 'run_cancellation_requested', row['revision'] + 1, row['stage'])
            return self._run(self._owned_run(connection, principal, run_id))

    @staticmethod
    def _lease_seconds(seconds):
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 1 <= seconds <= 300:
            _error('INVALID_LEASE', 'Lease duration must be between 1 and 300 seconds', 422)

    @staticmethod
    def _fenced(connection, run_id, token):
        row = connection.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if row is None or row['status'] != 'running' or not isinstance(token, str) or not secrets.compare_digest(row['lease_token'] or '', token) or row['lease_expires'] <= time.time():
            _error('LEASE_LOST', 'Execution lease is no longer valid')
        return row

    def claim(self, worker_id: str, lease_seconds=30) -> Lease | None:
        self._lease_seconds(lease_seconds)
        if not isinstance(worker_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', worker_id):
            _error('INVALID_WORKER', 'Invalid worker identity', 422)
        with self.store.transaction() as connection:
            row = connection.execute("SELECT * FROM runs WHERE status='queued' ORDER BY created_at,run_id LIMIT 1").fetchone()
            if row is None:
                return None
            token, expires = secrets.token_hex(32), time.time() + lease_seconds
            connection.execute("UPDATE runs SET status='running',worker_id=?,lease_token=?,lease_expires=?,revision=revision+1,updated_at=? WHERE run_id=?", (worker_id, token, expires, _now(), row['run_id']))
            self._event(connection, row['investigation_id'], row['run_id'], 'run_claimed', row['revision'] + 1)
            fresh = connection.execute('SELECT * FROM runs WHERE run_id=?', (row['run_id'],)).fetchone()
            scope = connection.execute('SELECT scope_json FROM investigations WHERE investigation_id=?', (row['investigation_id'],)).fetchone()[0]
            return Lease(run=self._run(fresh), scope=json.loads(scope), token=token, worker_id=worker_id, expires_at=expires)

    def heartbeat(self, run_id: str, token: str, lease_seconds=30) -> Run:
        self._lease_seconds(lease_seconds)
        with self.store.transaction() as connection:
            self._fenced(connection, run_id, token)
            connection.execute('UPDATE runs SET lease_expires=? WHERE run_id=?', (time.time() + lease_seconds, run_id))
            return self._run(connection.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone())

    def stage(self, run_id: str, token: str, stage: CodeStage) -> Run:
        stage = CodeStage(stage)
        stages = list(CodeStage)
        with self.store.transaction() as connection:
            row = self._fenced(connection, run_id, token)
            if row['cancel_requested']:
                _error('CANCELLATION_REQUESTED', 'Run cancellation has been requested')
            previous = stages.index(CodeStage(row['stage'])) if row['stage'] else -1
            if stages.index(stage) != previous + 1:
                _error('INVALID_STAGE', 'Run stages must advance once in order')
            connection.execute('UPDATE runs SET stage=?,revision=revision+1,updated_at=? WHERE run_id=?', (stage.value, _now(), run_id))
            self._event(connection, row['investigation_id'], run_id, 'stage_started', row['revision'] + 1, stage.value)
            return self._run(connection.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone())

    def finish(self, run_id: str, token: str, result: EngineResult | None, error_code=None) -> Run:
        if error_code is not None and (not isinstance(error_code, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', error_code)):
            _error('INVALID_ERROR_CODE', 'A safe diagnostic code is required', 422)
        with self.store.transaction() as connection:
            row = self._fenced(connection, run_id, token)
            if result is not None:
                result = EngineResult.model_validate(result)
                if result.usage.estimated_cost_usd != 0 or result.usage.uncertain_cost_usd != 0:
                    _error('MOCK_COST_VIOLATION', 'Mock execution cannot report paid usage')
            status = 'cancelled' if row['cancel_requested'] or error_code == 'CANCELLED' else ('failed' if error_code or result is None else 'completed')
            if status == 'completed' and row['stage'] != CodeStage.EXECUTE.value:
                _error('INCOMPLETE_EXECUTION', 'Successful completion requires the final execution stage')
            connection.execute('UPDATE runs SET status=?,result_json=?,error_code=?,lease_token=NULL,lease_expires=NULL,revision=revision+1,updated_at=? WHERE run_id=?', (status, _json(result.model_dump(mode='python')) if result else None, error_code or ('ENGINE_FAILED' if status == 'failed' else None), _now(), run_id))
            self._event(connection, row['investigation_id'], run_id, 'run_' + status, row['revision'] + 1, row['stage'])
            return self._run(connection.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone())

    def recover_expired(self) -> int:
        with self.store.transaction() as connection:
            rows = connection.execute("SELECT * FROM runs WHERE status='running' AND lease_expires<=?", (time.time(),)).fetchall()
            for row in rows:
                connection.execute("UPDATE runs SET status='needs_reconciliation',error_code='LEASE_EXPIRED',lease_token=NULL,lease_expires=NULL,revision=revision+1,updated_at=? WHERE run_id=?", (_now(), row['run_id']))
                self._event(connection, row['investigation_id'], row['run_id'], 'run_needs_reconciliation', row['revision'] + 1, row['stage'])
            return len(rows)
