# Second Source — authoritative delivery board

**CURRENT — 29 October 2026 IST.** Single current status source. Dated audit records are historical. [Product PRD](MASTER_PRD.md); [owner backend directive](https://github.com/Ankit6149/second-source/issues/2#issuecomment-6477673246); [ownership/policy](COORDINATION_CHARTER.md).

## Published baseline

PR #5 merged `bc9f9c11bb029a99ee3aa022749f266355aaa7e1`; PR #6 merged `ceb28b6f2f2292f75f766fbd3fbefc0822cfef98`; PR #7 merged `c214d60c8917f8e94859e268700c1ca07b4598b9`; PR #8/current main `0aba3bf42b735ae911b8b471aad43972abfa8d9d`.

[Exact main CI 40747405916](https://github.com/Ankit6149/second-source/actions/runs/40747405916) SUCCESS: Linux/Python3.11 job 123024752681 **434 passed/0 failed/3 skipped**; Windows/Python3.12 job 123024753054 **435/0/2**, bootstrap **435/0/2 BOOTSTRAP_OK**. Prior execution-source [CI 40742439039](https://github.com/Ankit6149/second-source/actions/runs/40742439039): Linux 428/0/3, Windows 429/0/2 and bootstrap 429/0/2.

Codex [backend PR #10](https://github.com/Ankit6149/second-source/pull/10), branch `feat/backend-control-plane`: implemented contracts/store/service/API/worker/artifacts with local targeted **55 passed / 0 failed / 1 Windows symlink-privilege skip**. Independent non-author review of source `0d12930956a59df3539394c1c40095a9ae747f54` found no P0/P1 blocker and separately reproduced the service-to-existing-G3 mock/export/restart journey (20 passed / 0 failed / 1 privilege skip). The packaged wheel includes the SQL migration. Exact latest-head CI, review and merge status are linked on PR #10; earlier main CI does not certify it. Complete descendant cancellation remains best effort on both OS because some staged workers create independent sessions. No production-readiness claim.

Muse owns intelligence/gateway/generation/admission. [Guided synthesis PR #9](https://github.com/Ankit6149/second-source/pull/9) has a [bounded independent review](https://github.com/Ankit6149/second-source/pull/9#pullrequestreview-5688427711): fixed scaffold decisions must be justified by the authorized contract or remain model/evidence-controlled before genuine-readiness acceptance and ticket integration. Do not infer either failed real response's cause. PR #7 is a merged read-only console, not full browser/product certification. PR #8 adds authenticated G2 observation auto-binding and future admission diagnostics.

Backend reproduction: [operations](BACKEND_OPERATIONS.md), [typed API/OpenAPI contract](BACKEND_API.md). The shared CLI/API control plane persists mock-only approvals, idempotent queueing, fenced leases, durable CODE events, cancellation and expired-run quarantine without replay. Its bounded worker calls the existing engine and reproduces **22/3/0/25 NON_AI**, then verifies a sanitized integrity bundle and restart. No paid engine adapter or HTTP spending authority is enabled; private original engine artifacts remain outside the public export.

## Genuine evidence — never confuse with controls

New genuine G2 `real-g2-20261028T163538Z-fd60310f`: 3 original hypotheses, 5 observations, one model-selected 3-action experiment, 2 real meta-direct/muse-spark-1.3 receipts. Input 2809/output 2347; estimate USD0.013486, uncertain 0. Witness `947910b0f645b78b9234859a899db3412171cbbbb3c400e072c9f661840e31f8`; original batch SHA `8fb04fa0dcf9e86b5fac5716bea2693966bc6144851ee34a785ca8071e7e615f`. Original witnesses/all five observations rechecked during continuation. Old 27 October missing hypotheses remain missing, not reconstructed.

| Genuine G3 attempt | Actual outcome | Accounting |
|---|---|---|
| `real-g3-from-g2-20261028T164126Z-8ee4d156` | Consumed broker_failed; no candidate/evaluation/score. Report SHA `bb1d8cf74c76f1ee3bc8029e0f83a9083369f6b5c4d8c1117ac59adeec2d9bbb` | Input 3314/output 1456; estimate USD0.0103305; uncertain 0 |
| `real-g3-checkpoint2-20261028T181223Z-256a7dfb` | Consumed MODEL_GATEWAY_ERROR; no candidate/evaluation/score. Report SHA `591ce48481d962ed5c0481942caa7faab0abf45585e9a3d1431ef7f09288bc27` | Input 3314/output 1343; estimate USD0.00985025; uncertain 0 |

Second response ID `chatcmpl-01a183bf-bc16-7406-bb03-1ea38954944e`; content SHA `7fae066f7460d68d284b72060c7ddaff252bc7a6f23c419832b008a7045aaea8`. Raw candidate/field-level rejection reason were not retained: **exact cause unknown**. Independent outcome SHA `dd4be291ee271fd3e9e911b00563497abed38c3334dfc6c7c29054bfb0925cf1`. PR #8 cannot retroactively diagnose these failures.

Original evidence remains only in operator checkout's ignored `.runs`; second authorization/claim/outcome records: `.runs/g3-main-postmerge-preflight-20261028T181223Z-256a7dfb/`. Both one-attempt allowances are exhausted. No retry, repair, allowance transfer or new inference authorized. Earlier failed G2 citation attempt estimate USD0.00455525 remains separately preserved. New-series combined estimate **USD0.03822200**, not provider-confirmed billing.

**NON_AI:** trusted positive 25/25; deliberate negative sensitivity 2/2/1; scripted mock 22/25. Never genuine reconstruction quality.

## Historical pins — spent authorization

Second G3 source `ceb28b6f2f2292f75f766fbd3fbefc0822cfef98`; context `sha256:8c65ba3baf30f4b08328200b6b27e77cc64cab3b23ff40c06e72c1294996493e`; unchanged private 25-case suite `sha256:0423935021db574bb68f654c1c37896c6ad4f6e5c40707c1bbe38459178b015b`. Packet SHA `a970f53eb955f6761c80d65eb0233a33c63d312f1631f49e6e3d32d50a5c1b5a` authorized one attempt, USD0.50 ceiling, no retries/repair; **consumed**. Changed main/backend requires fresh exact-checkout zero-call preflight and separate owner spending authorization. No credentials during nonbillable work.

## Acceptance and execution

| Priority | Deliverable | State / exact acceptance condition |
|---|---|---|
| P0 | Real G3 admission/intelligence | Two real failures. Resolve reproducible generation/admission issues nonbillably, preserve negative gates, independent review before new spending proposal |
| P0 | Modular backend/control plane/API | Implementation in progress. Prove transactional/idempotent state, migrations, typed API, approvals/budgets, bounded workers and existing-engine/verifier integration at exact combined head |
| P0 | Genuine independently measured candidate | **NOT DEMONSTRATED**: separately authorized authentic candidate admitted/executed/scored with complete provenance |
| P0 | Reproducibility/security/export | CLI tested; integrated backend pending. Clean setup, recovery/duplicate-operation/security acceptance, checksum-verifiable export, exact Linux/Windows CI |
| P1 | Recovery/observability/bounded repair/deployment readiness | Integrated acceptance pending; real repair only after baseline and separate authorization |
| P1 | Read-only demo/reporting | Merged; full browser/product acceptance unverified |
| P2 | Additional adapters/cloud/horizontal scale | Deferred until measured need after reliable core |

Frontend expansion is stopped. Capture → Organize → Distill → Execute must reuse existing engine/receipts/evaluator, not duplicate orchestrators or scoring. Isolated unit tests are not end-to-end acceptance; no infrastructure production-ready claim.

Parallel short-lived file-disjoint branches/PRs are owner-authorized. Routine merges require exact-head green CI, independent review and repository protections; synchronize main before subsequent integration. Paid inference/retries, credential operations, live deployment and material scope expansion still require separate authorization.

Submission completion, final video and organizer acceptance are **UNVERIFIED**. Deadline recorded in PRD: 2026-11-05 02:00 UTC / 07:30 IST, not newly organizer-verified. Greatest deadline risks: no admitted authentic candidate and incomplete integrated backend acceptance. Cut P2 before provenance/scoring/honest failure reporting.
