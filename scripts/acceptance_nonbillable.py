"""Run the local authenticated NON_AI acceptance and failure controls.

This uses SQLite, synthetic identities and fake Storage, not hosted services.
Install the project with its dev dependencies before running this script.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_backend_cloud_app.py",
    "tests/test_backend_cloud_artifacts.py",
    "tests/test_backend_worker.py",
)


def main() -> int:
    # Pass only OS/runtime essentials: no provider, database, or storage secrets.
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
               "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "COMSPEC")
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    environment["SECOND_SOURCE_MAX_RUN_USD"] = "0"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    print("LOCAL NON_AI acceptance: SQLite, synthetic authentication, fake Storage.", flush=True)
    print("This does not verify hosted authentication, persistence, or deployment.", flush=True)
    command = [sys.executable, "-m", "pytest", "-q", "-ra", *TESTS]
    try:
        completed = subprocess.run(command, cwd=ROOT, env=environment, timeout=1200, check=False)
    except subprocess.TimeoutExpired:
        print("Acceptance timed out; no successful result is claimed.", file=sys.stderr)
        return 1
    if completed.returncode:
        print("Acceptance failed or was interrupted; inspect test output.", file=sys.stderr)
    else:
        print("Local NON_AI acceptance checks passed; hosted acceptance remains unverified.")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
