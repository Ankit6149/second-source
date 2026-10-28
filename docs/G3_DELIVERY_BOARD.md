# Second Source - authoritative delivery board

**CURRENT - 28 October 2026.** This is the single current delivery board.
Historical records are dated evidence, not continuation instructions. No
engineering result grants input approval, model spending or a PR merge.

## Consolidated engineering milestone

One G2 persistence implementation now uses the existing discovery loop,
planner, gateway, evidence ledger and RunBudget, with a version-2 immutable
journal. Muse's original-response/proposal visibility requirements, readable
G3 progress/evaluation summaries, and Codex durability/preflight controls are
combined. The legacy in-memory G2Recorder/one-final-manifest path is retired;
there is no parallel persistence system or new orchestrator.

Source/test checkpoint: `bc16552cf4c204bbe3f3fb8fb136353e898156fb`,
combining Muse `c0e82b5`/`0849b48` and reviewed Codex `49fa288`/`3d1334e`
through integration `d20765d`, with the final pending-accounting view fix. Existing branch
`integrate/g3-reconstruct`, [PR #5](https://github.com/Ankit6149/second-source/pull/5),
remains unmerged. Owner explicitly authorized consolidation; no new branch,
force push, history rewrite, credential access or inference is authorized.

**GO for zero-cost consolidated engineering; NO-GO for genuine reconstruction
or product release.** Independent persistence18, input binding17 and inspector5
hard cases pass. Exact source/test
[CI 40701890631](https://github.com/Ankit6149/second-source/actions/runs/40701890631):

| Platform | Full suite passed / failed / skipped | Other checks |
|---|---|---|
| [Linux / Python3.11](https://github.com/Ankit6149/second-source/actions/runs/40701890631/job/122863594820) | 425 / 0 / 3 | Fresh install and deterministic demo pass |
| [Windows / Python3.12](https://github.com/Ankit6149/second-source/actions/runs/40701890631/job/122863595220) | 426 / 0 / 2 | Demo pass; fresh bootstrap repeats426/0/2, BOOTSTRAP_OK |

Counts were independently read from both job logs, not implementation claims.
Two real-smoke tests are intentionally unexecuted on both OS; Linux additionally
skips the Windows-junction probe. No paid calls are needed for engineering GO.
Documentation-only descendants require their own full exact-head CI; the
final combined SHA/check links are recorded in the [PR #5 review](https://github.com/Ankit6149/second-source/pull/5#pullrequestreview).
Prior zero-cost G3 acceptance at `936492dfa7c3eae4eb875e85f3619c30be11a22c`
remains valid for that checkpoint only:
[CI 40668775436](https://github.com/Ankit6149/second-source/actions/runs/40668775436),
Linux352/0/3, Windows353/0/2 and bootstrap353/0/2 BOOTSTRAP_OK.

## G2 acceptance conditions

| Requirement | Consolidated behavior / evidence |
|---|---|
| Missing receipts invalidate completeness | Original response, ordered dispatch/result receipts, terminal counters and external receipt witness are cross-checked; removed receipts block inspection/export |
| Final status cannot substitute model input | First registered original statement/citations/alternatives are immutable; statuses are independently replayed from archived predictions and actual observations |
| Later failure preserves earlier discovery | Each original response/batch is durable before proposal dispatch; failure/interruption retains prior hypotheses and exact known/uncertain accounting, remains incomplete, cannot export |
| Stable scope/approval pins | One canonical serializer sorts unordered contract collections; three-process hash-seed and credential/provider/reference sentinels pass |
| Actual experiment provenance | Completed rounds bind unique proposal IDs, full action sequence, observation IDs/order/bytes and post-proposal timing; unknown/replayed evidence is rejected |
| Durable publication | Shared fsynced staging + exclusive no-clobber publication; exact response text/hash, create-once events/receipt and externally retained witness |
| Offline recovery | Read-only inspection/status restoration; no automatic execution resume or unapproved retry; incomplete archives never supply G3 input |
| Pending exposure | Thin inspection shows pending attempt/reserved uncertainty separately from settled accounting; hard interrupted-dispatch regression |
| G2 -> G3 | External G2 witness, exact complete original batch/ledger/digests and target/reference pins feed the existing G3 preflight and bound mock; real mode rejects mock before key access |

All seven original G3 verifier regressions and positive/offline25/25 and
negative sensitivity2/2/1 remain unchanged gates. The naive standalone mock
scores22/25; none of these is an AI reconstruction result. See the
[consolidation review](G2_PERSISTENCE_REVIEW.md) and
[execution approval package](G2_G3_APPROVAL_PACKAGE.md) for provenance and
reproducible commands. The Master PRD and G3 contract remain authoritative.

Fresh CLI demonstration at this source: `codex-g2-final-20261028T140316Z-fe8cbe99`
completed G2 discovery (3 observations, 2 mock receipts), offline witness-bound
reload/export, both zero-call preflights, and G3 bound mock using those exact
inputs. Result22 passed/3 failed/0 indeterminate/25; one mock generation
attempt,1774 input/236 output synthetic tokens, estimated/uncertain USD0.
Full hashes are in the approval package. Complete mock remains
`approvable=false`, `real_input_eligible=false`, real provider calls0.

## Current delivery matrix

| Item | Current status | Remaining gate |
|---|---|---|
| G2 persistence/preflight | One journal, independently reviewed, full cross-platform CI green | Owner engineering review; separate real G2 authorization |
| Historical genuine G2 | Four retained reports/11 observations audited; successful run has five hash-valid observations and recorded model receipts | Original statements/citations/response bodies were not retained; recover authentic contemporaneous export or separately approve a NEW discovery |
| G3-A/B/D | Candidate DSL, strict sealed evaluator and CLI workflow delivered; accepted zero-cost checkpoint preserved | Actual authentic-input approval and genuine Meta-generated candidate/independent score |
| G3-C | Optional bounded repair support only; operator repair deferred | Genuine baseline first, separate authorization, at most2 attempts/unchanged suite/aggregate feedback |
| Product/demo/submission | Local CLI/report workflow; readable progress/results retained | Genuine result, complete sanitized evidence/demo/video and submission; premium UI not certified |

PRs #3/#4 are already merged; main is the earlier foundation at
`9c8bcc4eba5e8bf4b1b3e5dfc75273c2eb0ea203`. PR #5 must not be merged without
separate owner authorization. Earlier c0e82b5 CI358/0/3 Linux359/0/2 Windows
was green but did not cover four reproduced G2 defects; it is historical, not
consolidation acceptance. Local49fa288/3d1334e were inputs to consolidation,
not a competing supported release.

## Real-run and product verdict: NO-GO

1. Complete owner engineering review of the exact-head evidence; PR merge
   remains separately authorized.
2. Recover an authentic historical original export if one exists outside the
   bounded audit; never reconstruct it from IDs. Otherwise seek separate
   approval for one NEW G2 discovery against the reviewed G2 preflight pin.
3. Proposed new G2: one round, at most3 Meta attempts (hypothesize/propose plus
   at most1 guarded correction), application allowance<=USD0.25. Preserve all
   original batches/response IDs/bytes/citations, usage and failures. No ping,
   automatic provider-failure retry or repair is included.
4. Independently authenticate the new complete input package, run G3 zero-call
   preflight against its actual ledger/batch, and approve exact context/scope/
   budget/suite/reference/code pins. A mock digest never approves real input.
5. Separately approve one genuine G3 generation, allowance<=USD0.50, no repair.
   Archive exact candidate/broker bytes, score the unchanged sealed suite and
   report passed/failed/indeterminate/total honestly. Estimates and uncertain
   amounts are not provider-confirmed billing or a guaranteed invoice cap.

## Quality and deadline risk

- P0 release: authentic complete G2 input, genuine G3 measured baseline and
  final submission/video do not exist. Engineering green cannot replace them.
- P1 product: CLI-only experience, no certified polished responsive UI, no
  automatic interrupted execution resume and no single command for the whole
  approved genuine workflow. Raw private response archives are not automatic
  sanitized public exports. G3 fine-grained broker-failure taxonomy is limited.
- P2 deferred: optional repair, web/second adapter, cloud breadth and cosmetics.
  Keep focus on the authentic single-CLI result and demonstration.

Local hashes are integrity evidence, not provider attestations; keep receipt
witnesses outside mutable archives. Filesystem power-loss guarantees and
arbitrary generated-code OS sandboxing are not certified. Legacy final G2
manifests and version-1 local mock journals cannot be silently promoted to
version-2 authentic evidence. Source/OS/manifest changes need fresh preflight.

Target submission early Nov4 IST; the recorded PRD cutoff is Nov5,07:30 IST.
Reconfirm organizer requirements before submission. Provenance remains on the critical path;
reduce optional breadth if needed, never evidence integrity or honest scores.
This phase: genuine calls0, estimated spendUSD0, uncertain spendUSD0.
