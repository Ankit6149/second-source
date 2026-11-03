# Repository hygiene — 3 November 2026

Branch cleanup performed after PR #37 merged. Rule applied: delete
only branches fully merged into `main`, branches backing open PRs are
kept, and branches with unique commits are preserved under
`archive/*` tags before removal. No commit was discarded.

## Deleted (fully merged into `main`)

22 remote branches, e.g. `feat/coverage-gate-20261103`,
`feat/reconstruction-lab-20261102`, `feat/local-evidence-mcp-20261102`,
`feat/g4-owned-http-reference-argon`, `g3/verifier`,
`release/hackathon-review-20261102`, plus their merged local twins
(19 local branches). Stale temp worktrees `C:\tmp\ss-lab`,
`C:\tmp\ss-mcp` removed (clean).

## Archived, then deleted (unique commits preserved)

Each tip is preserved on origin under an `archive/` tag at the exact
SHA shown; restore with `git checkout -b <name> archive/<name>`.

| Branch | Tip | Archive tag | Last activity |
|---|---|---|---|
| `eng/science-engine` | `18ef4a0` | `archive/eng/science-engine` | 2026-10-31 |
| `feat/landing-console` | `3d5bd91` | `archive/feat/landing-console` | 2026-10-29 |
| `feat/postgres-control-plane-20261029` | `1b5b5d1` | `archive/feat/postgres-control-plane-20261029` | 2026-10-29 |
| `feat/supabase-owner-auth-20261029` | `90f365f` | `archive/feat/supabase-owner-auth-20261029` | 2026-10-29 |
| `integrate/backend-completion-20261030` | `b5a1b22` | `archive/integrate/backend-completion-20261030` | 2026-10-30 |
| `integrate/landing-vercel-20261030` | `71f00dc` | `archive/integrate/landing-vercel-20261030` | 2026-10-30 |

All six were 134+ commits behind `main`; their functionality was
superseded by merged PRs, but their patches were not patch-equivalent
to `main`, hence the tags.

## Kept

- `main` (protected by review practice; merge only on exact-head green CI).
- `fix/gemma-capture-20261103` — PR #38, in review.
- Open-PR branches: #16 `docs/release-evidence-gates-20261029`,
  #17 `infra/baseten-muse-open-provider-20261030`,
  #26 `docs/verified-status-20261101`,
  #28 `review/browser-acceptance-rate-window-20261101`.
- Worktrees with owner state, untouched: Desktop `second-source`
  (`eng/g3-readiness`, uncommitted submission docs),
  `second-source-verifier` (`integrate/release-20261029`),
  `.build/argon-g4` (uncommitted G4 work incl. `g4_gemma.py`).
