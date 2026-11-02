"""Canonicalization soundness for the Vikunja benchmark harness (NON_AI)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "vikunja_benchmark",
    Path(__file__).resolve().parents[1] / "scripts" / "vikunja_benchmark.py")
vb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vb)


def canon(body, status=200):
    return vb.canonical_result({"status": status, "body": body})


def test_server_ids_and_timestamps_normalized():
    a = canon({"id": 41, "project_id": 41, "created": "2026-01-01", "title": "X"})
    b = canon({"id": 7, "project_id": 7, "created": "2026-02-02", "title": "X"})
    assert a == b


def test_position_counter_ignored_but_presence_kept():
    a = canon({"id": 1, "position": 655360})
    b = canon({"id": 2, "position": 720896})
    assert a == b
    assert a["body"]["position"] == "<pos>"


def test_real_behavior_difference_still_detected():
    a = canon({"id": 1, "done": True})
    b = canon({"id": 9, "done": False})
    assert a != b


def test_status_difference_detected():
    assert canon({"id": 1}, 201) != canon({"id": 1}, 400)
