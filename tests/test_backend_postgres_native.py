"""Native private PostgreSQL acceptance; never a hosted DSN or live Auth.

Each case starts a fresh socket-only cluster and uses the real non-owner role.
Auth users and evidence records below are explicitly synthetic NON_AI controls.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid

import pytest

from second_source.backend.postgres import PostgresStore, RUNTIME_ROLE
from second_source.backend.contracts import (
    ArtifactReference, AuthorizeInvestigation, BackendError, CodeStage,
    CreateInvestigation, CreateRun, EngineResult, EvaluationSummary, Principal,
)
from second_source.backend.service import BackendService
from second_source.live_experiment import create_scope

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'jpqcqqbzriizxhigvjki'
OWNER = Principal(owner_id='00000000-0000-4000-8000-000000000001')
OTHER = Principal(owner_id='00000000-0000-4000-8000-000000000002')
MIGRATIONS = [ROOT / 'supabase/migrations' / name for name in (
    '20261028193413_initial_second_source_private_schema.sql',
    '20261029_backend_runtime_schema.sql',
    '20261030180237_runtime_private_role_and_bindings.sql')]


def _tools():
    if sys.platform != 'linux':
        pytest.skip('Native private PostgreSQL acceptance runs on Linux')
    candidates = [Path(p).parent for p in [shutil.which('initdb')] if p]
    candidates += sorted(Path('/usr/lib/postgresql').glob('*/bin'), reverse=True)
    for candidate in candidates:
        if all((candidate / tool).is_file() for tool in ('initdb', 'pg_ctl', 'psql')):
            return candidate
    if os.getenv('GITHUB_ACTIONS') == 'true' and os.getenv('RUNNER_OS') == 'Linux':
        pytest.fail('Native PostgreSQL server tools are required in Linux CI')
    pytest.skip('Install local PostgreSQL server tools for native acceptance')


@pytest.fixture
def native(monkeypatch):
    tools = _tools()
    psycopg = pytest.importorskip('psycopg')
    from psycopg.rows import dict_row
    for name in list(os.environ):
        if name.upper().startswith('PG'):
            monkeypatch.delenv(name)
    environment = {'PATH': os.defpath, 'LC_ALL': 'C', 'PGCONNECT_TIMEOUT': '5',
                   'PGPASSFILE': os.devnull}
    with tempfile.TemporaryDirectory(prefix='ss-native-private-') as temporary:
        root = Path(temporary)
        cluster = root / 'db'
        def command(tool, *args):
            result = subprocess.run([str(tools / tool), *map(str, args)],
                env=environment, capture_output=True, text=True, timeout=45)
            assert result.returncode == 0, result.stdout + result.stderr
            return result
        command('initdb', '-D', cluster, '-U', 'postgres', '--no-locale',
                '--encoding=UTF8', '--auth-local=trust', '--auth-host=reject')
        escaped = str(root).replace("'", "''")
        with (cluster / 'postgresql.conf').open('a', encoding='utf-8') as config:
            config.write("\nlisten_addresses=''\nport=5432\nmax_connections=15\n"
                         "shared_buffers='16MB'\n"
                         f"unix_socket_directories='{escaped}'\n")
        def connect(user):
            return psycopg.connect(host=str(root), port=5432, dbname='postgres',
                user=user, passfile=os.devnull, row_factory=dict_row,
                autocommit=False, prepare_threshold=None, connect_timeout=5)
        @contextmanager
        def admin():
            with connect('postgres') as connection:
                yield connection
        class LocalStore(PostgresStore):
            # Substitute only the isolated socket. Production role checks,
            # isolation, transaction handling and fencing run unchanged.
            def _open_connection(self):
                return connect(RUNTIME_ROLE)
        try:
            command('pg_ctl', '-D', cluster, '-l', root / 'postgres.log', '-w', '-t', '20', 'start')
            with admin() as db:
                db.execute('CREATE ROLE anon NOLOGIN')
                db.execute('CREATE ROLE authenticated NOLOGIN')
                db.execute('CREATE ROLE service_role NOLOGIN BYPASSRLS')
                db.execute('CREATE SCHEMA auth')
                db.execute('CREATE TABLE auth.users(id uuid PRIMARY KEY)')
                db.execute('INSERT INTO auth.users VALUES(%s),(%s)', (OWNER.owner_id, OTHER.owner_id))
            psql = ['-X', '--no-password', '--host', root, '--port', '5432',
                    '--username', 'postgres', '--dbname', 'postgres', '--set=ON_ERROR_STOP=1']
            for migration in MIGRATIONS:
                command('psql', *psql, '--file', migration)
            store = LocalStore(f'host=db.{PROJECT}.supabase.co dbname=postgres '
                              f'user={RUNTIME_ROLE} password=NON_SECRET_TEST_ONLY sslmode=verify-full',
                              project_ref=PROJECT)
            yield SimpleNamespace(store=store, service=BackendService(store=store),
                                  admin=admin, fresh=lambda: BackendService(store=store),
                                  psycopg=psycopg, connect=connect)
        finally:
            stopped = subprocess.run([str(tools / 'pg_ctl'), '-D', str(cluster),
                '-m', 'immediate', '-w', '-t', '20', 'stop'], env=environment,
                capture_output=True, text=True, timeout=30)
            if (cluster / 'postmaster.pid').exists():
                pytest.fail('Private native PostgreSQL did not stop: ' + stopped.stderr)


def investigation(service, key='investigation', principal=OWNER):
    item = service.create_investigation(principal,
        CreateInvestigation(title='NON_AI native private acceptance', scope=create_scope(0, 1)), key)
    return service.authorize_investigation(principal, item.investigation_id,
        AuthorizeInvestigation(expected_revision=item.revision, scope_digest=item.scope_digest))


def queued(service, item, key='run', principal=OWNER):
    return service.create_run(principal, item.investigation_id, CreateRun(), key)


def failure(code, function, *args, **kwargs):
    with pytest.raises(BackendError) as caught:
        function(*args, **kwargs)
    assert caught.value.code == code


def test_native_owner_scoped_restart_lifecycle_and_database_clock(native, monkeypatch):
    service = native.service
    assert service.readiness()
    import second_source.backend.service as module
    class NoHostTimestamp:
        @staticmethod
        def now(*args, **kwargs):
            pytest.fail('PostgreSQL lifecycle timestamps used the host clock')
    monkeypatch.setattr(module, 'datetime', NoHostTimestamp)
    item = investigation(service)
    assert service.create_investigation(OWNER, CreateInvestigation(title=item.title, scope=item.scope), 'investigation') == item
    failure('IDEMPOTENCY_CONFLICT', service.create_investigation, OWNER,
            CreateInvestigation(title='changed', scope=item.scope), 'investigation')
    failure('NOT_FOUND', service.get_investigation, OTHER, item.investigation_id)
    run = queued(service, item)
    assert queued(service, item) == run
    monkeypatch.setattr(module.time, 'time', lambda: 1.0)
    lease = service.claim('native', run_id=run.run_id)
    assert lease.run.run_id == run.run_id and lease.expires_at > 1_000_000
    service.heartbeat(run.run_id, lease.token)
    for stage in CodeStage:
        service.stage(run.run_id, lease.token, stage)
    result = EngineResult(stop_reason='completed_mock_run',
        evaluation=EvaluationSummary(passed=0, failed=0, indeterminate=0, total=0))
    completed = service.finish(run.run_id, lease.token, result)
    assert completed.status == 'completed'
    assert native.fresh().get_run(OWNER, run.run_id) == completed
    failure('NOT_FOUND', service.get_run, OTHER, run.run_id)
    failure('LEASE_LOST', service.heartbeat, run.run_id, lease.token)
    assert service.events(OWNER, item.investigation_id)[-1].event_type == 'run_completed'


def test_native_competing_exact_claims_and_unrelated_queue(native):
    service = native.service
    item = investigation(service)
    unrelated = queued(service, item, 'unrelated')
    target = queued(service, item, 'target')
    barrier = threading.Barrier(6)
    def compete(index):
        barrier.wait(10)
        try:
            return service.claim('worker_' + str(index), run_id=target.run_id)
        except BackendError as error:
            assert error.code == 'STORAGE_UNAVAILABLE'
            return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        leases = list(pool.map(compete, range(6)))
    lease, = [lease for lease in leases if lease is not None]
    assert lease.run.run_id == target.run_id
    assert service.get_run(OWNER, unrelated.run_id).status == 'queued'
    assert len([event for event in service.events(OWNER, item.investigation_id)
                if event.run_id == target.run_id and event.event_type == 'run_claimed']) == 1
    assert service.claim('replay', run_id=target.run_id) is None


def test_native_cancellation_expired_recovery_and_stale_fences(native):
    service = native.service
    item = investigation(service)
    cancelled = queued(service, item, 'cancel-before-claim')
    assert service.cancel_run(OWNER, cancelled.run_id, cancelled.revision).status == 'cancelled'
    assert service.claim('cancelled', run_id=cancelled.run_id) is None
    first, second = [queued(service, item, key) for key in ('expired-first', 'expired-second')]
    leases = [service.claim('worker', run_id=run.run_id) for run in (first, second)]
    requested = service.cancel_run(OWNER, first.run_id, leases[0].run.revision)
    assert requested.cancel_requested
    failure('CANCELLATION_REQUESTED', service.stage, first.run_id, leases[0].token, CodeStage.CAPTURE)
    with native.admin() as db:
        db.execute('UPDATE ss_runtime.runs SET lease_expires=EXTRACT(EPOCH FROM clock_timestamp())-1 WHERE run_id IN (%s,%s)',
                   (first.run_id, second.run_id))
    assert service.recover_expired(run_id=first.run_id) == 1
    assert service.get_run(OWNER, second.run_id).status == 'running'
    assert native.fresh().get_run(OWNER, first.run_id).status == 'needs_reconciliation'
    assert service.recover_expired(run_id=first.run_id) == 0
    for operation, extra in ((service.heartbeat, ()), (service.stage, (CodeStage.CAPTURE,)),
                             (service.finish, (None,)),
                             (service.repair_progress, ('repair_started',))):
        failure('LEASE_LOST', operation, first.run_id, leases[0].token, *extra)
    assert service.claim('replacement', run_id=first.run_id) is None
    assert service.recover_expired() == 1


def test_native_atomic_expiry_and_event_rollback(native):
    service = native.service
    item = investigation(service)
    run = queued(service, item)
    lease = service.claim('worker')
    # Change DB expiry after initial validation but before mutation. The SQL
    # fence must reject and roll back even that intervening synthetic change.
    with pytest.raises(BackendError) as expired:
        with native.store.transaction() as db:
            service._fenced(db, run.run_id, lease.token)
            db.raw.execute('UPDATE runs SET lease_expires=EXTRACT(EPOCH FROM clock_timestamp())-1 WHERE run_id=%s', (run.run_id,))
            db.execute('UPDATE runs SET stage=?,revision=revision+1,updated_at=? WHERE run_id=?',
                       ('capture', 'NON_AI', run.run_id))
    assert expired.value.code == 'LEASE_LOST'
    assert service.get_run(OWNER, run.run_id) == lease.run
    class FailingStore:
        def readiness(self): return True
        @contextmanager
        def transaction(self):
            with native.store.transaction() as db:
                class Connection:
                    def __getattr__(self, name): return getattr(db, name)
                    def execute(self, sql, parameters=()):
                        if sql.startswith('INSERT INTO events'):
                            raise BackendError('SYNTHETIC_EVENT_FAILURE', 'NON_AI rollback control')
                        return db.execute(sql, parameters)
                yield Connection()
    failing = BackendService(store=FailingStore())
    failure('SYNTHETIC_EVENT_FAILURE', failing.stage, run.run_id, lease.token, CodeStage.CAPTURE)
    assert native.fresh().get_run(OWNER, run.run_id) == lease.run
    assert service.events(OWNER, item.investigation_id)[-1].event_type == 'run_claimed'
    service.stage(run.run_id, lease.token, CodeStage.CAPTURE)
    failure('INVALID_STAGE', service.stage, run.run_id, lease.token, CodeStage.CAPTURE)
    uncertain = service.finish(run.run_id, lease.token, None, error_code='ARTIFACT_PUBLICATION_UNCERTAIN')
    assert uncertain.status == 'needs_reconciliation' and uncertain.error_code == 'ARTIFACT_PUBLICATION_UNCERTAIN'
    assert service.claim('replay', run_id=run.run_id) is None


def seed_evidence(native, owner, scope, *, investigation_id=None):
    investigation_id = investigation_id or str(uuid.uuid4())
    run_id, artifact_id = str(uuid.uuid4()), str(uuid.uuid4())
    with native.admin() as db:
        if db.execute('SELECT 1 FROM ss.investigations WHERE id=%s', (investigation_id,)).fetchone() is None:
            target = str(uuid.uuid4())
            db.execute("INSERT INTO ss.targets(id,owner_id,display_name,target_kind,permission_basis) VALUES(%s,%s,'NON_AI','cli','Synthetic schema test')", (target, owner.owner_id))
            db.execute("INSERT INTO ss.investigations(id,owner_id,target_id,title,goal) VALUES(%s,%s,%s,'NON_AI','Synthetic binding control')", (investigation_id, owner.owner_id, target))
        db.execute("INSERT INTO ss.runs(id,owner_id,investigation_id,origin,scope_sha256,idempotency_key) VALUES(%s,%s,%s,'mock',%s,%s)",
                   (run_id, owner.owner_id, investigation_id, scope, 'NON_AI_' + run_id))
        db.execute("INSERT INTO ss.artifacts(id,owner_id,run_id,category,object_key,content_sha256,size_bytes) VALUES(%s,%s,%s,'evidence',%s,%s,1)",
                   (artifact_id, owner.owner_id, run_id, 'NON_AI/' + artifact_id, 'a' * 64))
    return investigation_id, run_id, artifact_id


def test_native_explicit_immutable_evidence_bindings_and_private_refs(native):
    service, store = native.service, native.store
    item = investigation(service)
    run = queued(service, item)
    matching = seed_evidence(native, OWNER, item.scope_digest)
    other = seed_evidence(native, OTHER, item.scope_digest)
    assert store.evidence_bindings(OWNER, item.investigation_id)['evidence_investigation_id'] is None
    failure('INVALID_EVIDENCE_BINDING', store.bind_investigation, OWNER, item.investigation_id, other[0])
    store.bind_investigation(OWNER, item.investigation_id, matching[0])
    store.bind_investigation(OWNER, item.investigation_id, matching[0])
    wrong_scope = seed_evidence(native, OWNER, 'b' * 64, investigation_id=matching[0])
    failure('INVALID_EVIDENCE_BINDING', store.bind_run, OWNER, run.run_id, wrong_scope[1])
    failure('INVALID_EVIDENCE_BINDING', store.bind_run, OWNER, run.run_id, other[1])
    store.bind_run(OWNER, run.run_id, matching[1])
    store.bind_run(OWNER, run.run_id, matching[1])
    another = seed_evidence(native, OWNER, item.scope_digest, investigation_id=matching[0])
    failure('BINDING_CONFLICT', store.bind_run, OWNER, run.run_id, another[1])
    failure('INVALID_EVIDENCE_BINDING', store.bind_artifact, OWNER, run.run_id, other[2])
    store.bind_artifact(OWNER, run.run_id, matching[2])
    store.bind_artifact(OWNER, run.run_id, matching[2])
    bindings = store.evidence_bindings(OWNER, item.investigation_id)
    assert bindings['runs'] == [{'run_id': run.run_id, 'evidence_run_id': matching[1]}]
    assert bindings['artifacts'] == [{'run_id': run.run_id, 'evidence_artifact_id': matching[2]}]
    failure('NOT_FOUND', store.evidence_bindings, OTHER, item.investigation_id)
    failure('NOT_FOUND', store.bind_run, OTHER, run.run_id, matching[1])
    ref = ArtifactReference(artifact_id='private:candidate.r1.json', sha256='a' * 64, size_bytes=17, media_type='application/json')
    lease = service.claim('artifact_worker', run_id=run.run_id)
    store.record_artifact_ref(OWNER, run.run_id, ref, lease_token=lease.token)
    store.record_artifact_ref(OWNER, run.run_id, ref, lease_token=lease.token)
    failure('BINDING_CONFLICT', store.record_artifact_ref, OWNER, run.run_id,
            ref.model_copy(update={'sha256': 'b' * 64}), lease_token=lease.token)
    assert store.artifact_refs(OWNER, run.run_id) == [ref]
    restarted_store = type(store)(f'host=db.{PROJECT}.supabase.co dbname=postgres '
                                  f'user={RUNTIME_ROLE} password=NON_SECRET_TEST_ONLY sslmode=verify-full',
                                  project_ref=PROJECT)
    assert restarted_store.artifact_refs(OWNER, run.run_id) == [ref]
    failure('NOT_FOUND', restarted_store.artifact_refs, OTHER, run.run_id)
    failure('NOT_FOUND', store.artifact_refs, OTHER, run.run_id)
    failure('NOT_FOUND', store.record_artifact_ref, OTHER, run.run_id, ref, lease_token=lease.token)
    failure('LEASE_LOST', store.record_artifact_ref, OWNER, run.run_id, ref, lease_token='incorrect')
    service.finish(run.run_id, lease.token, None, error_code='ARTIFACT_PUBLICATION_UNCERTAIN')
    failure('LEASE_LOST', store.record_artifact_ref, OWNER, run.run_id,
            ref.model_copy(update={'artifact_id': 'stale_private_ref'}), lease_token=lease.token)
    assert store.artifact_refs(OWNER, run.run_id) == [ref]
    # Composite FK checks do not grant access to sealed evidence or Auth.
    for sql in ('SELECT * FROM ss.runs', 'SELECT * FROM auth.users',
                'UPDATE events SET revision=3', 'DELETE FROM investigations',
                'TRUNCATE runs', 'CREATE TABLE ss_runtime.forbidden(id integer)',
                "UPDATE investigations SET owner_id='changed'"):
        with pytest.raises(BackendError):
            with store.transaction() as db:
                db.execute(sql)
    with native.admin() as db:
        assert db.execute('SELECT count(*) AS n FROM ss.runs').fetchone()['n'] == 4
        assert db.execute("SELECT count(*) AS n FROM pg_policy WHERE polrelid IN (SELECT oid FROM pg_class WHERE relnamespace='ss'::regnamespace)").fetchone()['n'] == 0
    failure('STORAGE_UNAVAILABLE', service.create_investigation, Principal(owner_id='local_label'),
            CreateInvestigation(title='Must fail in PG', scope=item.scope), 'local-label')
    failure('STORAGE_UNAVAILABLE', service.create_investigation,
            Principal(owner_id='00000000-0000-4000-8000-000000000099'),
            CreateInvestigation(title='Absent Auth user', scope=item.scope), 'absent-user')


def test_native_role_drift_fails_closed(native):
    assert native.service.readiness()
    with native.admin() as db:
        db.execute('ALTER ROLE second_source_backend BYPASSRLS')
    assert native.service.readiness() is False
    failure('STORAGE_ROLE', native.service.list_investigations, OWNER)


def test_synthetic_socket_only_dump_restores_data_and_privileges(native):
    """A disposable synthetic drill, not a backup or restore of hosted Supabase.

    The archive includes only the fixture's synthetic auth, ss, and ss_runtime
    schemas. Roles are recreated from known test definitions in a second private
    cluster; Storage object bytes, platform configuration, role credentials,
    provider backups and a live-project restore are intentionally not covered.
    """
    tools = _tools()
    from psycopg.rows import dict_row
    for name in ('pg_dump', 'pg_restore'):
        if not (tools / name).is_file():
            if os.getenv('GITHUB_ACTIONS') == 'true' and os.getenv('RUNNER_OS') == 'Linux':
                pytest.fail(f'{name} is required for the synthetic restore drill in Linux CI')
            pytest.skip(f'{name} is required for the synthetic restore drill')

    service, store = native.service, native.store
    item = investigation(service, key='synthetic-restore-owner')
    run = queued(service, item, key='synthetic-restore-run')
    evidence = seed_evidence(native, OWNER, item.scope_digest)
    store.bind_investigation(OWNER, item.investigation_id, evidence[0])
    store.bind_run(OWNER, run.run_id, evidence[1])
    store.bind_artifact(OWNER, run.run_id, evidence[2])
    lease = service.claim('synthetic_restore_worker', run_id=run.run_id)
    ref = ArtifactReference(artifact_id='private:candidate.r1.json', sha256='a' * 64,
                            size_bytes=17, media_type='application/json')
    store.record_artifact_ref(OWNER, run.run_id, ref, lease_token=lease.token)
    stopped_run = service.finish(run.run_id, lease.token, None,
                                 error_code='ARTIFACT_PUBLICATION_UNCERTAIN')
    other_item = investigation(service, key='synthetic-restore-other', principal=OTHER)
    other_run = queued(service, other_item, key='synthetic-restore-other-run', principal=OTHER)
    cancelled = service.cancel_run(OTHER, other_run.run_id, other_run.revision)
    original_events = service.events(OWNER, item.investigation_id)
    original_bindings = store.evidence_bindings(OWNER, item.investigation_id)

    # Reject any source other than the socket directory made by this module's
    # native fixture: the dump command must never receive a hostname or live DSN.
    with native.admin() as db:
        source_socket = Path(db.info.host).resolve(strict=True)
        source_port = db.info.port
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    assert source_socket.parent == temp_root
    assert source_socket.name.startswith('ss-native-private-')
    assert source_port == 5432

    environment = {'PATH': os.defpath, 'LC_ALL': 'C', 'PGCONNECT_TIMEOUT': '5',
                   'PGPASSFILE': os.devnull}
    with tempfile.TemporaryDirectory(prefix='ss-restore-private-') as temporary:
        root = Path(temporary).resolve(strict=True)
        assert root.parent == temp_root and root.name.startswith('ss-restore-private-')
        archive, cluster = root / 'synthetic.dump', root / 'db'
        def command(name, *args):
            result = subprocess.run([str(tools / name), *map(str, args)],
                env=environment, capture_output=True, text=True, timeout=60)
            assert result.returncode == 0, result.stdout + result.stderr
            return result
        command('pg_dump', '--format=custom', '--no-password', '--host', source_socket,
                '--port', source_port, '--username', 'postgres', '--dbname', 'postgres',
                '--schema=auth', '--schema=ss', '--schema=ss_runtime', '--file', archive)
        assert archive.is_file() and archive.stat().st_size > 0
        command('initdb', '-D', cluster, '-U', 'postgres', '--no-locale',
                '--encoding=UTF8', '--auth-local=trust', '--auth-host=reject')
        escaped = str(root).replace("'", "''")
        with (cluster / 'postgresql.conf').open('a', encoding='utf-8') as config:
            config.write("\nlisten_addresses=''\nport=5432\nmax_connections=15\n"
                         "shared_buffers='16MB'\n"
                         f"unix_socket_directories='{escaped}'\n")
        try:
            command('pg_ctl', '-D', cluster, '-l', root / 'postgres.log', '-w', '-t', '20', 'start')
            def connect(user):
                return native.psycopg.connect(host=str(root), port=5432, dbname='postgres',
                    user=user, passfile=os.devnull, row_factory=dict_row,
                    autocommit=False, prepare_threshold=None, connect_timeout=5)
            with connect('postgres') as db:
                db.execute('CREATE ROLE anon NOLOGIN')
                db.execute('CREATE ROLE authenticated NOLOGIN')
                db.execute('CREATE ROLE service_role NOLOGIN BYPASSRLS')
                db.execute('CREATE ROLE second_source_backend LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD NULL')
            command('pg_restore', '--exit-on-error', '--no-password', '--host', root,
                    '--port', '5432', '--username', 'postgres', '--dbname', 'postgres', archive)

            class RestoredStore(PostgresStore):
                def _open_connection(self):
                    return connect(RUNTIME_ROLE)
            restored = RestoredStore(f'host=db.{PROJECT}.supabase.co dbname=postgres '
                                     f'user={RUNTIME_ROLE} password=NON_SECRET_TEST_ONLY sslmode=verify-full',
                                     project_ref=PROJECT)
            restored_service = BackendService(store=restored)
            assert restored_service.readiness()
            assert restored_service.get_investigation(OWNER, item.investigation_id) == item
            assert restored_service.get_run(OWNER, run.run_id) == stopped_run
            assert restored_service.get_run(OTHER, other_run.run_id) == cancelled
            assert restored_service.events(OWNER, item.investigation_id) == original_events
            assert restored.evidence_bindings(OWNER, item.investigation_id) == original_bindings
            assert restored.artifact_refs(OWNER, run.run_id) == [ref]
            failure('NOT_FOUND', restored_service.get_run, OTHER, run.run_id)
            assert restored_service.claim('no_blind_replay', run_id=run.run_id) is None
            new_run = queued(restored_service, item, key='synthetic-post-restore')
            assert new_run.status == 'queued'
            for sql in ('SELECT * FROM ss.runs', 'SELECT * FROM auth.users',
                        'DELETE FROM investigations', 'CREATE TABLE ss_runtime.forbidden(id integer)'):
                with pytest.raises(BackendError):
                    with restored.transaction() as db:
                        db.execute(sql)
            with connect('postgres') as db:
                assert db.execute('SELECT count(*) AS n FROM ss.runs').fetchone()['n'] == 1
                rls = db.execute("SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('ss','ss_runtime') AND c.relkind='r' AND NOT c.relrowsecurity").fetchone()['n']
                assert rls == 0
                policies = db.execute("SELECT count(*) AS n FROM pg_policies WHERE schemaname='ss_runtime' AND roles=ARRAY['second_source_backend'::name]").fetchone()['n']
                assert policies > 0
                for role in ('anon', 'authenticated', 'service_role'):
                    assert not db.execute("SELECT has_schema_privilege(%s,'ss_runtime','USAGE') AS allowed", (role,)).fetchone()['allowed']
        finally:
            stopped = subprocess.run([str(tools / 'pg_ctl'), '-D', str(cluster),
                '-m', 'immediate', '-w', '-t', '20', 'stop'], env=environment,
                capture_output=True, text=True, timeout=30)
            if (cluster / 'postmaster.pid').exists():
                pytest.fail('Synthetic restore PostgreSQL did not stop: ' + stopped.stderr)
