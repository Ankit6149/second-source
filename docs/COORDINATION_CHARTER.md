# Second Source — coordination charter

**CURRENT — 1 November 2026 IST.** The [delivery board](G3_DELIVERY_BOARD.md) is the sole owner of live status; the [master PRD](MASTER_PRD.md) owns product requirements. Dates, previous branch rules and merge statements under **Historical coordination** are archived snapshots, not current standing permissions. [Issue #25](https://github.com/Ankit6149/second-source/issues/25) tracks integration, blockers and evidence.

## Active ownership and shared interfaces

| Workstream | Primary owner | Scope and integration contract |
|:--|:--|:--|
| **Scientific reconstruction** | Muse, [PR #23](https://github.com/Ankit6149/second-source/pull/23) (`eng/g3-readiness`) | Observations, hypotheses, model gateway, candidate generation and admission, sealed differential evaluator, evidence-conditioned repair, provenance, science-facing adapters. Do not modify Codex cloud/frontend or Argon's independent reference without coordination. |
| **Product and hosted release** | Codex, [PR #24](https://github.com/Ankit6149/second-source/pull/24) | v0.8 frontend, backend/Auth/PostgreSQL/Storage/worker, browser QA, hosted acceptance, G3/G4 product integration and submission assets. Keep existing production landing stable. |
| **Independent G4 reference / benchmark** | Argon (proposed; branch and artifact **not yet verified**) | New *owned* stateful HTTP reference fixture, deterministic reset and independent tests; coordinate the typed target contract before editing shared scientific or backend code. A second ledger parameter variant is not a distinct protocol. |
| **Independent verification and documentation integration** | Separate reviewer, docs-only integration PR | Check exact SHAs/CI, scientific and security claims, links and acceptance boundaries. Review comments are not merge or production authorization. |

## Integration and approval rules

1. **One canonical current status:** [G3 delivery board](G3_DELIVERY_BOARD.md). Each claim records date, exact branch/SHA, test provenance, and whether the feature is merged, local-only, preview-only or hosted-accepted. Historical failures remain accessible but labeled.
2. **One writer per shared file at a time.** Coordinate changes to source-level interfaces in issue #25. Use a small contract patch, regression tests and explicit handoff; avoid duplicated scientific engines, concurrent migrations or broad unrelated reformatting.
3. **Exact-head acceptance:** independently reviewed relevant source plus Linux/Windows CI where required; local fake-provider and simulated-DOM results are distinct from real-model, real-browser and hosted acceptance. Python CI does not prove frontend tests passed in CI.
4. **No implied side-effect authorization:** paid inference/retry, live backups or sensitive-data exports, migrations, credentials, new cloud resources, worker enablement, production promotion and protected merges each require explicitly scoped approval. Never reveal owner billing/account balances in issues, PRs or logs.
5. **No misleading scientific claims:** preserved real Meta candidate **14/25** on unmerged PR #23, deterministic NON_AI control **22/25**, scientific repair engineering without a verified genuine repaired score, and G4 ledger-variant scaffolding without a distinct HTTP/browser reconstruction.
6. **Release discipline:** keep current `main` and active PR branches distinguishable; request independent review, respect Vercel auto-deploy risk on main, and never treat merging code as authorization to activate paid infrastructure.

## Historical coordination

Former `integrate/g3-reconstruct`/PR #5 single-branch and `g3/verifier` draft-PR instructions are ARCHIVED. PRs #5-#8 merged; board records exact evidence. Earlier [charter 44f4780](https://github.com/Ankit6149/second-source/blob/44f47803efcb0046c353942e42c36be1b34ca957/docs/COORDINATION_CHARTER.md). Do not recreate starter/duplicate board.
