# Owned synthetic ledger fixture

**Status pointer - 29 October 2026 IST.** Use the [single current delivery board](../../docs/G3_DELIVERY_BOARD.md) for exact published SHA/CI, both consumed real G3 attempts, evidence and backend acceptance. This document does not authorize inference, credentials or deployment.

New original synthetic program written during the hackathon. It accepts one JSON command per stdin line, emits one JSON response per line, and starts with empty state on each process launch. The observation adapter is allowed to call the fixed executable but does not provide this source to the model. The fixture contains intentionally discoverable rules (case-insensitive duplicate labels, numeric bounds, stable item IDs, stateful removal).

**Important:** this repository is public. It is not enough to write a prompt saying "do not peek". Any future model/candidate sandbox must receive **no repository checkout or tool access** to `reference.py`, hidden evaluation inputs, or generated expected outputs. Package reference execution and evaluator in distinct trust boundaries. A GitHub-readable fixture cannot be considered truly secret from a model with unrestricted internet or repository access. This release demonstrates process-level black-box API discipline; production-strength sealed benchmark isolation is a future deployment gate.
