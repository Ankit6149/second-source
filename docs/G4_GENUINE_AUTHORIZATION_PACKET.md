# G4 Genuine HTTP Reconstruction — Authorization Packet (PROPOSED)

**Status: PROPOSED 2026-11-02. No genuine HTTP inference has occurred.**
This packet requests ONE bounded genuine experiment. It does not authorize
repair rounds, retries, or any second synthesis.

## What already exists (zero spend, verified)

- `--mode discover-real` (new): genuine Meta planner discovery over the
  owned HTTP reference. Fail-closed without `--confirm-real-run`, positive
  budget, env cap, and `MODEL_API_KEY`. Hermetic tests prove the loop,
  persistence, and preflight binding with a fake provider (5 tests).
- `--mode real` (existing): gated genuine guided synthesis + independent
  30-case sealed evaluation, `REAL_MODEL` claim labeling.
- Zero-call preflight on hermetic inputs: `preflight_ready`,
  `provider_calls: 0`, context `sha256:07b5d804…`, suite
  `sha256:f464fb48…` (fresh seal; the genuine run re-preflights and
  re-pins before any call).

## Proposed operation

1. **Genuine discovery** — `--mode discover-real --max-usd 0.50
   --confirm-real-run`: Muse Spark 1.3 (`meta-direct`) hypothesizes from
   authorized observations and proposes scope-guarded experiments.
   Planner budget is scope-capped at **10 model calls**.
2. **Zero-call preflight** on the genuine ledger/hypotheses; owner
   approves the exact context digest out of band. **No calls.**
3. **Genuine synthesis** — `--mode real` with that pin: **1 guided
   generation** (`http-synthesize-v1`), admitted or rejected on schema,
   then independently evaluated on the frozen 30-case suite.
   `--repair-rounds 0` (repair needs a separate packet).

## Cost (fail-closed)

- Pricing pinned: muse-spark-1.3 at $1.25/M in, $4.25/M out.
- Worst case per call ≈ $0.023 (4k-token output ceiling). Discovery ≤10
  calls + 1 synthesis: theoretical worst ≈ $0.25; expected <$0.10
  (comparable genuine runs measured $0.007–$0.014 per call).
- Hard ceiling **$0.50** enforced three ways: `--max-usd`, env
  `SECOND_SOURCE_MAX_RUN_USD`, and gateway budget reservation. Uncertain
  cost fails closed. No refills, no fallback provider, no auto-retry.

## Recording (any outcome)

- Discovery summary with per-call receipts, response IDs, usage; run
  report with candidate digest, evaluation counts, dimension counts.
- Failures (broker, admission, evaluation) are recorded as truthful
  failure reports — never retried silently, never scored as zero.
- Sanitized export only; private receipts never leave the operator
  machine; sealed cases never enter model context.

## Owner approval checklist (out of band)

1. Approve target `owned-http-task-workflow-v1`, provider `meta-direct`,
   model `muse-spark-1.3`, ≤11 total calls, $0.50 hard ceiling.
2. Set `MODEL_API_KEY` + `SECOND_SOURCE_MAX_RUN_USD=0.50` in the operator
   environment only (never in chat, files, or logs).
3. After discovery, approve the printed preflight context digest before
   synthesis. Stop anywhere; each stage is independently complete.
