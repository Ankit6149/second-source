"""HTTP claim-coverage tests (NON_AI)."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "vikunja_coverage", ROOT / "scripts" / "vikunja_coverage.py")
vc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vc)


def oracle():
    return json.loads((ROOT / "scripts" / "vikunja_oracle_spec.json").read_text())


OBS = [
    {"action": "PUT /projects", "as": "alice", "status": 201, "body": {}},
    {"action": "PUT /projects", "as": "alice", "status": 412, "body": {}},
    {"action": "PUT /projects/{pid}/tasks", "as": "alice", "status": 201, "body": {}},
    {"action": "PUT /projects/{pid}/tasks", "as": "alice", "status": 400, "body": {}},
    {"action": "GET /projects/{pid}/tasks", "as": "bob", "status": 200, "body": []},
    {"action": "POST /tasks/{tid}", "as": "bob", "status": 403, "body": {}},
    {"action": "PUT /projects/{pid}/users", "as": "alice", "status": 201, "body": {}},
]


def states(report):
    return {c["dimension"]: c["state"] for c in report["claims"]}


def test_oracle_claims_mostly_observed():
    report = vc.analyze_spec(oracle(), OBS)
    s = states(report)
    assert s["route.PUT /projects"] == vc.OBSERVED
    assert s["route.PUT /projects.validate.title"] == vc.OBSERVED
    assert s["route.PUT /projects/{pid}/tasks.validate.title"] == vc.OBSERVED


def test_wrong_status_is_contradicted():
    spec = oracle()
    for route in spec["routes"]:
        if route["kind"] == "create_project":
            route["status"] = 200
    s = states(vc.analyze_spec(spec, OBS))
    assert s["route.PUT /projects"] == vc.CONTRADICTED


def test_unprobed_route_is_unknown_and_blocks_equivalence():
    report = vc.analyze_spec(oracle(), OBS[:2])
    assert vc.UNKNOWN in report["counts"].values() or report["counts"][vc.UNKNOWN] > 0
    assert report["verified_equivalence_blocked"] is True
