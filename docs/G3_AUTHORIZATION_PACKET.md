# G3 Exact-Input Inference Authorization Packet

**Status: REV-6 APPROVAL CONSUMED 2026-10-31 (attempt 5: admitted, 14/25). No open inference authorization remains in this document; any further paid call needs a new packet revision and explicit approval.**

**Revision 6 (source-vocabulary grounding):** the executable source is `54d5f7947d200479aac0f8bd5cced35b4f1084ed` (`eng/g3-readiness` head; exact-head CI run `41211853605` green on Linux and Windows). Addresses the rev-5 attempt failure at its root: the strict loader's per-command source table is now a shared constant (`RESPOND_SOURCES`) published model-visibly in the request envelope, with the prompt directing bindings from each command's own list; loader semantics unchanged. Fresh zero-call preflight from the exact checkout: `.runs/g3-preflight-guided-54d5f79/G3_preflight.json` (SHA-256 `36daa2c5204da1d38af43207f602030b28369ad7e3401a0f1c6c46e2c35239c2`), result `preflight_ready`, provider calls `0`, context `sha256:93a9a01a…` (unchanged inputs), new wire `sha256:5e111137007339e1aa78f5f84fb61f02e8290d5487e99ff7fb049421a1e98fab` with cap 4096, code pins `candidate_generation 52d88fd5…`, `candidate_spec edc76e44…` (all other pins unchanged).
**Revision 5 (envelope-key fix):** the executable source was `4b6676306b0a42a09f153a9855b3e447b79ad315` (exact-head CI run `41205135657` green on Linux and Windows). Fixes the rev-4 attempt failure at its root: the request now declares the runtime envelope (`ok`/`error` owned by runtime), the fill schema forbids those keys, the prompt names them, and the merger diagnostic names the envelope. Fresh zero-call preflight from the exact checkout: `.runs/g3-preflight-guided-4b66763/G3_preflight.json` (SHA-256 `617c9ad1276087068b72ff2ddce6112192e97d60ef54e5a1569a144fcaac34b3`), result `preflight_ready`, provider calls `0`, context `sha256:93a9a01a…` (unchanged inputs), new wire `sha256:8274d439929d6c432fa1656fd914a17562eefd421c5dc18700a9865c9b240178` with cap 4096, code pins `candidate_generation 8189001c…`, `schema_validate 74a85aef…` (all other pins unchanged).
**Revision 4 (exact-head re-pin):** the executable source was `875eb64e8cb81a7151b3d48119d2db5f0c581fc6` (exact-head CI run `41195766252` green on Linux and Windows; `src/` identical to `dcda5fb`). `git diff dcda5fb..875eb64` touches only `tests/test_g3_readiness.py` and this packet — `src/` is byte-identical, so code pins, wire digest, and context digest are unchanged from rev 3. Fresh zero-call preflight from the exact checkout: `.runs/g3-20261031T113051Z-c7a1aad2/G3_preflight.json` (SHA-256 `eb1a83cb33dc2bbb44dae52471dc6141f04eb25b996d7e212cd5fefdb3fe6123`), result `preflight_ready`, provider calls `0`, plan digest `sha256:c4958cd645864e712d1c5c60ae89409f7ccca0481cf77dad9944d5a60178ca7e` (per-run unique by design: the frozen plan binds a fresh `run_id`, so plan digests differ between preflights while context/wire/code pins stay identical).
**Revision 3 (source identity + reservation proof):** the executable source was
`dcda5fbf86417282a0d0ba7c46a9654992bd6671` (`eng/g3-readiness` head, which
contains the 4096 remediation; `main @ bc16065` predates it and MUST NOT be
used for this attempt). Code pins from the zero-call preflight:
`candidate_generation 476be65c…`, matching the working tree byte for byte.
If PR #23 merges before approval, re-pin to the new `main` SHA and re-run
preflight; do not substitute SHAs.
**Revision 2 (remediation):** guided `max_completion_tokens` raised 800 → 4096
after the 2026-10-31 attempt returned `EMPTY_MODEL_RESPONSE`
(`finish_reason=length`; 798 reasoning tokens consumed inside the 800 cap
with zero content). All other terms unchanged. The failed attempt and its
receipts are preserved untouched; this packet proposes the next single call,
not a retry of any consumed allowance.

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
  semantics) at 556 vs 945 model-output chars with a 4096-token output cap
  (vs 2000 for full), shrinking cost and schema-violation surface with zero
  measured expressiveness loss on the ledger DSL.
- Maximum generation attempts: **1**. Repair rounds: **0** (real-mode repair
  needs a separate authorization; the operator refuses `--repair-rounds`
  otherwise).
- Maximum permitted spend: **$0.50** hard ceiling (`MAX_REAL_RUN_USD`;
  the operator blocks above it before any provider use). Expected cost from
  measured worst case: **under $0.022** (guided input measured at 2556
  tokens on the failed attempt × $1.25/M ≈ $0.0032, plus the full 4096-token
  output cap × $4.25/M ≈ $0.0174). The cap admits ~798 reasoning tokens plus
  fill content with margin; `reasoning_effort` stays `low`. Reservation proof
  (`model_gateway.py`): real-provider calls reserve `est_out =
  request.max_output_tokens` BEFORE dispatch and breach raises, so the full
  4096-token ceiling (reasoning included, as reasoning tokens bill as output)
  is covered by the $0.50 ceiling or the call never dispatches.
- Uncertain-cost handling: the run fails closed if `uncertain_cost_usd`
  cannot be bounded inside the ceiling; uncertain remainder is reported, not
  absorbed.
- Data-use mode: default provider API handling only. No training-use
  agreement, zero-retention endpoint, or regional processing guarantee is in
  place — stated explicitly so approval is informed.

## Exact frozen inputs

- Operator checkout (exact executable source SHA):
  `54d5f7947d200479aac0f8bd5cced35b4f1084ed` (branch `eng/g3-readiness`, rev 6;
  verified `git rev-parse HEAD`; `dcda5fb` (rev 3) is src-identical and superseded). Earlier revisions named `bc16065`, which
  lacks the 4096 remediation — that pairing is withdrawn.
- Genuine G2 run: `real-g2-20261028T163538Z-fd60310f` (`REAL_EXPERIMENT_OBSERVED`;
  2 real calls, `muse-spark-1.3`, `$0.013486` estimated, `$0` uncertain).
- G2 receipt SHA-256: `947910b0f645b78b9234859a899db3412171cbbbb3c400e072c9f661840e31f8`
- Hypotheses (original, 3 items):
  `.runs/codex-g2-independent-20261028T164026Z-e0a9d2e6/hypotheses.original.json`
  SHA-256 `8fb04fa0dcf9e86b5fac5716bea2693966bc6144851ee34a785ca8071e7e615f`
- Evidence ledger (5 artifacts): `630c986a…cfdc40`, `8909c2c6…f8452d71e`,
  `c3c08bbe…6c54f4`, `ca3922a0…9e2ccc530`, `da499546…a59eb9` (full digests in
  the preflight file below).
- Current zero-call preflight (4096 cap, exact head `54d5f79`, rev 6): `.runs/g3-preflight-guided-54d5f79/G3_preflight.json`, SHA-256 `36daa2c5204da1d38af43207f602030b28369ad7e3401a0f1c6c46e2c35239c2`, result `preflight_ready`, provider calls `0`, context `sha256:93a9a01a…`, wire `sha256:5e111137…`, plan `sha256:fcf2350c…` (per-run unique by design).
- Superseded zero-call preflight (4096 cap, `4b66763`, rev 5): `.runs/g3-preflight-guided-4b66763/G3_preflight.json`, SHA-256 `617c9ad1276087068b72ff2ddce6112192e97d60ef54e5a1569a144fcaac34b3`, result `preflight_ready`, provider calls `0`, wire `sha256:8274d439…`.
- Superseded zero-call preflight (4096 cap, exact head `875eb64`): `.runs/g3-20261031T113051Z-c7a1aad2/G3_preflight.json`, SHA-256 `eb1a83cb33dc2bbb44dae52471dc6141f04eb25b996d7e212cd5fefdb3fe6123`, result `preflight_ready`, provider calls `0`, context `sha256:93a9a01a…`, wire `sha256:f1e72efb…`, plan `sha256:c4958cd6…` (per-run unique by design).
- Superseded zero-call preflight (4096 cap, `dcda5fb`): `.runs/g3-preflight-guided-dcda5fb/G3_preflight.json`,
  result `preflight_ready`, provider calls `0`, plan digest
  `sha256:70b3f103be742d9d5bc39135e1979b69b7c38c03a2f196d66d64a898ad91ff8d`.
  Inspected guided wire digest `sha256:f1e72efb…` with
  `request_max_output_tokens: 4096`, `reasoning_effort: low`.
- Superseded 4096 preflight: `.runs/g3-readiness-preflight-guided-4096/G3_preflight.json`
  SHA-256 computed at approval time from that file; result `preflight_ready`,
  provider calls `0`, inspected wire digest
  `sha256:f1e72efb6e296aaabe939e28c074e6b4c8f5424907d15a3773a700ae3056aadb`
  with `request_max_output_tokens: 4096`, synthesis `guided`, ceiling `$0.50`.
- Prior zero-call preflight: `.runs/g3-readiness-preflight-20261031/G3_preflight.json`
  SHA-256 `51d190d1069e59749c24af9aa3942a751f631a3fba85fce6d6a56ed9b9564139`,
  result `preflight_ready`, provider calls `0`.
- Approved context digest (guided): `sha256:93a9a01ad473e7aa3b92ba1726c9552d41f049a77355671b202993566a5bf009`
  (Revision 1 of this packet wrongly listed the full-mode pin
  `sha256:8c65ba3b…`; the broker domain-separates protocol pins and rejects
  the cross-protocol pairing with zero provider contact. The guided pin above
  is the only valid pin for the proposed guided call.)
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
- Attempt 4 (rev-5 authorized): genuine response `chatcmpl-01a1925f-…` (2695 in / 1814 out tokens, $0.0110782, uncertain $0), envelope-clean but `CANDIDATE_SPEC_INVALID`: `command 'list': respond source 'records' unresolvable`. Evidence in `.runs/real-g3-guided-20261031T133000Z-rev5/`. Root cause addressed in rev 6; allowance consumed.
- Attempt 3 (rev-4 authorized): genuine response `chatcmpl-01a191e3-…` (2556 in / 1242 out tokens, $0.0084735, uncertain $0) but `POST_MODEL_ADMISSION_REJECTED` at `candidate_admission`: the fill echoed envelope key `ok` as a respond binding. Evidence in `.runs/real-g3-guided-20261031T121200Z-authorized1/`. Root cause fixed in rev 5; allowance consumed.
- Attempt 2: broker failure at dispatch (`MODEL_GATEWAY_ERROR`, response
  `chatcmpl-01a183bf-…`, 3314 in / 1343 out tokens); evaluation: none.
- Attempt 5 (rev-6 authorized, executed 2026-10-31): ADMITTED and independently scored — `completed_real_run`, response `chatcmpl-01a19314-…`, candidate `sha256:ee1f3f32…a146cd`, **14 passed / 11 failed / 0 indeterminate / 25** (2 error-category + 9 schema-category mismatches), 2756 in / 2555 out tokens, $0.01430375 estimated, $0 uncertain. Evidence in `.runs/real-g3-guided-20261031T153000Z-rev6/`. Offline replay of the preserved candidate bytes reproduces 14/11/0 identically. Allowance consumed; no repair authorized or attempted.
- Attempts 1–4 admitted no candidate and produced no score. This packet
  proposes the next attempt, not a retry of either allowance.

## Expected outputs on approval

Admitted candidate bytes + broker envelope + evaluation receipt + full
independent manifest (`evaluation-manifest.v1.json`), exact 25-case counts,
model response identity, token/uncertain-cost receipts, and a sanitized
report — or a truthful `broker_failed`/`evaluation_failed` report with the
same provenance. A mock result is never a substitute.

## Owner approval checklist (out of band) — CONSUMED by attempt 5; retained as procedure for future revisions

1. Confirm suite reuse (digest above) or cut a fresh sealed bundle.
2. Approve provider, model, guided protocol, 1 attempt, $0.50 ceiling.
3. Set `MODEL_API_KEY` + `SECOND_SOURCE_MAX_RUN_USD=0.50` in the operator
   environment only (never in chat, files, or logs).
4. Invoke the exact preflight-pinned command; hand resulting evidence to an
   independent verifier before any further spend.
