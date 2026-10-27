# G3-B Verifier Contract — independent evaluation implementer

**Owner:** Codex (G3-B). **Status:** G3-A interface published, then revised by
independent review on 28 October 2026 to match the actual G0 wire contract.
No G3-B implementation is included here. **Applies to:** branch
`g3/candidate-synthesis` and its eventual merge with reviewed `main`.

## What G3-A guarantees

- `candidate_spec.CandidateSpec` — closed declarative schema
  (`spec_version`, subsystem, requirement IDs, four ledger commands with
  typed params, uniqueness/store/lookup/aggregate/respond blocks). No code,
  imports, shell, eval, subprocess, file paths, or network can be expressed;
  unknown keys fail closed at load.
- Command effects are pinned to the trusted operator-owned public contract:
  `add` may store; `remove` may lookup/delete by id; `list` and `total`
  are read-only. A model cannot smuggle in-memory mutation behind a nominally
  read-only command.
- `candidate_spec.load_candidate(spec, contract) -> LoadedCandidate` validates
  schema, per-command semantics, scope mapping (subsystem `cli_ledger` in
  scope, requirement IDs subset of scope) and the one-file manifest through
  G0 `ScopeGuard.validate_candidate_files`. Violations raise
  `CandidateError`. The loader owns the generated spec digest.
- `candidate_runtime.CandidateInterpreter(spec, ...)` is the trusted
  in-memory executor implementing G0 `ReferenceProtocol`:
  `execute_sequence(actions, *, sequence_id=None) -> SequenceResult`.
  It performs no model-written code execution, filesystem or network access.
- Resource caps fail closed:
  `MAX_SEQUENCE_ACTIONS=64`, `MAX_RECORDS=10000`,
  `MAX_OUTPUT_BYTES=131072`.
- `candidate_generation` provides the generation boundary with immutable
  origin meaning: `mock` vs `real`; author-written fixture provenance is
  tracked separately. It accepts only the closed top-level generation context
  and redacts again immediately before `ModelGateway`.

## Exact action wire contract (normative)

The reference and candidate MUST receive the **same flat action dictionary**.

Examples:

```json
{"command":"add","label":"Alpha","amount":5}
{"command":"list"}
{"command":"total"}
{"command":"remove","id":"1"}
```

Do **not** wrap action parameters inside a `params` object. The trusted owned
reference reads `label`, `amount`, and `id` directly from the action
object. `DifferentialVerifier` passes the exact same action object to both
sides.

## Reset boundary (normative)

The interpreter resets to empty state at the START of every
`execute_sequence` call, mirroring the reference fresh-process boundary.
State accumulates WITHIN a sequence only. An explicit `reset()` exists for
harness control. G3-B MUST use the same sequence list, in the same order,
against reference and candidate.

## How to evaluate

G0 `DifferentialVerifier(reference_adapter, candidate_interpreter)` already
accepts any `ReferenceProtocol`. G3-B should add only the adapter/storage and
sealed-suite ownership needed around that existing verifier, not rewrite its
comparison logic without a specific defect.

Call:

```python
verifier.verify([SealedCase(case_id, actions, category), ...])
```

The trusted evaluation report may retain case IDs for owner-side diagnostics.
The inference/repair model receives ONLY `EvaluationReport.model_feedback()`:
`passed`, `failed`, `indeterminate`, `total`, aggregate failure
categories. No case IDs, hidden inputs or expected outputs.

## Sealed-suite rules (binding)

1. Case IDs, hidden inputs and expected outputs never enter generation
   context, prompts, model tools, public logs or repair messages.
2. The generator process/tool set must not read
   `fixtures/owned_ledger/reference.py`, sealed case material, environment
   secrets, or evaluator storage. Prompt wording alone is not isolation.
3. Test categories must cover at least: valid add; invalid amount; invalid
   label; duplicate + case/whitespace handling; remove present/missing; list
   shape/order; total count/sum; unknown command; reset-sensitive ordered
   sequences. Hidden values remain evaluator-owned.
4. Independent controls are explicitly labeled `TRUSTED_CONTROL`, never
   `META_GENERATED`: one reference-equivalent positive control and at least
   one deliberately buggy negative control.
5. Metrics refer strictly to authorized scope and the exact sealed suite; no
   finite suite justifies a claim of universal equivalence.
6. Any evaluator read attempt from generation/candidate context is a critical
   failure and invalidates the run.

## Required Codex phase-1 audit before writes

Codex must independently inspect the committed G3-A interface and report:
- exact baseline SHA and read paths;
- severity-ranked contract/security findings with file/line evidence;
- whether the flat wire contract and reset semantics are now coherent;
- evaluator-owned storage boundary and leakage attack tests;
- proposed `CandidateReferenceAdapter` / `g3_verification` API;
- deterministic Linux/Windows integration tests;
- whether a disjoint code-write handoff is safe.

Do not report a Codex audit as completed until that actual output exists.

## Codex phase-2 allowed files

After phase-1 acceptance and an explicit disjoint write handoff, Codex may
implement only:
- `src/second_source/candidate_adapter.py`
- `src/second_source/g3_verification.py`
- `tests/test_g3_verifier_*.py`
- evaluator-owned sealed fixture material in its restricted path
- `docs/G3_VERIFIER_ACCEPTANCE.md`

Do not rewrite `candidate_spec.py`, `candidate_runtime.py`,
`candidate_generation.py`, G0 `verifier.py`, or reference source without a
new cross-review.

## Repair interface (G3-C, only after real baseline)

A repair is a new model response with a new immutable spec digest and receipt.
The only repair signal is aggregate `model_feedback()`. Maximum 0–2 rounds;
scope, permissions, DSL capabilities and sealed suite stay unchanged.
Before/after metrics must use the identical evaluator version and case suite.
