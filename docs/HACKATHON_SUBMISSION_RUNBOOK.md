# Second Source â€” Hackathon Submission & Demo Runbook

**Status pointer - 3 November 2026.** Use [issue #25](https://github.com/Ankit6149/second-source/issues/25) for current heads, scientific review and release gates. The older delivery-board and dated sections below are historical unless independently updated. This document does not authorize inference, credentials or deployment. Current verified scorecard is in "Final measured scorecard" below; production: https://second-source-alpha.vercel.app/ - routes /, /evidence/, /console/, /app/, /lab/ verified signed-out with 0 console errors; main 1e09d15 (1e09d15).

**CURRENT - 3 November 2026:** Portal submission is NOT done; no receipt exists. Video v3 is local only (.runs/submission-v3/second-source-v3.mp4, 170.02s, SHA-256 20E0079343E93B06C80361DCF7EFE3AD9850F07E9A808969C492FB25556F548A) and NOT yet publicly hosted. Production https://second-source-alpha.vercel.app/ routes /, /evidence/, /console/, /app/, /lab/ verified signed-out with 0 console errors. Historical REAL_MODEL Muse ledger 14/25; provider attestation incomplete. Meta Vikunja packet EXECUTED (REAL_MODEL): C 2/6, D 1/6, 3 calls, digests matched, $0.50 reservation cap, receipts lost to a driver crash. Track Indie. Deadline: Nov 4, 9:00 PM ET (Nov 5, 7:30 AM IST) via Cerebral Valley portal. Judge-facing G3 evidence: [JUDGE_EVIDENCE_G3.md](JUDGE_EVIDENCE_G3.md).

## Final measured scorecard â€” 3 November 2026 (release review)

**Not submitted. No portal receipt exists.** Only the owner submits, using the exact steps in SUBMISSION_DRAFT.md (Owner-only portal steps). Final main SHA: 1e09d15 (main at 1e09d15).

- Gemma arm A (prior only): **0/6** â€” `GEMMA_TEST`, model-authored, scored.
- Gemma arm C (coverage-grounded): **2/6** - `GEMMA_TEST`, model-authored, scored. B: unmeasured. D: selection fixed/verified (strict parse, 6 probes, 27 observations), synthesis blocked by provider 429/500 (INFRASTRUCTURE), unscored (never 0/6).
- Oracle control (Vikunja): **6/6** â€” `NON_AI`, runtime-supplied. Never a model result.
- Historical ledger: **14/25** â€” `REAL_MODEL`, model-authored (Muse Spark 1.3, frozen 25-case suite; not comparable to Vikunja).
- Hybrid H_hybrid: **3/6 re-measured (cases 0, 2, 3)** - GEMMA_TEST, model-authored, scored (compiler-assisted model synthesis).
- Gemma per-route repair (semantic admission): **2/6** - GEMMA_TEST; admitted but regressed held-out from 3/6 to 2/6. Measured negative result.
- Public-verification gate audit: **0/8 model route edits kept, 5 regressed public conformance, 3 tied; gated candidate = compiled NON_AI 6/6** - NON_AI mechanism over GEMMA_TEST edits. Damage-prevention audit, NEVER a model score.
- Meta Vikunja C_grounded: **2/6 (cases 1, 3)** - `REAL_MODEL` (muse-spark-1.3), EXECUTED, admitted.
- Meta Vikunja D_active: **1/6 (case 3)** - `REAL_MODEL`, EXECUTED, admitted; selected probes D1, D4, D5, D6, D7; 22 probe observations. Packet total 3 calls, digests matched, $0.50 reservation cap; receipts lost to a driver crash. Record: `.runs/vikunja-model/meta_arms_result.json`.
- Compiled evidence `EVIDENCE_COMPILED` (`NON_AI`, evidence-compiled): **6/6** â€” deterministic transcription of the 20 public observations (`scripts/evidence_compiler.py`, spec sha256 `a5c9104eâ€¦`); status-mutation control 2/6. Never a model result; Gemma C stays 2/6.
- Browser / motion: **bounded recorded slice** - browser-slice/ held-out drag RMSE 1.054px and 1.741px, adversarial variants detected; in-app execution unavailable, one owned fixture only. NON_AI.

## Current evidence and submission stop

Use [single delivery board](G3_DELIVERY_BOARD.md) for exact source/CI and [approval package](G2_G3_APPROVAL_PACKAGE.md) for spent grants/evidence identities. PRs #5-#8 merged. G3-D exists and is engineering-tested. New genuine G2 has complete original hypotheses/receipts; older missing historical statements remain missing.

The prior real-attempt summary is superseded by the recorded result above; consumed authorizations do not authorize another inference, retry or repair. NON_AI controls never measure Meta quality. A local synthetic-identity fixture journey does not establish hosted product acceptance.

Keep submission checklist boxes unverified until direct evidence exists. Plans/example records/commits do not establish a submitted portal entry. Routine merges follow [charter](COORDINATION_CHARTER.md); paid/credential/deployment operations remain separately gated.

## One-sentence pitch (working)

**Second Source learns how an explicitly authorized software feature behaves by asking better black-box questions, then builds a scoped independent implementation and checks it with a separate evaluator.**

The product **does not** recover source code, bypass access controls, clone unspecified features, or promise equivalence on every possible input.

## Submission copy and local recording outline

**Problem.** Teams replacing an undocumented system often know its inputs and
outputs but not the rules behind them. Plausible generated code can miss the
state transitions and errors that users rely on.

**Approach.** Within an explicitly authorized scope, Second Source captures
observations, records evidence and hypotheses, admits a constrained candidate,
and compares candidate behavior against a separately managed evaluation suite.
The workspace exposes supported fixture targets, run state, verification and a
sanitized integrity export. See `product/README.md` for the local commands.

**Evidence.** The historical genuine Meta `muse-spark-1.3` candidate is reported
at 14/25 (9 schema and 2 error mismatches); the original local receipts passed internal consistency checks and the pinned-source,
pinned-suite offline replay; provider and ephemeral broker signatures remain unverified. Separately, the local ledger and owned HTTP
fixtures are deterministic NON_AI controls. The HTTP 25/30 to 30/30 repair uses
previously collected active evidence; it is not a genuine Meta run or proof of
AI independently discovering a fix. Scores from different suites are not a
head-to-head comparison.

**Recording sequence.** Show the authorized target and its scope, start the
local NON_AI run, show real persisted stage events, verification and candidate
lineage, then download and verify the export. Switch to the separately labeled
historical Meta record and explain its failures. State that test identities and
Storage are synthetic, hosted authentication is unverified, and no genuine repair
improvement is claimed. Inspect the recording and exported material for private
data before sharing. Do not represent a browser automation run as a live Google
login, or a checksum as provider attestation.

**Before submission.** The owner-provided participant guide requires a three-minute
demo video. Confirm the current format and submission details in the organizer's
participant interface. Open all final links in a private browser, preserve the tested
commit and artifact digests, and retain an actual portal confirmation. The
official event page lists the November 4, 9 p.m. Eastern deadline, subject to
change: <https://dev.meta.ai/events/global-hackathon>.

## What the demo must prove (in order)

1. **Owner-specified scope:** observation commands, requested implementation modules and exclusions are visibly distinct.
2. **Opaque authorized reference:** a stateful owned fixture accepts structured actions; model has no access to reference code or withheld tests.
3. **Real Muse reasoning:** a real Meta response creates evidence-linked competing hypotheses, proposes a distinguishing experiment, and records a true provider receipt.
4. **Scope guard:** an unauthorized action is declined; allowed sequence runs; evidence hashes are stored.
5. **Independent reconstruction:** model-generated minimal candidate (not hand-written fixture/canned response) runs in a constrained executor; all artifacts map to allowed requirements.
6. **Blind evaluation:** candidate and reference run against the same withheld suite outside model context. Publish numerator/denominator, failure/indeterminate counts.
7. **Bounded repair:** if implemented and observed, show before/after improvement using the **same** independent tests. Never claim repair if not demonstrated.
8. **Final audit view:** runtime, model ID, estimated cost vs provider billing, exclusions, unknowns, evidence references.

## Required three-minute recorded story

| Elapsed | Visual / voiceover | Proof artifact |
|---|---|---|
| 0:00â€“0:20 | "Tell Second Source **exactly what to learn and rebuild**." Three scopes, forbidden operations | ScopeContract and ScopeGuard decision |
| 0:20â€“0:55 | Observe owned stateful program. Show two competing evidence-cited hypotheses | Redacted ledger artifact IDs; real Meta receipt |
| 0:55â€“1:25 | Muse selects a discriminating multi-action experiment. Guard checks each step. See result | Real model-selected proposal and runner observations |
| 1:25â€“1:55 | Build only the requested behavior, no account system or unrelated feature | Candidate manifest, output tree |
| 1:55â€“2:30 | Hidden differential tests score implementation. Fix failure only if verified | Evaluator result, bounded repair before/after |
| 2:30â€“2:50 | Deliberately reject a forbidden action or extra subsystem | Machine-readable policy denial |
| 2:50â€“3:00 | Show measured score, limitations and GitHub URL | Final honest evidence report |

**Recording requirement:** pre-seed a reproducible authorized run; do not impersonate a real Meta execution with mocks or display invented scores. If an acceptance predicate is missing, shorten/replace its demo segment and clearly disclose the limitation.

## Final submission materials

- [ ] Public repository: https://github.com/Ankit6149/second-source (review secret/history scan; LICENSE, setup, architecture, safety)
- [ ] One clean reproduction path from fresh checkout (Python 3.11+, Windows + Linux) with nonbillable fixture demonstration
- [ ] Real Meta model identifier, response ID, redacted prompt/output schema, observed token usage, cost estimate and genuine run ID
- [ ] At least one model-selected *in-scope* experiment, evidence hashes, prediction-vs-observation record
- [ ] Model-generated candidate **if claimed** with its manifest, bounded executor proof, reference separation
- [ ] Independent withheld evaluation, reported denominator, concrete passed/failed/indeterminate counts
- [ ] Controlled negative case: forbidden command/output file rejected, no secret or privileged action disclosed
- [ ] Required demo video: v3 local file 170.02s (SHA-256 20E0079343E93B06C80361DCF7EFE3AD9850F07E9A808969C492FB25556F548A), NOT yet publicly hosted - owner must upload, verify signed-out, and paste public URL; confirm portal upload details
- [ ] Live hosted demo URL **only if working and safe**; fallback local deterministic demo noted as such
- [ ] Screenshot/thumbnail: scope > hypothesis > experiment > evidence > candidate > score
- [ ] Description: problem, technical novelty, Meta API use, safeguards, target users, limitations, comparison against baseline
- [ ] Indie developer track and prize category checked against the actual submission form
- [ ] Submission confirmation receipt and links opened in signed-out/browser-private test
- [ ] Disable/rotate exposed keys if any; no private run archives or gold cases in commit
- [ ] Save final tested commit SHA and environment versions

## Accurate claims register

| Statement | Conditions before saying it |
|---|---|
| "Second Source uses Meta Muse" | Genuine live response ID and allowed experiment included in a run |
| "It learns behaviors by experimentation" | Distinguishing predictions, model-selected action, guard approval and actual reference outcome |
| "It reconstructs software" | Independently generated runnable candidate, not a hand-written mock or copied fixture |
| "It verifies correctness" | Withheld independent reference/candidate test suite, nonzero denominator and failure disclosure |
| "It fixes errors" | Same sealed suite before and after verified bounded repair |
| "Safe" | State precise safety boundaries, tests and residual risks; never imply production sandbox without evidence |
| "Works with websites" | Live owned HTTP/browser adapter tested; otherwise label planned |
| "Zero-cost" | Not valid for real model calls. Separate internal estimates and actual provider billing |

## ARCHIVED planning schedule (27 October 2026, IST)

These were initial targets, not completion claims. Use the current delivery
board for the active critical path and dated P0/P1/P2 decisions.

- **Oct 28**: close G2 model-selection gate; record sanitized genuine Meta result; merge reviewed G2.
- **Oct 29â€“30**: build EXEC-010 candidate manifest + limited generation; use a safe constrained candidate representation, not arbitrary model code executed on host.
- **Oct 31**: EXEC-011 independent candidate evaluation and bounded repair; baseline metrics.
- **Nov 1**: compare active-vs-fixed probing on the same owned fixture and budget. Add second owned adapter only if core path is reliable.
- **Nov 2**: implement minimal readable evidence/results presentation; fix top security defects; start screencast rehearsal.
- **Nov 3**: scope/feature freeze, fresh-clone test, public docs, demo recording and captions.
- **Nov 4**: upload, verify video/repo/demos from private browser, submit, save confirmation well ahead of the **Nov 5 07:30 IST** cutoff.

**Cut rule:** If any milestone slips, drop cloud coordinator, general-purpose browser crawling, authentication automation and decorative UI. Preserve one honest end-to-end authorized fixture and independent evaluator.

## Judge interview preparation: defend these five decisions

1. **Why active experiments?** Compare a fixed probe baseline vs Muse-selected discriminating queries under the same budget and withheld test suite; report actual measured delta, not assumed gains.
2. **Why three scopes?** Being allowed to observe does not imply permission or intent to build everything seen. ScopeGuard rejects unapproved observation and generated modules.
3. **Why independent verification?** The agent can propose claims but cannot see gold tests or award itself success; evaluator owns the reference and hidden suite.
4. **Why explicit cost/security controls?** Real requests are opt-in, estimated spend and uncertain outcomes recorded, credentials kept local, external effects need trusted approval.
5. **Where can it fail?** Partial observability, unstable reference behavior, model formatting errors, budget exhaustion, no verified sandbox, or uncovered edge cases. Show the failure categories and honest stop reasons.

## ARCHIVED SNAPSHOT â€” first three owner attempts (27 Oct 2026)

The following snapshot is superseded. A later local G2 run recorded an accepted
experiment; G2 and G3 foundation PRs subsequently merged and G3-D is now coded.
See the board for current new G2 evidence, consumed G3 failures and backend gates.

- G0/G1: guarded owned fixture and independent verifier implemented.
- G2: authenticated real Muse calls observed; first response malformed, third attempt completed 2 model calls but **no accepted action**. Live experiment not yet accepted.
- PR: integration branch `integrate/g2-discovery`, do not claim merged until GitHub confirms it.
- G3 synthesis/repair and end-to-end demo: **not implemented/verified** at this milestone.

All timestamps, pass counts and costs in the final submission MUST come from actual run receipts, not this planning runbook.

## Evidence, contribution and submission checks â€” 1 November

- Historical G3: original local records bind candidate `ee1f3f32e66050bbdf2dde86aaba09e56d17b25c21c35762eeea6208c2a146cd` to suite `0423935021db574bb68f654c1c37896c6ad4f6e5c40707c1bbe38459178b015b`. An offline replay using source commit `54d5f7947d200479aac0f8bd5cced35b4f1084ed` reproduced 14/25, with 9 schema and 2 error failures. Run `scripts/audit_g3_receipt.py --help` for the local, hash-pinned receipt check. This does not verify a provider signature or the expired ephemeral broker HMAC. Original private material and sealed suite are not in the public bundle; an outside reviewer needs separately authorized access to reproduce that replay.
- Repository history dates the initial PRD and foundation to October 27, the reviewed backend integration to PR #21, and the integrated product and owned HTTP target to PRs #24 and #27 on November 1. Git records use one GitHub account under two display names. The owner must confirm real human collaborators, their actual work and ownership; Git authorship and AI agent labels alone do not establish those facts. Review `git log --reverse --date=iso --format="%ad %an %s"` before submission.
- The public repository has no tracked root LICENSE or NOTICE; the owner must determine the intended source license and review dependency obligations before claiming it is open source. The npm lockfile lists MIT, MPL-2.0, Apache-2.0, ISC, BSD and 0BSD dependencies; this inventory is not a legal review.
- A limited scan of the 226 tracked files found no GitHub-token, AWS-key, private-key-header or Slack-token pattern matches. This is not a complete secret scan and does not cover historical commits, alternate token formats, private artifacts or deployed environments. Do not publish local `.runs` wholesale.
- The owner-provided guide requires a three-minute video. Video v3 (170.02s, SHA-256 20E0079343E93B06C80361DCF7EFE3AD9850F07E9A808969C492FB25556F548A) is local only and NOT yet publicly hosted; it needs human visual/audio review, publication to a judge-accessible location, and an unauthenticated playback check; no public video link or portal confirmation exists yet. The [official event page](https://dev.meta.ai/events/global-hackathon) lists November 4 at 9 p.m. Eastern as the submission deadline.
- A future Gemma result must identify its own provider, model, authorization, usage and evaluator receipt. It must never use a Meta credential, be relabeled as Meta evidence, or run before its exact packet and budget are approved. No Gemma transport or paid call is enabled by this note.
