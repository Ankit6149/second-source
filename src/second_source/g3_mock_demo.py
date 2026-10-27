"""MOCK-only candidate generation integration (NON-AI demonstration).

Exercises the complete typed boundary — mock transport, spec validation,
manifest, trusted interpreter, differential comparison against the owned
reference — with every artifact honestly labeled. The spec CONTENT here is an
author-written trusted test fixture transported over a mock channel; it is
NOT Muse output and this module never claims otherwise.

Real generation uses `candidate_generation.request_candidate_spec` with a genuine
`ModelGateway` response (explicit owner authorization required).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

DEMO_CASES: list[dict[str, Any]] = [
    {
        "case_id": "demo-add-total",
        "category": "value",
        "actions": [
            {"command": "add", "params": {"label": "Milk", "amount": 2}},
            {"command": "total"},
        ],
    },
    {
        "case_id": "demo-duplicate",
        "category": "errors",
        "actions": [
            {"command": "add", "params": {"label": "Eggs", "amount": 1}},
            {"command": "add", "params": {"label": "EGGS", "amount": 1}},
        ],
    },
    {
        "case_id": "demo-invalid-remove",
        "category": "errors",
        "actions": [
            {"command": "add", "params": {"label": "X", "amount": 0}},
            {"command": "remove", "params": {"id": "99"}},
        ],
    },
]

ORIGIN = "mock"


def run_demo(root: Path = ROOT) -> dict[str, Any]:
    import sys as _sys

    _sys.path.insert(0, str(root / "src"))
    from second_source.candidate_generation import mock_propose_candidate
    from second_source.candidate_runtime import CandidateInterpreter
    from second_source.contracts import ScopeContract
    from second_source.reference import CLIReferenceAdapter
    from second_source.verifier import DifferentialVerifier, SealedCase

    fixture_path = root / "tests" / "g3_fixtures" / "valid_candidate.json"
    spec_dict = json.loads(fixture_path.read_text(encoding="utf-8"))
    manifest_path = root / "fixtures" / "owned_ledger" / "public_contract.json"
    public = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract = ScopeContract(
        target={
            "kind": "cli",
            "permission_ref": "authz-owned-ledger-001",
            "reference_command_id": "owned-ledger-cli",
        },
        goal="mock wiring demonstration only",
        mode="selected_surfaces",
        observation={
            "permitted_actions": ["cli"],
            "allowed_commands": sorted(public["commands"].keys()),
            "allowed_roles": ["guest"],
            "authenticated_access": "not_required",
        },
        implementation={
            "requirements": ["REQ-LEDGER"],
            "allowed_subsystems": ["cli_ledger"],
            "route_patterns": [],
            "fidelity": ["behavioral"],
            "required_flows": ["counter-basics"],
        },
        exclusions={"url_patterns": [], "subsystems": [], "external_side_effects": []},
        budgets={},
    )
    loaded, receipt = mock_propose_candidate(spec_dict, contract)
    reference = CLIReferenceAdapter(
        [_sys.executable, str(root / "fixtures" / "owned_ledger" / "reference.py")],
        cwd=root,
    )
    candidate = CandidateInterpreter(loaded.spec)
    verifier = DifferentialVerifier(reference, candidate)
    report = verifier.verify([
        SealedCase(case_id=c["case_id"], actions=list(c["actions"]), category=c["category"])
        for c in DEMO_CASES
    ])
    return {
        "demo_kind": "mock_transport_of_trusted_fixture_not_AI",
        "origin": ORIGIN,
        "content_provenance": "trusted-test-fixture",
        "generation_receipt": receipt.model_dump(mode="json"),
        "spec_digest": loaded.digest,
        "evaluation": report.model_dump(mode="json"),
    }


def main() -> int:
    print(json.dumps(run_demo(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
