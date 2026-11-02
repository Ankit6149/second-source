# Owned ledger variant fixture (G4 scaffolding)

Second authorized black-box target for cross-target reconstruction work.

- Same command surface as `../owned_ledger` (`add`/`list`/`total`/`remove`,
  identical parameter signatures and side-effect classes).
- Different hidden rules: label 1..48 trimmed, case-SENSITIVE uniqueness,
  amount 1..500, error codes `invalid_title` / `invalid_qty` /
  `duplicate_title` / `missing_id`.
- Protocol: stdin JSONL actions, stdout JSONL results; fresh process resets
  all state.

Status: fixture plus differential scaffolding tests only. Control-plane
integration (target selection in discovery, per-target sealed suites and
code pins) is pending joint contract work and is NOT claimed here.
