# Second Source — G3 Delivery Board / Acceptance Gates

**Snapshot:** 2026-10-28 IST. Update after each verified commit. No invented progress.
**Owner deadline:** 2026-11-05 07:30 IST, target November 4 IST submission.
**Source contract:** [G3_IMPLEMENTATION_CONTRACT.md](G3_IMPLEMENTATION_CONTRACT.md). Read before coding.

| ID | Owner | Task | Current observed state | Gate to DONE |
|---|---|---|---|---|
| G2-REVIEW | ChatGPT + owner | Evaluate PR #1, G2 operator evidence, CI, merge decision | Live G2 *minimum* satisfied per operator-reported projection; PR open/unmerged; latest pre-doc SHA `6ee6698` CI green | Current PR SHA/CI checked, security diff approved, owner explicitly approves merge |
| G3-A1 | Muse | Versioned typed CandidateSpec + ProposedFile manifest + schema validator | NOT STARTED/NOT VERIFIED at handoff | Rejects malformed DSL, overbuild, forbidden effects/paths and unknown commands |
| G3-A2 | Muse | Trusted bounded JSONL DSL runtime with fresh state per sequence | NOT STARTED | Executes data-only rules, no eval/subprocess/network, deterministic outputs and resource limits |
| G3-A3 | Muse | Real-provider candidate generation integration + MOCK mode | NOT STARTED | Exact curated model input only; mock end-to-end test; actual live run requires owner spending approval |
| G3-B0 | Codex | **Read-only** contract/security audit and sealed-test plan while Muse works | NOT STARTED | Filed independent interface risks and evaluator expected result envelope without leaked gold cases |
| G3-B1 | Codex | DifferentialVerifier adapter for trusted CandidateSpec runtime | BLOCKED on Muse G3-A interface checkpoint | `ReferenceProtocol.execute_sequence` works on identical reset/action sequences; no evaluator self-grading |
| G3-B2 | Codex | Protected sealed-suite + positive/negative controls + leakage tests | BLOCKED on G3-B1 / isolation design | Accurate passed/failed/indeterminate/total, sealed inputs unavailable to model, mocks labeled |
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
- `D-001` G2 merge: **OWNER DECISION REQUIRED**. G2 minimum is evidenced in operator-provided local projection; independent live repeat not required, but final PR diff/CI must be checked.
- `D-002` G3 execution style: **APPROVED ENGINEERING DIRECTION** (existing G3 spec): restricted declarative DSL, no model-generated code execution on Windows.
- `D-003` G3 model spend: **NOT AUTHORIZED IN THIS HANDOFF**. Budget suggested in G3 spec is an example, not consent.
- `D-004` Optional second target/browser/UI/cloud: **DEFER**, cut if G3 not independently evaluated by Oct 31.
- `D-005` Actual selected G2 action payloads/outputs: **NOT PROVIDED HERE**. Do not infer from proposal name.

## Short reports
- **Green:** tested + independently verified. **Yellow:** code present but acceptance evidence missing. **Red:** blocked/fails. Never label a gate green merely because code compiled.
