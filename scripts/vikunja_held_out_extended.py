"""EVALUATOR-ONLY extended held-out sequences for the Vikunja benchmark.

Separation rule: this module is evaluator material. It must never be
copied into a reconstruction agent's prompt, context, or accessible
notes. The agent receives only public probe observations
(.runs/vikunja-benchmark/public_observations.json). Frozen BEFORE any
prompt use for the extended Muse hybrid packet
(docs/VIKUNJA_MUSE_HYBRID_PACKET_EXTENDED.md). Any change here bumps
EXTENDED_SUITE_VERSION and invalidates prior extended comparisons; the
original frozen suite in vikunja_held_out.py is untouched.

Action shape: (method, path_template, body, user) as in
vikunja_benchmark.py. {pid}/{tid} resolve from prior responses.
Sequences recombine only semantics already observable on the public
ladder (project/task create, task update, done toggle, login errors,
cross-user isolation, read-only share); no expected outputs are encoded
here -- scoring is differential (fresh reference vs fresh candidate).
"""

EXTENDED_SUITE_VERSION = 1

EXTENDED_HELD_OUT = [
    # Multi-entity ordering: two projects, tasks stay with their project.
    [("PUT", "/projects", {"title": "Ext Alpha"}, "alice"),
     ("PUT", "/projects", {"title": "Ext Beta"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Alpha task"}, "alice"),
     ("GET", "/projects/{pid}/tasks", None, "alice")],
    # Update round-trip: rename a task, then read it back.
    [("PUT", "/projects", {"title": "Ext Update"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Before rename"}, "alice"),
     ("POST", "/tasks/{tid}", {"title": "After rename"}, "alice"),
     ("GET", "/tasks/{tid}", None, "alice")],
    # Done toggle twice returns to the original state.
    [("PUT", "/projects", {"title": "Ext Toggle"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Toggle twice"}, "alice"),
     ("POST", "/tasks/{tid}", {"done": True}, "alice"),
     ("POST", "/tasks/{tid}", {"done": False}, "alice"),
     ("GET", "/tasks/{tid}", None, "alice")],
    # A failed login does not poison a later correct login.
    [("POST", "/login", {"username": "bench_alice", "password": "wrong"}, "anon"),
     ("PUT", "/projects", {"title": "Ext After Login"}, "alice"),
     ("GET", "/projects/{pid}/tasks", None, "alice")],
    # Cross-user isolation on a single task in a second project.
    [("PUT", "/projects", {"title": "Ext Private"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Private extended"}, "alice"),
     ("GET", "/tasks/{tid}", None, "bob"),
     ("POST", "/tasks/{tid}", {"done": True}, "bob")],
    # Read-only share: bob reads the shared task but cannot rename it.
    [("PUT", "/projects", {"title": "Ext Shared"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Shared extended"}, "alice"),
     ("PUT", "/projects/{pid}/users", {"username": "bench_bob", "permission": 0}, "alice"),
     ("GET", "/tasks/{tid}", None, "bob"),
     ("POST", "/tasks/{tid}", {"title": "Bob rename attempt"}, "bob")],
]
