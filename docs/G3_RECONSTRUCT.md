# G3 Reconstruct — verified zero-cost engineering / real inference NO-GO

**Status pointer - 29 October 2026 IST.** Use the [single current delivery board](G3_DELIVERY_BOARD.md) for exact published SHA/CI, both consumed real G3 attempts, evidence and backend acceptance. This document does not authorize inference, credentials or deployment.

**Current delivery and exact CI:** [authoritative board](G3_DELIVERY_BOARD.md).
This runbook documents supported commands; it does not grant input, spending
or merge approval. Preflight inspects a proposed budget, not owner consent.

Single reproducible command owning the full G3 path: approved scope, G2
evidence/hypotheses, pinned generation broker, CandidateSpec loader, trusted
interpreter (evaluator-owned worker), independent sealed evaluator, sanitized
run report.

## Guided synthesis binding

Published reproduction baseline is main `2dd919bf54cbc77318be20ba1468698d7a49fbfb`; [post-merge CI 40845419026](https://github.com/Ankit6149/second-source/actions/runs/40845419026) passed Linux 504/0/3, Windows 505/0/2 and bootstrap 505/0/2 BOOTSTRAP_OK. Guided binding is implemented in source `3c77390f94c839364b83025918d7109c0e2bea3a`, [PR #11](https://github.com/Ankit6149/second-source/pull/11). Its exact-head CI and review are recorded on that PR; the baseline CI above does not certify this newer interface. Local independent checks passed all 17 new cases, including explicitly NON_AI controls.

The existing command defaults to `--synthesis full` (maximum 2000 output tokens). `--synthesis guided` explicitly selects the guided protocol (maximum 800 output tokens). Use the same selection in zero-call preflight and any later separately authorized operation. A version-2 domain-separated input approval binds the protocol: a full-protocol context pin or spent historical packet cannot approve guided dispatch. Fresh exact-checkout preflight is required after code/protocol changes; no new spending is authorized here.

The existing gateway audit hook writes create-once private run artifacts `generation-dispatch.v1.private.json` and `generation-result.v1.private.json`. A successful provider response is archived before semantic candidate admission so a later rejection can be inspected without another call. Invalid provider responses may not expose their raw body; do not promise universal raw-output recovery. The hook receives no credential or signing key. Original request/response content remains private and is excluded from sanitized public exports. Existing consumed attempts are unchanged and cannot be retroactively diagnosed by this archive path.

## Modes

```powershell
# Fully nonbillable plumbing run (default). Fresh local evidence, mock
# channel with a deliberately naive spec, sealed 25-case score.
.venv/Scripts/python.exe -m second_source.reconstruct --mode mock

# ZERO-CALL inspection of genuine operator G2 inputs. No provider, no
# inference. Prints the context digest for separate owner review and freezes
# the suite the real run must reuse.
.venv/Scripts/python.exe -m second_source.reconstruct --mode preflight `
  --max-usd 0.50 --ledger-dir <approved-ledger> `
  --hypotheses-file <batch.json> --observation-digests <d1,d2,...> `
  --g2-receipt <G2-run/G2_receipt.json> `
  --g2-receipt-sha256 <externally-retained-receipt-hash> `
  --seal-dir <external-dir>

# Real run. EVERY input below is required; any gap fails closed with
# BLOCKED_* and no provider transport.
# BILLABLE TEMPLATE ONLY; separate owner approval required. Configure key securely.
$env:SECOND_SOURCE_MAX_RUN_USD = "0.50"
.venv/Scripts/python.exe -m second_source.reconstruct --mode real `
  --max-usd 0.50 --confirm-real-run `
  --operator-context-pin <preflight-approved-digest> `
  --ledger-dir <approved-ledger> --hypotheses-file <batch.json> `
  --observation-digests <d1,d2,...> `
  --g2-receipt <same-G2-run/G2_receipt.json> `
  --g2-receipt-sha256 <same-externally-retained-receipt-hash> `
  --suite <preflight-frozen-suite.json> --suite-digest <digest>
```

`--run-dir` defaults to `.runs/<id>/` (git-ignored, create-once: every
pre-existing directory is refused, including empty or interrupted ones).
`--fixture` accepts only `owned-ledger`. Reports, candidate bytes, and the
broker-artifact envelope publish atomically (staging write + fsync, then a
no-clobber link): a partial write never appears under a final name, and a
second publish is rejected, never merged. The HMAC authority key is never
persisted; the archived local signature is replay evidence for the frozen
evaluator only, not provider attestation.

## Critical provenance rule

A digest printed by `--mode mock` authenticates **that mock context only**.
It never approves historical G2 inputs and must never be supplied as
`--operator-context-pin`. Real approval flows exclusively through
`--mode preflight` run against the actual operator ledger/hypotheses, whose
printed `approved_context_digest` the owner reviews out of band. The real
invocation re-derives that digest from the same inputs and the broker rejects
any mismatch before transport. A suite sealed for one scope/budget is not
valid for another: the suite digest binds the exact scope (budgets included).

## Real-run authorization matrix

No billable call happens unless ALL hold: `MODEL_API_KEY` set,
`SECOND_SOURCE_MAX_RUN_USD` finite positive, `--max-usd` finite positive
within both that env limit and the $0.50 hard cap (`NaN`/`inf`/zero/negative
rejected before evidence loading or provider construction),
`--confirm-real-run`, `--operator-context-pin`, operator
ledger/hypotheses/digests, and a frozen `--suite`/`--suite-digest`. The broker
additionally enforces single-use tickets, frozen code pins, and attempt
limits. The historical one-attempt **$0.50** proposals are consumed; this runbook proposes no new spending allowance.

A complete version-2 G2 receipt with its external SHA-256 witness is also
required. The original exported batch, exact observation set, target and
reference/public bytes must match. All receipts must have genuine origin;
complete mock archives remain NON_AI and are refused before key access.

## Durable run states (CLI + report `stop_reason`)

| State | Meaning | Exit | Next action |
|---|---|---|---|
| `completed_mock_run` | mock plumbing scored on sealed suite | 0 | review context digest; run preflight on genuine inputs |
| `preflight_ready` | zero-call inspection recorded, no provider touched | 0 | approve digest + frozen suite out of band, then `--mode real` |
| `completed_real_run` | genuine score on frozen suite | 0 | optional bounded repair is a separate approval |
| `blocked_*` | missing approval/input, pre-dispatch, zero attempts, no report | 2 | resolve the named gap and re-invoke |
| `broker_failed` | generation dispatch failed; admitted nothing; budget mirrored | 1 | fix the broker category; mock origin is never relabeled real |
| `evaluation_failed` | candidate admitted + archived, scoring failed; budget mirrored | 1 | admitted bytes retained for offline replay; fix and re-invoke |
| `interrupted_stopped` | stopped outcome with candidate, budget, uncertain spend preserved | 130 | receipts are complete; re-invoke only deliberately |
| `inspection_failed` | request inspection rejected, zero attempts | 1 | fix inputs; no provider was reached |

Failure receipts carry `attempts`, estimated/uncertain USD, and a category —
never provider exceptions or secret values verbatim. Scores print as honest
`passed/failed/indeterminate/total` (mock default currently 22/25); a mock
score is plumbing evidence, never reconstruction success.

## Report (`.runs/<id>/G3_report.json`, git-ignored)

`kind`, `mode`, `origin` (`mock`/`real`, never relabeled), `spec_digest` plus
the persisted `candidate.v1.json` bytes (digest-verified on reload, offline
re-score supported) and the `broker-artifact.v1.json` envelope (exact broker
payload + signature + sanitized origin receipt), `scope_digest`,
`suite_digest`, `approved_context_digest`, `plan_digest`, the full pinned
`evaluation_receipt` (comparator/interpreter/adapter/reference/environment/
origin-receipt/registry digests), reference command id + source digest, exact
counts, actual token/attempt/estimated/uncertain counters mirrored from the
trusted budget, `stop_reason`. Preflight receipts reuse the evaluator's
detached `inspection_manifest()` so identical genuine inputs hash identically
in every process. No prompts, observations, credentials, case ids, hidden
inputs, reference source, or HMAC keys. No REAL-RUN-READY or production
claim is made while acceptance gates are open.

## Operator visibility

Every run emits ordered stderr progress events (`evidence_ready`,
`inspected`, `admitted`, `evaluated`, `reported`, `stopped`) carrying the run
ID after the associated operation succeeds. These stderr notifications are
not themselves a durable stage journal. Reports include a
plain-language `evaluation_summary` (counts plus per-category mismatch
lines); mock scores are labeled plumbing evidence, never success.

## G2 persistence (new discoveries only)

`src/second_source/g2_persistence.py` is the single version-2 discovery
journal: complete original responses/batches, evidence references, model
attempts/receipts, actual experiment linkage and terminal accounting are
create-once stage records under `discovery/`, sealed by `G2_receipt.json`.
Offline inspect/restore does not resume execution. Only a complete archive
with its externally retained receipt hash can export an original batch for
this existing G3 preflight. Old `g2_manifest.json` files cannot be promoted
without their missing provenance. The [approval package](G2_G3_APPROVAL_PACKAGE.md)
documents zero-call G2 preflight, mock demonstration and gated real operation.

To exercise G2 -> G3 without replacing its observations or hypotheses, first
run G2 mock discovery, retain the receipt hash and export its complete original
batch using that witness. Then invoke this same `--mode mock` command with
`--ledger-dir`, `--hypotheses-file`, `--observation-digests`, `--g2-receipt` and
`--g2-receipt-sha256`, as shown in the approval package. Supply all five input
arguments together. The authenticated mock archive feeds the same evaluator;
the default scripted candidate scores22/25 NON_AI. Bound input provenance is
published before the sole mock dispatch. This does not grant real approval.

## Status

Published main/CI and local backend work are recorded on [delivery board](G3_DELIVERY_BOARD.md). G2/G3 CLI engineering implemented; new genuine G2 complete. Two genuine G3 attempts failed before admission; no candidate/score. Both grants consumed; no retry/repair/credential access/new inference authorized.

PR #8 adds complete authenticated observation auto-binding using literal `--observation-digests '@g2'` with genuine `--g2-receipt` and external `--g2-receipt-sha256`. Future admission codes improve diagnostics, not retrospective failure diagnosis or model quality. Resolve reproducible generation/admission issues nonbillably, then fresh exact-source preflight and separate spending decision. Controls remain NON_AI.
