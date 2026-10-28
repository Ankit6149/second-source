# G3 G2-evidence auto-binding and admission diagnosis

**NONBILLABLE source change.** Both preflight and real G3 now accept `--observation-digests @g2` when paired with `--g2-receipt <path>/G2_receipt.json` and `--g2-receipt-sha256 <external-witness>`. The operator loads the entire original observation sequence from the authenticated version-2 G2 archive rather than attempting to reconstruct it from citations in an original hypothesis batch (which may cite only a subset). Missing/invalid witnesses, incomplete archives and duplicate evidence remain fail-closed before any credential access.

The trusted broker now distinguishes transport/schema rejection from **post-provider candidate admission rejection** using a fixed code, not exception text. A successful provider receipt followed by an invalid declarative candidate reports `failure_stage: candidate_admission` and `failure_code: CANDIDATE_SPEC_INVALID`; other post-response admission failures are `POST_MODEL_ADMISSION_REJECTED`. Existing model-schema failures retain their provider failure codes. No raw model output, original source, private paths or secrets are added to reports.

**Important:** These corrections do NOT repair the two consumed real attempts, imply an authentic score, or authorize another billable invocation. Any changed code/source requires a fresh zero-call preflight, exact checkout, context/suite pin and separate explicit owner approval. Run the focused tests, then exact-head cross-platform CI before accepting this source.

The auto-binding value is intended as a literal PowerShell argument `'@g2'`. It avoids fragile, manually concatenated 64-hex strings in wrapped chat messages.
