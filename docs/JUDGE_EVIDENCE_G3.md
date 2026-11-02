# Judge evidence — genuine Meta G3 reconstruction (14/25)

**Purpose.** Make the one genuine Meta-model result in this repository
understandable in five minutes: what was observed, what the model built,
how it was scored independently, where it failed, and what is *not* claimed.

All numbers below come from the sanitized export in
[`evidence/g3-rev6-sanitized/`](evidence/g3-rev6-sanitized/) (exported with
`scripts/export_g3_evidence.py`; private receipts excluded by construction).

## The experiment

| Step | What happened | Evidence |
|---|---|---|
| Reference | Owned stateful ledger CLI (`owned-ledger-v1`): `add` / `list` / `total` / `remove` over stdin JSONL. Source never sent to the model. | `fixtures/owned_ledger/reference.py`, source digest `sha256:539cf592…` |
| Discovery (G2) | Genuine Meta Muse Spark 1.3 reasoning produced evidence-linked hypotheses and experiments against the authorized reference. | G2 run `real-g2-20261028T163538Z-fd60310f`, receipt SHA-256 `947910b0…` |
| Synthesis (G3) | Muse Spark 1.3 (`meta-direct`, guided `synthesize-v2`) filled a declarative candidate spec — no executable code. Response `chatcmpl-01a19314-e7c6-7014-bddd-a49e08a6c210`, 2,756 in / 2,555 out tokens, est. $0.0143. | `candidate.v1.json`, digest `sha256:ee1f3f32…` |
| Evaluation | Independent pinned evaluator ran the candidate against a frozen, sealed 25-case suite (digest `sha256:04239350…`) outside model context. | `G3_report.json` |

## Result (REAL_MODEL)

**14 passed / 11 failed / 0 indeterminate / 25** — 9 `schema` mismatches,
2 `error` mismatches. `g3_accepted: false`. This is a measured partial
reconstruction, not a success claim.

## Reference vs candidate — concrete mismatches

Reproduced locally on public (non-sealed) probes by running the reference
and the candidate interpreter on identical inputs:

| Probe | Reference (observed) | Meta candidate | Category |
|---|---|---|---|
| `add {label:"Milk", amount:2}` | `{"ok":true,"id":"1"}` | `{"ok":true,"id":"1","label":"Milk","amount":2}` — extra fields | schema |
| `add Milk`, then `add MILK` | second rejected `duplicate_label` (case-insensitive) | accepted (`unique_casefold:false`) | error |
| `add {amount:500}` | rejected `invalid_amount` (max 100) | accepted (guessed max 1,000,000) | error |
| `add {label: 30 chars}` | rejected `invalid_label` (max 24) | accepted (guessed max 100) | schema |
| `remove {id:"1"}` | `{"ok":true,"removed":"1"}` | `{"ok":true,"id":"1"}` — wrong field name | schema |

The pattern is scientifically interesting: the model inferred the command
set, state model, IDs, aggregation and most error codes correctly from
black-box evidence, but guessed wrong values for unprobed boundary rules
(label/amount limits, case-folding) and response shapes. Those are exactly
the behaviors a screenshot or prompt cannot reveal — and exactly what
active, hypothesis-driven probing is designed to settle.

## What is NOT claimed

- **No repair improvement is claimed.** Rev-7 proposes ≤2 aggregate-feedback
  repair calls (≤$0.50 ceiling); it is **PROPOSED, not approved**, and zero
  calls have been made under it. See
  [`G3_REPAIR_AUTHORIZATION_REV7.md`](G3_REPAIR_AUTHORIZATION_REV7.md).
- **Provider attestation is incomplete.** The broker artifact is a local
  attestation (`BROKER_ARTIFACT_LOCAL_ATTESTATION_NOT_PROVIDER`); the
  ephemeral broker signature cannot be reverified. The 14/25 score was
  reproduced by offline replay at pinned source, which verifies internal
  consistency, not provider provenance.
- **NON_AI controls are separate.** Deterministic mock/HTTP results
  (e.g. 25→30/30 on the owned HTTP fixture) test the harness and repair
  loop mechanics. They are never presented as Meta model scores.

## Limits

- One target, one genuine synthesis, one sealed suite of 25 cases.
- The sealed suite and private receipts are not published; judges see
  digests, the candidate, and the sanitized report, not gold cases.
- `G3_report.json` retains the original local `report_path`; review before
  public redistribution.
