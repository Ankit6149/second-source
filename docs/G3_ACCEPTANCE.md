# G3 Acceptance Log — independently generated candidate (MOCK ONLY)

**Gate under test:** G3 contract — a real Muse model generates a runnable
candidate spec from authorized black-box observations; a trusted runtime
executes it; the independent verifier scores it on a sealed suite.

**Verdict: G3 NOT DEMONSTRATED.** No real candidate generation has occurred.
Everything below is mock/trusted-fixture evidence for the G3-A mechanism,
plus the exact interface Codex needs for G3-B. Nothing here is Muse output.

## What exists (branch `g3/candidate-synthesis`)

| # | Deliverable | Files | Status |
|---|---|---|---|
| 1 | Versioned `CandidateSpec`/`CandidateManifest`, scope-pinned loader | `src/second_source/candidate_spec.py` | 16 tests pass |
| 2 | Trusted DSL interpreter (`ReferenceProtocol`, in-memory, no code execution) | `src/second_source/candidate_runtime.py` | 14 tests pass |
| 3 | Malformed/adversarial rejection (shell, egress, eval, imports, overbuild, oversize) | `tests/test_g3_adversarial.py` | 11 tests pass |
| 4 | Mock generation path + real adapter skeleton (no billable calls) | `src/second_source/candidate_gen.py`, `src/second_source/g3_mock_demo.py` | 8 tests pass |
| 5 | G3-B verifier contract for the independent evaluator | `docs/G3B_VERIFIER_CONTRACT.md` | written, unimplemented by design |

## Mock-only evidence (all artifacts labeled, none is model output)

- `python -m pytest tests/test_g3_*.py` → **49 passed** (16 spec + 14 runtime
  + 11 adversarial + 8 mockgen), exit 0, on the project venv.
- `python -m second_source.g3_mock_demo` runs a mock-transported
  trusted-test-fixture spec against the owned reference on 3 demo cases and
  prints `origin: mock`, `content_provenance: trusted-test-fixture`, spec
  digest, and per-case outcomes. Deterministic and non-billable.
- Origin discipline: `mock` (scripted transport) vs `trusted-test-fixture`
  (author-written content) vs `real` (genuine Meta response) are distinct
  labels asserted by tests; validation never upgrades an origin.

## Unresolved limitations (honest)

- No genuine Muse-generated candidate exists; DSL expressiveness against real
  model output is unproven (server-side validation fails closed, but the
  repair loop is untested).
- Sealed G3-B suite not yet authored; demo cases are NOT sealed evaluation.
- Reconciliation/trajectory attribution beyond final-step matching is future work.
- No guaranteed billing hard cap (ledger bounds attempts, provider billing
  is authoritative).

## Remaining real-model requirements

1. Owner-authorized `request_candidate_spec` run with key + budget → genuine
   receipt + spec digest.
2. Sealed G3-B evaluation with exact passed/failed/indeterminate counts.
3. Bounded repair (≤2) with before/after `delta_passed` on the identical suite.
4. Record observed values only; never relabel mock/fixture content as generated.
