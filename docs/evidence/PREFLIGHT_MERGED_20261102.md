# Zero-call preflight — merged release-review branch (2026-11-02)

Purpose: verify the integrated branch (PR #23 science + PR #24 product)
still validates the genuine G2 inputs exactly, with no inference.

Command (credential deliberately absent, `--mode preflight`):

```
python -m second_source.reconstruct --mode preflight --synthesis guided \
  --max-usd 0.50 --ledger-dir <genuine G2 evidence> \
  --hypotheses-file <original hypotheses> --observation-digests @g2 \
  --g2-receipt <G2_receipt.json> --g2-receipt-sha256 947910b0… \
  --seal-dir <fresh external seal> --run-dir <external run dir>
```

Result:

- `result: preflight_ready`, `provider_calls: 0`
- `approved_context_digest: sha256:93a9a01ad473e7aa3b92ba1726c9552d41f049a77355671b202993566a5bf009`
  — identical to the frozen rev-6/rev-7 context, so the merge preserves
  the genuine science inputs bit-for-bit.
- `evidence_artifact_count: 5`; fresh-seal suite digest differs from the
  frozen rev-6 suite by construction (new seal), so this preflight is a
  compatibility check, not a rev-7 execution authorization.
- No model call was made; rev-7 remains PROPOSED and unexecuted per owner
  decision (ship the measured 14/25).
