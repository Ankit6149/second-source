"""Adversarial evaluator tests (NON_AI): a deliberately mutated candidate
must be caught by the same comparison the Vikunja benchmark uses.

A reference-vs-reference self-check alone only proves determinism. These
tests prove discrimination: each behavioral mutation flips the verdict.
"""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "vikunja_benchmark",
    Path(__file__).resolve().parents[1] / "scripts" / "vikunja_benchmark.py")
vb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vb)

SEQ = [
    ("PUT", "/projects", {"title": "P"}, "alice"),
    ("PUT", "/projects/{pid}/tasks", {"title": "T", "priority": 5}, "alice"),
    ("POST", "/tasks/{tid}", {"done": True}, "alice"),
    ("GET", "/tasks/{tid}", None, "alice"),
]


class Stub:
    def __init__(self, mutation=None):
        self.mutation = mutation
        self.projects = {}
        self.tasks = {}
        self.next_id = 100

    def handle(self, method, path, body):
        self.next_id += 1
        nid = self.next_id
        parts = [p for p in path.split("/") if p]
        if method == "PUT" and parts == ["api", "v1", "projects"]:
            proj = {"id": nid, "title": body["title"], "created": "2026-01-01"}
            self.projects[nid] = proj
            return (200 if self.mutation == "wrong_status" else 201), proj
        if method == "PUT" and len(parts) == 5 and parts[4] == "tasks":
            task = {"id": nid, "project_id": int(parts[3]), "title": body["title"],
                    "priority": body.get("priority", 0), "done": False,
                    "done_at": None, "position": 655360.0}
            self.tasks[nid] = task
            return 201, task
        if method == "POST" and len(parts) == 4 and parts[2] == "tasks":
            task = self.tasks[int(parts[3])]
            if self.mutation != "no_done_transition":
                task = {**task, "done": body.get("done", False),
                        "done_at": "2026-01-02" if body.get("done") else None}
                self.tasks[task["id"]] = task
            return 200, task
        if method == "GET" and len(parts) == 4 and parts[2] == "tasks":
            task = dict(self.tasks[int(parts[3])])
            if self.mutation == "missing_field":
                task.pop("priority", None)
            if self.mutation == "wrong_done_at":
                task["done_at"] = None
            return 200, task
        return 404, {"message": "nf"}


def run_stub(mutation=None):
    stub = Stub(mutation)

    class Handler(BaseHTTPRequestHandler):
        def _go(self, method):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw else None
            status, out = stub.handle(method, self.path, body)
            data = json.dumps(out).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self): self._go("GET")
        def do_PUT(self): self._go("PUT")
        def do_POST(self): self._go("POST")
        def log_message(self, *a): pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        results = vb.run_actions(SEQ, {"alice": "tok"}, base=f"http://127.0.0.1:{port}/api/v1")
        return vb.canonical_sequence(results)
    finally:
        server.shutdown()


def test_unmutated_candidate_matches_reference_behavior():
    assert run_stub() == run_stub()


@pytest.mark.parametrize("mutation", [
    "wrong_status", "no_done_transition", "missing_field", "wrong_done_at",
])
def test_mutated_candidate_is_caught(mutation):
    assert run_stub() != run_stub(mutation), f"evaluator missed mutation: {mutation}"
