# Session handoff — 2026-11-03 (read this first next session)

Deadline: **Nov 4, 2026, 9:00 PM ET** (Nov 5, 7:30 AM IST). The entry is
NOT submitted. No portal receipt exists. Everything below is verified;
nothing is claimed beyond its evidence.

## State

- `main` = the merge of PR #46 (see `git log -1`). Only branch left:
  `main`. Worktrees: `second-source` (detached at main, clean) and
  `second-source-release-review` (main, clean). Stale agent copies and
  dirty-worktree diffs are preserved in
  `Desktop/second-source-archive-20261103/` (nothing was destroyed).
- Production: https://second-source-alpha.vercel.app/ — routes `/`,
  `/evidence/`, `/console/`, `/app/`, `/lab/`, `/handoff/` verified
  signed-out, 200, 0 console errors, desktop + mobile.
- Owner handoff page (live): `/handoff/` — steps 1–2 DONE, 3–5 owner.

## Verified scoreboard (provenance is absolute — never relabel)

| Result | Class | Score |
|---|---|---|
| Muse Spark ledger (historical) | REAL_MODEL | 14/25 |
| Muse Spark Vikunja Arm C grounded | REAL_MODEL | 2/6 (cases 1,3) |
| Muse Spark Vikunja Arm D active (probes D1,D4,D5,D6,D7; 22 obs) | REAL_MODEL | 1/6 (case 3) |
| Gemma A prior / C grounded | GEMMA_TEST | 0/6, 2/6 |
| Gemma H_hybrid (per-route, templates compiled) | GEMMA_TEST | 3/6 (cases 0,2,3) |
| Gemma per-route repair (semantic admission) | GEMMA_TEST | 2/6 — measured regression |
| Gemma B; Gemma D synthesis | GEMMA_TEST | unmeasured / provider-blocked (429/500), unscored |
| Evidence compiler; oracle | NON_AI | 6/6 |
| Public-verification gate audit | NON_AI mechanism | 0/8 model edits kept; NOT a model score |
| Browser slices v1/v2 held-out RMSE | NON_AI | 1.054px / 1.741px, pass |

Meta packet: EXECUTED as frozen (3 calls, digests matched, $0.50
reservation cap). Gateway receipts were lost to a driver crash after
both arms completed; candidates were re-scored from frozen specs.
Record: `.runs/vikunja-model/meta_arms_result.json` (local, uncommitted).
No further paid inference without a NEW explicit owner packet.

Key scientific finding: on observed behavior, model edits damage
evidence-compiled facts (gate audit). The classic spec format is the
current ceiling for model arms; the compiled-template hybrid is the
stronger representation. Provider reliability (429/500/timeout) is
the main experimental risk for Gemma synthesis-class calls.

## Remaining (in order)

1. OWNER: upload video v3 `.runs/submission-v3/second-source-v3.mp4`
   (170.02s, SHA-256 `20E00793…6F548A`) to a signed-out-playable host;
   share URL. Fallback v2 in `.runs/submission-final/`.
2. OWNER: portal submit via `docs/SUBMISSION_DRAFT.md` /
   `.runs/submission-v3/PORTAL_CHECKLIST.md`; save + share receipt.
3. Optional science (needs NEW owner authorization + packet): Meta
   hybrid arm (per-route synthesis + gate) — do not reuse the spent
   packet. Gemma D synthesis retry after provider quota reset.
4. After the event: delete/rotate the exposed Gemma key; clear
   `MODEL_API_KEY` env if not needed (`setx MODEL_API_KEY ""`).

## Rules that must survive

- Merge only on exact-head green CI; batch changes; one PR per batch.
- REAL_MODEL / GEMMA_TEST / NON_AI never blended; provider failures
  are recorded, never scored; held-out never enters prompts.
- Keys via local env only, never chat/repo. Gemma key (exposed
  earlier) stays until the owner rotates it post-event.
- Local `.runs/` artifacts are uncommitted evidence; do not delete.

## Next-session prompt

See the owner chat message accompanying this handoff; the same text
is the fastest way to re-brief any fresh agent.
