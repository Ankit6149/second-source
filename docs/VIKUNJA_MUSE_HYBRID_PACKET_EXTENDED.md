# Muse hybrid packet — Vikunja frozen + extended (PREPARED, NOT EXECUTED)

Status: **PREPARED ONLY. Do not execute without a fresh owner packet.**
No model call has been made under this packet. No score is claimed.
Prepared by Agent H (independent QA) as a Gate A–F follow-up.

## Goal

One Muse (REAL_MODEL) hybrid arm, decomposed per route, targeting
**≥5/6 on the frozen Vikunja suite AND ≥5/6 on the new frozen extended
suite**. Compiler (NON_AI) 6/6 remains a control, never relabeled as a
model result. Anything below 5/6 on either suite is reported as-is.

## Frozen material (freeze before any prompt use — done)

| Suite | File | SHA-256 |
|---|---|---|
| Frozen Vikunja (original) | `scripts/vikunja_held_out.py` | `2B7E01DBCEF43F7230F16AA896E4118F5CB09C2930878B1D836CEFF023E6C5B5` |
| Extended Vikunja v1 (new, 6 seqs) | `scripts/vikunja_held_out_extended.py` | `AE666B22F05DAAA6B5D0A67D2EA3D268BAE825E0A2E26B2EEE2A5124745E218B` |

Rules: neither file is ever copied into a prompt, subtask context, or
agent-accessible notes. Isolation is AST-tested
(`tests/test_vikunja_extended_isolation.py`, mirroring the existing
held-out AST test). Any edit to either file bumps its version and
invalidates comparisons. Prompts are built ONLY from
`.runs/vikunja-benchmark/public_observations.json` (20 public probes).

## Ordered execution (only after owner authorization)

- **S0 — Compiler baseline first ($0, NON_AI).** Compile from public
  observations (`evidence_compiler.compile_spec`), serve via the generic
  interpreter, and score the compiler candidate differentially on BOTH
  suites with fresh reference + fresh candidate instances (evaluator-only
  runner importing `vikunja_benchmark` canonicalization; frozen files
  unedited). Record both baselines. *Not yet run in this preparation:
  no Vikunja reference server/binary is present in this checkout — S0
  is a hard precondition, not an optional step.*
- **S1 — Freeze + provenance split.** Freeze template/method/path
  (`COMPILED_FROZEN_FIELDS`); model may decide only
  `REPAIR_EDITABLE_FIELDS` (≤8 edits). Templates are non-emittable.
- **S2 — Per-route subtasks.** One route per Muse call via
  `ModelGateway`/`MetaProvider` (never bare HTTP), each with light public
  observations + field inventory for that route only. Monolithic
  single-call spec authoring is prohibited (measured 2/6 cap).
- **S3 — Public-conformance gate per edit.** Before/after diff on the
  PUBLIC ladder only; any edit increasing divergences is rejected.
- **S4 — Bounded repair.** ≤8 edits, ≤1 repair call, same gate.
- **S5 — Single final evaluation.** Each suite evaluated ONCE, fresh
  instances, evaluator-only. No iterative tuning against either suite.

## Receipt durability (at call completion — mandatory)

Before dispatch: journal `{seq, call_id, stage, model, prompt_version,
reservation}`. Immediately on completion (success OR failure, before
any next call): synchronously write the receipt (provider, response id,
tokens, estimated/uncertain cost, content hash, failure code) with
fsync, append the budget-ledger snapshot, and copy the receipt hash
outside the run directory as witness. A crash loses at most the
in-flight call, booked uncertain. (Fixes the lost Meta receipts defect;
reuses `ModelGateway` reserve/commit + `DiscoveryJournal` machinery.)

## Owner fields — must be filled before execution

- `packet_id`: ______________________
- `max_spend_usd` (hard cap): ______________________
- `max_model_calls`: ______________________
- `expires_at` (freshness window): ______________________
- Authorizing owner + date: ______________________

Execution must route through `SpendingGuard.check()` with this packet;
paid mode without a fresh, matching, unexpired packet fails closed
(`SPEND_PACKET_REQUIRED` / `SPEND_PACKET_STALE` / `SPEND_LIMIT_EXCEEDED`).

## Abort / reporting

Abort on: any held-out leak into a prompt, any frozen-field overwrite
without a complete justified-override record, any public-conformance
regression, budget exhaustion, or provider failure (recorded unscored,
never as 0). Report per-suite scores separately with provenance
REAL_MODEL; publish receipts with the result.
