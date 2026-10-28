"""Zero-call G2 discovery inspection (read-only; never dispatches or retries).

Reads one run directory's `g2_manifest.json`, revalidates it, verifies every
recorded digest against the co-located evidence ledger, and prints a verdict:

    python -m second_source.g2_inspect <run-dir>

Exit 0 means the package is approvable G3 input; exit 1 means it loaded but
is incomplete or unusable (gaps printed, nothing guessed); exit 2 means the
archive itself is unreadable or unsafe. No model calls, no credentials.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .evidence import EvidenceLedger
from .g2_persistence import (
    MANIFEST_FILENAME,
    G2RunManifest,
    PersistenceError,
    load_manifest,
    manifest_approvable,
    manifest_completeness,
    verify_ledger_coverage,
)


def inspect_run(run_dir: str | Path) -> dict:
    from pydantic import ValidationError

    root = Path(run_dir)
    try:
        manifest = load_manifest(root / MANIFEST_FILENAME)
    except PersistenceError:
        try:
            raw = (root / MANIFEST_FILENAME).read_bytes()
            manifest = G2RunManifest.model_validate_json(raw)
        except (OSError, ValidationError, ValueError) as exc:
            raise PersistenceError(f"manifest unreadable: {exc}") from exc
    ledger = EvidenceLedger(root / "evidence")
    coverage = verify_ledger_coverage(manifest, ledger)
    blockers = manifest_approvable(manifest)
    return {
        "kind": "G2_INSPECTION_VERDICT",
        "run_id": manifest.run_id,
        "manifest_version": manifest.manifest_version,
        "scope_digest": manifest.scope_digest,
        "stop_reason": manifest.stop_reason,
        "rounds": len(manifest.rounds),
        "evidence_artifacts": sum(
            len(record.evidence_digests) for record in manifest.rounds
        ),
        "model_receipts": len(manifest.model_receipts),
        "completeness_gaps": manifest_completeness(manifest),
        "ledger_coverage_missing": coverage,
        "approval_blockers": blockers,
        "approvable": not blockers and not coverage,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a G2 run archive")
    parser.add_argument("run_dir", help="run directory holding g2_manifest.json")
    args = parser.parse_args(argv)
    try:
        verdict = inspect_run(args.run_dir)
    except PersistenceError as exc:
        print(json.dumps({"kind": "G2_INSPECTION_VERDICT",
                          "approvable": False, "error": type(exc).__name__}))
        return 2
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if verdict["approvable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
