"""Hybrid synthesis machinery: compose/diff/light-observation units.

No network, no model calls. The live experiment is exercised only
through scripts/vikunja_hybrid_experiment.py --live --confirm-live.
"""
import sys
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
