# Owned HTTP items fixture (G4 cross-protocol scaffolding)

Stateful JSON resource API (`server.py`, stdlib only, no dependencies).

- `POST /items` → 201 / 400 / 409; `GET /items` → 200;
  `GET /items/{id}` → 200 / 404; `DELETE /items/{id}` → 200 / 404.
- Hidden rules: label 1..32 trimmed, case-SENSITIVE uniqueness,
  amount 1..250, distinct error-code strings.
- Run: `python server.py --port-file <path>` (binds 127.0.0.1 ephemeral,
  writes the port, serves until killed; fresh process resets state).

Status: fixture plus adapter/candidate/evaluation scaffolding and tests.
Full control-plane integration (discovery target selection, per-target
sealed suites and pins) is pending joint contract work and is NOT claimed.
