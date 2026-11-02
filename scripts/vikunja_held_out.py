"""EVALUATOR-ONLY held-out sequences for the Vikunja benchmark.

Separation rule: this module is evaluator material. It must never be
copied into a reconstruction agent's prompt, context, or accessible
notes. The agent receives only public probe observations
(.runs/vikunja-benchmark/public_observations.json). Versioned with the
benchmark charter in docs/BENCHMARK_VIKUNJA.md; any change here bumps
the benchmark version and invalidates prior arm comparisons.

Action shape: (method, path_template, body, user) as in
vikunja_benchmark.py. {pid}/{tid} resolve from prior responses.
"""

HELD_OUT = [
    [("PUT", "/projects", {"title": "Held A"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Write report", "priority": 5}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Review report"}, "alice"),
     ("GET", "/projects/{pid}/tasks", None, "alice")],
    [("PUT", "/projects", {"title": ""}, "alice")],
    [("PUT", "/projects", {"title": "Held B"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Toggle me"}, "alice"),
     ("POST", "/tasks/{tid}", {"done": True}, "alice"),
     ("POST", "/tasks/{tid}", {"done": False}, "alice"),
     ("GET", "/tasks/{tid}", None, "alice")],
    [("POST", "/login", {"username": "bench_alice", "password": "wrong"}, "anon")],
    # Cross-user isolation on a fresh project (deterministic; listing
    # another user's projects is state-dependent and excluded by design).
    [("PUT", "/projects", {"title": "Held Private"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Private task"}, "alice"),
     ("GET", "/tasks/{tid}", None, "bob")],
    # Multi-user workflow: share read-only, bob can read but not write.
    [("PUT", "/projects", {"title": "Held Shared"}, "alice"),
     ("PUT", "/projects/{pid}/tasks", {"title": "Shared task"}, "alice"),
     ("PUT", "/projects/{pid}/users", {"username": "bench_bob", "permission": 0}, "alice"),
     ("GET", "/projects/{pid}/tasks", None, "bob"),
     ("POST", "/tasks/{tid}", {"done": True}, "bob")],
]
