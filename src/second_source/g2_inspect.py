"""Read-only zero-call view of the sole version-2 discovery journal.

Exit0 means a complete NON_AI or real archive, never model-input/spend approval.
Exit1 means interrupted/stopped/incomplete; exit2 means invalid/unreadable.
A real-input-eligible verdict additionally requires genuine origin and the
externally retained receipt witness. No execution, credential read or retry.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .g2_persistence import JOURNAL_VERSION, PersistenceError, inspect_run as inspect_archive


def inspect_run(run_dir: str | Path, receipt_sha256: str | None = None) -> dict:
    archive = inspect_archive(Path(run_dir), receipt_sha256)
    complete = archive["complete"]
    return {
        "kind": "G2_INSPECTION_VERDICT", "run_id": archive["run_id"],
        "manifest_version": JOURNAL_VERSION, "scope_digest": archive["scope_digest"],
        "stop_reason": archive["stop_reason"], "state": archive["state"],
        "origin": archive["origin"], "complete": complete,
        "rounds": len(archive["completed_rounds"]),
        "evidence_artifacts": len(archive["observation_digests"]),
        "model_receipts": len(archive["model_receipts"]), "budget": archive["budget"],
        "pending_attempt": archive["pending_attempt"],
        "pending_uncertain_cost_usd": archive["pending_uncertain_cost_usd"],
        "receipt_sha256": archive["receipt_sha256"], "receipt_pinned": receipt_sha256 is not None,
        "completeness_gaps": [] if complete else ["discovery_" + archive["state"]],
        "ledger_coverage_missing": [],
        "real_input_eligible": complete and archive["origin"] == "real" and receipt_sha256 is not None,
        "approvable": complete and archive["origin"] == "real" and receipt_sha256 is not None,
        "provider_calls": 0, "execution_resume_supported": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--receipt-sha256", help="externally retained G2 receipt hash")
    args = parser.parse_args(argv)
    try:
        verdict = inspect_run(args.run_dir, args.receipt_sha256)
    except (PersistenceError, OSError):
        print(json.dumps({"kind": "G2_INSPECTION_VERDICT", "complete": False, "approvable": False,
                          "real_input_eligible": False, "error": "INVALID_OR_UNREADABLE_ARCHIVE", "provider_calls": 0}))
        return 2
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if verdict["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
