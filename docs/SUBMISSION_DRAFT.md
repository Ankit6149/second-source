# Submission draft — Meta Global AI Developer Hackathon (Indie)

**Status: DRAFT for owner review. Not submitted. No portal receipt exists.**
Deadline: **Nov 4, 9:00 PM ET** — https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit

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

- 2:59 video (v2, 179.78s, SHA-256 `97333A5E…` (v1 `069D7DB4…`)): scope → observation →
  genuine Meta 14/25 → NON_AI HTTP control 25→30/30 → honest limits.
  **Owner must upload publicly and verify signed-out before submitting.**
- Interactive Reconstruction Lab (/lab/): two targets, recorded public probes with per-step diff highlighting, versions and uncertainty - REAL_MODEL vs NON_AI always labeled (PR #34).
- Genuine HTTP reconstruction: engineered and spend-gated (PR #33, <=11 calls, .50 cap); not yet run - do not claim a genuine HTTP score until its report exists.
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

## Owner checklist before clicking submit

- [ ] Upload video publicly; open link signed-out; paste URL in form.
- [ ] Confirm merged release SHA on `main`; open repo signed-out.
- [ ] Re-read every claim above against evidence; remove anything unproven.
- [ ] Submit; save the portal confirmation receipt (screenshot + text).
