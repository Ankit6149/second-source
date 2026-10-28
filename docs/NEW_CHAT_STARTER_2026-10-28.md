# New Chat Starter ? Second Source continuation (copy-paste)

Paste the following assignment into the next session.

Continue Second Source autonomously from the current GitHub PRD, implementation contract and latest coordinator comment on PR #4. Complete the remaining G3-B provenance/security requirements, independently verify Muse's corrections, and prepare the integrated evaluator for G3-D.

Repository: https://github.com/Ankit6149/second-source
Work ONLY on existing `g3/verifier`; use `C:/Users/ANKIT BHARDWAJ/Desktop/second-source-verifier`. Fetch and verify the current HEAD. Last verified code SHA: `aeed582483cbf0f2d57bfb53a4fef948273d9ec6`; a documentation-only handoff commit follows it. Do not create another branch.

Read `docs/HANDOFF_2026-10-28.md`, `docs/COORDINATION_CHARTER.md`, `docs/CODEX_G3_B_REVIEW_BRIEF.md`, `docs/G3_DELIVERY_BOARD.md`, `docs/G3_CANDIDATE_INTERFACE.md`, `docs/G3_IMPLEMENTATION_CONTRACT.md`, `docs/G3_VERIFIER_ACCEPTANCE.md`, `docs/G3_ACCEPTANCE.md`, and relevant `docs/MASTER_PRD.md` requirements. Read the current G3-D contract if one has been published.

Latest verified coordinator direction:
https://github.com/Ankit6149/second-source/pull/4#issuecomment-6461226733
Re-fetch comments; newer direction may supersede this snapshot.

G2 PR #1 is merged. Draft PR #4 targets `g3/candidate-synthesis`; draft PR #3 then targets `main`. Neither G3 PR is merged. G3-B's engineering slice is CONDITIONALLY GREEN after independent coordinator source/CI review, not final G3 acceptance.

Verified code CI: https://github.com/Ankit6149/second-source/actions/runs/40581058875 ? Linux 250 passed/3 skipped; Windows 251 passed/2 skipped, including bootstrap. Local Windows 250 passed/3 skipped. Strict probes 26/26. NON_AI positive control and bounded CLI 25/25; three bad DSL controls fail 2, 2 and 1 cases. No genuine G3 generation/accuracy/repair claim; G3 spend remains $0.

Next: require attested pinned reference identity, frozen suite/comparator and immutable candidate origin/receipt for REAL evaluation; reject caller-substituted or forged provenance. Bind inspected requests to approved G2 observation/hypothesis provenance and pinned scope/public signatures, preserving exact messages/schema through the broker. Independently test Muse's precedence fix once committed; the integration branch was still `bfd605d...` at the last fetch, so no fix is yet verified. Fetch/integrate cleanly before claiming combined green CI. Keep hidden cases, reference source and credentials out of generation/repair; only aggregate model_feedback() is repair-visible.

Stay inside the existing Codex-owned adapter/evaluator/test files and narrow verifier exception. Do not rewrite Muse modules, reference/provider code, scope contracts or G2 evidence. No credentials, paid calls, force pushes, additional branches or merges without required approvals. Python audit hooks are a data-only defense, not an arbitrary-code sandbox. Proceed with owned reversible work; report exact commits, CI, controls, costs, blockers and integration readiness. Do not ask the user to repeat history.
