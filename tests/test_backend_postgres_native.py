"""Prove the SAME backend service statements against disposable native PostgreSQL.

No URL/DSN/user credentials are read from the host. No TCP listeners and no
provider access. The generated cluster is stopped even after test failure.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager

import pytest

from second_source.backend.postgres import _Connection
from second_source.backend.contracts import (
    AuthorizeInvestigation, BackendError, CodeStage, CreateInvestigation,
    CreateRun, EngineResult, EvaluationSummary, Principal, UsageSummary,
)
from second_source.backend.service import BackendService
from second_source.live_experiment import create_scope

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20261029_backend_runtime_schema.sql"


def _tools():
    if sys.platform != "linux":
        pytest.skip("Native PostgreSQL test is Linux-only")
    candidates = [Path(p).parent for p in [shutil.which("initdb")] if p]
    candidates += sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True)
    for candidate in candidates:
        if all((candidate / s).is_file() for s in ["initdb", "pg_ctl", "psql"]):
            return candidate
    if os.getenv("GITHUB_ACTIONS") == "true" and os.getenv("RUNNER_OS") == "Linux":
        pytest.fail("Native PostgreSQL binaries missing on CI")
    pytest.skip("Requires a local PostgreSQL server installation")


@pytest.mark.skipif(sys.platform != "linux", reason="Native local PG test runs on Linux")
def test_complete_owner_scoped_lifecycle_in_disposable_postgres():
    psycopg = pytest.importorskip("psycopg")
    from psycopg.rows import dict_row
    binaries = _tools()
    environment = {"PATH": os.defpath, "LC_ALL": "C",
                   "PGCONNECT_TIMEOUT": "5", "PGPASSFILE": os.devnull}

    with tempfile.TemporaryDirectory(prefix="ss-control-pg-") as d:
        root = Path(d)
        directory = root / "db"

        def command(binary, *args, timeout=45):
            result = subprocess.run([str(binaries / binary), *map(str, args)],
                                    env=environment, capture_output=True,
                                    text=True, timeout=timeout)
            assert result.returncode == 0, result.stderr + result.stdout
            return result

        command("initdb", "-D", directory, "-U", "postgres", "--no-locale",
                "--encoding=UTF8", "--auth-local=trust", "--auth-host=reject")
        escaped = str(root).replace("'", "''")
        with (directory / "postgresql.conf").open("a", encoding="utf-8") as cfg:
            cfg.write("\nlisten_addresses=''\nport=5432\nmax_connections=15\n"
                      "shared_buffers='16MB'\n"
                      f"unix_socket_directories='{escaped}'\n")
        try:
            command("pg_ctl", "-D", directory, "-l", root / "postgres.log",
                    "-w", "-t", "20", "start")
            psql = ["-X", "--no-password", "--host", root, "--port", "5432",
                    "--username", "postgres", "--dbname", "postgres",
                    "--set=ON_ERROR_STOP=1"]
            command("psql", *psql, "--command",
                    "CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN;")
            command("psql", *psql, "--file", MIGRATION)

            dsn = f"host={root} port=5432 dbname=postgres user=postgres"
            class LocalPostgresStore:
                @contextmanager
                def transaction(self):
                    with psycopg.connect(dsn, autocommit=False,
                                         prepare_threshold=None, row_factory=dict_row) as raw:
                        raw.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                        raw.execute("SET LOCAL search_path TO ss_runtime, pg_catalog")
                        yield _Connection(raw)

                def readiness(self):
                    with self.transaction() as db:
                        return db.execute("SELECT version FROM schema_version LIMIT 1").fetchone()[0] == 1

            store = LocalPostgresStore()
            backend = BackendService(store=store)
            assert backend.readiness()
            owner, other = Principal(owner_id="owner"), Principal(owner_id="other")
            params = CreateInvestigation(title="NON_AI native PG", scope=create_scope(0, 1))
            inv = backend.create_investigation(owner, params, "pg-migration-idempotency")
            assert backend.create_investigation(owner, params, "pg-migration-idempotency") == inv
            with pytest.raises(BackendError) as mismatch:
                backend.create_investigation(owner, CreateInvestigation(
                    title="changed", scope=params.scope), "pg-migration-idempotency")
            assert mismatch.value.code == "IDEMPOTENCY_CONFLICT"
            with pytest.raises(BackendError) as denied:
                backend.get_investigation(other, inv.investigation_id)
            assert denied.value.code == "NOT_FOUND"
            approved = backend.authorize_investigation(
                owner, inv.investigation_id, AuthorizeInvestigation(
                    expected_revision=inv.revision, scope_digest=inv.scope_digest))
            assert approved.status.value == "authorized"
            run = backend.create_run(owner, inv.investigation_id, CreateRun(), "pg-run")
            assert backend.create_run(owner, inv.investigation_id, CreateRun(), "pg-run") == run
            lease = backend.claim("native", lease_seconds=30)
            assert lease and lease.run.run_id == run.run_id
            for stage in CodeStage:
                backend.stage(run.run_id, lease.token, stage)
            result = EngineResult(stop_reason="completed_mock_run",
                                  usage=UsageSummary(),
                                  evaluation=EvaluationSummary(passed=0,failed=0,
                                                               indeterminate=0,total=0))
            completed = backend.finish(run.run_id, lease.token, result)
            assert completed.status.value == "completed"
            assert backend.get_run(owner, run.run_id) == completed
            assert backend.claim("other-worker") is None
            with pytest.raises(BackendError) as stale:
                backend.heartbeat(run.run_id, lease.token)
            assert stale.value.code == "LEASE_LOST"
            events = backend.events(owner, inv.investigation_id)
            assert len(events) >= 8 and events[-1].event_type == "run_completed"
            with pytest.raises(BackendError):
                backend.get_run(other, run.run_id)
            # The persisted state also survives a newly created service.
            assert BackendService(store=LocalPostgresStore()).get_run(owner, run.run_id) == completed
        finally:
            stopped = subprocess.run([str(binaries / "pg_ctl"), "-D", str(directory),
                                      "-m", "immediate", "-w", "-t", "20", "stop"],
                                     env=environment, capture_output=True, text=True, timeout=30)
            if (directory / "postmaster.pid").exists():
                pytest.fail("Disposable native PostgreSQL failed to shut down: " + stopped.stderr)
