"""Hybrid synthesis machinery: compose/diff/light-observation units.

No network, no model calls. The live experiment is exercised only
through scripts/vikunja_hybrid_experiment.py --live --confirm-live.
"""
import ast
import copy
import json
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vikunja_hybrid_experiment as hybrid  # noqa: E402


def _compiled():
    return {
        "users": {"alice": "bench_alice", "bob": "bench_bob"},
        "auth": {"login_error_status": 403},
        "routes": [
            {"method": "PUT", "path": "/projects", "kind": "compiled_create",
             "status": 201, "template": {"id": "<new_id>", "views": [{"id": 1}]}},
            {"method": "GET", "path": "/projects", "kind": "compiled_list",
             "status": 200, "template": []},
        ],
    }


def test_compose_edited_records_exact_model_diff():
    compiled = _compiled()
    edited_projects = [
        {"method": "PUT", "path": "/projects", "kind": "compiled_create",
         "status": 201, "template": {"id": "<new_id>"}},  # views restored
        {"method": "GET", "path": "/projects", "kind": "compiled_list",
         "status": 200, "template": []},
        {"method": "DELETE", "path": "/projects/{pid}",
         "kind": "compiled_get", "status": 204, "template": None},
    ]
    spec, diff = hybrid.compose_edited(compiled, {"projects": edited_projects})
    changes = {(d["change"], tuple(d["route"])) for d in diff}
    assert ("added", ("DELETE", "/projects/{pid}")) in changes
    # PUT /projects differs only by the restored views payload, which is
    # declared plumbing: after restoration it equals the baseline, so it
    # must NOT be recorded as a model modification.
    assert ("modified", ("PUT", "/projects")) not in changes
    put = next(r for r in spec["routes"] if r["method"] == "PUT")
    assert put["template"]["views"] == [{"id": 1}]
    assert spec["users"]["alice"] == "bench_alice"


def test_compose_edited_records_omission():
    compiled = _compiled()
    spec, diff = hybrid.compose_edited(compiled, {"projects": [
        {"method": "PUT", "path": "/projects", "kind": "compiled_create",
         "status": 201, "template": {"id": "<new_id>"}}]})
    assert {"change": "removed_by_model_omission",
            "route": ["GET", "/projects"]} in diff
    assert len(spec["routes"]) == 1


def test_light_observations_keep_errors_drop_success_bodies():
    obs = [
        {"action": "PUT /projects", "as": "alice", "status": 201,
         "request": {"title": "X"}, "body": {"id": 1, "big": "y" * 500}},
        {"action": "PUT /projects", "as": "alice", "status": 412,
         "request": {"title": ""}, "body": {"message": "title empty"}},
    ]
    text = hybrid.light_observations(obs)
    assert '"message": "title empty"' in text
    assert "y" * 100 not in text  # success bodies are not repeated


def test_module_split_covers_all_routes_without_overlap():
    seen = []
    for keep in (v[1] for v in hybrid.MODULES.values()):
        pass
    compiled = _compiled()
    all_keys = {(r["method"], r["path"]) for r in compiled["routes"]}
    covered = set()
    for name, (_scope, keep) in hybrid.MODULES.items():
        for r in compiled["routes"]:
            if keep(f"{r['method']} {r['path']}"):
                assert (r["method"], r["path"]) not in covered, name
                covered.add((r["method"], r["path"]))
    assert covered == all_keys


# --- Offline public conformance / diagnosis / bounded repair ---
# Synthetic public observations only; no network, no model call, and
# no sealed evaluator material. Recorded artifacts, when present, are
# exercised by the last test and skipped (not fabricated) otherwise.

def _public_observations():
    return [
        {"action": "GET /info", "as": None, "request": None,
         "status": 200, "body": {"version": "x"}},
        {"action": "PUT /projects", "as": "alice",
         "request": {"title": "Bench"}, "status": 201,
         "body": {"id": 1, "title": "Bench"}},
        {"action": "PUT /projects", "as": "alice",
         "request": {"title": ""}, "status": 412,
         "body": {"code": 2002, "message": "Invalid Data"}},
        {"action": "GET /projects", "as": "alice", "request": None,
         "status": 200, "body": [{"id": 1, "title": "Bench"}]},
        {"action": "GET /user", "as": None, "request": None,
         "status": 401, "body": {"message": "unauthorized"}},
    ]


def _compiled_spec():
    return {
        "users": {"alice": "bench_alice", "bob": "bench_bob"},
        "auth": {"unauthenticated_status": 401,
                 "unauthenticated_body": {"message": "unauthorized"},
                 "login_error_status": 403},
        "routes": [
            {"method": "PUT", "path": "/projects",
             "kind": "compiled_create", "collection": "projects",
             "auth": True, "status": 201, "access": "owner",
             "template": {"id": "<new_id>",
                          "title": {"$input": "title", "default": ""}},
             "validate": [{"field": "title", "rule": "nonempty",
                           "status": 412,
                           "error_body": {"code": 2002,
                                          "message": "Invalid Data"}}]},
            {"method": "GET", "path": "/projects",
             "kind": "compiled_list", "collection": "projects",
             "auth": True, "status": 200, "access": "owner",
             "template": [{"id": "<new_id>", "title": "Bench"}]},
            {"method": "GET", "path": "/user",
             "kind": "compiled_single", "collection": "user",
             "auth": True, "status": 200, "access": "owner",
             "template": {"id": "<new_id>", "username": "bench_alice"}},
        ],
    }


def test_offline_conformance_compiled_candidate_passes_public_only():
    report = hybrid.check_public_conformance(
        _compiled_spec(), _public_observations(), _compiled_spec())
    assert report["public_only"] is True
    assert report["live_replay"] is False
    assert report["checked"] == 4 and report["passed"] == 4
    assert report["divergences"] == []
    assert report["skipped"][0]["action"] == "GET /info"


def test_deliberately_wrong_candidate_is_bad_inference():
    compiled = _compiled_spec()
    wrong = copy.deepcopy(compiled)
    wrong["routes"][0]["status"] = 200  # observed + compiled say 201
    report = hybrid.check_public_conformance(
        wrong, _public_observations(), compiled)
    assert report["passed"] < report["total"]
    assert report["divergences"][0]["probe_index"] == 1
    assert report["divergences"][0]["classification"] == "bad-inference"
    earliest = hybrid.diagnose_earliest_divergence(
        report["divergences"], wrong, compiled, _public_observations())
    assert earliest["classification"] == "bad-inference"
    assert earliest["probe_index"] == 1


def test_divergence_classes_missing_representation_implementation():
    compiled = _compiled_spec()
    obs = _public_observations()
    missing = hybrid.diagnose_divergence(
        {"action": "DELETE /projects/{pid}", "probe_index": 99},
        compiled, compiled, obs)
    assert missing["classification"] == "missing-observation"
    # Compiled template cannot represent the observed body; a candidate
    # carrying it verbatim is a representation gap, not bad inference.
    narrow = copy.deepcopy(compiled)
    narrow["routes"][0]["template"] = {"id": "<new_id>"}
    rep = hybrid.diagnose_divergence(
        {"action": "PUT /projects", "probe_index": 1,
         "kind": "template_shape", "expected_status": 201},
        narrow, narrow, obs)
    assert rep["classification"] == "representation"
    impl = hybrid.diagnose_divergence(
        {"action": "PUT /projects", "probe_index": 1,
         "kind": "state_transition", "expected_status": 201},
        compiled, compiled, obs)
    assert impl["classification"] == "implementation"
    assert set(hybrid.DIVERGENCE_CLASSES) == {
        "missing-observation", "bad-inference",
        "representation", "implementation"}


def test_compiled_facts_cannot_be_mutated_by_repair():
    compiled = _compiled_spec()
    snapshot = copy.deepcopy(compiled)
    candidate = copy.deepcopy(compiled)
    candidate["routes"][0]["status"] = 200
    candidate["routes"][0]["template"] = {"tampered": True}
    repaired, record = hybrid.apply_repair_edits(candidate, compiled, [
        {"method": "PUT", "path": "/projects",
         "changes": {"status": 201}}])
    put = repaired["routes"][0]
    assert put["status"] == 201
    # Evidence-compiled template restored verbatim, tampering discarded.
    assert put["template"] == snapshot["routes"][0]["template"]
    assert record["compiled_templates_preserved"] is True
    assert compiled == snapshot  # inputs never mutated
    assert candidate["routes"][0]["template"] == {"tampered": True}
    put["template"]["id"] = "mutated-after-repair"
    assert compiled["routes"][0]["template"]["id"] == "<new_id>"
    with pytest.raises(ValueError, match="frozen"):
        hybrid.apply_repair_edits(candidate, compiled, [
            {"method": "PUT", "path": "/projects",
             "changes": {"template": {"id": 1}}}])
    with pytest.raises(ValueError, match="bound exceeded"):
        hybrid.apply_repair_edits(candidate, compiled, [
            {"method": "PUT", "path": "/projects",
             "changes": {"status": 201}},
            {"method": "GET", "path": "/projects",
             "changes": {"status": 200}}], max_edits=1)
    with pytest.raises(ValueError, match="unknown route"):
        hybrid.apply_repair_edits(candidate, compiled, [
            {"method": "DELETE", "path": "/projects/{pid}",
             "changes": {"status": 204}}])
    assert compiled == snapshot


def test_repair_spec_is_bounded_with_per_route_provenance():
    compiled = _compiled_spec()
    wrong = copy.deepcopy(compiled)
    wrong["routes"][0]["status"] = 200
    report = hybrid.check_public_conformance(
        wrong, _public_observations(), compiled)
    spec = hybrid.build_repair_spec(
        wrong, compiled, report, _public_observations())
    assert spec["provenance"]["public_only"] is True
    assert spec["provenance"]["held_out_used"] is False
    assert spec["bounded"]["max_model_calls"] == 1
    assert spec["bounded"]["max_edits"] == hybrid.MAX_REPAIR_EDITS
    assert ["PUT", "/projects"] in spec["editable_routes"]
    assert spec["earliest_divergence"]["classification"] == "bad-inference"
    origins = {tuple(p["route"]): p["origin"]
               for p in spec["route_provenance"]}
    assert origins[("PUT", "/projects")] == "model_modified_compiled"
    assert origins[("GET", "/projects")] == "compiled_non_ai"
    assert all(p["compiled_template_preserved"]
               for p in spec["route_provenance"])


def test_repair_path_never_imports_sealed_evaluator():
    # The hybrid module's own repair path must not import or reference
    # the sealed evaluator. (Live scoring in sibling harness modules
    # is separate evaluator infrastructure, not synthesis input here.)
    tree = ast.parse(Path(hybrid.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert "vikunja_held_out" not in imported
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "HELD_OUT" not in names


def test_recorded_artifacts_offline_conformance_if_present():
    root = Path(__file__).resolve().parents[1]
    obs_path = root / ".runs/vikunja-benchmark/public_observations.json"
    compiled_path = root / ".runs/vikunja-model/spec_compiled.json"
    hybrid_path = root / ".runs/vikunja-model/spec_H_hybrid.json"
    if not (obs_path.exists() and compiled_path.exists()
            and hybrid_path.exists()):
        pytest.skip("recorded hybrid artifacts absent; synthetic only")
    observations = json.loads(obs_path.read_text(encoding="utf-8"))
    compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
    candidate = json.loads(hybrid_path.read_text(encoding="utf-8"))
    report = hybrid.check_public_conformance(candidate, observations,
                                              compiled)
    assert report["public_only"] is True
    assert report["checked"] == len(observations) - 1  # /info skipped
    for div in report["divergences"]:
        assert div["classification"] in hybrid.DIVERGENCE_CLASSES
    repair = hybrid.build_repair_spec(candidate, compiled, report,
                                      observations)
    assert repair["provenance"]["held_out_used"] is False
    assert len(repair["route_provenance"]) == len(candidate["routes"])
