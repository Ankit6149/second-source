# Second Source — current delivery board

**Current as of 28 October 2026.** Evidence first. This is the current status; older dated acceptance reports remain historical snapshots. The [Master PRD](MASTER_PRD.md) defines the full product, and the [submission runbook](HACKATHON_SUBMISSION_RUNBOOK.md) defines the external deliverables.

## Source and engineering acceptance

| Checkpoint | Verified state |
|---|---|
| [PR #5](https://github.com/Ankit6149/second-source/pull/5) | Merged at `bc9f9c11bb029a99ee3aa022749f266355aaa7e1`, one G2 discovery journal, zero-cost G2 → G3 workflow. Main CI [40722455069](https://github.com/Ankit6149/second-source/actions/runs/40722455069) succeeded Linux425/0/3, Windows426/0/2 plus bootstrap |
| [PR #6](https://github.com/Ankit6149/second-source/pull/6) | Merged at `ceb28b6f2f2292f75f766fbd3fbefc0822cfef98`, additive broker diagnostic preservation. [Exact PR-head CI](https://github.com/Ankit6149/second-source/actions/runs/40736323555) succeeded Linux428/0/3, Windows429/0/2 + bootstrap. Review/negative probes passed. |
| [PR #7](https://github.com/Ankit6149/second-source/pull/7) | New read-only operator/evidence console and smoke tests. Separate review/CI required before claiming UI acceptance or merging |
| Cost/auth boundary | No merge or demo action grants further real model attempts, repair or paid retries |

A passing test suite certifies tested contracts, **not real reconstruction quality**. The complete project is not released.

## Actual model work — do not confuse with scripted controls

**Genuine G2:** Fresh 28 October operator discovery `real-g2-20261028T163538Z-fd60310f` recorded 3 original hypotheses, 5 hash-valid observations, a 3-action model-selected experiment, and 2 genuine `meta-direct / muse-spark-1.3` receipts. Usage 2809 input / 2347 output, receipt-derived estimated `$0.013486`, uncertain `$0`. The independent local review reports validated original-batch/citation and external receipt association. This evidence is local and not a provider-signed billing attestation; the prior 27 October incomplete run remains historical, not recovered.

**Genuine G3:** One separately authorized attempt on the above inputs `real-g3-from-g2-20261028T164126Z-8ee4d156`: 3314 input / 1456 output tokens, estimated `$0.0103305`, uncertain `$0`, outcome `broker_failed` **before candidate admission**. No candidate was scored and no repair lift exists. The precise provider/model failure reason was lost by the earlier reporting path. PR #6 saves future sanitized codes and response IDs but does not explain/recover that consumed attempt. No automatic retry, second paid call or repair authorized.

**NON_AI engineering controls:** scripted negative/naive candidate 22 passed / 3 failed / 0 indeterminate out of 25; hand-authored trusted positive 25/25; deliberate negative sensitivity 2/2/1. These are deliberately not framed as Meta model quality.

## Hackathon acceptance by outcome

| Priority | Demo/PRD deliverable | State | Exact next condition |
|---|---|---|---|
| P0 | Authorized black-box reference and guard | Implemented, tested | Show real action/policy denial with recorded event IDs |
| P0 | Model-driven active discovery and evidence | **One genuine G2 success observed** | Create sanitized, independently inspectable judge-facing trace without raw private response disclosure |
| P0 | Genuine candidate synthesis | **FAILED before admission** | A *new separately authorized* real candidate must be admitted, executed and archived. No mock relabeling |
| P0 | Independent model-generated behavior score | **NOT MEASURED** | Exact frozen suite score with numerator, denominator, failures, indeterminate and origin receipt |
| P0 | Product investigation/results experience | Read-only responsive UI in PR #7, not yet certified | Review responsive/keyboard/import/export and integrate with genuine sanitized report |
| P0 | Public reproducibility / originality / video / submission | In progress, not submitted | Validated judge package, <=180-second video and submission confirmation |
| P1 | Model-led bounded repair and improvement delta | Not demonstrated | Only after real baseline, same unchanged evaluator, separate authorization |
| P1 | API/web second target, hosted orchestration | Not demonstrated | Only after first real score and demo, or explicitly mark deferred |
| P2 | Generalized cloud/multi-target feature breadth | Deferred | Outside current critical path |

## Immediate execution order

1. Finish exact post-merge main CI and review demo-console PR #7; keep any public sample labels honest and private sealed inputs off the web.
2. Revalidate zero-call G3 preflight on **actual merged main execution bytes** with genuine G2 witness, exact original batch, external sealed suite and all corresponding pins. Previously supplied local preflight from PR #6 source is not a substitute for the new checkout.
3. Diagnose schema/candidate-admission risks using **nonbillable** tests. Do not run the provider to discover a failure category without owner authorization.
4. Seek a **separate owner decision** for one new G3 synthesis (proposed allowance <=$0.50, single attempt, max2000 output, no repair), then independently score and archive the true outcome. This is an application spending bound, *not guaranteed provider billing*.
5. Finish console/claim mapping to genuine sanitized evidence; record a truthful demo and submit early.
6. Intelligence workstream: constraint-guided synthesis skeleton plus strict fill merge (PR #9, nonbillable, pending review/CI); v2 mock wire end-to-end proven before any real attempt.

**Cut rule:** Drop P2 and any unproven repair/second-surface scenes before dropping the honest Meta causal chain, independent scoring, redaction or submission.

**Deadline from PRD:** 2026-11-05 02:00 UTC / 07:30 IST. Target submission on Nov 4 IST.

## Accounting/limitations

Existing new runs' receipt-based combined estimated G2+G3 model charges: **USD0.0238165** for successful G2 and failed G3 alone; including the separate earlier incomplete G2 attempt of `$0.00455525`, the reported new-series total is `$0.02837175` (not provider-confirmed billing). The old 27 October run is separate.

No client-side HTML viewer proves input attestation; signed provider truth, unredacted archive access, auto resume, cloud background operation, arbitrary-code sandbox and universal clone equivalence are not claimed. Live status events and one-click portable authenticated evidence archive remain unimplemented beyond CLI/read-only projections.
