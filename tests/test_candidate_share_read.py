"""Candidate share semantics: a read share on a parent grants child reads."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "vikunja_candidate_server",
    Path(__file__).resolve().parents[1] / "scripts" / "vikunja_candidate_server.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_read_share_grants_single_item_get_under_shared_parent():
    cand = mod.Candidate({"users": {"alice": "bench_alice", "bob": "bench_bob"},
                          "auth": {}, "routes": []})
    cand._owners[7] = "alice"
    cand.shares[7] = {"bob": 0}  # read-only share
    route = {"method": "GET", "path": "/tasks/{tid}", "access": "owner"}
    assert cand._compiled_access(route, "bob", 7) is None


def test_read_share_does_not_grant_write():
    cand = mod.Candidate({"users": {"alice": "bench_alice", "bob": "bench_bob"},
                          "auth": {}, "routes": []})
    cand._owners[7] = "alice"
    cand.shares[7] = {"bob": 0}
    route = {"method": "POST", "path": "/tasks/{tid}", "access": "owner"}
    assert cand._compiled_access(route, "bob", 7) is not None
