# Second Source — documentation index

**Verified navigation snapshot: 1 November 2026 IST.** The [delivery board](G3_DELIVERY_BOARD.md) is the **single current implementation and acceptance status**. The [master PRD](MASTER_PRD.md) is the **normative product/engineering specification**, not a record that every proposed feature is deployed. [Coordination charter](COORDINATION_CHARTER.md) covers ownership, branch discipline and approval boundaries. Avoid copying old `CURRENT` banners from archived research records into release claims.

## Start here

| Purpose | Primary document | Boundary |
|:--|:--|:--|
| Product introduction and local quick start | [Root README](../README.md) | Current merged implementation vs unmerged science/product PRs must be distinguished |
| **Current gates, exact SHAs and open decisions** | **[G3–G6 delivery board](G3_DELIVERY_BOARD.md)** | Only canonical current status; historical dated checkpoints below its active table are archived |
| Product definition, scope, research and implementation specification | [Master PRD v2.0](MASTER_PRD.md) | Normative direction; not proof of implementation or organizer submission |
| Responsibilities, approvals and integration sequencing | [Coordination charter](COORDINATION_CHARTER.md) | Separate owner approval for paid calls, live data, credentials, migrations, deployments and merges |
| Final submission, narrative, evidence and checklist | [Hackathon submission runbook](HACKATHON_SUBMISSION_RUNBOOK.md) | Codex PR #24 updates this file; main's older dated snapshot is not the current G3 verdict |

## Scientific engine and verification

| Topic | Document | Read as |
|:--|:--|:--|
| Current genuine result, limitations, historical decision trail | [G3 acceptance](G3_ACCEPTANCE.md) | Real research candidate reported 14/25 on **unmerged PR #23**; private receipt-level verification outstanding |
| Reconstruction CLI, mock/preflight/real boundaries | [G3 operator guide](G3_RECONSTRUCT.md) | Historical command templates are versioned; do not reuse consumed approval hashes |
| Independent evaluator/negative controls | [G3 verifier acceptance](G3_VERIFIER_ACCEPTANCE.md) | Frozen-suite procedure; date-stamped older verdicts are archived |
| Candidate and verifier semantics | [G3 candidate interface](G3_CANDIDATE_INTERFACE.md) | Implementation contract; validate against exact checked-out source |
| Execution module assumptions | [G3 implementation contract](G3_IMPLEMENTATION_CONTRACT.md) | Design contract, not unconditional runtime acceptance |
| Engine-owned repair integration | [G3 repair contract](G3_REPAIR_CONTRACT.md) | Muse implementation; real-model repair requires separate exact-input authorization |
| Original real-model G2 investigation | [G2 acceptance](G2_ACCEPTANCE.md) | Historical evidence, not proof of new inference |
| Prior G2/G3 authorization and evidence identities | [Approval package](G2_G3_APPROVAL_PACKAGE.md) | **Historical spent approvals only**; do not treat as active spending permission |
| Experimentation, tasks and evidence methodology | [Execution playbook](EXECUTION_PLAYBOOK.md) | Playbook and proposals, not release claims |

**Current scientific branch:** [PR #23](https://github.com/Ankit6149/second-source/pull/23) @ `d7508ce33e67b414370b29cc0db713800d72fb59`, [Linux/Windows CI success](https://github.com/Ankit6149/second-source/actions/runs/41237650430). Contains genuine 14/25 evidence provenance and bounded feedback-conditioned repair engineering. No improved genuine repaired score. The current `owned_ledger_variant` uses the **same JSONL ledger command surface** with different rules; G4 distinct HTTP/browser reconstruction remains unproven. Argon's distinct owned HTTP reference implementation was assigned but **no landed branch or acceptance is verified in this snapshot**.

## Backend, product, security and operations

| Topic | Document | Boundary |
|:--|:--|:--|
| Local API/worker/SQLite execution | [Backend operations](BACKEND_OPERATIONS.md) | Local NON_AI accepted paths |
| Supported and refused API contracts | [Backend API v1](BACKEND_API.md) and [frontend/backend contract](FRONTEND_BACKEND_CONTRACT.md) | No arbitrary-target or hosted real-model execution |
| Proposed cloud deployment, cost and rollback | [Cloud backend operations](CLOUD_BACKEND_OPERATIONS.md) | Prepared, not authorized or hosted-accepted |
| Dedicated runtime schema/role and database constraints | [PostgreSQL backend](POSTGRES_BACKEND.md) and [Supabase baseline](../supabase/README.md) | Existing live `ss` baseline must be preserved; two proposed runtime migrations unapproved |
| OAuth and identity | [Supabase authentication](SUPABASE_AUTH.md) | Browser only receives publishable key; backend retains privileged credentials |
| Private artifact integrity | [Cloud artifact storage](CLOUD_ARTIFACTS.md) | Storage object bytes and recovery must be validated separately from DB dump |
| Optional sandbox integration | [Sandbox boundary](SANDBOX_BACKEND.md) | No claim that paid production sandbox is enabled |
| Local public research preview | [Web preview](../web/README.md) | Static pages, not the authenticated product |
| Early read-only demo | [Demo console](../demo/README.md) | Historical product surface |

**Current product branch:** [PR #24](https://github.com/Ankit6149/second-source/pull/24) @ `ee81f37d5ba735685aa8586e7122db9d033b8784`, [Linux/Windows Python CI success](https://github.com/Ankit6149/second-source/actions/runs/41279523175). Local real-Chromium synthetic testing reported passing, but production Auth/Storage/worker and a two-user hosted journey remain **unverified**. Its `product/` source, frontend CI proposal and [cloud activation decision](https://github.com/Ankit6149/second-source/blob/ee81f37d5ba735685aa8586e7122db9d033b8784/docs/CLOUD_ACTIVATION_DECISION.md) are **not in main**. The existing Supabase Free project has no verified live database + private Storage restore; **live migration NO-GO** until an approved recoverable strategy exists.

## Archived records, audits and context

These retain history and named-checkpoint measurements. They should not be used to overwrite the current delivery table.

- [Foundation acceptance](FOUNDATION_ACCEPTANCE.md), [G2 persistence review](G2_PERSISTENCE_REVIEW.md), [G3-B independent audit](G3_B_PHASE1_AUDIT_2026-10-28.md)
- [October 28/29 handoff](HANDOFF_2026-10-28.md), [Codex earlier G3-B brief](CODEX_G3_B_REVIEW_BRIEF.md), [G3 backend unblock](G3_BACKEND_UNBLOCK.md)
- [Hackathon originality register](HACKATHON_ORIGINALITY.md)

## Documentation maintenance rules

1. **Current facts go to the delivery board first.** Record branch, exact commit, CI, model-vs-mock origin, test denominators, and an explicit gate verdict. Update root README only after evidence is verified.
2. **Keep normative specifications separate from acceptance.** A PRD requirement is not a deployed capability. A green Python workflow is not frontend CI or browser/hosted acceptance.
3. **Avoid duplicate “current” snapshots.** Historical dated documents may retain original SHA and old claims but must be marked as archived or link to the current board.
4. **Do not add unapproved secrets, raw private evidence or spending data.** Private model outputs, sealed suites, database backups, object bytes and credential values remain out of public docs.
5. **Integrate sequentially.** PR #23, PR #24 and this documentation-only work are separate until reviewed. Recheck actual heads and links at merge/submission time; merging into `main` may trigger Vercel production deployment and requires an explicit safe-release decision.
