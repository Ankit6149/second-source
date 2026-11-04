# Second Source — judge-facing evidence dossier
**Evidence status: 4 November 2026.** This document distinguishes measured results from product ambitions. It is a synthesis of repository source and dated records, not a new experiment or an independent provider attestation.

## The question
Can a system reconstruct the *behavior* of authorized software without access to its source? A visual clone can look correct while violating subtle API response shapes, case-insensitive uniqueness, numeric limits, permissions, and state-dependent workflows.

Second Source uses an explicit authorized scope, recorded black-box inputs/outputs, evidence-linked hypotheses, bounded candidate specifications, and a separate evaluator with withheld tests. The evaluator's gold cases are not used to generate or repair the candidate. The agent must report failures and unknowns instead of promising unmeasured equivalence.

## The strongest evidence — not one blended score
| Target/experiment | Provenance | Measured result | What it establishes — and what it does not |
|---|---|---|---|
| Owned ledger CLI, Meta Muse Spark 1.3 synthesis | REAL_MODEL / model-authored | 14/25 frozen sealed cases (11 failed: 9 schema + 2 error; 0 indeterminate) | One genuine admitted Meta declarative candidate was tested independently. It **did not pass** the suite; provider attestation is incomplete despite pinned-source offline consistency replay. |
| Vikunja v2.4.0, Meta Muse C grounded | REAL_MODEL / model-authored | 2/6 frozen | Genuine model candidate reproduces some workflows; still partial. |
| Vikunja, Meta Muse D active | REAL_MODEL / model-authored | 1/6 frozen | Active-probe model arm was measured, not a successful improvement over C. |
| Vikunja, Muse assisted evidence-compiled hybrid | REAL_MODEL / model-authored edits on compiled baseline | 6/6 frozen and 6/6 extended raw candidate | Genuine model-assisted path tied the **NON_AI evidence compiler**, which also achieved 6/6 on both. Public-conformance gate rejected all proposed edits. **No measured improvement over the compiler is claimed.** |
| Vikunja, evidence compiler | EVIDENCE_COMPILED / NON_AI | 6/6 frozen and 6/6 extended | Deterministic transcription of collected observations was sufficient on these bounded suites. Not a Meta model score. |
| File Browser v2.63.23 | NON_AI | 7/7 recorded workflow cases | Second professional target supporting the evidence-driven method; not evidence of live hosted cloning or AI reconstruction. |
| Owned HTTP task workflow, deterministic repair control | NON_AI | 25/30 to 30/30 on its own suite | Verifies a bounded mechanics/repair demonstration using pre-collected evidence. Not AI self-repair. |
| Browser spring motion, owned slice | NON_AI / deterministic fit | Recorded held-out trajectory RMSE 1.054px (another recorded slice: 1.741px) | A narrow browser/motion evidence experiment, not general browser reconstruction or an in-app browser adapter. |

**Never add scores across targets or compare denominators as if they measure identical behaviors.** Provider failures and unscored arms are not zeros. The Meta Vikunja provider gateway lost some original receipts after a driver crash; the stored run record and frozen specs are evidence, not independent billing/provider attestations.

## Three recorded public observations — see /challenge/
1. **Case-insensitive uniqueness.** The owned ledger rejects adding `MILK` after `Milk` with `duplicate_label`. The historical genuine Meta candidate accepted it (`unique_casefold:false`).
2. **Input boundary.** The reference rejects `amount:500` as `invalid_amount`; the candidate guessed a much larger maximum.
3. **Exact response schema.** The reference's successful `add` returns `{"ok":true,"id":"1"}`; the candidate included extra fields, creating a schema mismatch.

These are public replayable probes, **not** the withheld evaluator cases. The browser challenge and lab show recorded evidence; they do not call a live model or operate the reference.

## Engineering artifacts delivered
- Authorized scope and run boundaries; source code from the reference is not passed to the candidate generator.
- Hypothesis, experiment, candidate-admission and bounded interpreter paths for supported targets.
- Independent evaluation with versioned evidence, digests and separate runner ownership.
- Local API/worker lifecycle, events, owner-scoped investigation records and sanitized integrity export.
- Local deterministic engine for owned Vikunja and fixture control runs.
- Public evidence viewer, reconstruction lab, Black-Box Challenge and product application preview.
- Frontend reports/exports derived from sanitized backend data, with origin/provenance labels.

## Honest implementation and release boundaries
- The hosted public site, challenge and lab are accessible as read-only evidence/product previews. A green frontend deployment **does not establish live hosted authentication, real-model execution, multi-user persistence or general website reconstruction**.
- The candidate for the genuine ledger experiment is a restricted declarative specification—not arbitrary recovered source code, a cloned website, or production-ready app.
- The local product can show bounded NON_AI fixture runs. New real Meta inference, feedback-driven model repair, arbitrary URL ingestion and browser/motion execution through the app are not proven.
- Local event logs contain stage/event/status metadata. They do not expose detailed reference inputs/outputs unless the backend explicitly publishes a safe artifact. The UI must say this.
- Source/documented smoke checks and GitHub CI do not substitute for an actual fresh-run browser acceptance and credentialed hosted backend end-to-end test.
- Proof bundle digests establish integrity and consistency, not provider signatures.

## How to judge us in three minutes
**Observe an unexpected rule → reveal where the model disagreed → show the measured evidence boundary → show an actual NON_AI execution and its persisted events (if local backend is available) → open source-independent verification and report → explain what remains unknown.**

This sequence is both more persuasive and more defensible than a wall of scores.

## Reproduction and evidence entry points
- [Challenge (recorded public probes)](https://second-source-alpha.vercel.app/challenge/)
- [Reconstruction Lab (recorded comparisons)](https://second-source-alpha.vercel.app/lab/)
- [Evidence Report](https://second-source-alpha.vercel.app/evidence/)
- [Genuine Meta ledger audit](JUDGE_EVIDENCE_G3.md)
- [Vikunja benchmark and scientific limits](BENCHMARK_VIKUNJA.md)
- [Detailed submission status and gates](HACKATHON_SUBMISSION_RUNBOOK.md)
- [Local app acceptance workflow](../product/README.md)

## Submission integrity
An official entry exists only with the participant portal confirmation. Before submitting, confirm the published video plays signed-out, record the final `main` commit SHA and open all links in a private window. Do not state that submission or hosted real-AI execution is complete without direct proof.
