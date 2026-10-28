"""Durable NON_AI control-plane acceptance: no model transport or credentials."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from second_source.backend import service as service_module
from second_source.backend.contracts import (
    AuthorizeInvestigation, BackendError, CodeStage, CreateInvestigation, CreateRun,
    EngineResult, Principal, UsageSummary,
)
from second_source.backend.service import BackendService
from second_source.live_experiment import create_scope


OWNER = Principal(owner_id='owner')
OTHER = Principal(owner_id='other')


def new_service(tmp_path, **kwargs):
    return BackendService(tmp_path / 'backend.sqlite', **kwargs)


def investigation(service, key='investigation'):
    return service.create_investigation(OWNER, CreateInvestigation(title='NON_AI acceptance', scope=create_scope(0, 1)), key)


def authorized(service, key='investigation'):
    item = investigation(service, key)
    return service.authorize_investigation(OWNER, item.investigation_id, AuthorizeInvestigation(expected_revision=item.revision, scope_digest=item.scope_digest))


def run(service, investigation_id, key='run'):
    return service.create_run(OWNER, investigation_id, CreateRun(), key)


def assert_error(code, function, *args, **kwargs):
    with pytest.raises(BackendError) as exc:
        function(*args, **kwargs)
    assert exc.value.code == code
    return exc.value


def test_restart_preserves_scope_approval_events_and_completed_result(tmp_path):
    service = new_service(tmp_path)
    item = authorized(service)
    queued = run(service, item.investigation_id)
    lease = service.claim('worker')
    assert lease.run.run_id == queued.run_id
    assert lease.scope == item.scope
    for stage in CodeStage:
        service.stage(queued.run_id, lease.token, stage)
    completed = service.finish(queued.run_id, lease.token, EngineResult(stop_reason='NON_AI_COMPLETE'))
    assert completed.status == 'completed' and not completed.result.real
    restarted = new_service(tmp_path)
    assert restarted.get_run(OWNER, queued.run_id) == completed
    assert restarted.get_investigation(OWNER, item.investigation_id) == item
    events = restarted.events(OWNER, item.investigation_id)
    assert [e.event_type for e in events] == ['investigation_created', 'investigation_authorized_mock_only', 'run_queued', 'run_claimed', *(['stage_started'] * 4), 'run_completed']
    assert len({e.event_id for e in events}) == len(events)
    assert restarted.readiness()
    with restarted.store.transaction() as connection:
        assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert connection.execute('PRAGMA synchronous').fetchone()[0] == 2
        assert connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 1
        receipt = json.loads(connection.execute('SELECT receipt_json FROM approvals').fetchone()[0])
        assert receipt['maximum_model_spend_usd'] == 0 and receipt['mode'] == 'mock'


def test_database_and_wal_aliases_are_rejected_before_connect(tmp_path):
    service = new_service(tmp_path)
    item = investigation(service)
    alias = tmp_path / 'alias.sqlite'
    os.link(service.store.path, alias)
    assert_error('UNSAFE_STORAGE', BackendService, alias)
    assert_error('UNSAFE_STORAGE', service.get_investigation, OWNER, item.investigation_id)
    alias.unlink()
    # An attacker cannot redirect a WAL to another locally readable file either.
    elsewhere = tmp_path / 'private-file'
    elsewhere.write_bytes(b'PRIVATE_SENTINEL')
    os.link(elsewhere, Path(str(service.store.path) + '-wal'))
    assert_error('UNSAFE_STORAGE', service.get_investigation, OWNER, item.investigation_id)
    assert elsewhere.read_bytes() == b'PRIVATE_SENTINEL'


def test_owner_isolation_for_all_reads_and_writes(tmp_path):
    service = new_service(tmp_path)
    item = authorized(service)
    queued = run(service, item.investigation_id)
    assert service.list_investigations(OTHER) == []
    for function, args in [
        (service.get_investigation, (OTHER, item.investigation_id)),
        (service.get_run, (OTHER, queued.run_id)),
        (service.list_runs, (OTHER, item.investigation_id)),
        (service.events, (OTHER, item.investigation_id)),
        (service.create_run, (OTHER, item.investigation_id, CreateRun(), 'other')),
        (service.cancel_run, (OTHER, queued.run_id, 1)),
        (service.authorize_investigation, (OTHER, item.investigation_id, AuthorizeInvestigation(expected_revision=2, scope_digest=item.scope_digest))),
    ]:
        assert assert_error('NOT_FOUND', function, *args).status_code == 404


def test_concurrent_idempotency_and_request_conflict(tmp_path):
    service = new_service(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(lambda _: investigation(service), range(12)))
    assert len({i.investigation_id for i in items}) == 1
    assert len(service.events(OWNER, items[0].investigation_id)) == 1
    assert_error('IDEMPOTENCY_CONFLICT', service.create_investigation, OWNER, CreateInvestigation(title='different', scope=create_scope(0, 1)), 'investigation')
    item = service.authorize_investigation(OWNER, items[0].investigation_id, AuthorizeInvestigation(expected_revision=1, scope_digest=items[0].scope_digest))
    with ThreadPoolExecutor(max_workers=8) as pool:
        runs = list(pool.map(lambda _: run(service, item.investigation_id), range(12)))
    assert len({r.run_id for r in runs}) == 1
    assert len(service.list_runs(OWNER, item.investigation_id)) == 1


def test_atomic_rollback_when_event_write_fails(tmp_path, monkeypatch):
    service = new_service(tmp_path)
    def fail(*args, **kwargs):
        raise RuntimeError('injected interruption')
    monkeypatch.setattr(service, '_event', fail)
    with pytest.raises(RuntimeError):
        investigation(service)
    assert service.list_investigations(OWNER) == []
    monkeypatch.undo()
    assert investigation(service).revision == 1


def test_scope_approval_revision_and_queue_limits(tmp_path):
    service = new_service(tmp_path, max_queued_runs=1)
    item = investigation(service)
    assert_error('APPROVAL_REQUIRED', run, service, item.investigation_id)
    assert_error('SCOPE_MISMATCH', service.authorize_investigation, OWNER, item.investigation_id, AuthorizeInvestigation(expected_revision=1, scope_digest='0' * 64))
    approved = service.authorize_investigation(OWNER, item.investigation_id, AuthorizeInvestigation(expected_revision=1, scope_digest=item.scope_digest))
    assert_error('REVISION_CONFLICT', service.authorize_investigation, OWNER, item.investigation_id, AuthorizeInvestigation(expected_revision=1, scope_digest=item.scope_digest))
    queued = run(service, approved.investigation_id)
    service.claim('worker')
    assert_error('QUEUE_FULL', run, service, approved.investigation_id, 'second')
    # Replaying the same operation succeeds even when capacity is exhausted.
    assert run(service, approved.investigation_id).run_id == queued.run_id


def test_concurrent_exclusive_claim_and_fencing(tmp_path):
    service = new_service(tmp_path)
    queued = run(service, authorized(service).investigation_id)
    with ThreadPoolExecutor(max_workers=8) as pool:
        leases = list(pool.map(lambda i: service.claim('worker_' + str(i)), range(8)))
    lease, = [lease for lease in leases if lease is not None]
    assert lease.run.run_id == queued.run_id
    for function, args in [
        (service.heartbeat, (queued.run_id, 'wrong')),
        (service.stage, (queued.run_id, 'wrong', CodeStage.CAPTURE)),
        (service.finish, (queued.run_id, 'wrong', EngineResult(stop_reason='mock'))),
    ]:
        assert_error('LEASE_LOST', function, *args)
    assert service.heartbeat(queued.run_id, lease.token).status == 'running'
    service.finish(queued.run_id, lease.token, None, error_code='ENGINE_FAILED')
    assert_error('LEASE_LOST', service.finish, queued.run_id, lease.token, None)


def test_stale_lease_restart_requires_reconciliation_no_replay(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(service_module.time, 'time', lambda: clock[0])
    service = new_service(tmp_path)
    queued = run(service, authorized(service).investigation_id)
    lease = service.claim('worker', lease_seconds=1)
    clock[0] += 2
    assert_error('LEASE_LOST', service.heartbeat, queued.run_id, lease.token)
    restarted = new_service(tmp_path)
    assert restarted.recover_expired() == 1
    assert restarted.recover_expired() == 0
    result = restarted.get_run(OWNER, queued.run_id)
    assert result.status == 'needs_reconciliation' and result.error_code == 'LEASE_EXPIRED'
    assert restarted.claim('replacement') is None
    assert_error('LEASE_LOST', restarted.finish, queued.run_id, lease.token, EngineResult(stop_reason='late'))


def test_cancel_queued_and_running_and_revisions(tmp_path):
    service = new_service(tmp_path)
    item = authorized(service)
    queued = run(service, item.investigation_id)
    assert_error('REVISION_CONFLICT', service.cancel_run, OWNER, queued.run_id, 99)
    assert service.cancel_run(OWNER, queued.run_id, 1).status == 'cancelled'
    assert service.claim('worker') is None
    second = run(service, item.investigation_id, 'second')
    lease = service.claim('worker')
    cancellation = service.cancel_run(OWNER, second.run_id, lease.run.revision)
    assert cancellation.status == 'running' and cancellation.cancel_requested
    assert_error('CANCELLATION_REQUESTED', service.stage, second.run_id, lease.token, CodeStage.CAPTURE)
    assert service.heartbeat(second.run_id, lease.token).cancel_requested
    assert service.finish(second.run_id, lease.token, None).status == 'cancelled'


def test_immutable_scope_approval_and_events(tmp_path):
    service = new_service(tmp_path)
    item = authorized(service)
    for sql in ["UPDATE investigations SET scope_digest='fake'", 'DELETE FROM approvals', "UPDATE approvals SET owner_id='other'", 'DELETE FROM events', "UPDATE events SET event_type='fake'", 'DELETE FROM idempotency']:
        assert_error('STORAGE_UNAVAILABLE', lambda: execute(service, sql))
    assert service.get_investigation(OWNER, item.investigation_id) == item
    assert len(service.events(OWNER, item.investigation_id)) == 2


def execute(service, sql):
    with service.store.transaction() as connection:
        connection.execute(sql)


def test_stage_order_safe_error_and_mock_cost_guards(tmp_path):
    service = new_service(tmp_path)
    queued = run(service, authorized(service).investigation_id)
    lease = service.claim('worker')
    assert_error('INCOMPLETE_EXECUTION', service.finish, queued.run_id, lease.token, EngineResult(stop_reason='mock'))
    assert_error('INVALID_STAGE', service.stage, queued.run_id, lease.token, CodeStage.DISTILL)
    service.stage(queued.run_id, lease.token, CodeStage.CAPTURE)
    assert_error('INVALID_STAGE', service.stage, queued.run_id, lease.token, CodeStage.CAPTURE)
    assert_error('INVALID_ERROR_CODE', service.finish, queued.run_id, lease.token, None, error_code='secret transport response')
    assert_error('MOCK_COST_VIOLATION', service.finish, queued.run_id, lease.token, EngineResult(stop_reason='mock', usage=UsageSummary(estimated_cost_usd=.1)))
    assert service.get_run(OWNER, queued.run_id).status == 'running'


def test_worker_shutdown_cancellation_is_terminal_without_user_request(tmp_path):
    service = new_service(tmp_path)
    queued = run(service, authorized(service).investigation_id)
    lease = service.claim('worker')
    assert service.finish(queued.run_id, lease.token, None, error_code='CANCELLED').status == 'cancelled'


def test_unknown_schema_version_rejected(tmp_path):
    service = new_service(tmp_path)
    with service.store.transaction() as connection:
        connection.execute('PRAGMA user_version=999')
    assert not service.readiness()
    assert_error('SCHEMA_VERSION', new_service, tmp_path)


def test_real_process_death_rolls_back_state_and_event_together(tmp_path):
    service = new_service(tmp_path)
    item = investigation(service)
    child = """
import os, sys
from second_source.backend.store import SQLiteStore
store = SQLiteStore(sys.argv[1])
with store.transaction() as connection:
    connection.execute("UPDATE investigations SET title='uncommitted',revision=2 WHERE investigation_id=?", (sys.argv[2],))
    connection.execute("INSERT INTO events(investigation_id,event_type,created_at,revision) VALUES(?,'uncommitted','unused',2)", (sys.argv[2],))
    os._exit(17)
"""
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH'}}
    env.update(PYTHONPATH=str(Path(service_module.__file__).resolve().parents[2]), PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-c', child, str(service.store.path), item.investigation_id], env=env, capture_output=True, timeout=30)
    assert result.returncode == 17, result.stderr.decode(errors='replace')
    restarted = new_service(tmp_path)
    assert restarted.get_investigation(OWNER, item.investigation_id) == item
    assert [e.event_type for e in restarted.events(OWNER, item.investigation_id)] == ['investigation_created']
