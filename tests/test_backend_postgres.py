"""No-network PostgreSQL control-plane adapter tests."""
import pytest
from second_source.backend.postgres import PostgresStore, RUNTIME_ROLE, _Connection, _Row, _translate
from second_source.backend.contracts import AuthorizeInvestigation, BackendError, CreateInvestigation, CreateRun, Principal
from second_source.backend.service import BackendService

PROJECT = "jpqcqqbzriizxhigvjki"
DSN = ("postgresql://second_source_backend." + PROJECT + ":fake@aws-0-ap-south-1.pooler.supabase.com:6543/"
       "postgres?sslmode=verify-full")


def test_tenant_and_tls_policy():
    try:
        adapter = PostgresStore(DSN, project_ref=PROJECT)
    except ValueError as error:
        if "Invalid Postgres configuration" in str(error):
            pytest.skip("Optional psycopg driver is not installed")
        raise
    assert adapter.SCHEMA_VERSION == 2
    with pytest.raises(ValueError):
        PostgresStore(DSN.replace("sslmode=verify-full", "sslmode=disable"), project_ref=PROJECT)
    with pytest.raises(ValueError):
        PostgresStore(DSN, project_ref="aaaaaaaaaaaaaaaaaaaa")
    with pytest.raises(ValueError):
        PostgresStore(DSN + "&hostaddr=203.0.113.1", project_ref=PROJECT)
    with pytest.raises(ValueError):
        PostgresStore(DSN.replace("verify-full", "require"), project_ref=PROJECT)
    with pytest.raises(ValueError):
        PostgresStore(DSN.replace('second_source_backend.', 'postgres.'), project_ref=PROJECT)
    with pytest.raises(ValueError):
        PostgresStore(DSN.replace(':fake@', '@'), project_ref=PROJECT)


@pytest.mark.parametrize('option', ['service=other', 'options=-csearch_path=public',
                                  'passfile=private', 'sslkey=private', 'target_session_attrs=any'])
def test_implicit_routing_and_credential_files_are_rejected(option):
    pytest.importorskip('psycopg')
    with pytest.raises(ValueError):
        PostgresStore(DSN + '&' + option, project_ref=PROJECT)


def test_environment_override_rejected_before_connection_or_reading_values(monkeypatch):
    psycopg = pytest.importorskip('psycopg')
    store = PostgresStore(DSN, project_ref=PROJECT)
    monkeypatch.setenv('PGHOSTADDR', '192.0.2.1')
    monkeypatch.setattr(psycopg, 'connect', lambda *a, **k: pytest.fail('Implicit options reached connection'))
    with pytest.raises(BackendError) as error:
        store._open_connection()
    assert error.value.code == 'STORAGE_CONFIGURATION'


def test_query_translation_uses_bound_parameters_and_locks_claims():
    assert _translate("SELECT * FROM runs WHERE status='queued' ORDER BY created_at,run_id LIMIT 1").endswith(
        "FOR UPDATE SKIP LOCKED")
    assert _translate("SELECT * FROM runs WHERE run_id=?") == "SELECT * FROM runs WHERE run_id=%s"
    assert _translate("SELECT * FROM runs WHERE status='queued' AND run_id=? ORDER BY created_at,run_id LIMIT 1").endswith(
        "FOR UPDATE SKIP LOCKED")
    for unsafe in ("DROP TABLE runs; DELETE FROM investigations", "PRAGMA user_version", "SELECT '%secret'"):
        with pytest.raises(BackendError):
            _translate(unsafe)
    row = _Row({"status": "queued", "revision": 3})
    assert row[0] == row["status"] and row[1] == row["revision"]
    assert dict(row)["status"] == "queued"


def test_store_injection_preserves_sqlite_mode(tmp_path):
    class UnreadyStore:
        def transaction(self): pass
        def readiness(self): return False
    assert BackendService(store=UnreadyStore()).readiness() is False
    with pytest.raises(ValueError):
        BackendService(tmp_path / "x.sqlite", store=UnreadyStore())


def test_schema_never_mutates_existing_evidence_tables():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sql = (root / "supabase/migrations/20261029_backend_runtime_schema.sql").read_text()
    assert "CREATE SCHEMA ss_runtime" in sql
    assert "REVOKE ALL ON ALL TABLES IN SCHEMA ss_runtime" in sql
    assert "DROP TABLE" not in sql and "ALTER TABLE ss." not in sql


def test_fenced_mutation_uses_database_clock_and_fails_before_event():
    class Raw:
        rowcount = 0
        def execute(self, sql, parameters):
            assert sql.endswith("AND status='running' AND lease_token=%s AND lease_expires>EXTRACT(EPOCH FROM clock_timestamp())")
            assert parameters == ('capture', 'run', 'secret_fence')
            return self
    db = _Connection(Raw())
    db.set_fence('run', 'secret_fence')
    with pytest.raises(BackendError) as error:
        db.execute('UPDATE runs SET stage=? WHERE run_id=?', ('capture', 'run'))
    assert error.value.code == 'LEASE_LOST'


def test_scoped_recovery_and_uncertain_publication_preserve_sqlite(tmp_path):
    from second_source.live_experiment import create_scope
    service = BackendService(tmp_path / 'local.sqlite')
    owner = Principal(owner_id='still_a_local_label')
    item = service.create_investigation(owner, CreateInvestigation(title='NON_AI', scope=create_scope(0, 1)), 'inv')
    item = service.authorize_investigation(owner, item.investigation_id,
        AuthorizeInvestigation(expected_revision=1, scope_digest=item.scope_digest))
    first, second = [service.create_run(owner, item.investigation_id, CreateRun(), key) for key in ('first', 'second')]
    lease = service.claim('worker', run_id=second.run_id)
    assert service.get_run(owner, first.run_id).status == 'queued'
    uncertain = service.finish(second.run_id, lease.token, None, error_code='ARTIFACT_PUBLICATION_UNCERTAIN')
    assert uncertain.status == 'needs_reconciliation'
    assert service.claim('retry', run_id=second.run_id) is None
    first_lease = service.claim('worker', run_id=first.run_id)
    with service.store.transaction() as db:
        db.execute('UPDATE runs SET lease_expires=? WHERE run_id=?', (0, first.run_id))
    assert service.recover_expired(run_id=second.run_id) == 0
    assert service.get_run(owner, first.run_id).status == 'running'
    assert service.recover_expired(run_id=first.run_id) == 1
    assert service.recover_expired() == 0
    assert first_lease.run.run_id == first.run_id
