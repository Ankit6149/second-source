# Submission draft Ã¢â‚¬â€ Meta Global AI Developer Hackathon (Indie)

**Status: DRAFT for owner review. Not submitted. No portal receipt exists.**
Deadline: **Nov 4, 9:00 PM ET** Ã¢â‚¬â€ https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit
Final `main` SHA: enter the live `main` HEAD at submit time (post-PR#48: `f559140` or later).
Production: https://second-source-alpha.vercel.app/ Ã¢â‚¬â€ routes `/` and `/app/` verified (former showcase routes redirect to `/app/`) signed-out with 0 console errors.

## Judge-first entry — the experience before the scorecard

**Lead with the problem, not the model benchmark.** A code generator can copy a screen while missing the hidden rules its users rely on. Second Source begins with a **permitted running black box**, forms testable hypotheses, observes edge cases, constructs an independent bounded candidate, and independently tests what actually matches.

**Judge-facing opening (proposed copy):** "Can you reconstruct software you can operate but cannot inspect? Second Source treats the running application as experimental evidence. Watch it discover what a screenshot never shows, generate a separate behavioral specification using Meta Muse, and check that candidate against an independent evaluator. It reports the errors, too — because the difference between plausible software and compatible software is what the tests reveal."

**Try first:** [Open the public landing](https://second-source-alpha.vercel.app/) to see the recorded reference-versus-candidate duplicate, amount-boundary and response-schema contrasts. Then [open the app](https://second-source-alpha.vercel.app/app/) for Reports and Compare. The former `/challenge/`, `/lab/`, and `/evidence/` routes now redirect to the app; do not submit them as separate demos. No live model or sealed evaluator runs in the public browser. The two actual NON_AI jobs (HTTP 30/30 control and Vikunja 11/19 **public** conformance) require a locally served app and local services; the hosted backend is not deployed.

**Proof, with provenance separated:** The ledger reconstruction was authored by genuine Muse Spark 1.3 and scored **14/25** on its own sealed suite (11 failures; incomplete provider attestation). A separate genuine Muse-assisted Vikunja hybrid scored **6/6 frozen and 6/6 extended**, but the NON_AI evidence compiler also scored 6/6 on both suites, so **no lift over that compiler is claimed**. The HTTP 25/30 → 30/30 improvement is **NON_AI**, not AI self-repair. These benchmarks must never be added together or depicted as comparable.

**Audience promise:** Second Source does not promise arbitrary code recovery, perfect equivalence or fully autonomous site cloning. Its current differentiated result is evidence-linked **behavioral investigation + bounded generation + independent measurement**. Never replace this with an unsupported blanket accuracy number.

**Publication dependency:** The v3 video is recorded locally but still needs a public playback URL, signed-out verification and an actual owner portal submission receipt. This draft is **not a submission confirmation**.

## Final measured scorecard (change only with a receipt)

| Entry | Label / provenance | Result | Notes |
|---|---|---|---|
| Gemma arm A (prior only) | GEMMA_TEST / model-authored | 0/6 | Scored. Gemma dev test, not Meta, not REAL_MODEL. |
| Gemma arm C (coverage-grounded) | GEMMA_TEST / model-authored | 2/6 | Scored. A vs C does not isolate the coverage-gate effect. |
| Hybrid H_hybrid (compiler-assisted model synthesis) | GEMMA_TEST / model-authored | 3/6 | Re-measured 3/6 (cases 0, 2, 3). Model edits compiled NON_AI facts per route; below compiled NON_AI 6/6; public conformance 7/19. |
| Gemma per-route repair (semantic admission) | GEMMA_TEST / model-authored | 2/6 | Admitted but regressed held-out from 3/6 to 2/6. Measured negative result; do not claim repair improvement. |
| Public-verification gate audit | NON_AI mechanism over GEMMA_TEST edits | 0/8 kept | Damage-prevention audit, NEVER a model score: 0/8 model route edits kept, 5 regressed public conformance, 3 tied; gated candidate = compiled NON_AI 6/6. |
| Gemma arm D | GEMMA_TEST | Unscored | Selection fixed and verified (strict parse, 6 probes, 27 observations); synthesis blocked by provider 429/500 - INFRASTRUCTURE, unscored. |
| Oracle control (Vikunja) | NON_AI / runtime-supplied | 6/6 | Hand-written oracle via generic interpreter. Never a model result. |
| Historical ledger | REAL_MODEL / model-authored | 14/25 | Muse Spark 1.3, frozen 25-case suite. Not comparable to Vikunja. |
| Meta Vikunja C_grounded | REAL_MODEL / model-authored | 2/6 | EXECUTED: 3 calls total for packet, digests matched, cases 1, 3. Record `.runs/vikunja-model/meta_arms_result.json`. Receipts lost to a driver crash; spend reservation-capped at $0.50. |
| Muse hybrid per-route (packet muse-hybrid-20261104) | REAL_MODEL / model-authored | Raw 6/6 frozen, 6/6 extended | EXECUTED 2026-11-04: 8 per-route calls (~$0.19 total across attempts incl. provider-failure bookings), durable fsync receipts in `.runs/vikunja-model/muse_hybrid_20261104/`. Public-conformance gate rejected every edit (gated candidate = compiler NON_AI, also 6/6 + 6/6); raw candidate evaluated once scored 6/6 frozen / 6/6 extended. Ties the compiler on both suites; no improvement over compiler claimed. |
| Meta Vikunja D_active | REAL_MODEL / model-authored | 1/6 | EXECUTED: case 3 only; model selected probes D1, D4, D5, D6, D7; 22 probe observations. Same packet/receipt note as C. |
| Compiled evidence | EVIDENCE_COMPILED (NON_AI) / evidence-compiled | 6/6 | Deterministic transcription of the 20 public observations (`scripts/evidence_compiler.py`); status-mutation control 2/6. Never a model result; Gemma C stays 2/6. |
| Browser / motion | NON_AI slice / evidence-compiled | Bounded pass | `browser-slice/`: spring-drag fit from observations only, held-out drag RMSE 1.054px and 1.741px, adversarial variants detected. In-app execution unavailable; one owned fixture only. |

Gemma arm B is unmeasured. Gemma arm D stays unscored (selection verified; synthesis provider-blocked 429/500, INFRASTRUCTURE) - never 0/6.

## Title

Second Source Ã¢â‚¬â€ evidence-first reconstruction of authorized black-box software

## One-liner

Second Source learns how an explicitly authorized system behaves by asking
black-box questions, builds a separate candidate implementation, and scores
it against a withheld evaluator Ã¢â‚¬â€ reporting matches, failures, and unknowns.

## Problem / impact (30%)

Teams inherit undocumented internal and legacy APIs whose behavior lives
only in the running system. A screenshot or prompt cannot reveal boundary
rules, state transitions, or error behavior. Second Source targets
authorized behavioral reconstruction for migration, maintenance, and
regression testing: observe Ã¢â€ â€™ hypothesize Ã¢â€ â€™ run distinguishing experiments
Ã¢â€ â€™ synthesize an independent candidate Ã¢â€ â€™ measure it blind.

## Meta AI use (25%)

- Genuine **Muse Spark 1.3** (`meta-direct`) performed G2 discovery
  reasoning (evidence-linked hypotheses, discriminating experiments) and
  G3 guided synthesis of a declarative candidate spec.
- Vikunja packet EXECUTED with genuine Meta `muse-spark-1.3`: C_grounded **2/6**, D_active **1/6** (REAL_MODEL, digests matched, 3 calls, $0.50 reservation cap; receipts lost to a driver crash).
- Measured result: **14/25** on a frozen sealed suite (9 schema, 2 error
  mismatches), response `chatcmpl-01a19314-Ã¢â‚¬Â¦`, 2,756/2,555 tokens, ~$0.014.
- Full provenance, concrete mismatches, and limits:
  [`JUDGE_EVIDENCE_G3.md`](JUDGE_EVIDENCE_G3.md) +
  [`evidence/g3-rev6-sanitized/`](evidence/g3-rev6-sanitized/).
- No repair improvement is claimed (rev-7 not executed; owner decision).

## Demo (25%)

- Video v3 (170.02s, local .runs/submission-v3/second-source-v3.mp4, SHA-256 20E0079343E93B06C80361DCF7EFE3AD9850F07E9A808969C492FB25556F548A): scope, observation, genuine Meta 14/25, NON_AI controls, honest limits. **NOT yet publicly hosted. Owner must upload publicly and verify signed-out before submitting.**
- Reports & exports (in /app/): comparison scoreboard, recorded public probes with per-step diff highlighting, versions and uncertainty - REAL_MODEL vs NON_AI always labeled (PR #34).
- muse-spark-1.3 Vikunja packet EXECUTED (REAL_MODEL): C_grounded 2/6 (cases 1, 3), D_active 1/6 (case 3), 3 calls total, digests matched, $0.50 reservation cap; receipts lost to a driver crash (no billing claim beyond cap). Record: `.runs/vikunja-model/meta_arms_result.json`.
- 2D browser reconstruction: assessed NO-GO for this window (docs/P3_BROWSER_SPIKE_ASSESSMENT.md); explicitly not implemented.
- Live local demo: `npm run demo:local` (product) Ã¢â‚¬â€ synthetic identities,
  loopback-only HTTP fixture, clearly labeled NON_AI.

## Technical (20%)

- Scope contracts + scope guard (observation Ã¢â€°Â  permission to rebuild).
- Declarative candidate DSL executed by a trusted sandboxed interpreter Ã¢â‚¬â€
  the model never emits arbitrary code.
- Independent pinned evaluator; sealed suite never enters model context;
  aggregate-only repair feedback (no case IDs/inputs/gold).
- Two-target product: ledger CLI + owned HTTP task-workflow fixture through
  the same scope/evidence/worker/report/export pipeline, with owner
  isolation, cancellation, and offline-verifiable proof bundles.

## Original work

Built during the hackathon window (repo created 2026-10-26). Human: Ankit
Bhardwaj (owner/design/decisions). AI coding agents assisted implementation
under owner direction across dated PRs #1Ã¢â‚¬â€œ#28; see
[`HACKATHON_ORIGINALITY.md`](HACKATHON_ORIGINALITY.md). Dependencies:
pydantic, FastAPI, pytest (backend); Vite/TypeScript (product).

## Known limits (state plainly)

- One genuine synthesis, one target, 25 sealed cases; provider attestation
  incomplete (local broker attestation only, offline replay consistent).
- Hosted cloud Auth/Storage two-user acceptance not established; the
  demonstrated product runs locally with synthetic identities.
- No arbitrary-website cloning; authorized owned fixtures only.
- Video v3 is local only and NOT yet publicly hosted; portal submission is NOT done and no receipt exists.
- Meta Vikunja receipts were lost to a driver crash; only the $0.50 reservation cap and the run record are claimed, not a billing total. Gemma per-route repair regressed held-out to 2/6 (negative); gate audit is a NON_AI damage-prevention mechanism, not a model score; Gemma D synthesis is provider-blocked and unscored.

## Owner-only portal steps (exact; only the account owner does these)

No agent submits. No receipt exists until step 8 completes.

1. Fetch the exact live `main` HEAD from GitHub and record that commit in the portal; do not use the older historical SHA printed in prior drafts. Re-check no placeholder remains.
2. Upload the final demo video publicly (unlisted/public per portal rules); open the link in a signed-out/private window and confirm it plays with readable labels.
3. Open the repo signed-out: https://github.com/Ankit6149/second-source Ã¢â‚¬â€ confirm it loads, the README path works, and no private `.runs` material is public.
4. Sign in **as the owner** to https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit before **Nov 4, 9:00 PM ET**.
5. Select the **Indie** track; paste Title, One-liner and section text from this draft verbatim. Enter the repo URL and the final `main` SHA from step 1.
6. Paste the verified public video URL from step 2. State Meta Vikunja as EXECUTED REAL_MODEL (C 2/6, D 1/6; receipts lost, $0.50 cap) and browser/motion as a bounded recorded slice (in-app execution unavailable); claim no submitted status.
7. Re-read every number against the scorecard above (Gemma A 0/6, C 2/6, H re-measured 3/6, per-route repair 2/6 negative, Gemma D unscored; Meta C 2/6, D 1/6 REAL_MODEL; oracle/compiled NON_AI 6/6; gate audit NON_AI mechanism not a score; ledger REAL_MODEL 14/25). Remove anything without a receipt, then preview the full entry.
8. Click submit **once**. Save the portal confirmation receipt (screenshot + copied text/ID + timestamp) outside the repo. Only then may any document say "submitted", quoting that receipt.

## Owner checklist before clicking submit

- [ ] Upload video publicly; open link signed-out; paste URL in form.
- [ ] Confirm merged release SHA on `main`; open repo signed-out.
- [ ] Re-read every claim above against evidence; remove anything unproven.
- [ ] Submit; save the portal confirmation receipt (screenshot + text).
