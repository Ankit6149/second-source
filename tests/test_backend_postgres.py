"""No-network PostgreSQL control-plane adapter tests."""
import pytest
from second_source.backend.postgres import PostgresStore, _Row, _translate
from second_source.backend.contracts import BackendError
from second_source.backend.service import BackendService

PROJECT = "jpqcqqbzriizxhigvjki"
DSN = ("postgresql://postgres." + PROJECT + ":fake@aws-0-ap-south-1.pooler.supabase.com:6543/"
       "postgres?sslmode=require")


def test_tenant_and_tls_policy():
    try:
        adapter = PostgresStore(DSN, project_ref=PROJECT)
    except ValueError as error:
        if "Invalid Postgres configuration" in str(error):
            pytest.skip("Optional psycopg driver is not installed")
        raise
    assert adapter.SCHEMA_VERSION == 1
    with pytest.raises(ValueError):
        PostgresStore(DSN.replace("sslmode=require", "sslmode=disable"), project_ref=PROJECT)
    with pytest.raises(ValueError):
        PostgresStore(DSN, project_ref="aaaaaaaaaaaaaaaaaaaa")


def test_query_translation_uses_bound_parameters_and_locks_claims():
    assert _translate("SELECT * FROM runs WHERE status='queued' ORDER BY created_at,run_id LIMIT 1").endswith(
        "FOR UPDATE SKIP LOCKED")
    assert _translate("SELECT * FROM runs WHERE run_id=?") == "SELECT * FROM runs WHERE run_id=%s"
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
