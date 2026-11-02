# Second Source — judge-readiness and comparison packet
**Snapshot: 2026-11-02 IST.** Evidence-based preparation, not a release authorization, new inference run, or submission receipt.

## Pitch and significance
**One-line:** An AI scientist for software behavior: observe it, experiment with it, reconstruct it, and independently verify it.

Problem: replacing an undocumented internal CLI or legacy API is difficult because input/output examples hide state, role restrictions, validation and failure behavior. Second Source investigates **owned, explicitly authorized** references, collects observations, records hypotheses and reconstructs a constrained implementation with a separately managed differential evaluator. It does **not** recover original source, clone arbitrary websites, bypass access controls or guarantee equivalence on inputs never evaluated.

**Competition:** Meta Global AI Developer Hackathon, Indie Developer track, *Push the Frontier*. Official [event](https://dev.meta.ai/events/global-hackathon) and [submission](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit). Participant guide requires a **public repository**, clarity about work built during the event, and an accessible **three-minute video**. Deadline **Nov 4, 2026 at 9:00 PM ET = Nov 5 at 7:30 AM IST**. The copied participant guide omits the actual rubric table: confirm grading weights from original signed rules rather than inventing them.

## What each agent finished; what is still open

| Workstream | Evidence | Current status |
|---|---|---|
| **Codex: app, integration, acceptance, draft demo** | [PR #24](https://github.com/Ankit6149/second-source/pull/24), `efc2628fd84f1682ccdb4cfc844c98af9c4713d1`; [Linux/Windows Python CI SUCCESS](https://github.com/Ankit6149/second-source/actions/runs/41330506231); [frontend quick/real Chromium CI SUCCESS](https://github.com/Ankit6149/second-source/actions/runs/41330506254) | Two-target local UI, scope authorization, real local API + NON_AI worker, progress, report, lineage, export, desktop/mobile emulation. **Draft PR; unmerged.** Local synthetic identities and fake Storage, no hosted or live-model call. Local 179.85s draft video reported, not publicly accessible. |
| **Argon: G4 stateful HTTP science** | [PR #27](https://github.com/Ankit6149/second-source/pull/27), `37ba0484f7cbc5a77d41dbc82068efff3314bd31` | Owned loopback `/v1/tasks` reference, roles/transitions/errors, 30-case sealed suite, deterministic active vs passive controls and mock repair; **already history-integrated into PR #24**, but #27 separately unmerged. No genuine HTTP Meta inference. |
| **Muse: real G3 science** | [PR #23](https://github.com/Ankit6149/second-source/pull/23), `da8437505ff6699e3c0375f41290064790ccd57f` | Real Meta Muse Spark 1.3 admitted ledger candidate scored **14/25**. Model-conditioned bounded repair code present, but rev-7 request unapproved and **no genuine repaired improvement**. Original local artifacts passed consistency/pinned-suite replay per Codex; provider signature and expired ephemeral HMAC not reverified. **Open and not integrated into final PR #24.** |
| **Independent review: docs** | [PR #26](https://github.com/Ankit6149/second-source/pull/26) | Initial docs snapshot was stale (pre-G4); this dated packet updates the review without changing product code. |
| **Independent review: rate-window regression** | [PR #28](https://github.com/Ankit6149/second-source/pull/28), `87bcfb4135b779f055b904af95cbb36fd72991e9` | Isolated test-server cap patch, both Python CI jobs green. **Not required automatically**: PR #24's own frontend/Chromium CI now passes with its existing wait-for-headroom logic. Prefer smallest release; do not merge #28 without reproducible need. |
| **Optional infra/providers** | [PR #17](https://github.com/Ankit6149/second-source/pull/17), [PR #16](https://github.com/Ankit6149/second-source/pull/16) | Baseten provider no credits/no live call; hosted Auth/DB/private Storage deployment blocked by unverified recovery, not part of accepted local demo. |

**Main remains `951ed681ab707a54e9e76a3377546235c98a0369`**, not the integrated product. A green PR is not a merge. PR #23 and PR #24 need a joint compatibility check if both science and product changes are in the final release; merging separately without testing the combined head is not acceptance. Do not reapply #27 blindly over its copy already in #24.

## Actual app capability — honest judge checklist

| Judge tries | Supported now? | Evidence/limit |
|---|---|---|
| Landing and investigation workspace | Yes, local | Combined static landing → `/app/` in PR #24; hosted app not accepted |
| Select ledger CLI or HTTP task-workflow target | Yes | Only exact backend-advertised **owned fixtures**; **no arbitrary URL** |
| Review scope, authorize run | Yes | Strict allowed operations/exclusions and scope digest; browser UI exercised |
| Run, show progress, inspect reconstruction and repair lineage | Yes, **NON_AI** | Local API/worker, deterministic fixture execution; not live Muse or Gemma |
| Inspect hidden-suite evaluation | Yes | Ledger **25-case** and HTTP **30-case** fixture suites |
| Download report and ZIP proof | Yes | Four local desktop/mobile exports reportedly verified; checksums give integrity, **not provider attestation** |
| Test cancellation, reload, restart, cross-owner denials | Yes, **synthetic** | Browser+backend CI; fake identity/Storage instead of real cloud OAuth |
| Genuine Muse-generated candidate | Separate historical run | **14/25** on owned CLI; should be displayed with model identity, receipts and limitations |
| General unseen software reconstruction | **Not demonstrated** | Do not market as working on arbitrary apps |
| Hosted real login, remote storage, independent cloud worker | **Not accepted** | No approved migration or verified full backup/restore |
| Public three-minute video and portal submission | **Not evidenced** | Draft local recording only; no public link or receipt |

## Benchmark comparison: do not combine unrelated numbers

| Test / provider | Passed | Correct classification |
|---|---:|---|
| Genuine **Meta Muse Spark 1.3**, CLI | **14/25**: 9 schema and 2 error mismatches, 0 indeterminate | Real model inference, admitted candidate, independently evaluated, provider attestation still limited |
| Deterministic NON_AI ledger control | **22/25** | Scripted control, not model accuracy |
| HTTP G4 A: target-specific uninformed prior | **19/30**, 0 experiments | Deterministic control, not general zero-shot reconstruction |
| HTTP G4 B: passive observations | **25/30**, **5 sequences/15 actions** | Within-fixture control |
| HTTP G4 C: active observations | **30/30**, **5 sequences/15 actions** | +5 cases within this fixture at matched action budget, **not** measured Meta reasoning |
| HTTP G4 D: scripted repair | **25/30 → 30/30** | Scripted access to active evidence collected before initial candidate; **not** proof AI discovered a repair |

**Leakage/causality caveat:** The G4 deterministic extractor contains target-specific priors/constants and error labels. Active data were collected before initial mock generation; repair selection reveals previously gathered evidence. The experiment demonstrates within-fixture evidence sufficiency—not generalizing intelligence or feedback-only learned repair. The G3 CLI suite and G4 HTTP suite are different. **Never visually compare 14/25 vs 30/30 as a head-to-head model contest.**

## Market comparison (product positioning, NOT a benchmark)

| Adjacent product category | Publicly advertised purpose | Our distinct proposed job | Actually proven? |
|---|---|---|---|
| [Lovable](https://lovable.dev/build/app-builder), prompt-to-app | Builds apps from human instructions | Infer missing behavior specification from permitted observations | Partial; Meta candidate on CLI, HTTP mock |
| [OpenHands](https://www.openhands.dev/), repository coding | Modify a codebase, complete engineering tasks | Work from opaque interface behavior when source isn't available | Limited owned fixtures |
| [Skyvern](https://www.skyvern.com/blog/8-browser-workflows-with-skyvern/), [Browser Use](https://browser-use.com/), browser agents | Operate browser workflows | Construct an independent substitute and score behavioral match | Controlled local verification |
| Conventional black-box testing | Capture how a reference behaves | Evidence-linked candidate synthesis plus independent evaluator | NON_AI local pipeline; historical Muse inference separate |

This is **comparative positioning only**. No competitor was run against the same reference/evaluator. Do not claim the products lack capabilities they may have added or that Second Source outperforms them.

## Three-minute demo storyboard (must label video origins)

| Timing | Required visual and message |
|---|---|
| **0:00–0:18** | Customer problem: undocumented old API. State transitions/permissions make prompt-only clones unreliable. |
| **0:18–0:44** | Owned HTTP fixture: choose target, show permitted scope and forbidden operations. Synthetic test account label stays visible. |
| **0:44–1:16** | Actual local workflow: trigger bounded NON_AI investigation and show task transitions/errors and event timeline. |
| **1:16–1:48** | Separate **historical real Meta** evidence: Muse Spark 1.3 candidate, **14/25**, exact failures and available hashed receipt/provenance, with caveat provider signature not independently verified. |
| **1:48–2:19** | HTTP NON_AI baseline **25/30** and scripted correction **30/30**; show `NON_AI` prominently. Say that the rules/evidence were pre-collected, **not** AI fixing itself. |
| **2:19–2:43** | Independent report, difference summary, ZIP integrity validation, explicit unknowns/authorization limit. |
| **2:43–3:00** | Practical use: confidence when replacing an undocumented internal workflow. GitHub, hackathon contributions and honest limitations. |

**Suggested closing:** “Instead of asking AI to guess how old software works, Second Source gathers evidence, builds a candidate, and shows exactly what matches—and what we still don't know.”

Codex reported **179.85-second draft** in its local checkout `.runs/submission-video/`. This GitHub reviewer **cannot verify that local file's contents or public accessibility**. Owner must review/edit it, publish, test playback while signed out, and retain submission proof. Do not say it is live Meta inference.

## What to do now — with coding agents unavailable

**P0, no credential/spending needed:** review exact final SHA; preserve and compare recorded browser evidence; inspect PR #23↔#24 compatibility before proposing a merge; resolve documentation drift; review original work/third-party asset attribution and source LICENSE (none detected via GitHub repo metadata in this review; public repo ≠ automatically open-licensed); rehearse with local `npm run demo:local`; obtain a public video link and actual submission receipt. Freeze all new UI/features.

**P1, only if P0 safe:** blind variation of an **owned** fixture with frozen independent tests; a genuine G3 repair or G4 Meta-model run using new exact-input authorization and cost cap. A Gemma test can help engineering but **does not satisfy Meta usage** and must be recorded separately. No provider secrets, paid calls, merges, migrations or production promotion are approved by this document.

**Explicitly defer:** unrestricted websites, web scraping/auth bypass, hosted SaaS without cloud Auth+database+private Storage restore, repeated provider experiments and speculative redesign.

**Current gate verdict:** `LOCAL_DEMO_CONDITIONAL_GO` / `HOSTED_PRODUCT_NO_GO` / `SUBMISSION_NOT_CONFIRMED`. The project has working code but still needs an owner-reviewed submission and final release decision.
