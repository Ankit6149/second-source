# Submission draft — Meta Global AI Developer Hackathon (Indie)

**Status: DRAFT for owner review. Not submitted. No portal receipt exists.**
Deadline: **Nov 4, 9:00 PM ET** — https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit
Final `main` SHA: `c984dfc1793b9d0ff960a02b445914805889dde4` (`main` at `c984dfc`).
Production: https://second-source-alpha.vercel.app/ — routes `/`, `/evidence/`, `/console/`, `/app/`, `/lab/` verified signed-out with 0 console errors.

## Final measured scorecard (change only with a receipt)

| Entry | Label / provenance | Result | Notes |
|---|---|---|---|
| Gemma arm A (prior only) | GEMMA_TEST / model-authored | 0/6 | Scored. Gemma dev test, not Meta, not REAL_MODEL. |
| Gemma arm C (coverage-grounded) | GEMMA_TEST / model-authored | 2/6 | Scored. A vs C does not isolate the coverage-gate effect. |
| Hybrid H_hybrid (compiler-assisted model synthesis) | GEMMA_TEST / model-authored | 3/6 | Model edits compiled NON_AI facts per route; beats model-only 2/6, below compiled NON_AI 6/6; public conformance 7/19; repair not admitted. |
| Oracle control (Vikunja) | NON_AI / runtime-supplied | 6/6 | Hand-written oracle via generic interpreter. Never a model result. |
| Historical ledger | REAL_MODEL / model-authored | 14/25 | Muse Spark 1.3, frozen 25-case suite. Not comparable to Vikunja. |
| muse-spark-1.3 Vikunja packet | REAL_MODEL (prospective) | Not run | Owner-authorized but not yet run. No genuine Meta Vikunja result exists; no score claimed. |
| Compiled evidence | EVIDENCE_COMPILED (NON_AI) / evidence-compiled | 6/6 | Deterministic transcription of the 20 public observations (`scripts/evidence_compiler.py`); status-mutation control 2/6. Never a model result; Gemma C stays 2/6. |
| Browser / motion | NON_AI slice / evidence-compiled | Bounded pass | `browser-slice/`: spring-drag fit from observations only, held-out drag RMSE 1.054px and 1.741px, adversarial variants detected. In-app execution unavailable; one owned fixture only. |

Gemma arms B and D were provider failures and stay unscored — never 0/6.

## Title

Second Source — evidence-first reconstruction of authorized black-box software

## One-liner

Second Source learns how an explicitly authorized system behaves by asking
black-box questions, builds a separate candidate implementation, and scores
it against a withheld evaluator — reporting matches, failures, and unknowns.

## Problem / impact (30%)

Teams inherit undocumented internal and legacy APIs whose behavior lives
only in the running system. A screenshot or prompt cannot reveal boundary
rules, state transitions, or error behavior. Second Source targets
authorized behavioral reconstruction for migration, maintenance, and
regression testing: observe → hypothesize → run distinguishing experiments
→ synthesize an independent candidate → measure it blind.

## Meta AI use (25%)

- Genuine **Muse Spark 1.3** (`meta-direct`) performed G2 discovery
  reasoning (evidence-linked hypotheses, discriminating experiments) and
  G3 guided synthesis of a declarative candidate spec.
- Measured result: **14/25** on a frozen sealed suite (9 schema, 2 error
  mismatches), response `chatcmpl-01a19314-…`, 2,756/2,555 tokens, ~$0.014.
- Full provenance, concrete mismatches, and limits:
  [`JUDGE_EVIDENCE_G3.md`](JUDGE_EVIDENCE_G3.md) +
  [`evidence/g3-rev6-sanitized/`](evidence/g3-rev6-sanitized/).
- No repair improvement is claimed (rev-7 not executed; owner decision).

## Demo (25%)

- Video v3 (170.02s, local .runs/submission-v3/second-source-v3.mp4, SHA-256 20E0079343E93B06C80361DCF7EFE3AD9850F07E9A808969C492FB25556F548A): scope, observation, genuine Meta 14/25, NON_AI controls, honest limits. **NOT yet publicly hosted. Owner must upload publicly and verify signed-out before submitting.**
- Interactive Reconstruction Lab (/lab/): two targets, recorded public probes with per-step diff highlighting, versions and uncertainty - REAL_MODEL vs NON_AI always labeled (PR #34).
- muse-spark-1.3 Vikunja packet: owner-authorized but not yet run. No genuine Meta Vikunja result exists; do not claim a genuine Vikunja/HTTP score until its report exists.
- 2D browser reconstruction: assessed NO-GO for this window (docs/P3_BROWSER_SPIKE_ASSESSMENT.md); explicitly not implemented.
- Live local demo: `npm run demo:local` (product) — synthetic identities,
  loopback-only HTTP fixture, clearly labeled NON_AI.

## Technical (20%)

- Scope contracts + scope guard (observation ≠ permission to rebuild).
- Declarative candidate DSL executed by a trusted sandboxed interpreter —
  the model never emits arbitrary code.
- Independent pinned evaluator; sealed suite never enters model context;
  aggregate-only repair feedback (no case IDs/inputs/gold).
- Two-target product: ledger CLI + owned HTTP task-workflow fixture through
  the same scope/evidence/worker/report/export pipeline, with owner
  isolation, cancellation, and offline-verifiable proof bundles.

## Original work

Built during the hackathon window (repo created 2026-10-26). Human: Ankit
Bhardwaj (owner/design/decisions). AI coding agents assisted implementation
under owner direction across dated PRs #1–#28; see
[`HACKATHON_ORIGINALITY.md`](HACKATHON_ORIGINALITY.md). Dependencies:
pydantic, FastAPI, pytest (backend); Vite/TypeScript (product).

## Known limits (state plainly)

- One genuine synthesis, one target, 25 sealed cases; provider attestation
  incomplete (local broker attestation only, offline replay consistent).
- Hosted cloud Auth/Storage two-user acceptance not established; the
  demonstrated product runs locally with synthetic identities.
- No arbitrary-website cloning; authorized owned fixtures only.
- Video v3 is local only and NOT yet publicly hosted; portal submission is NOT done and no receipt exists.
- muse-spark-1.3 Vikunja packet is owner-authorized but not yet run; no genuine Meta Vikunja result exists.

## Owner-only portal steps (exact; only the account owner does these)

No agent submits. No receipt exists until step 8 completes.

1. Confirm main is at c984dfc1793b9d0ff960a02b445914805889dde4 (c984dfc) and that this draft records that exact SHA. Re-check no placeholder remains.
2. Upload the final demo video publicly (unlisted/public per portal rules); open the link in a signed-out/private window and confirm it plays with readable labels.
3. Open the repo signed-out: https://github.com/Ankit6149/second-source — confirm it loads, the README path works, and no private `.runs` material is public.
4. Sign in **as the owner** to https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit before **Nov 4, 9:00 PM ET**.
5. Select the **Indie** track; paste Title, One-liner and section text from this draft verbatim. Enter the repo URL and the final `main` SHA from step 1.
6. Paste the verified public video URL from step 2. State the muse-spark-1.3 Vikunja packet as owner-authorized but not yet run (no genuine Meta Vikunja result exists) and browser/motion as a bounded recorded slice (in-app execution unavailable); claim no genuine HTTP score and no submitted status.
7. Re-read every number against the scorecard above (A 0/6, C 2/6 GEMMA_TEST; oracle NON_AI 6/6; compiled NON_AI 6/6; ledger REAL_MODEL 14/25). Remove anything without a receipt, then preview the full entry.
8. Click submit **once**. Save the portal confirmation receipt (screenshot + copied text/ID + timestamp) outside the repo. Only then may any document say "submitted", quoting that receipt.

## Owner checklist before clicking submit

- [ ] Upload video publicly; open link signed-out; paste URL in form.
- [ ] Confirm merged release SHA on `main`; open repo signed-out.
- [ ] Re-read every claim above against evidence; remove anything unproven.
- [ ] Submit; save the portal confirmation receipt (screenshot + text).
