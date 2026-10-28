# Second Source — Multi-Agent Coordination Charter (2026-10-28)

**Goal:** ChatGPT, Muse Code and Codex build one secure, provable G3 demonstration quickly, with NO duplicated implementations, hidden-test leakage or contradictory status.

## Responsibility matrix

| Worker | Primary authority | Allowed initial writes | Prohibited overlap |
|---|---|---|---|
| Muse Code | G3-A design/implementation: typed CandidateSpec, validated DSL, local trusted in-memory runtime, provider-facing candidate generation adapter | `src/second_source/candidate_spec.py`, `candidate_runtime.py`, `candidate_generation.py`; `tests/test_g3_candidate_*.py`; `docs/G3_CANDIDATE_INTERFACE.md` | Do NOT edit `verifier.py`, sealed test sources, original fixture reference or scope contracts without cross-review |
| Codex | G3-B independent verifier design/audit, gold isolation policy and adversarial evaluation; once interfaces are frozen, implementation of candidate adapter and sealed test harness | Phase 1: **read-only** audit and acceptance-case design. Phase 2: `src/second_source/candidate_adapter.py`, `g3_verification.py` and `tests/test_g3_verifier_*.py` after explicit handoff | Do NOT rewrite candidate DSL/runtime or expose gold cases/target source to Muse's candidate generation |
| ChatGPT | Architecture, coordination, PR security/code review, integration conflict resolution, acceptance documentation and independent CI verification | `docs/HANDOFF_2026-10-28.md`, `COORDINATION_CHARTER.md`, `G3_DELIVERY_BOARD.md`, `G3_ACCEPTANCE.md`; narrowly scoped fixes only after review | Do NOT label the product real/verified just because simulated tests pass |
| Owner | Product scope, API spending, authorizations, final merges, external infrastructure and hackathon submission | Approves any paid call, reference access expansion, merge, deployment or public submission | Never asked to paste secrets into chats |

## One-branch rule / concurrency protocol
- Existing G2: `integrate/g2-discovery` and PR #1 into `main`. DO NOT modify `main` or merge #1 without explicit owner authorization. After approved G2 merge, resync local `main` with `origin/main`; never preserve stale local draft commits by force-push.
- For G3 create ONE integration branch such as `g3/implementation` from latest reviewed G2 head if working ahead of G2 merge, or from verified `main` after approved merge. Document exact base SHA. The resulting G3 PR must not be merged independently ahead of G2.
- Muse is the first writer to the G3 branch. Codex does **read-only design and test contracts concurrently**. After Muse publishes a clean interface checkpoint, ChatGPT grants Codex a *file-disjoint* write window; Codex fetches latest branch and commits only its assigned modules. No simultaneous edits to the same branch head and no simultaneous commits touching overlapping files.
- Every push: `git fetch` -> verify upstream and head -> `git pull --ff-only` -> run targeted + full tests -> push once -> record SHA. Never force-push; never create disposable public branches for each thought.
- If a concurrent update occurs, stop, fetch, compare diffs and integrate cleanly. Do not force or silently rewrite the other's work.

## Strict trust-zone boundaries
**Developer-assistant vs inference agent are different roles.** Muse Code as a programmer may inspect repo-level architecture, but the product's *candidate-generating model invocation* may receive **only** operator-approved public contract and redacted evidence; it must have no model tools with access to `reference.py`, `fixtures/owned_ledger/reference.py`, sealed evaluator files, environment variables, secrets or hidden cases. Verify outgoing model messages AND tool capabilities. Do not claim isolation based only on prompt wording if the generator can read the repository.

Gold evaluator has privileged reference/executable access; it returns to the inference model ONLY approved aggregated feedback (no exact hidden inputs, outputs, case IDs, private file paths or unexpected text). If a test requires reference-specific knowledge, Codex must keep it in evaluator-owned material not included in generation context.

Model-generated specs are **untrusted input**. Trusted interpreter executes an allowlisted data DSL, never Python/JS/shell/SQL from candidate; avoid generic eval, arbitrary filesystem and network. Resource limits, fresh per-sequence state and approval requirements enforced in executable code.

## Change/review protocol
1. Worker reports a contract proposal with exact types, function signatures, test files and security concerns; reviewer gives concise acceptance or concrete blocking diff.
2. Implement smallest vertical slice; test locally; publish commit and CI.
3. A second worker reviews critical trust boundaries and regression tests. Disagreements recorded as factual `OPEN` decisions with alternatives; no guesswork.
4. Only factual report from a real user-run Meta API command may authorize a real-model claim. Never convert mocks, templates or seeded fixtures into allegedly generated candidates.
5. Authorize paid calls per run; default ZERO. Stop after a failed paid attempt and inspect sanitized diagnostics before another.

## Meeting-free progress format (copy into each agent completion)
- Baseline SHA / resulting SHA / remote branch + PR.
- Requirements and files changed.
- Exact command(s) run and observed passes/fails/skips; CI URL/status.
- Mock vs real inference, response IDs, run IDs, model spend estimated/uncertain.
- Reference/gold boundary evidence, blocked scope actions, leak/adversarial tests.
- Known limitations and requested owner decision.
- Which files are now safe for the next worker to modify.

## Conflict resolution rule
The Master PRD states WHAT; G3 Implementation Contract states G3 minimum; Execution Playbook states acceptance/schedule; this charter delegates WHO. If an assumption is unsupported by source or actual run, label it `UNKNOWN`. Engineering estimates are not observed outcomes. Security failures take precedence over feature throughput.

## Order of coordination
**Now:** Muse begins G3-A and publishes interface; Codex performs read-only G3-B audit, no overlapping writes; ChatGPT checks PR/CI and prepares acceptance artifacts. **Then:** Codex implements G3-B against committed interface, Muse connects model generation and mock path. **Then:** joint integration review, one owner-authorized real G3 run, independent report, optional 0–2 repairs, demo/submission.

## Current coordination receipt ? 2026-10-28 session boundary

The historical kickoff above is superseded by current delivery state: G2 merged; G3-B engineering code `aeed582483cbf0f2d57bfb53a4fef948273d9ec6` on existing `g3/verifier` has conditional coordinator source/CI review. PR #4 targets `g3/candidate-synthesis`; PR #3 targets `main`. Both remain draft and unmerged. Exact-code CI `40581058875` is green on Linux/Windows, including Windows bootstrap. G3 is NOT ACCEPTED.

Latest direction: https://github.com/Ankit6149/second-source/pull/4#issuecomment-6461226733. Codex continues real-run evaluator provenance/security in existing owned files; Muse owns its precedence correction; Codex independently verifies that correction. No additional branches. A caller-provided reference/mapping/marker scan is not proof of real-run provenance. Integrate moving upstream cleanly and require combined CI before claims. No new merge or paid-call authorization is created here.

The user authorized a documentation/handoff refresh and requested implementation continuation in the next session. Consult `HANDOFF_2026-10-28.md` and `NEW_CHAT_STARTER_2026-10-28.md`; do not restart completed G3-B work or ask the user to repeat history.
