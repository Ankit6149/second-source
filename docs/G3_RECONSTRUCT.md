# G3 Reconstruct — operator workflow (REAL-RUN-READY, no paid calls made)

Single reproducible command owning the full G3 path: approved scope, G2
evidence/hypotheses, pinned generation broker, CandidateSpec loader, trusted
interpreter (evaluator-owned worker), independent sealed evaluator, sanitized
run report.

## Commands

```powershell
# Fully nonbillable plumbing run (default). Fresh local evidence, mock
# channel with a deliberately naive spec, sealed 25-case score.
.venv/Scripts/python.exe -m second_source.reconstruct --mode mock

# Real run. EVERY input below is required; any gap fails closed with
# BLOCKED_* and no provider transport.
$env:MODEL_API_KEY = "<owner key>"
$env:SECOND_SOURCE_MAX_RUN_USD = "0.50"
.venv/Scripts/python.exe -m second_source.reconstruct --mode real `
  --max-usd 0.50 --confirm-real-run `
  --operator-context-pin <approved-context-digest> `
  --ledger-dir <approved-ledger> --hypotheses-file <batch.json> `
  --observation-digests <d1,d2,...> `
  --suite <frozen-suite.json> --suite-digest <digest>
```

Useful options: `--run-dir` (default `.runs/<id>/`, git-ignored),
`--seal-dir` (external fresh-suite directory for mock; default system temp —
sealed material must stay outside the Git checkout), `--fixture`
(only `owned-ledger` is registered).

## Real-run authorization matrix

No billable call happens unless ALL hold: `MODEL_API_KEY` set,
`SECOND_SOURCE_MAX_RUN_USD` positive, `--max-usd` within both that env limit
and the $0.50 hard cap, `--confirm-real-run`, `--operator-context-pin`,
operator ledger/hypotheses/digests, and a frozen `--suite`/`--suite-digest`.
The evaluator broker additionally enforces single-use tickets, frozen code
pins, and attempt limits. Proposed maximum spend for the first real run:
**$0.50**.

## Pin workflow (no paid calls yet)

1. Run `--mode mock`; read `approved_context_digest` from stdout.
2. Operator reviews the frozen context (scope projection, redacted evidence,
   hypotheses) and approves its digest out of band.
3. Real run passes that digest as `--operator-context-pin`; the broker
   rejects any mismatch before transport.

## Report (`.runs/<id>/G3_report.json`, git-ignored)

`kind`, `mode`, `origin` (`mock`/`real`, never relabeled), `spec_digest`,
`scope_digest`, `suite_digest`, `approved_context_digest`, `plan_digest`,
reference command id + source digest, exact
`passed/failed/indeterminate/total`, token usage, estimated/uncertain USD,
`stop_reason`, and the sealed-suite path. No prompts, observations,
credentials, case ids, hidden inputs, or reference source.

## Status

REAL-RUN-READY checkpoint: mock path proven end to end (naive spec honestly
scores below 25/25); real path implemented but never executed — missing owner
approvals: spend authorization, API key, approved G2 evidence pin, frozen
suite selection. Repair (`--repairs`) is cut for this milestone; single-pass
generation + evaluation only.
