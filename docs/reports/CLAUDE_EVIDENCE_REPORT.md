# Genuine Claude Evidence — Complete Report

**Scope:** every genuine Meta Muse Spark 1.3 (`REAL_MODEL`) result in Second
Source, what each report can and cannot claim, and what would be required
for more. No new model calls were made for this document; it consolidates
recorded, independently scored experiments.
**Date:** 4 November 2026 · Codebase `6c15570`

---

## 1. Why there is one headline Muse report (14/25), not five

A "solid" Muse report needs four things at once: a candidate the model
actually authored, an evaluator the model never saw, a suite large enough
to mean something, and artifacts that survive audit. Only one run has all
four:

| Requirement | Ledger 14/25 | Vikunja C 2/6 | Vikunja D 1/6 | Vikunja hybrid |
|---|---|---|---|---|
| Model-authored candidate | ✅ full candidate | ✅ | ✅ | ⚠️ per-route edits only |
| Sealed/held-out evaluator | ✅ 25 cases | ✅ 6 cases | ✅ 6 cases | ✅ 6 + 6 cases |
| Suite size | **25** | 6 | 6 | 6 + 6 |
| Durable receipts/artifacts | ⚠️ locally consistent; provider attestation incomplete | ✅ packet receipts | ✅ packet receipts | ✅ durable fsync receipts |
| Result | **14/25** | 2/6 | 1/6 | raw 6/6 + 6/6; deployable = compiler (tie) |

The 6-case Vikunja suites were designed for continuity with the original
benchmark, not statistical weight. The hybrid is reported in full below,
but its deployable outcome is the deterministic compiler, so headlining it
as a "Claude 6/6 product" would be false. That is why 14/25 leads — and
why this document exists: the other Muse work deserves a proper report
too, at its true weight.

## 2. Report A — Owned ledger, Muse candidate: 14/25 (REAL_MODEL)

- **Task:** reconstruct a bounded ledger CLI's behavior from public
  evidence; candidate authored by Muse Spark 1.3 as a declarative spec.
- **Evaluator:** independent, sealed 25-case suite (frozen before scoring).
- **Result:** **14 passed / 25**. Failure taxonomy: 9 schema/response-shape
  mismatches, 2 error-contract mismatches (per recorded audit).
- **What it proves:** a model can author a bounded behavioral candidate
  that passes a majority of sealed cases with zero access to them.
- **Limits:** provider attestation is incomplete (artifacts are locally
  consistent; the run predates the durable-receipt fix). Never compare
  14/25 with Vikunja 6-case numbers — different target and suite.
- **Artifacts:** research record in the product; registry run
  `REAL_MODEL` ledger entries; `docs/JUDGE_EVIDENCE_G3.md` (source-backed).

## 3. Report B — Vikunja, Muse coverage-grounded (arm C): 2/6

- **Method:** model received coverage-grounded public evidence (no
  held-out data) and synthesized a candidate in one pass.
- **Result:** **2/6** frozen held-out.
- **Diagnosis:** failures concentrate in exact constants, response fields,
  and authorization statuses the model had to guess — the direct cause of
  the current architecture (compiler transcribes observed facts; the model
  reasons only about unknowns).
- **Status:** recorded baseline. Superseded as a method, kept as evidence.

## 4. Report C — Vikunja, Muse active probing (arm D): 1/6

- **Method:** model selected its own additional public probes before
  synthesis (active experiment selection).
- **Result:** **1/6** frozen held-out — worse than grounded (2/6).
- **Diagnosis:** self-selected probes did not cover the discriminating
  behaviors; probe selection without a coverage model wastes budget.
  A second synthesis attempt in this family was blocked by provider
  errors and is recorded as **unscored infrastructure failure**, never 0/6.
- **Status:** negative result, retained deliberately.

## 5. Report D — Vikunja, Muse per-route hybrid (packet `muse-hybrid-20261104`)

- **Method:** the deterministic compiler's candidate (6/6) was decomposed
  per route. Muse could propose bounded edits to editable fields only;
  each edit needed a justification (rule, evidence, uncertainty,
  distinguishing experiment, regression risk) and had to pass a
  **public-conformance gate** (19-step ladder; held-out never consulted).
- **Calls/cost:** 8 recorded calls, ≈ $0.19 total including failed
  attempts; durable fsync receipts in `.runs/vikunja-model/muse_hybrid_20261104/`.
- **Gate outcome:** every Muse edit was rejected — single edits scored
  1–2/19 on the public ladder vs the compiler's 11/19. The gated,
  deployable candidate is therefore the compiler itself.
- **Post-gate measurement (single evaluation, no tuning after):** the raw
  merged candidate scored **6/6 frozen + 6/6 extended**.
- **Claim (exact):** Claude-authored edits tied the compiler at ceiling
  but added **no measured improvement**; the gate prevented regressions.
  This is a tie with a safety result, not a Claude victory.
- **Extended suite note:** an early 0/6 extended reading was a scorer
  defect (shared ports across sequential scorings); fixed and re-scored
  publicly to 6/6. The correction is in the registry, not hidden.

## 6. What is deliberately NOT reported as Claude

- **Gemma arms (0/6, 2/6, 3/6, repair 2/6):** development baselines on a
  different model family. Historical context only; never Meta evidence,
  and removed from the product UI.
- **NON_AI compiler (6/6, 6/6, 7/7, 22/25, 30/30):** deterministic
  transcription of observations. It is the control every Muse claim is
  measured against — reporting it as AI would be fabrication.
- **Provider-failed attempts:** unscored, listed as infrastructure.

## 7. What more solid Claude reports would require

Each needs a fresh owner-approved packet (scope + spending ceiling +
durable receipts before the first call). Highest-value options:

1. **File Browser, Muse vs compiler (7/7 ceiling problem):** only useful
   on a harder, unobserved extension suite frozen first — same lesson as
   Vikunja: design headroom before spending.
2. **Gitea name-generalization repair:** the NON_AI baseline is 2/6 with a
   precisely diagnosed gap (literal route templates). A bounded Muse
   repair task — propose a segment-generalization rule, gate it on public
   cases, score on frozen held-out repo/issue cases — is the cleanest
   possible "Claude improves the system" report, positive or negative.
3. **Ledger extension suite:** 25 new sealed cases in the ledger family to
   test whether a second Muse candidate beats 14/25 without suite reuse.

Until a packet is approved, this document and the registry are the
complete, honest Claude record: one solid headline (14/25), two small
baselines (2/6, 1/6), one gated tie (hybrid), and the failures kept.
