"""Replay the recovered schema only in a fresh private PostgreSQL test cluster.

Never connects to an existing server or accepts a DSN. No Supabase/provider keys.
Linux CI must run the native replay; other environments may lack server tools.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20261028193413_initial_second_source_private_schema.sql"


def test_recovered_supabase_baseline_bytes_are_unchanged():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/verify_supabase_baseline.py")],
                            capture_output=True, text=True, timeout=10, check=True)
    witness = json.loads(result.stdout)
    assert witness["valid"] is True and witness["database_accessed"] is False
    assert witness["size_bytes"] == 10_244


def _server_tools():
    if sys.platform != "linux":
        pytest.skip("Disposable native PostgreSQL replay runs on Linux")
    candidates = sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True)
    path_initdb = shutil.which("initdb")
    if path_initdb:
        candidates.insert(0, Path(path_initdb).parent)
    for directory in candidates:
        if all((directory / name).is_file() for name in ("initdb", "pg_ctl", "psql")):
            return directory
    if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_OS") == "Linux":
        pytest.fail("Linux CI requires native PostgreSQL server tools for baseline replay")
    pytest.skip("Install local PostgreSQL server tools to replay the baseline")


def test_disposable_native_postgres_baseline_constraints_and_permissions():
    tools = _server_tools()
    # Drop PGHOST, PGSERVICE, PGPASSWORD, provider keys and all other inherited
    # configuration. The only connection is a newly created private Unix socket.
    env = {"PATH": os.defpath, "LC_ALL": "C", "PGCONNECT_TIMEOUT": "5",
           "PGPASSFILE": os.devnull}
    with tempfile.TemporaryDirectory(prefix="ss-pg-") as temporary:
        root = Path(temporary)
        cluster = root / "data"

        def command(name, *args, timeout=45):
            completed = subprocess.run([str(tools / name), *map(str, args)], env=env,
                                       capture_output=True, text=True, timeout=timeout)
            assert completed.returncode == 0, completed.stdout + completed.stderr
            return completed

        command("initdb", "-D", cluster, "-U", "postgres", "--no-locale",
                "--encoding=UTF8", "--auth-local=trust", "--auth-host=reject")
        socket_path = str(root).replace("\\", "\\\\").replace("'", "''")
        with (cluster / "postgresql.conf").open("a", encoding="utf-8") as config:
            config.write("\nlisten_addresses=''\nport=5432\nmax_connections=10\n"
                         "shared_buffers='16MB'\n"
                         f"unix_socket_directories='{socket_path}'\n")
        try:
            command("pg_ctl", "-D", cluster, "-l", root / "postgres.log",
                    "-w", "-t", "20", "start")
            completed = command("psql", "-X", "--no-password", "--host", root,
                "--port", "5432", "--username", "postgres", "--dbname", "postgres",
                "--set=ON_ERROR_STOP=1", "--file", ROOT / "tests/postgres/bootstrap.sql",
                "--file", MIGRATION, "--file", ROOT / "tests/postgres/baseline.sql")
            assert "BASELINE_CONSTRAINTS_OK / NON_AI / rolled_back" in completed.stdout
        finally:
            # Stop only this generated cluster, even if startup/test fails.
            stopped = subprocess.run([str(tools / "pg_ctl"), "-D", str(cluster),
                "-m", "immediate", "-w", "-t", "20", "stop"], env=env,
                capture_output=True, text=True, timeout=30)
            if (cluster / "postmaster.pid").exists():
                pytest.fail("Disposable PostgreSQL cluster did not stop: " + stopped.stderr)
