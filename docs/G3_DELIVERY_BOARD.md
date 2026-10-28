# Second Source — G3 Delivery Board / Acceptance Gates

**Snapshot:** 2026-10-28 10:46 IST. G3-B code head `aeed582483cbf0f2d57bfb53a4fef948273d9ec6`; fetch before acting. No invented progress.
**Owner deadline:** 2026-11-05 07:30 IST, target November 4 IST submission.
**Source contract:** [G3_IMPLEMENTATION_CONTRACT.md](G3_IMPLEMENTATION_CONTRACT.md). Read before coding.

| ID | Owner | Task | Current observed state | Gate to DONE |
|---|---|---|---|---|
| G2-REVIEW | ChatGPT + owner | Evaluate PR #1, G2 operator evidence, CI, merge decision | **DONE / VERIFIED MERGE:** PR #1 merged to `main` at `9ed81cce406e0adf91ecc36e94d2263265366c30`; push CI run `40572246014` succeeded on Linux/Windows. Real G2 run remains `real-g2-20261027T192406Z-5482abee`; operator-reported estimated usage `$0.012715`, zero uncertain usage. | DONE |
| G3-A1 | Muse | Versioned typed CandidateSpec + ProposedFile manifest + schema validator | **YELLOW / CODE GREEN:** original Muse checkpoint `8f881cd...` was independently rejected; hardened interface was synchronized with `main` by `208aeb4e...`; final post-freeze wire-semantics review is accepted at `a1a137649a51178e30f438e1069788a0e8b2de81`. Strict params/effects/digests are present. **OPEN:** action-parameter error precedence differs for text vs dictionary loading; Muse correction not yet observed at `origin/g3/candidate-synthesis` `bfd605d...`. | Independent G3-B evaluator must accept the frozen interface; no real candidate claim yet |
| G3-A2 | Muse | Trusted bounded JSONL DSL runtime with fresh state per sequence | **YELLOW / CODE GREEN:** exact flat G0 action wire fixed; trusted control now fails closed on mismatch; interpreter detaches mutable spec aliases. GitHub run `40576855908`: **179 passed, 2 skipped, 0 failed** on Ubuntu/Py3.11 and Windows/Py3.12; Windows bootstrap `BOOTSTRAP_OK`. Non-object actions are explicitly outside dict-only `ReferenceProtocol` and fail the sequence closed; missing/non-string command within a dict maps to `unknown_command`. | G3-B resource/data-only engineering controls verified; retain no-arbitrary-code-sandbox limitation and resolve precedence/provenance blockers |
| G3-A3 | Muse | Real-provider candidate generation integration + MOCK mode | **YELLOW:** model adapter path exists; generation context now validates nested public-manifest/evidence/hypothesis provenance and re-redacts at final boundary. Mock/trusted controls only. **No paid G3 call; G3 spend `$0.00`.** | Real Muse CandidateSpec requires explicit owner spend authorization *after* G3-B sealed evaluator is green |
| G3-B0 | Codex | **Read-only** contract/security audit and sealed-test plan while Muse works | **DONE:** Codex audited `8f881cd37...`, ran 164 non-billable Windows tests, reproduced public mock **0/3**, and filed severity-ranked wire/verifier/isolation/resource findings. Record: `docs/G3_B_PHASE1_AUDIT_2026-10-28.md`. | DONE |
| G3-B1 | Codex | DifferentialVerifier adapter + strict comparator hardening | **DELIVERED / CONDITIONAL GREEN:** `aeed582...`, draft PR #4. Strict probes 26/26; exact-head CI `40581058875` green on Linux/Windows, Windows bootstrap green. Independent coordinator review complete for engineering slice only. | Final provenance/security requirements below; no real candidate accuracy claim |
| G3-B2 | Codex | Protected suite, controls, isolation and real-run provenance | **ENGINEERING CONTROLS VERIFIED:** external pinned suite 25 cases, positive 25/25, three bad DSL controls fail 2/2/1 cases; bounded workers and leakage/resource tests pass. **REAL-RUN PROVENANCE OPEN:** require attested reference, pinned scope/signatures/G2 provenance and immutable candidate receipt. | Reject substituted reference/forged origin; bind exact inspected generation request; independently verify Muse correction; combined CI green |
| G3-C | Muse + Codex reviewed by ChatGPT | Up to 2 bounded repair cycles, same sealed suite | NOT STARTED | Real observed before/after lift; no scope expansion; may be CUT if deadline |
| G3-D | ChatGPT + assigned implementer | Reproducible single operator command + redacted G3 report, acceptance document | NOT STARTED | Real model receipts, spec hashes, scored independent run, documented false claims prevented |
| DEMO | Owner with ChatGPT | <=180s recording, correct provenance, submission fields | Planning doc exists; recording/URLs NOT VERIFIED | Public working repo/video, exact metrics/limitations, logged submission confirmation |

## Critical-path acceptance definition
1. **A valid real Muse-generated CandidateSpec** created solely from approved public/redacted context. Response ID/receipt; no hardcoded benchmark-perfect candidate.
2. CandidateSpec verified by `ScopeGuard.validate_candidate_files` and DSL schema; no executable text from model.
3. Trust-owned interpreter runs candidate with fresh state and bounded CPU/wall/memory semantics appropriate to verified local runner; do not claim OS-level isolation if not installed.
4. Independent `DifferentialVerifier` computes real nonempty gold `passed/failed/indeterminate/total`; model sees ONLY `model_feedback()`.
5. Adversarial validation: path traversal, forbidden command, external side effect, credential leakage, evaluator read attempt, candidate DSL escape, output budget and reset mismatch.
6. Reproducible Linux/Windows CI, explicit real-vs-mock labels, run reports with correct cost uncertainty.
7. All material claims reflect actual evidence. Never assert full equivalence from a finite suite.

## Before opening a new coding task
- Fetch current GitHub SHA; identify exact file owner and last published interface.
- Read dependency contract and nearest tests. Name ALL assumptions.
- No overlapping module rewrite; stage one change; run tests.
- Report completion only with exact SHA and CI; screenshots or narrative alone are not acceptance.

## Daily stop/go sequence (IST)
- **Oct 28:** verify G2 receipt/CI and merge authorization; G3-A interface + safe runtime slice; Codex read-only G3-B audit.
- **Oct 29:** working candidate adapter + independent sealed suite under mock; add real generation path gated by credentials/budget.
- **Oct 30:** owner-authorized first real G3 candidate generation and scored candidate run; fix only observed flaws.
- **Oct 31:** optional bounded repair and comparable baseline run; build one verifiable demo story.
- **Nov 1–2:** hardened fresh clone, documentation, redacted samples and video rehearsals. Additional target only if critical path passes.
- **Nov 3:** feature freeze, license/README/threat model, video capture.
- **Nov 4:** public links/permission checks, submission, save receipt early.

## Decision ledger (no silent assumptions)
- `D-001` G2 merge: **DONE.** Owner authorized; PR #1 merged at `9ed81cce...` after green integration review.
- `D-002` G3 execution style: **APPROVED ENGINEERING DIRECTION** (existing G3 spec): restricted declarative DSL, no model-generated code execution on Windows.
- `D-003` G3 model spend: **NOT YET AUTHORIZED.** G3 spend remains `$0.00`; do not make a real synthesis/repair call until owner explicitly authorizes it after G3-B evaluator acceptance.
- `D-004` Optional second target/browser/UI/cloud: **DEFER**, cut if G3 not independently evaluated by Oct 31.
- `D-005` Actual selected G2 action payloads/outputs: **NOT PROVIDED HERE**. Do not infer from proposal name.

## Short reports
- **Green:** tested + independently verified. **Yellow:** code present but acceptance evidence missing. **Red:** blocked/fails. Never label a gate green merely because code compiled.

## Next-session continuation ? coordinator direction verified

Source: https://github.com/Ankit6149/second-source/pull/4#issuecomment-6461226733

- Continue autonomously on existing `g3/verifier`; no additional branches or Muse-owned edits.
- Complete real-run attested reference/suite/comparator/candidate-receipt provenance; generic adapters remain explicitly TRUSTED_CONTROL only for claims.
- Bind approved G2 observations/hypotheses and pinned public scope/signatures to the exact inspected request; caller mappings/marker scans alone do not authenticate provenance.
- Independently verify Muse's committed precedence correction; fetch/integrate the updated integration branch before claiming combined verification.
- Keep PR #4 and PR #3 draft/unmerged until blockers are dispositioned and required approvals are obtained. No paid call authorization.
- Local Windows: 250 passed/3 skipped. Code-head CI: Linux 250/3, Windows 251/2 plus passing bootstrap. Controls are NON_AI; G3 is NOT ACCEPTED. See `G3_VERIFIER_ACCEPTANCE.md` and current handoff.
