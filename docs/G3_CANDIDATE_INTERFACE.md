# G3-B Verifier Contract — independent evaluation implementer

**Owner:** Codex (G3-B). **Status:** G3-A interface is frozen after Muse implementation, ChatGPT hardening and Codex phase-1 audit. The final G3-A freeze is `a1a137649a51178e30f438e1069788a0e8b2de81`; GitHub run `40576855908` passed with 179 passed / 2 skipped / 0 failed on both Linux and Windows and Windows bootstrap `BOOTSTRAP_OK`. Canonical-main synchronization is recorded by `208aeb4e7ee5559e176daccd19fc2b7c1eb207d7`. Phase 2 is released on `g3/verifier` from the coordinator freeze baseline. G3 itself is NOT accepted.

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
- Interpreter-local caps exist (`MAX_SEQUENCE_ACTIONS=64`, `MAX_RECORDS=10000`, `MAX_OUTPUT_BYTES=131072`), but these are NOT sufficient evidence of OS-level wall/CPU/memory isolation. G3-B owns trusted execution limits and admission failure when stronger containment cannot be enforced.
- `candidate_generation` provides the generation boundary with immutable origin meaning: `mock` vs `real`; author-written fixture provenance is tracked separately. It validates the nested public manifest, evidence envelopes/digests and evidence-linked hypotheses, rejects unknown nested fields, and redacts again immediately before `ModelGateway`.

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

## Validation precedence (normative)

`load_candidate` applies checks in this fixed order; the FIRST failure wins so
digests and errors are deterministic:

1. Spec byte-size cap (`MAX_SPEC_BYTES`).
2. JSON parse (must decode to an object).
3. Pydantic schema (closed shapes, enums, literal versions).
4. Per-command semantics (exact param sets, op-compatibility matrix:
   `add` stores with uniqueness; `remove` looks up and deletes;
   `list`/`total` neither store nor look up; pinned respond sources).
5. Scope mapping (subsystem `cli_ledger` in scope; requirement ids ⊆ scope).
6. File manifest through `ScopeGuard.validate_candidate_files`.

The loader owns the single spec digest (canonical input bytes). The runtime
never recomputes digests; manifest digest == loaded digest, asserted by test.

Param/command validation iterates sorted names, so identical spec content
loaded as JSON bytes or as a mapping with different key order yields the
same first error (regression: `test_param_error_precedence_representation_independent`).

G3-D provenance binding (Muse-owned `candidate_generation`): a context is
broker-bound only when its scope projection equals the pinned `ScopeContract`,
its public manifest digest matches the pinned manifest, and every evidence
view equals the ledger-backed approved registry byte for byte. The exact
inspected `ModelRequest` is built by `build_synthesize_request`; the
credential-owning broker delivers it with only its deterministic
schema-preamble prepended.

## Failure semantics (normative)

| Input | Candidate output | Status |
|---|---|---|
| `actions` not a list / sequence over cap | `protocol_error`, no observations | harness fault |
| Any non-object action in a sequence | `protocol_error`, no observations | harness fault / outside dict-only `ReferenceProtocol` |
| Missing/non-string `command` | `{ok:false,error:<unknown_command_error>}` | `target_error` |
| Unknown command label | `{ok:false,error:<unknown_command_error>}` | `target_error` |
| Param missing/invalid per declaration | `{ok:false,error:<param.error>}` | `target_error` |
| Duplicate label (casefolded) | `{ok:false,error:duplicate_label}` | `target_error` |
| Lookup miss / non-string id | `{ok:false,error:not_found}` | `target_error` |
| Record store over cap | `{ok:false,error:resource_exhausted}` | `target_error` |
| Serialized output over byte cap | `protocol_error` (prior observations kept) | harness fault |

Dict-shaped malformed inputs never raise: each in-contract action yields an
observation or the sequence fails closed at the harness level. Non-dict JSON
values are outside `SealedCase.actions` / `ReferenceProtocol`; both trusted
sides must reject such a sequence as `protocol_error` before comparison.

## How to evaluate

G0 `DifferentialVerifier(reference_adapter, candidate_interpreter)` accepts any `ReferenceProtocol`, but Codex phase 1 reproduced a **specific comparator defect**: Python equality can false-pass JSON-type differences and malformed/inconsistent result envelopes. Therefore acceptance MUST NOT use the old comparator unchanged. G3-B may make a narrow, API-preserving `verifier.py` hardening patch with strict JSON typing and result-envelope validation, backed by regression tests.

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

## Codex phase-1 audit — COMPLETE

The completed audit is recorded in `docs/G3_B_PHASE1_AUDIT_2026-10-28.md`. It audited `8f881cd37...` and reproduced the action-wire mismatch, verifier false passes, contaminated generation context, unsafe DSL combinations, mutability/digest risks, resource-containment gaps and shared-suite mutation risk. Later G3-A commits address the interface/DSL/context findings; strict verifier correctness and evaluator-owned containment remain phase-2 work.

## Codex phase-2 allowed files

After phase-1 acceptance and an explicit disjoint write handoff, Codex may
implement only:
- `src/second_source/candidate_adapter.py`
- `src/second_source/g3_verification.py`
- `tests/test_g3_verifier_*.py`
- evaluator-owned sealed fixture material in its restricted path
- `docs/G3_VERIFIER_ACCEPTANCE.md`
- narrow API-preserving changes to `src/second_source/verifier.py` and verifier regression tests solely for the reproduced strict-comparison/envelope defect.

Do not modify `candidate_spec.py`, `candidate_runtime.py`, `candidate_generation.py`, reference source, scope contracts, provider code or G2 evidence during the phase-2 write window.

## Repair interface (G3-C, only after real baseline)

A repair is a new model response with a new immutable spec digest and receipt.
The only repair signal is aggregate `model_feedback()`. Maximum 0–2 rounds;
scope, permissions, DSL capabilities and sealed suite stay unchanged.
Before/after metrics must use the identical evaluator version and case suite.
