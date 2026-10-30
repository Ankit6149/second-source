# G3 Repair — Worker Integration Contract (Muse engine side)

**Status pointer.** This contract describes the engine-owned repair surface
that the backend worker (Codex-owned) can invoke. It changes no backend file:
the worker keeps full ownership of `backend/worker.py`, `service.py`, the API,
and all persistence/migration decisions. Engine changes live in
`src/second_source/repair_loop.py`, `src/second_source/reconstruct.py`
(`--mode mock --repair-rounds`), and `tests/test_g3_repair_loop.py`.

## Supported repair configuration

- Repair runs only through the operator CLI today:
  `second_source.reconstruct --mode mock --repair-rounds N` with `N` in
  `{1, 2, 3}` (default `0` = single generate/evaluate, behavior unchanged).
- Mock-only. Real mode rejects `--repair-rounds` without a separate,
  explicitly authorized repair approval; the broker's own attempt cap
  (`min(max_model_calls, 1 + min(2, max_repair_rounds))`, default 3 total
  generations per run) stays authoritative and stops the loop with a
  preserved broker diagnostic.
- The HTTP layer must never accept a client-supplied repair count: any future
  worker integration must hard-code the bound server-side (or in worker
  argv), never bind it to request input. `G3MockEngine` currently invokes
  `--mode mock` WITHOUT the flag, so API→worker→repair→export is explicitly
  NOT yet integrated (see § Lifecycle below for the hook point).

## Report schema additions (all additive; existing keys unchanged)

- `initial_evaluation`, `initial_candidate_digest`, `initial_response_id`,
  `initial_candidate_artifact`: the true original, always present.
- `selected`: `{version, candidate_digest, response_id, evaluation,
  candidate_artifact, broker_artifact}` where `version` is `"initial"` or
  `"repair-N"`. Top-level `evaluation`/`spec_digest`/`response_id`/
  `candidate_artifact`/`broker_artifact` always describe the SELECTED version.
- `selection_policy`: `"best_failed_then_indeterminate_then_earliest"`.
  Minimum `(failed, indeterminate)`; ties keep the earliest version, so a
  later regression is never silently promoted.
- `repair_history` (null when no repair ran): `{verdict, stop_reason,
  rounds_used, selection_policy, versions[], broker_diagnostic}`; each
  version carries `{round, candidate_digest, response_id, origin, evaluation,
  feedback, files}` with `files = {candidate, envelope, receipt}`.
- Perfect means exactly `passed == total` with zero failed AND zero
  indeterminate; counts are strictly validated (nonnegative integers summing
  to the denominator). An indeterminate outcome is never success.

## Version artifacts and offline replay

Per version, immutable round-tagged files: `candidate.v1.json` /
`candidate.rN.json` (admitted spec bytes), `broker-artifact.v1.json` /
`broker-artifact.rN.json` (payload + local HMAC attestation; never provider
proof), `evaluation-receipt.v1.json` / `evaluation-receipt.rN.json` (counts,
origin receipt, aggregate feedback). Replay: reload any candidate bytes
through `CandidateReferenceAdapter` and compare `spec_digest`; re-verify the
envelope against the run's `G3_repair_history.json` digests. The HMAC
authority key is never persisted.

## Lifecycle events (progress stream)

`repair` (bounded retry starts, names the initial failed/indeterminate
counts), then `repaired` (verdict `improved`) or `repair_done` (any other
verdict, names the verdict). The existing `evidence_ready → inspected →
admitted → evaluated → reported` sequence is unchanged. Interruption
(`KeyboardInterrupt`) propagates: already-persisted versions stay on disk and
the operator writes its standard stopped failure report; in-memory-only
retries are never silently kept.

## Budget accounting

Initial generation plus repair attempts share the run's immutable budget and
the broker's single-use tickets. The driver never widens either; hitting the
broker cap stops with `stop_reason: broker_blocked`, the broker diagnostic
attached, and the full version history retained.

## P1 design note — feedback-conditioned synthesis (NOT implemented)

Today regeneration reuses the frozen approved context (honest bounded retry).
A future feedback-conditioned path must: (a) define a versioned repair-hint
schema carrying ONLY aggregate sanitized failure data (counts, categories,
requirement IDs — never sealed cases, gold values, reference internals, or
private evaluator material); (b) give the amended request a new versioned
identity, updated context digest, and separate admission checks; (c) require
fresh explicit authorization without mutating historical approved inputs; (d)
ship nonbillable tests proving the redaction boundary (sealed canaries must
not reach the request wire). Real-mode repair stays disabled until that
design is independently reviewed and explicitly authorized.

## Frontend data mapping (truthful fields)

Observations/hypotheses: existing ledger fields. Candidate versions:
`repair_history.versions[]` (round, digests, counts, files). Progress:
lifecycle events above. Verification: `selected.evaluation` + `suite_digest`
+ sealed-suite-withheld notice. Repair: `verdict`, `stop_reason`, and the
initial-vs-selected comparison. Anything labeled mock stays mock; a failed
broker attempt is unmeasured, never zero.
