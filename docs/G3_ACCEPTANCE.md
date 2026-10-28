# G3 acceptance - current verdict and historical evidence

**Status pointer - 29 October 2026 IST.** Use the [single current delivery board](G3_DELIVERY_BOARD.md) for exact published SHA/CI, both consumed real G3 attempts, evidence and backend acceptance. This document does not authorize inference, credentials or deployment.

## CURRENT - 29 October 2026 IST

GO for source-specific tested nonbillable CLI engineering baseline; NO-GO for full backend/product acceptance or genuine reconstruction success. The [single delivery board](G3_DELIVERY_BOARD.md) holds exact source/CI/evidence and remaining gates.

PRs #5-#8 merged. Main `0aba3bf42b735ae911b8b471aad43972abfa8d9d` passed [CI 40747405916](https://github.com/Ankit6149/second-source/actions/runs/40747405916): Linux 434/0/3, Windows 435/0/2, bootstrap 435/0/2 BOOTSTRAP_OK. G3-D mock/preflight/archive/report code exists. New local backend work is not covered by this CI.

New genuine G2 has complete original hypotheses/citations/two receipts; missing 27 October history remains unrecovered. Both real G3 grants consumed: no admitted candidate/evaluation/score. Exact old field rejection causes unknown. PR #8 cannot recover them. No inference/retry/repair/credentials authorized.

Trusted25/25, negative 2/2/1 and mock 22/25 are NON_AI. Integrated backend/API/recovery/security/export and authentic reconstruction acceptance pending. Routine merges follow updated [charter](COORDINATION_CHARTER.md): exact-head CI, independent review/protections. No frontend expansion/production-readiness claim.

## ARCHIVED SNAPSHOTS — G3-A / early G3-B

Everything below records the dated checkpoint named in that section. Earlier
open defects, branch names, PR states and next steps are superseded by the
current board; they are retained as audit history, not active instructions.

**Gate under test:** G3 contract — a real Muse model generates a runnable
candidate spec from authorized black-box observations; a trusted runtime
executes it; the independent verifier scores it on a sealed suite.

**Verdict: G3 NOT DEMONSTRATED.** No real candidate generation has occurred.
This branch now contains G3-A and G3-B engineering evidence; G3-B is conditionally reviewed, with real-run provenance work still open.
Nothing below is a Muse-generated candidate score.

## Independent review correction — 28 October 2026

ChatGPT reviewed Muse's first G3-A checkpoint at
`8f881cd37c99acb5c8045bf9c3441e06920d373e` and found a **blocking protocol
mismatch**: `CandidateInterpreter` accepted nested
`{"command":"add","params":{...}}` actions while the trusted G0 reference
and sealed verifier use flat `{"command":"add","label":"...","amount":...}`
actions. The original mock demo asserted only `total == 3`, so its tests
could pass even when all candidate/reference comparisons failed.

That checkpoint is therefore **not accepted as a clean G3-A interface** even
though its document reported 49 local G3 tests. Those local counts were not
GitHub-CI verified because the branch had no PR/workflow run.

The follow-up branch fixes:
- pin the candidate runtime to the exact flat G0 ReferenceProtocol action wire;
- make the non-sealed trusted control demo fail unless all public control cases
  pass;
- pin generated command effects to the operator-owned public contract so
  `list`/`total` cannot mutate state and `remove` cannot create/aggregate;
- restrict v1 lookup to in-memory id lookup and reject contradictory bounds;
- close the top-level generation context and redact again immediately before
  the model boundary;
- preserve mock / trusted-test-fixture / real origin separation.

**VERIFIED G3-A code gate:** final interface SHA `a1a137649a51178e30f438e1069788a0e8b2de81`; GitHub Actions run `40576855908` completed successfully on Ubuntu/Python 3.11 and Windows/Python 3.12 with **179 passed, 2 skipped, 0 failed** on each OS; Windows bootstrap returned `BOOTSTRAP_OK`. Canonical-main synchronization is contained in history at `208aeb4e7ee5559e176daccd19fc2b7c1eb207d7`. No paid G3 model call has occurred; G3 spend is `$0.00`.

## G3-A deliverables now present on `g3/candidate-synthesis`

| # | Deliverable | Files | Acceptance state |
|---|---|---|---|
| 1 | Versioned `CandidateSpec` / manifest + scope-pinned loader | `src/second_source/candidate_spec.py` | code green; hardened after independent findings |
| 2 | Trusted data-only interpreter implementing G0 ReferenceProtocol | `src/second_source/candidate_runtime.py` | flat wire fixed; bounded trusted worker delivered in G3-B; precedence correction remains open |
| 3 | Malformed/adversarial rejection and effect-smuggling tests | `tests/test_g3_candidate_*.py` | integrated in the frozen 179-pass G3-A cross-platform suite |
| 4 | Mock generation boundary + real adapter skeleton | `src/second_source/candidate_generation.py` | nested provenance hardened; no billable call made |
| 5 | Non-sealed trusted positive-control demo | `src/second_source/g3_mock_demo.py` | positive control required to be 3/3 or exit nonzero; never labeled AI/sealed |
| 6 | Codex phase-1 independent audit | `docs/G3_B_PHASE1_AUDIT_2026-10-28.md` | **complete**; verifier/resource engineering slice delivered in G3-B; real-run provenance remains open |

## What this still does NOT prove

- No genuine Muse-generated CandidateSpec exists.
- No real-run attested evaluator/candidate provenance acceptance exists yet.
- Sealed TRUSTED_CONTROL scores exist; no genuine model-generated candidate score exists.
- No real repair or before/after lift exists.
- No active-vs-fixed baseline result exists.
- No production sandbox or website adapter exists.

## Next acceptance sequence

1. Current branch passes full Linux/Windows CI and the trusted mock control is
   3/3 with explicit NON-AI / NON-SEALED labels.
2. **DONE:** Codex phase-1 audit is recorded and its reproduced findings are dispositioned.
3. **ENGINEERING SLICE DELIVERED:** G3-B code `aeed582...` is conditionally reviewed; finish real-run provenance controls and independently verify Muse precedence corrections before integration acceptance.
4. Owner explicitly authorizes a bounded paid Muse candidate-generation call.
5. The real generated spec is validated, executed by the trusted interpreter,
   and scored by the sealed evaluator with exact counts.
6. Repair is optional and may be claimed only with a genuine unchanged-suite
   before/after result.

## Verified G3-B engineering checkpoint - 28 October 2026

Code: `aeed582483cbf0f2d57bfb53a4fef948273d9ec6`, from frozen coordinator baseline `bfd605d...`.
At this historical checkpoint PR #4 was draft/unmerged. It subsequently merged;
see the current board for exact merge/source/CI identities.
Exact-code CI: https://github.com/Ankit6149/second-source/actions/runs/40581058875 ? success on Linux/Python 3.11 (250 passed/3 skipped) and Windows/Python 3.12 (251 passed/2 skipped, bootstrap reproduced the result and returned BOOTSTRAP_OK). Local Windows: 250 passed/3 skipped.

Strict verifier probes: 26/26; baseline failed 24/26. External suite: 25 cases, NON_AI positive control 25/25; three deliberate DSL defects fail 2, 2 and 1 cases. Bounded reference/candidate workers, isolation/resource tests and aggregate-only feedback are implemented. Full evidence: `G3_VERIFIER_ACCEPTANCE.md`.

Coordinator source/CI review is **CONDITIONAL GREEN for engineering**, not G3 acceptance. Required before a real run: pinned/attested reference identity, frozen suite/comparator, immutable candidate origin/receipt, approved G2 observation/hypothesis and scope/signature provenance, exact request-to-broker binding, and independently verified Muse precedence correction. Latest direction: https://github.com/Ankit6149/second-source/pull/4#issuecomment-6461226733.

No real G3 generation or repair has occurred. No merge, paid call or arbitrary-code sandbox is authorized by this checkpoint; G3 model spend remains $0.
