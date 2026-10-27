"""Run a fully local G0/G1 verifier check; NOT a model experiment."""
from __future__ import annotations

from pathlib import Path
import json
import sys

from .reference import CLIReferenceAdapter
from .verifier import DifferentialVerifier, SealedCase


def main():
    root = Path(__file__).resolve().parents[2]
    ref = CLIReferenceAdapter([sys.executable, str(root / "fixtures/owned_ledger/reference.py")], cwd=root)
    bad = CLIReferenceAdapter([sys.executable, str(root / "fixtures/candidates/buggy.py")], cwd=root)
    suite = [
        SealedCase(case_id="empty", actions=({"command": "list"},)),
        SealedCase(case_id="duplicate", actions=({"command": "add", "label": "Alpha", "amount": 3}, {"command": "add", "label": "alpha", "amount": 4})),
        SealedCase(case_id="remove", actions=({"command": "add", "label": "Alpha", "amount": 3}, {"command": "remove", "id": "1"}, {"command": "total"})),
        SealedCase(case_id="invalid", actions=({"command": "add", "label": "Alpha", "amount": -1},)),
    ]
    report = DifferentialVerifier(ref, bad).verify(suite)
    print(json.dumps({"demo_kind": "deterministic_harness_not_AI", "result": report.model_dump(mode="json")}, indent=2))
    if report.failed < 1 or report.passed < 1:
        raise SystemExit("Evaluator did not distinguish matching and failing cases")


if __name__ == "__main__":
    main()
