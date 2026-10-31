# G3 Exact-Input Inference Authorization Packet

**Status: PREPARED — NOT APPROVED. No inference authorized by this document.**

Generic approval of the engineering directive is explicitly NOT spending
approval. A real run requires the owner to approve THIS packet out of band
(the exact provider, model, protocol, inputs, attempt count, and spend
ceiling below), after which the operator invokes `--mode real` with the
pinned digests. Historical authorizations are consumed and are not reused.

## Proposed operation (single attempt, no repair)

- Provider: `meta-direct`. Model: `muse-spark-1.3`.
- Protocol: **guided** (`synthesize-v2`): trusted skeleton plus bounded model
  fill. Rationale (nonbillable evidence, `tests/test_g3_readiness.py`):
  guided merges to the exact full-spec control candidate (byte-identical
  semantics) at 556 vs 945 model-output chars with an 800-token output cap
  (vs 2000 for full), shrinking cost and schema-violation surface with zero
  measured expressiveness loss on the ledger DSL.
- Maximum generation attempts: **1**. Repair rounds: **0** (real-mode repair
  needs a separate authorization; the operator refuses `--repair-rounds`
  otherwise).
- Maximum permitted spend: **$0.50** hard ceiling (`MAX_REAL_RUN_USD`;
  the operator blocks above it before any provider use). Expected cost from
  priced rehearsal accounting: under **$0.02** (guided input ~2k tokens,
  output capped at 800).
- Uncertain-cost handling: the run fails closed if `uncertain_cost_usd`
  cannot be bounded inside the ceiling; uncertain remainder is reported, not
  absorbed.
- Data-use mode: default provider API handling only. No training-use
  agreement, zero-retention endpoint, or regional processing guarantee is in
  place — stated explicitly so approval is informed.

## Exact frozen inputs

- Operator checkout (source SHA): `bc16065bae17be1e96f29f16cd20ae66b2c8e3a8`
- Genuine G2 run: `real-g2-20261028T163538Z-fd60310f` (`REAL_EXPERIMENT_OBSERVED`;
  2 real calls, `muse-spark-1.3`, `$0.013486` estimated, `$0` uncertain).
- G2 receipt SHA-256: `947910b0f645b78b9234859a899db3412171cbbbb3c400e072c9f661840e31f8`
- Hypotheses (original, 3 items):
  `.runs/codex-g2-independent-20261028T164026Z-e0a9d2e6/hypotheses.original.json`
  SHA-256 `8fb04fa0dcf9e86b5fac5716bea2693966bc6144851ee34a785ca8071e7e615f`
- Evidence ledger (5 artifacts): `630c986a…cfdc40`, `8909c2c6…f8452d71e`,
  `c3c08bbe…6c54f4`, `ca3922a0…9e2ccc530`, `da499546…a59eb9` (full digests in
  the preflight file below).
- Zero-call preflight: `.runs/g3-readiness-preflight-20261031/G3_preflight.json`
  SHA-256 `51d190d1069e59749c24af9aa3942a751f631a3fba85fce6d6a56ed9b9564139`,
  result `preflight_ready`, provider calls `0`.
- Approved context digest: `sha256:8c65ba3baf30f4b08328200b6b27e77cc64cab3b23ff40c06e72c1294996493e`
- Sealed suite digest: `sha256:0423935021db574bb68f654c1c37896c6ad4f6e5c40707c1bbe38459178b015b`
  (25 cases, `owned-ledger-v1`; reuses the previously cut sealed bundle —
  confirm explicitly at approval, or cut a fresh bundle and re-pin).
- Reference identity: `owned-ledger-v1`. Scope: `cli_ledger` / `REQ-LEDGER`.

## Sealed-boundary guarantee (tested, not asserted)

`tests/test_g3_readiness.py::test_generation_wires_carry_no_sealed_material`
captures the exact model-request bytes for both protocols and proves no
sealed case ID, suite path, reference source, or gold marker is present;
`prepare_generation_request` additionally rejects listed forbidden markers.
Repair rounds reuse the frozen wire byte-for-byte
(`test_repair_rounds_carry_no_sealed_or_reference_material`).

## Historical attempts (retained evidence only)

- Attempt 1: `broker_failed` before admission; candidate admitted: no;
  evaluation: none; precise rejection cause UNKNOWN by record (the broker
  collapsed detail; no response ID retained). Do not infer a cause.
- Attempt 2: broker failure at dispatch (`MODEL_GATEWAY_ERROR`, response
  `chatcmpl-01a183bf-…`, 3314 in / 1343 out tokens); evaluation: none.
- Neither attempt admitted a candidate or produced a score. This packet
  proposes the next attempt, not a retry of either allowance.

## Expected outputs on approval

Admitted candidate bytes + broker envelope + evaluation receipt + full
independent manifest (`evaluation-manifest.v1.json`), exact 25-case counts,
model response identity, token/uncertain-cost receipts, and a sanitized
report — or a truthful `broker_failed`/`evaluation_failed` report with the
same provenance. A mock result is never a substitute.

## Owner approval checklist (out of band)

1. Confirm suite reuse (digest above) or cut a fresh sealed bundle.
2. Approve provider, model, guided protocol, 1 attempt, $0.50 ceiling.
3. Set `MODEL_API_KEY` + `SECOND_SOURCE_MAX_RUN_USD=0.50` in the operator
   environment only (never in chat, files, or logs).
4. Invoke the exact preflight-pinned command; hand resulting evidence to an
   independent verifier before any further spend.
