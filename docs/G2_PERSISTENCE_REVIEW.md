# G2 persistence follow-up: independent evidence

**ARCHIVED source-specific record.** Earlier CURRENT headings, holds, branch/merge directions and counts below apply only to their dated checkpoint. Use the [single current delivery board](G3_DELIVERY_BOARD.md) for exact published SHA/CI, both consumed real G3 attempts, evidence and backend acceptance. This document does not authorize inference, credentials or deployment.

28 October 2026. This records a bounded follow-up, not another delivery board.
The [authoritative board](G3_DELIVERY_BOARD.md) owns project readiness.
No merge, input approval or model spending is authorized here.

## ARCHIVED consolidation checkpoint

Owner authorized consolidation on the existing shared branch. Source/test
checkpoint `bc16552cf4c204bbe3f3fb8fb136353e898156fb` contains one version-2
DiscoveryJournal, replacing the legacy in-memory final-manifest recorder.
Muse's progress/evaluation summaries remain, and all five meaningful original
persistence tests are ported to the same journal API. The original
G3 verifier regression files remain unchanged.

All four original defects are closed by hard regressions. Independent review
also reproduced final-status/round-reference consistency gaps in the early
journal; these are fixed by validating first-registered immutable hypothesis
fields, replaying original prediction verdicts, and binding completed rounds
to unique archived proposals and their actual post-proposal observation
sequences. Changed final statements/citations/status, nonexistent/replayed
observations, missing receipts and changed original batches now reject.
An independent reviewer authored18 persistence and17 G2/G3 binding scenarios;
the thin inspector's5 cases also pass. The final independent pending-dispatch
probe initially failed because the thin inspector omitted pending exposure;
two direct field forwards close it without changing settled accounting or
eligibility. Independent final inspector+persistence23 passed with no skips.
Exact-source [CI40701890631](https://github.com/Ankit6149/second-source/actions/runs/40701890631)
is green: Linux425 passed/0 failed/3 skipped; Windows426/0/2 with bootstrap
426/0/2 and BOOTSTRAP_OK. Both demos pass. All seven original G3 verifier
files are byte-unchanged from936492d; NON_AI 25/25 and 2/2/1 remain hard.
Documentation-only descendants receive their own exact-head CI and final
review; use the board/PR for that final combined head.

G2 scope and manifest pins agree in three fresh hash-seed processes with
credential/provider/reference constructor sentinels. Invalid approvals block
before key access. Original hypotheses and exact stage usage survive later
proposal failure/interruption and remain nonexportable incomplete evidence.
Offline restoration never resumes execution. G3 real inspected progress now
follows successful prepare and does not claim spend reservation before it.

Muse's later `0849b48` was inspected and merged into `d20765d` with both
histories retained, not overwritten. Its thin inspector and G3 input checks
now use only the version-2 journal: external receipt witness, exact all-field
original batch, complete evidence set, target/reference/public identity and
genuine-origin checks before credential access. Bound mock feeds that exact
G2 input through the existing generation broker/evaluator. Trusted approval
modules are covered by the existing evaluator code pins, not copied into
candidate workers. Invalid original evaluator-context tests stay hard.

The approval package documents the sole consolidated CLI. Historical
observations/receipts do not recover missing statements/citations; no paid
calls, credentials, PR merge or spending approval were used. Converged source
was published by ordinary fast-forward pushes with serialized ownership;
no branch or history rewrite was used. Full CLI mock demonstration completed
at the source above: G2 reload/export -> zero-call preflights -> bound G3
mock 22/25, no substituted observations/hypotheses. All output remains NON_AI.

## ARCHIVED pre-consolidation comparison

Everything below records the earlier local/remote comparison at its named
commits. Old holds, failures and pending work are historical; use the current
board and consolidation section above to determine active status.

## Checkpoint identities and integration hold

Accepted engineering checkpoint: `936492dfa7c3eae4eb875e85f3619c30be11a22c`.
[CI 40668775436](https://github.com/Ankit6149/second-source/actions/runs/40668775436)
passed Linux **352/0/3** and Windows **353/0/2**, including Windows bootstrap.
Its review remains valid for that exact checkpoint. Genuine G3 remains NO-GO.

Muse subsequently pushed overlapping G2 work to PR #5 at
`c0e82b5d763f99ff4631d81dc05363b39b29da0e`, during the announced local
Codex write window. Codex has made no remote push, force push or revert.
[Coordination hold](https://github.com/Ankit6149/second-source/pull/5#issuecomment-6468496884)
and [reproduced findings](https://github.com/Ankit6149/second-source/pull/5#issuecomment-6468569681)
are published on the existing PR. Preserve both authors' work and converge on
one implementation before another shared push. The accepted GO cannot be
silently transferred to the newer PR head.

Codex proposal: local commit `49fa288a179c2dea0da407ea1d1b0d7c6c86f60a`,
parented directly on accepted `936492d`, in the existing verifier worktree.
It is not published to the shared branch and is not a descendant of Muse's
new change. Applying it over that change requires explicit file reconciliation,
preserving useful existing tests and Muse's readable-result/progress work.
No new branch or PR was created. No reset of the shared branch is proposed.

## Remote-head review: green CI is insufficient

At exact `c0e82b5`,
[CI 40683707722](https://github.com/Ankit6149/second-source/actions/runs/40683707722)
is SUCCESS: [Ubuntu/Python 3.11](https://github.com/Ankit6149/second-source/actions/runs/40683707722/job/122800599797)
**358 passed / 0 failed / 3 skipped**;
[Windows/Python 3.12](https://github.com/Ankit6149/second-source/actions/runs/40683707722/job/122800600217)
**359/0/2**, bootstrap repeats **359/0/2**, `BOOTSTRAP_OK`.
Counts were independently read from pytest progress tokens in both job logs.
The four checks below are not covered by that green CI.

| Severity | Reproduced failure at c0e82b5 | Acceptance condition |
|---|---|---|
| P0 for authentic-input approval | Removing all model receipts still passes `load_manifest` completeness | Missing attempt/stage/response receipts prevent complete input/export |
| P0 for authentic-input approval | Replacing a final hypothesis statement survives `load_manifest` and `rebuild_store` | Reconciliation may change derived status, never original statement/citations/alternatives; bind to original response |
| P1 material persistence defect | Hypothesize succeeds, propose fails: attempts 2, settled calls 1, hypothesis remains only in memory; recorder refuses all manifest output | Durable prior valid batch and usage survive later failures/interruption, explicitly incomplete and nonapprovable |
| P1 preflight blocker | Same G2 scope serializes to different digests with hash seeds 1/37/99 | Stable canonical scope/approval pins in separate processes |

Retained reproducible NON_AI probe:

```powershell
# Requires a clean checkout already at c0e82b5; never changes checkout or Git refs.
.venv/Scripts/python.exe -B scripts/audit_g2_checkpoint.py --repo <c0e82b5-checkout>
```

The probe uses existing mock/reference fixtures, temporary directories and hard
Meta/HTTP sentinels. Exit **1** honestly records defects. Both Codex and the
independent parallel reviewer reproduced all four. Raw model observations and
historical payloads are not published. No credentials/provider calls occurred.

## Locally reviewed proposal

The existing `DiscoveryLoop`, planner, evidence ledger, gateway and RunBudget
remain the execution path. The proposal adds optional persistence hooks:

- Create-once events record observations, pre-transport reservation/identity,
  exact successful response text and its receipt/hash, validated original
  hypothesis batches, actual round completion and terminal state.
- Original batches remain distinct from derived statuses. Offline export
  revalidates original response association, observation bytes and a separately
  retained receipt hash. Missing/changed records never become complete input.
- Reload is read-only. Pending dispatch after interruption remains uncertain;
  no automatic model retry or execution resume exists.
- A settled response whose archive write failed retains its exact usage in
  the terminal record, marks response archival incomplete and blocks export.
  Failed pre-dispatch persistence releases dollars without claiming transport.
- Existing G3 atomic no-clobber publication is shared through
  `evidence.publish_once`; the `reconstruct._write_once` interface remains.
  No independent evaluator or scoring system was introduced.
- Existing G2 entrypoint adds nonbillable mock, zero-call preflight and offline
  inspect/export modes. Real dispatch requires finite budget, confirmation and
  exact reviewed manifest pin before reading the key. The manifest binds
  source/reference/public bytes, canonical scope, seed, caps and pricing snapshot.

Independent review found one early defect in reload after result-publication
failure. It was corrected and retested independently. The reviewer exercised
three fresh hash seeds with constructor/credential sentinels and invalid pin,
budget, round-count and confirmation changes. No remaining reproducible
high-risk defect was found in this bounded local review.

All seven original G3 regression tests are byte-for-byte unchanged. Targeted
existing G2/G3 tests: **79 passed**. Initial full local Windows/Python 3.12
run: **370 passed / 0 failed / 3 skipped**, 231.47 seconds. Five later
focused regression cases exercise semantic substitution/missing receipts,
proposal failure/interruption and budget stop; all **23** new persistence
cases pass. Final full local Windows/Python 3.12.4 run against committed source
`49fa288a179c2dea0da407ea1d1b0d7c6c86f60a`: **375 passed / 0 failed /
3 skipped**, **229.75 seconds**. Credentials were absent, spend environment
zero, external pytest plugins disabled and cache/bytecode writes disabled.
No exact-proposal Linux/Windows CI is claimed. WSL is unavailable locally;
remote publication is held to avoid conflicting overlapping pushes.

## Nonbillable workflow demonstration

Source `49fa288`, retained local run
`.runs/codex-g2-followup-20261028T121418Z-209b2f43/verification.json`:

1. Existing discovery CLI with mock provider executes an actual guarded
   reference experiment, stores three observations and a complete original
   hypothesis/response archive; two mock attempts, zero real calls.
2. A new process reloads the archive using its retained receipt hash and
   exports a validated original batch, with no execution resume.
3. G2 proposed-real preflight and existing G3 input preflight both complete
   with **zero provider calls**. The G3 preflight consumes that exported mock
   batch and its exact ledger, not a reconstructed historical hypothesis.

Evidence pins:

| Artifact | SHA-256 / authoritative pin |
|---|---|
| G2 receipt | `1eb2636517ba3ae615aa4124e6eb93070306cf7367d40d88f501d8b0f101ae23` |
| Original batch export | `2d8a59d487f99f3a0113f182290c9e47fd48985de2118820165369556ab7a16d` |
| Proposed-real G2 manifest | `0eb1a9b473a175edb3b071e5e869f2544a68f296a41dbdcae7f8cad8594ffc26` |
| G3 preflight receipt | `1c96b1751a058751c178d2eaff77101afac86b2670240325e386e9771f2314bc` |
| Mock-input G3 context | `sha256:48cc2a0803cb60aad76d3f343b846df5d7d712b0d014bd47f50926d0575ddd53` |

Every artifact above is **NON_AI**. Estimated/uncertain spend is **$0/$0**;
no genuine candidate was generated. The mock context is not actual-input
approval. Accepted 25/25 positive/offline and 2/2/1 negative controls remain
NON_AI; they measure harness sensitivity, not reconstruction quality.

## Remaining decisions and limitations

The [approval package](G2_G3_APPROVAL_PACKAGE.md) contains the bounded recovery
audit and separate proposed G2/G3 operations, input pins and spending limits.
Authentic historical statements/citations were not recovered. An owner-held
contemporaneous export may still exist outside the audit boundary; otherwise
approve a new G2 only after implementation convergence and cross-platform review.
Do not rebuild old evidence from identifiers. Proposed application allowances
are $0.25 G2 and separately $0.50 G3, never an inferred authorization or billing
guarantee. Genuine model quality and submission remain unmeasured/incomplete.

Raw successful response text is private local evidence, not automatically a
sanitized public export. Invalid provider responses retain their failure and
available usage/digest metadata, not a promoted hypothesis. Hash chains are
local integrity evidence, not provider signatures; retain receipt pins outside
the archive. Power-loss filesystem guarantees and automatic execution resume
are not certified. The proposal does not add a polished UI or demonstrate one
command for the entire genuine reconstruction path. Defer cosmetic/cloud
breadth while authentic evidence remains on the critical path.
