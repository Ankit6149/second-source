# Second Source — authoritative delivery board

**CURRENT — 29 October 2026 IST.** Single current status source. Dated audit records are historical. [Product PRD](MASTER_PRD.md); [owner backend directive](https://github.com/Ankit6149/second-source/issues/2#issuecomment-6477673246); [ownership/policy](COORDINATION_CHARTER.md).

## Published baseline

**Current verified main:** `1ba89054b7335aa7c26a0fa9e347d7d766eeeafe`, merged
[PR #11](https://github.com/Ankit6149/second-source/pull/11) with
[independent production review](https://github.com/Ankit6149/second-source/pull/11#pullrequestreview-5695343331).
[Exact post-merge CI 40849690763](https://github.com/Ankit6149/second-source/actions/runs/40849690763)
succeeded: Linux **521 passed / 0 failed / 3 skipped**, Windows **522 / 0 / 2**,
fresh Windows bootstrap **522 / 0 / 2, BOOTSTRAP_OK**; both demos passed.
The older checkpoints below remain historical evidence, not the current SHA.

PR #5 merged `bc9f9c11bb029a99ee3aa022749f266355aaa7e1`; PR #6 merged `ceb28b6f2f2292f75f766fbd3fbefc0822cfef98`; PR #7 merged `c214d60c8917f8e94859e268700c1ca07b4598b9`; PR #8 merged `0aba3bf42b735ae911b8b471aad43972abfa8d9d`; PR #10 merged `a2a82fae085540a7719646074b8cbe33a7ef0e7c` (durable NON_AI control plane); PR #9 merged prior main `2dd919bf54cbc77318be20ba1468698d7a49fbfb` (reviewed constraint-guided synthesis helpers).

| Verified checkpoint | Exact cross-platform CI |
|---|---|
| PR #10 merged `a2a82fae085540a7719646074b8cbe33a7ef0e7c` | [40759124434](https://github.com/Ankit6149/second-source/actions/runs/40759124434): Linux **490 passed / 0 failed / 3 skipped**; Windows **491 / 0 / 2**; Windows bootstrap passed |
| PR #9 independently reviewed head `9dd028e9c143e911e94dd85f75dec017d00f685b` | [40759540461](https://github.com/Ankit6149/second-source/actions/runs/40759540461): Linux **504 passed / 0 failed / 3 skipped**; Windows **505 / 0 / 2**; Windows bootstrap passed. Merged at `2dd919bf54cbc77318be20ba1468698d7a49fbfb` under standing reviewed-merge policy |

Prior main merge `2dd919bf54cbc77318be20ba1468698d7a49fbfb` also passed [post-merge CI 40845419026](https://github.com/Ankit6149/second-source/actions/runs/40845419026): Linux **504 passed / 0 failed / 3 skipped**; Windows **505 / 0 / 2**; bootstrap **505 / 0 / 2 BOOTSTRAP_OK**. These counts certify their named checkpoints only. Earlier `0aba3bf` CI 40747405916 (Linux 434/0/3, Windows 435/0/2) and consumed execution source `ceb28b6` CI 40742439039 (Linux 428/0/3, Windows 429/0/2) remain historical.

Codex [backend PR #10](https://github.com/Ankit6149/second-source/pull/10), merged after independent reviewer GO and [exact-head cross-platform CI](https://github.com/Ankit6149/second-source/actions/runs/40754050439): implemented contracts/store/service/API/worker/artifacts with local targeted **55 passed / 0 failed / 1 Windows symlink-privilege skip**. Independent non-author review of source `0d12930956a59df3539394c1c40095a9ae747f54` found no P0/P1 blocker and separately reproduced the service-to-existing-G3 mock/export/restart journey (20 passed / 0 failed / 1 privilege skip). The packaged wheel includes the SQL migration. These implementation checks are **NON_AI** and local SQLite/single-host; Cloud PostgreSQL and Google Auth remain unintegrated. Complete descendant cancellation remains best effort on both OS because some staged workers create independent sessions. No production-readiness claim.

Muse owns intelligence/gateway/generation/admission. [Guided synthesis PR #9](https://github.com/Ankit6149/second-source/pull/9) is merged after independent review of head `9dd028e9c143e911e94dd85f75dec017d00f685b` and its exact-head CI above. This is nonbillable engineering evidence, not a genuine successful candidate or retrospective diagnosis of either failed response. PR #7 remains a read-only console, not full browser/product certification; PR #8 adds authenticated G2 observation auto-binding and future admission diagnostics.

**Guided verifier binding:** source `3c77390f94c839364b83025918d7109c0e2bea3a`, [PR #11](https://github.com/Ankit6149/second-source/pull/11), based on main `2dd919bf54cbc77318be20ba1468698d7a49fbfb`. The full synthesis path remains the default. The implementation binds explicit guided mode through a version-2 domain-separated approval identity and immutable dispatch/result private receipts using the existing gateway. Local independent gates: **17 new cases passed / 0 remaining failures** across targeted runs; existing workflow/reconstruct **39 passed**, preflight/receipt/API/worker **66 passed / 1 Windows privilege skip**. Exact-head CI and independent review are recorded on PR #11; the earlier baseline CI does not certify this newer source. Explicit `--synthesis guided` uses an 800-token output cap; default full uses 2000. Protocol-separated input identity requires a fresh exact-checkout preflight; old/full approval cannot authorize guided dispatch. Immutable `generation-dispatch.v1.private.json` and `generation-result.v1.private.json` retain existing-gateway events privately, including successful response content before semantic admission. Provider-invalid raw bodies may remain unavailable. The audit hook receives neither credentials nor signing authority, and sanitized export excludes original private content. This interface must preserve existing strict admission, private evaluator controls, provenance and no-transport-under-invalid-approval gates.

Backend reproduction: [operations](BACKEND_OPERATIONS.md), [typed API/OpenAPI contract](BACKEND_API.md). The shared CLI/API control plane persists mock-only approvals, idempotent queueing, fenced leases, durable CODE events, cancellation and expired-run quarantine without replay. Its bounded worker calls the existing engine and reproduces **22/3/0/25 NON_AI**, then verifies a sanitized integrity bundle and restart. No paid engine adapter or HTTP spending authority is enabled; private original engine artifacts remain outside the public export.

## Frozen operator proposal — no spending authorization

The [latest Issue #2 handoff](https://github.com/Ankit6149/second-source/issues/2#issuecomment-6493220085)
records independent reproduction in the actual operator checkout at `1ba8905`:

| Identity | Exact pin |
|---|---|
| Guided context | `sha256:93a9a01ad473e7aa3b92ba1726c9552d41f049a77355671b202993566a5bf009` |
| Inspected request | `sha256:0fbc7a06aec86d4ca3bb218ffb607b6dbb65dd6e5b149d609ce71f96d320c762` |
| Unchanged 25-case suite | `sha256:0423935021db574bb68f654c1c37896c6ad4f6e5c40707c1bbe38459178b015b` |
| Genuine G2 witness | `947910b0f645b78b9234859a899db3412171cbbbb3c400e072c9f661840e31f8` |
| Operator packet SHA-256 | `f3387bd6f36ed9a638b2a242d8c26bc0931524b31911252eba2bae58e0dcf11b` |

Operator-local packet:
`.runs/g3-guided-zero-call-20261029T092644Z-8ca2e2e6/G3_GUIDED_APPROVAL_PACKET.json`.
It proposes one `meta-direct` / `muse-spark-1.3` Standard `synthesize-v2` call,
800 output tokens, $0.50 application ceiling, zero retries/repairs/discovery;
only an admitted candidate may be scored. Local initial reservation estimate
$0.0058025 is not a billing guarantee. This proposal remains **unauthorized**.
Both old allowances remain consumed. Credentials/inference require explicit
owner authorization of this exact packet and its prerequisite checks.

Raw-byte operator code pins are authoritative; LF/CRLF differs across worktrees.
Backend work in the verifier checkout does not authorize substituting that
checkout, editing frozen inputs, or refreshing the proposal silently.

## Nonbillable database continuation

`feat/postgres-baseline` in the separate verifier checkout records the
[unchanged already-applied SQL and lifecycle mapping](../supabase/README.md).
The recovered 10,244-byte export was matched to its retained connector statement
and SHA-256 `8a89975315fd8b9e1287bace3073e5fe7a3a185eb673c4341038234157d5aac2`.
Local embedded PostgreSQL 17.5 exercised the constraints/ACLs with synthetic
rows and complete rollback; native Linux PostgreSQL replay is included in the
existing pytest CI path through `tests/test_postgres_baseline.py`.
Independent review and exact-head CI are still required before merge.
This is a baseline prerequisite, not an implemented/connected cloud adapter.
No live DB access, credentials, migration application, inference or deployment.

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
| P0 | Modular backend/control plane/API | PR #10 merged and independently reviewed: local SQLite/single-host NON_AI service/API/worker/export journey. Production infrastructure and genuine paid-engine integration remain unproved; do not treat this as full product acceptance |
| P0 | Genuine independently measured candidate | **NOT DEMONSTRATED**: separately authorized authentic candidate admitted/executed/scored with complete provenance |
| P0 | Reproducibility/security/export | Backend NON_AI recovery/security/export tests and exact-head CI recorded above. Guided verifier binding and genuine model-driven integrated acceptance remain pending |
| P1 | Recovery/observability/bounded repair/deployment readiness | Integrated acceptance pending; real repair only after baseline and separate authorization |
| P1 | Read-only demo/reporting | Merged; full browser/product acceptance unverified |
| P2 | Additional adapters/cloud/horizontal scale | Deferred until measured need after reliable core |

Frontend expansion is stopped. Capture → Organize → Distill → Execute must reuse existing engine/receipts/evaluator, not duplicate orchestrators or scoring. Isolated unit tests are not end-to-end acceptance; no infrastructure production-ready claim.

Parallel short-lived file-disjoint branches/PRs are owner-authorized. Routine merges require exact-head green CI, independent review and repository protections; synchronize main before subsequent integration. Paid inference/retries, credential operations, live deployment and material scope expansion still require separate authorization.

Submission completion, final video and organizer acceptance are **UNVERIFIED**. Deadline recorded in PRD: 2026-11-05 02:00 UTC / 07:30 IST, not newly organizer-verified. Greatest deadline risks: no admitted authentic candidate and incomplete genuine model-driven integration acceptance. Cut P2 before provenance/scoring/honest failure reporting.
