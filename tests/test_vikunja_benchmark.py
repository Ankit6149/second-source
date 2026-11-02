"""Canonicalization soundness for the Vikunja benchmark harness (NON_AI)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "vikunja_benchmark",
    Path(__file__).resolve().parents[1] / "scripts" / "vikunja_benchmark.py")
vb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vb)


def canon(body, status=200):
    return vb.canonical_sequence([{"status": status, "body": body}])


def test_server_ids_and_timestamps_normalized():
    a = canon({"id": 41, "project_id": 41, "created": "2026-01-01", "title": "X"})
    b = canon({"id": 7, "project_id": 7, "created": "2026-02-02", "title": "X"})
    assert a == b


def test_cross_step_id_relationship_preserved():
    # Same server entity across steps must keep ONE placeholder, even
    # when raw ids differ between two independent runs. Shapes mirror
    # real responses (projects carry views, tasks carry done).
    def run(pid, t1, t2, link=None):
        return vb.canonical_sequence([
            {"status": 201, "body": {"id": pid, "title": "P", "views": []}},
            {"status": 200, "body": [
                {"id": t1, "project_id": link or pid, "done": False},
                {"id": t2, "project_id": link or pid, "done": True}]},
        ])
    assert run(41, 9, 10) == run(3, 100, 101)
    # A candidate pointing step 2 at a DIFFERENT project must not match.
    assert run(3, 100, 101) != run(3, 100, 101, link=999)


def test_per_type_id_sequences_do_not_collide():
    # Fresh databases reuse the same numeric id per entity type
    # (project 1, task 1): placeholders must not merge them.
    seq = vb.canonical_sequence([
        {"status": 201, "body": {"id": 1, "title": "P", "views": []}},
        {"status": 201, "body": {"id": 1, "project_id": 1, "done": False}},
    ])
    assert seq[0]["body"]["id"] != seq[1]["body"]["id"]
    assert seq[1]["body"]["project_id"] == seq[0]["body"]["id"]


def test_position_rank_preserves_order_not_magnitude():
    a = canon([{"id": 1, "position": 655360}, {"id": 2, "position": 720896}])
    b = canon([{"id": 5, "position": 100}, {"id": 6, "position": 200}])
    assert a == b
    swapped = canon([{"id": 5, "position": 200}, {"id": 6, "position": 100}])
    assert a != swapped


def test_distinct_entity_shapes_never_merge():
    # Reviewer defect: label {id:1,title} and bucket {id:1,name} both
    # fell back to one shared namespace and merged.
    seq = vb.canonical_sequence([
        {"status": 201, "body": {"id": 1, "title": "l", "hex_color": ""}},
        {"status": 201, "body": {"id": 1, "name": "b"}},
    ])
    assert seq[0]["body"]["id"] != seq[1]["body"]["id"]


def test_same_user_keeps_one_placeholder_across_shapes():
    # Reviewer defect: {id, username} vs {id, username, permission}
    # split one user into two placeholders.
    seq = vb.canonical_sequence([
        {"status": 200, "body": {"id": 2, "username": "bench_bob"}},
        {"status": 201, "body": {"id": 2, "username": "bench_bob", "permission": 0}},
    ])
    assert seq[0]["body"]["id"] == seq[1]["body"]["id"]


def test_real_behavior_difference_still_detected():
    assert canon({"id": 1, "done": True}) != canon({"id": 9, "done": False})


def test_status_difference_detected():
    assert canon({"id": 1}, 201) != canon({"id": 1}, 400)
