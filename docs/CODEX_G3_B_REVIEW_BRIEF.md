# Codex G3-B Independent Audit Brief — Second Source (2026-10-28)

**Assignment phase 1: READ-ONLY independent technical audit. Do not edit shared G3-A files, push code, read credentials, or make paid calls.**
**Repository:** https://github.com/Ankit6149/second-source
**Sources:** `docs/MASTER_PRD.md`, `docs/G3_IMPLEMENTATION_CONTRACT.md`, `docs/COORDINATION_CHARTER.md` and `docs/HANDOFF_2026-10-28.md`.

## G3-B goal
Ensure the candidate runtime is evaluated by a separate, trusted verifier. The actual model-facing generation step MUST NOT receive gold inputs, expected outputs, hidden suite identifiers or original reference source. Model-written Python, shell or arbitrary code cannot run on Windows. The candidate is a typed, constrained, data-only spec executed by a trusted interpreter.

## Existing exact interface from G0
- `src/second_source/verifier.py` exports `ReferenceProtocol.execute_sequence(actions: list[dict], sequence_id: str|None) -> SequenceResult`, `SealedCase`, `DifferentialVerifier.verify(cases) -> EvaluationReport` and `EvaluationReport.model_feedback()`.
- `SequenceResult` is defined in `contracts.py`; each `Observation` has `input_action`, `output`, `status`, `sequence_id`, `action_index`.
- `CLIReferenceAdapter` uses a trusted executable fixed argv, with fresh process per sequence and retained state within sequence. Candidate must match reset semantics without shared state.
- `ScopeGuard.validate_candidate_files` rejects overbuild; all model-produced candidate artifacts must pass it before runtime.
- Current owned public manifest: `fixtures/owned_ledger/public_contract.json`; do not pass original reference source to a candidate-generation model.

## Required READ-ONLY audit output
1. Confirm exact current remote SHA and whether PR #1/G2 has merged; cite source paths and call out any contract mismatches.
2. Propose a minimal `CandidateReferenceAdapter`-compatible API that can accept Muse's typed candidate **only after** Muse has committed its G3-A spec interface.
3. Define a sealed-suite policy and evaluator-owned storage boundary: only evaluator process can access gold; inference prompt/tool set is demonstrably restricted; fail test if model can read originals/gold.
4. Outline tests by **behavioral category only** (valid/invalid inputs, duplicate logic, normalization, ordering, deletion, aggregate, reset, invalid shape, timeout); do not publish hidden case inputs/expected outputs to model context.
5. Define independent positive and deliberately buggy control implementations and how their outputs will be labeled `TRUSTED_CONTROL`, NOT `META_GENERATED`.
6. Identify how `EvaluationReport.model_feedback()` becomes the only repair signal: totals and aggregate mismatch categories, no case IDs and no gold inputs/expected outputs.
7. List attack tests: model-supplied shell/exec/import, filesystem escape, egress, oversized nested specs, overly long commands, unsupported DSL opcodes, candidate-induced hangs, cross-case state persistence, label spoofing, scope expansion and evaluator information leakage.
8. Propose deterministic mock-mode integration checks for Linux/Windows; never infer real accuracy from mock controls.
9. Return explicit severity, file/line references, proposed test names, blockers and a candidate adapter interface proposal. No code changes until G3-A interface is published and integration owner approves a disjoint write window.

## Implementation phase 2 (separately released by coordinator)
Once Muse publishes the G3-A interface and the owner confirms the assigned file boundary, Codex may implement ONLY:
- `src/second_source/candidate_adapter.py` and `src/second_source/g3_verification.py`;
- `tests/test_g3_verifier_*.py` and evaluator-only fixtures in a restricted path;
- `docs/G3_VERIFIER_ACCEPTANCE.md` with factual (not invented) tests.

Test via the existing `DifferentialVerifier` on the *same* ordered sequence and reset on both sides. Keep sealed suite out of inference context and candidate generation tool filesystem. Use one integration branch and commit window; no force pushes or duplicate `verifier.py` rewrite. Do not merge or run billable experiments.

## Output response contract
- Baseline SHA, actual read paths, found risks (severity + evidence).
- Exact adapters and types; test plan that avoids exposing gold.
- Proposed acceptance criteria and required G3-A interface.
- Whether a code-write handoff can begin (normally NO until Muse interface checkpoint).
- No optimistic claims, no estimated scores posed as real results.
