# G3-B Phase 1 Independent Audit Record — 2026-10-28

**Auditor:** Codex  
**Mode:** read-only independent technical/security audit  
**Audited G3-A SHA:** `8f881cd37c99acb5c8045bf9c3441e06920d373e`  
**Canonical main observed:** `9ed81cce406e0adf91ecc36e94d2263265366c30`  
**Paid calls / credentials / repository writes during audit:** none  
**Audit verdict at audited SHA:** **BLOCKED**

This document records the Codex phase-1 response supplied to the coordinator.
It is not a retrospective claim that the audited SHA was acceptable. Several
findings have since been corrected on `g3/candidate-synthesis`; unresolved
items remain assigned to G3-B phase 2.

## Reproduced evidence at the audited SHA

- Codex ran 164 non-billable tests on Windows/Python 3.12.4, excluding the
  credential-reading live-smoke module before collection.
- The public G3 mock demo reproduced **0 passed / 3 failed / 0 indeterminate**.
- No GitHub workflow run existed for `8f881cd...`; cross-platform CI for that
  exact checkpoint was therefore unverified.
- Codex used focused synthetic probes to demonstrate the findings below.
- No evidence showed a real private-data leak; the generation finding was an
  exploitable admission-path defect, not a claim of observed exfiltration.

## Findings and coordinator disposition

| Severity | Codex finding | Status after coordinator hardening |
|---|---|---|
| BLOCKER | G0/reference actions are flat while G3-A consumed nested `params` | **FIXED**. Candidate runtime now consumes the exact flat G0 action dictionary; trusted control is required to pass 3/3. |
| BLOCKER | Existing `DifferentialVerifier` can false-pass Python-equal but JSON-different values and malformed result envelopes | **OPEN — G3-B PHASE 2**. Must be fixed with strict typed comparison/envelope validation before sealed scoring. |
| BLOCKER | Generation boundary accepted arbitrary nested caller context | **HARDENED, RE-AUDIT REQUIRED**. Closed top-level and nested provenance validation now rejects malformed evidence/hypothesis/public-manifest projections and re-redacts at the final model boundary. |
| HIGH | Accepted DSL combinations could crash aggregation or shadow record IDs | **FIXED/HARDENED**. Exact command parameter sets, integer aggregate-source checks, reserved response keys and contradictory-bound rejection are enforced. |
| HIGH | Declared semantics were incomplete (normalization/lookup/effect ambiguity) | **FIXED/HARDENED**. Unsupported normalization capability was removed; lookup is id-only; command effects are pinned to add/store, remove/id-delete, list/total read-only. |
| HIGH | Loader/runtime hashes and mutable nested aliases did not identify immutable behavior reliably | **FIXED/HARDENED**. Loader is sole spec-digest authority; interpreter reconstructs an independent validated CandidateSpec before execution. |
| HIGH | Resource containment/isolation was not proven; execution remained in-process | **OPEN — G3-B PHASE 2**. Candidate adapter must own trusted input/output/wall/CPU/memory limits and fail admission where enforcement is unavailable. Do not claim OS sandboxing yet. |
| MAJOR | Shared mutable suite actions and weak schema/runtime agreement | **PARTLY FIXED**. Provider schema now pins supported command parameter names and runtime DSL is stricter. G3-B must deep-copy/serialize sealed inputs independently for each side. |

## Required strict verifier behavior

Before any real candidate score is accepted, G3-B must demonstrate:

1. JSON type-strict comparison: `true` must not equal `1`; missing/extra keys
   and structurally different outputs cannot pass.
2. Reference and candidate result envelopes are validated before output
   comparison.
3. Invalid reference execution => **indeterminate**; invalid candidate execution
   against a valid reference => **failed**.
4. Nonzero exit, timeout/protocol inconsistency, partial/malformed observations
   and action-index/sequence mismatches cannot false-pass.
5. Legitimate target/business errors remain comparable behavior, not harness
   failures.
6. Each side receives an independent immutable copy of the same sealed action
   sequence.
7. Aggregate-only `EvaluationReport.model_feedback()` remains the sole
   inference/repair signal.

## Candidate adapter boundary accepted for phase 2

Codex proposed a trusted adapter with evaluator-owned limits:

```python
@dataclass(frozen=True)
class CandidateExecutionLimits:
    max_actions: int
    max_input_bytes: int
    max_output_bytes: int
    max_records: int
    wall_seconds: float
    cpu_seconds: float
    memory_bytes: int

class CandidateReferenceAdapter:
    def __init__(
        self,
        spec_bytes: bytes,
        contract: ScopeContract,
        *,
        limits: CandidateExecutionLimits,
    ) -> None: ...

    @property
    def spec_digest(self) -> str: ...

    def execute_sequence(
        self,
        actions: list[dict],
        *,
        sequence_id: str | None = None,
    ) -> SequenceResult: ...
```

The adapter must load only through `load_candidate`, preserve original G0
flat actions in observations, reset per sequence, return sanitized bounded
worker failures, and take all limits from trusted evaluator policy.

## Isolation/trust zones for phase 2

- **Generation worker:** public scope/signatures, approved redacted observations
  and hypotheses only. No reference source, sealed cases, repository history,
  run directories, credentials or general-purpose tools.
- **Provider broker:** approved provider credential and outbound inference
  request only.
- **Evaluator:** sealed suite, trusted reference, comparator, candidate artifact
  and detailed private results. No inference calls.
- **Candidate worker:** trusted interpreter, immutable candidate spec and only
  the current action sequence. No reference/gold/provider credential/network.

A directory convention alone is not isolation evidence. Phase 2 must test
symlink/junction escape, inherited environment/handles where applicable,
egress denial, oversized/deep inputs, hangs, cross-case state, label spoofing,
scope expansion and evaluator-information leakage.

## Phase-2 test groups

- `test_g3_verifier_wire_conformance`
- `test_g3_verifier_positive_control`
- `test_g3_verifier_negative_controls`
- `test_g3_verifier_behavior_categories`
- `test_g3_verifier_reset_and_replay`
- `test_g3_verifier_scope_denial`
- `test_g3_verifier_strict_comparison`
- `test_g3_verifier_adversarial_spec`
- `test_g3_verifier_isolation_and_feedback`
- `test_g3_verifier_accounting_and_reproducibility`

No hidden case inputs or expected outputs belong in model-visible artifacts.

## Coordinator state after phase 1

Phase 1 is **complete**. Phase 2 may begin only from the coordinator-frozen G3-A
SHA documented in the current delivery board. No real candidate accuracy,
sealed-suite performance, repair lift or G3 acceptance is implied by this
audit.
