# G3-B Verifier Contract — for the independent evaluation implementer

**Owner:** Codex (G3-B). **Status:** interface frozen by G3-A; no implementation
here, only the exact boundary to build against. **Applies to:** branch
`g3/candidate-synthesis` (and any rebase onto reviewed G2).

## What G3-A guarantees

- `candidate_spec.CandidateSpec` — closed declarative schema (spec_version,
  subsystem, requirement_ids, four ledger commands with param/normalize/
  uniqueness/store/lookup/aggregate/respond blocks). No code, imports, shell,
  eval, subprocess, file paths, or network can be expressed; unknown keys
  fail closed at load.
- `candidate_spec.load_candidate(spec, contract) -> LoadedCandidate` —
  validates schema, per-command semantics, scope mapping (subsystem
  `cli_ledger` ∈ scope subsystems, requirement ids ⊆ scope requirements),
  and the file manifest through G0
  `ScopeGuard.validate_candidate_files` (exactly one file, `candidate.json`).
  Raises `CandidateError` on any violation. Records `spec_digest`.
- `candidate_runtime.CandidateInterpreter(spec, ...)` — trusted in-memory
  executor implementing G0 `ReferenceProtocol`
  (`execute_sequence(actions, *, sequence_id=None) -> SequenceResult`,
  `reset()`). Same observation contract (`Observation` with
  `observation_id == f"{sequence_id}:{i}"`, `exit_code` 0, status
  `ok`/`target_error`/`protocol_error`). Resource caps fail closed
  (`MAX_SEQUENCE_ACTIONS=64`, `MAX_RECORDS=10000`, `MAX_OUTPUT_BYTES=131072`).
- `candidate_generation` — generation boundary with origin labels
  (`mock`/`trusted-test-fixture`/`real`); context builder takes explicit
  inputs only and never reads reference source, sealed cases, or secrets.

## Reset boundary (normative)

The interpreter resets to empty state at the START of every
`execute_sequence` call, mirroring the reference fresh-process boundary.
State accumulates WITHIN a sequence only. An explicit `reset()` exists for
harness control. G3-B MUST use the same sequence list, in the same order,
against reference and candidate.

## How to evaluate (no new verifier needed for the happy path)

G0 `DifferentialVerifier(reference_adapter, candidate_interpreter)` already
accepts any `ReferenceProtocol`. Call
`verifier.verify([SealedCase(case_id, actions, category), ...])` and report
`passed/failed/indeterminate/total` plus `model_feedback()` (counts and
categories ONLY) for any repair step.

## Sealed-suite rules (binding)

1. Case IDs, hidden inputs, and expected outputs NEVER enter generation
   context, prompts, logs, or repair messages. Repair input is
   `model_feedback()` aggregates only.
2. The generator boundary must not import or read
   `fixtures/owned_ledger/reference.py`, `tests/gold*`, or any sealed-case
   file. Keep the regression test that pins this (see
   `test_context_build_reads_no_restricted_paths`).
3. Required acceptance cases: valid add; invalid amount; invalid label;
   duplicate + case/whitespace handling; remove present/missing; list shape;
   total count/sum; ordered reset-sensitive sequences.
4. Controls (never presented as model output): the intentionally faulty
   `fixtures/candidates/*` doubles (sensitivity) and a reference-equivalent
   candidate (specificity baseline).
5. Metrics refer strictly to the authorized scope and the exact sealed suite;
   never claim full behavioral equivalence.

## Repair interface (G3-C, when authorized)

`request_candidate_spec` re-runs with feedback context; each accepted repair
produces a NEW immutable spec digest + real receipt; max 2 attempts on the
same scope; re-run the IDENTICAL sealed suite and report `delta_passed` with
regressions. Repair must not widen scopes, permissions, or DSL capabilities.

## Open items for G3-B

- Author the sealed sequence suite and its storage location (must stay out of
  model-visible paths).
- Decide timeout-category probing policy (the interpreter never hangs by
  construction; document as inapplicable or simulate).
- Wire `python -m second_source.reconstruct` (G3-D) once synthesis is real.
