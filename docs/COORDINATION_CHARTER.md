# Second Source — current coordination charter

**CURRENT — 28 October 2026.** Read the [authoritative delivery board](G3_DELIVERY_BOARD.md),
[Master PRD](MASTER_PRD.md), [G3 contract](G3_IMPLEMENTATION_CONTRACT.md) and
latest coordinator reviews on [PR #5](https://github.com/Ankit6149/second-source/pull/5).
The board holds current SHA, CI, risks and readiness; this charter delegates work.

## Ownership

| Owner | Responsibility / files | Boundary |
|---|---|---|
| Muse | Candidate DSL/runtime/generation; operator `reconstruct.py`, operator tests, report/export/product experience and operator runbook | Preserve independent evaluator/negative tests; no reference/gold changes or misleading real claims |
| Codex | Independent verifier, `candidate_adapter.py`, `g3_verification.py`, narrow API-preserving verifier fixes, `tests/test_g3_verifier_*.py`, acceptance/security/reproducibility review | No Muse-owned generation/operator/gateway source changes; documentation status reconciliation is explicitly authorized |
| Coordinator / owner | Review, genuine input approval, scope/cost decisions, merge/deployment/submission authorization | Engineering green is not inference or spending approval |

## Shared branch and serialized writes

- Use the one existing `integrate/g3-reconstruct` branch and PR #5. PRs #3/#4
  are merged; do not resume their old branch/merge sequence.
- Fetch, confirm current head and worktree changes, inspect committed interfaces,
  announce the disjoint write window and retain file ownership. Do not overwrite
  another worker's draft edits. Commit/push serially with ordinary fast-forwards.
- No new branches/PRs, force pushes, merges, paid calls or inferred spend approval.
- Preserve all seven independent regressions, NON_AI 25/25 positive control and
  2/2/1 sensitivity. Report exact-head Linux/Windows CI, not an earlier green.
- New blockers need reproduced failures, severity and explicit acceptance.
  Keep material P1 limitations visible; avoid expanding scope through speculation.
- Reuse existing contracts, budgets, receipts, broker and evaluator. The private
  signing key stays private. Historical G2 hypothesis text/citations must never
  be reconstructed from identifiers or replaced with mock data.

**Authority:** PRD defines product; implementation contract defines G3; board
records current delivery; latest owner/coordinator instructions govern review.
Resolve genuine conflicts explicitly rather than rewriting history as success.

## Archived kickoff

The earlier charter and `g3/verifier`/draft-PR instructions are an
**ARCHIVED SNAPSHOT**, retained in
[Git history at 44f4780](https://github.com/Ankit6149/second-source/blob/44f47803efcb0046c353942e42c36be1b34ca957/docs/COORDINATION_CHARTER.md).
They are not current continuation instructions. The deleted starter file must
not be recreated as another status source.
