"""Verify the recovered migration bytes offline. No database or credentials."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "20261028193413_initial_second_source_private_schema.sql"
EXPECTED_SHA256 = "8a89975315fd8b9e1287bace3073e5fe7a3a185eb673c4341038234157d5aac2"
EXPECTED_SIZE = 10_244


def main() -> int:
    try:
        raw = (ROOT / "supabase" / "migrations" / MIGRATION).read_bytes()
    except OSError:
        print(json.dumps({"valid": False, "code": "BASELINE_UNAVAILABLE"}))
        return 1
    digest = hashlib.sha256(raw).hexdigest()
    valid = len(raw) == EXPECTED_SIZE and digest == EXPECTED_SHA256
    print(json.dumps({"valid": valid, "migration": MIGRATION,
                      "size_bytes": len(raw), "sha256": digest,
                      "verification": "retained_byte_witness_only",
                      "database_accessed": False}))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
