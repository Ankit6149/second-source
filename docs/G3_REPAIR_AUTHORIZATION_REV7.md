# G3 Genuine Repair Authorization — REV 7 (PROPOSED — NOT APPROVED)

**Status: PROPOSED 2026-11-01. No inference authorized by this document.
No paid call has been made under it. Rev-6 is CONSUMED (attempt 5: admitted,
14/25 on 2026-10-31); there is no standing unused inference authorization.**

## Proposed operation (genuine repair only, no fresh synthesis)

- Repair the admitted rev-6 v1 candidate with strictly aggregate,
  feedback-conditioned guided generations (`synthesize-v2-repair1`).
- Maximum NEW model calls: **2** (`--repair-rounds 2`, one generation per
  round; single-use round-bound tickets; the loop stops early on perfect).
- Initial-synthesis calls: **0** (the seed candidate already exists).
- Provider: `meta-direct`. Model: `muse-spark-1.3`.
  Protocol: **guided repair** (`SYNTHESIZE_PROMPT_VERSION_V2_REPAIR`),
  `max_completion_tokens=4096`, `reasoning_effort=low` (same cap/params as
  rev-6; repair wire = guided wire shape plus `repair_guidance`).
- Executable source: `6139a8cfa98fc36dd40a6f116430057ec858d234`
  (branch `eng/g3-readiness`; exact-head CI run `41294793533` green on
  Linux and Windows). Source contains the real-mode repair wiring
  (`--confirm-real-repair` gate, `REAL_MODEL` replay claims,
  best-of-lineage selection, per-version receipts).

## Seed under repair (preserved rev-6 evidence, immutable)

- Run: `.runs/real-g3-guided-20261031T153000Z-rev6/`
  (`completed_real_run`, offline replay reproduces the score identically).
- Candidate: `sha256:ee1f3f32e66050bbdf2dde86aaba09e56d17b25c21c35762eeea6208c2a146cd`
- Genuine response: `chatcmpl-01a19314-e7c6-7014-bddd-a49e08a6c210`
  (2756 in / 2555 out tokens, $0.01430375 estimated, $0 uncertain).
- Independent evaluation: **14 passed / 11 failed / 0 indeterminate / 25**
  (`failure_categories: {error: 2, schema: 9}`).
- Model-facing repair feedback (aggregate only, sanitized by construction,
  sealed-clean by `test_repair_rounds_carry_no_sealed_or_reference_material`):
  `{"failed": 11, "failure_categories": {"error": 2, "schema": 9},
  "indeterminate": 0, "passed": 14, "total": 25}`.
  No case IDs, inputs, expected outputs, or reference source reach the model.

## Exact frozen inputs (unchanged from rev-6)

- Approved guided context digest:
  `sha256:93a9a01ad473e7aa3b92ba1726c9552d41f049a77355671b202993566a5bf009`
- Sealed suite digest:
  `sha256:0423935021db574bb68f654c1c37896c6ad4f6e5c40707c1bbe38459178b015b`
  (25 cases, `owned-ledger-v1`; denominator MUST stay 25 across rounds —
  the loop halts with `denominator_changed` otherwise; suite reuse needs
  explicit owner confirmation at approval).
- Genuine G2 run `real-g2-20261028T163538Z-fd60310f`, receipt SHA-256
  `947910b0f645b78b9234859a899db3412171cbbbb3c400e072c9f661840e31f8`;
  hypotheses `.runs/codex-g2-independent-20261028T164026Z-e0a9d2e6/hypotheses.original.json`
  (`8fb04fa0…`); 5 evidence artifacts (`630c986a…`, `8909c2c6…`,
  `c3c08bbe…`, `ca3922a0…`, `da499546…`).
- Scope `cli_ledger` / `REQ-LEDGER`; reference `owned-ledger-v1`
  (source digest `sha256:539cf592…`).

## Cost (reservation-proof, fail-closed)

- Per-call reservation covers the FULL 4096-token output ceiling
  (reasoning bills as output) plus input: worst case ≈ 4000 input tokens
  × $1.25/M ($0.005) + 4096 × $4.25/M ($0.0174) ≈ **$0.023/call**.
- Two rounds: worst-case reserved ≈ **$0.046**; expected under $0.035
  (rev-6 measured $0.0143 for a same-shape call).
- Hard ceiling **$0.50** (`MAX_REAL_RUN_USD`; the operator blocks above it
  before any provider use). Uncertain cost fails closed, never absorbed.
- Spend of $0.00 has occurred under this revision.

## Stop, selection, and failure conditions

- Stop early with no further calls on 25/25 (`repaired_to_perfect`),
  `no_repair_needed` (already perfect — not the case: seed is 14/25),
  `rounds_exhausted`, broker/admission failure, budget breach, or
  denominator change. No retries beyond the 2 authorized rounds; no
  refills; consumed allowance is never reused.
- Selection: best-of-lineage (fewest failed, then indeterminate, then
  earliest); the v1 seed is always retained and replays identically, so
  the reported score cannot go below 14/25 by selection construction —
  `repair_history` records every version either way.
- Every failure is a truthful `broker_failed` / `evaluation_failed` /
  `unrepaired` report with receipts, never a silent success.

## Zero-call preflight evidence (exact checkout `6139a8c`, 2026-11-01)

Full genuine inputs + `--synthesis guided --confirm-real-run
--confirm-real-repair --repair-rounds 2`, credential deliberately absent:

`BLOCKED_REAL_MODEL: configure MODEL_API_KEY securely after exact input approval.`

All frozen inputs validated (context pin, evidence, suite freeze, G2
binding, spend gates, repair authorization gate) with **0 provider calls**
and no run directory created. A `--synthesis`-less invocation is correctly
rejected at the evaluator (`EvaluationBlocked`), proving the guided pin
cannot authorize a full-protocol run.

## Known limitations (disclosed, not waived)

- Repair rounds archive admitted candidate bytes, receipts, and evaluation
  per version, but NOT verbatim raw provider responses (initial generation
  only). Per-round wire digests are runtime-bound in single-use signed
  repair tickets (`round` / `repair_of` / `feedback_digest`), not pre-pinned.
- A second repair proposal after this allowance needs a new packet.
- Mock/fake-provider repair successes demonstrate loop mechanics ONLY,
  never model quality.

## Owner approval checklist (out of band)

1. Confirm suite reuse (digest above) or cut a fresh bundle and re-pin.
2. Approve provider, model, guided-repair protocol, ≤2 new attempts,
   $0.50 ceiling, expected <$0.05.
3. Set `MODEL_API_KEY` + `SECOND_SOURCE_MAX_RUN_USD=0.50` in the operator
   environment only (never in chat, files, or logs).
4. Invoke with the pinned digests above; hand ALL resulting evidence to an
   independent verifier before any further spend.
