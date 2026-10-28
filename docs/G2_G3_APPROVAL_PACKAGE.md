# Genuine G2 → G3 run — owner approval package (no paid calls made)

This package is everything the owner reviews before authorizing one real
Meta-powered reconstruction. Nothing here executes inference; every value is
either observed from committed code or a blank the owner must fill.

## 1. Required authentic inputs (owner supplies, tool verifies)

| Input | Source | Binding |
|---|---|---|
| G2 evidence ledger directory | Fresh separately-approved G2 discovery with `g2_manifest.json` (see `src/second_source/g2_persistence.py`) — never the historical run, whose hypothesis text is irrecoverably absent | Content-addressed digests; `ledger.inspect` rejects tampering |
| Hypothesis batch JSON | Same discovery's complete batch (statements + cited digests + statuses) | `validate_batch` against ledger digests |
| `--observation-digests` | Manifest's recorded digests | Must equal the approved set |
| Frozen sealed suite + digest | `--mode preflight` seal (external dir) reviewed out of band | Digest equality; scope-bound (budgets included) |
| `--operator-context-pin` | `approved_context_digest` printed by preflight on THESE inputs | Broker rejects mismatch before transport |

Historical verdict: the accepted `real-g2-20261027T192406Z-5482abee` run
retained 5 hash-valid observations, 2 real provider receipts (response IDs
`chatcmpl-01a17ed1-…`, `chatcmpl-01a17ed2-…`, $0.012715 estimated), and the
hypothesis/proposal IDs — but no hypothesis statements, citations, proposal
payloads, or response content. It is **not usable** as G3 input. A new G2
discovery with durable persistence is the only authentic path; nothing here
recreates the missing text.

Read-only recovery audit (report SHA-256 recomputed from the local `.runs/`
archives; statements/citations absent in all four):

| Run | Report SHA-256 | Observations | Usable as G3 input |
|---|---|---|---|
| `real-g2-20261027T184607Z-73bbd66a` | `8e39a104…a4c1a7` | 5 hash-valid, no hygiene/digest check | No: hypotheses/receipts absent |
| `real-g2-20261027T190034Z-530e42f8` | `6ad25013…d2dd0b` | 5 hash-valid | No: hypotheses/receipts absent |
| `real-g2-20261027T190454Z-f43553c6` | `ac8519c8…8a30` | 5 hash-valid | No: hypotheses/receipts absent |
| `real-g2-20261027T192406Z-5482abee` | `05aa16f0…c2c0e` | 5 hash-valid + 2 real receipts | No: statements/citations absent |

## 1b. Discovery manifest gate (new discoveries)

Every new G2 run writes a validated create-once `g2_manifest.json`
(`src/second_source/g2_persistence.py`): complete batches, executed
proposals, evidence digests, per-stage model receipts, budget state.
Inspect any archive with zero calls before approval:

```powershell
.venv/Scripts/python.exe -m second_source.g2_inspect <run-dir>
```

Exit 0 with `"approvable": true` is required. The gate rejects: missing
receipts or hypothesize coverage, substituted final statements/citations
(only status changes allowed; resume promotes statuses only), failed or
interrupted rounds (preserved durably, never approvable until an approved
recovery re-runs discovery), cross-process pin drift, and ledger tampering.
`--mode preflight` cross-checks the manifest when `--g2-manifest` is given;
`--mode real` requires it.

## 2. Expected API operations (from committed code)

- Exactly **1** synthesize call (`attempt_limit = min(max_model_calls,
  1 + min(2, max_repair_rounds))`), model `muse-spark-1.3`, schema-constrained
  `CandidateSpec` output, prompt `synthesize-v1`.
- Pricing (committed `MODEL_PRICING`): $1.25 / 1M input, $4.25 / 1M output.
- Worst-case reservation is booked **before** transport; breach raises
  `BudgetExhausted` with zero transport. Failure books uncertain spend.
- Repair (`≤2` rounds, aggregate feedback only) needs a separate approval;
  this package covers single-pass generation + evaluation only.

## 3. Maximum spending

Hard cap **$0.50** (`MAX_REAL_RUN_USD`), additionally bounded by
`SECOND_SOURCE_MAX_RUN_USD`. `--max-usd` must be finite, positive, and within
both, validated before evidence loading or provider construction.

## 4. Immutable pins recorded in the run report

Scope, suite, approved context, plan, observation/hypothesis registries, code
pins (13 modules + reference + manifest), reference identity, candidate and
origin-receipt digests, single-use ticket nonce, `REAL_MODEL` claim
enforcement (mock artifacts cannot claim real accuracy).

## 5. Command sequence

```powershell
.venv/Scripts/python.exe -m second_source.reconstruct --mode preflight --max-usd 0.50 --ledger-dir <L> --hypotheses-file <H> --observation-digests <D> --seal-dir <S>
# owner reviews G3_preflight.json digest + frozen suite out of band, then:
$env:MODEL_API_KEY = "<owner key>"
$env:SECOND_SOURCE_MAX_RUN_USD = "0.50"
.venv/Scripts/python.exe -m second_source.reconstruct --mode real --max-usd 0.50 --confirm-real-run --operator-context-pin <digest> --ledger-dir <L> --hypotheses-file <H> --observation-digests <D> --suite <S/suite.json> --suite-digest <digest>
```

## 6. Acceptance checks for the real run

Real provider receipt (`real: true`, non-empty response ID), candidate digest
equality across artifact/report/receipt, exact 25-case
passed/failed/indeterminate counts from the frozen suite, positive 25/25 and
2/2/1 negative controls still green, usage/uncertain costs reconciled to the
budget, no sealed material or secrets in any output.

## 7. Owner decision required

[ ] Authorize a new G2 discovery (billable, same $0.50 discipline, durable manifest)
[ ] Approve the preflight context digest + frozen suite
[ ] Authorize the single G3 synthesize run (max $0.50)
[ ] Merge PR #5 (engineering milestone only, separate from real-run approval)
