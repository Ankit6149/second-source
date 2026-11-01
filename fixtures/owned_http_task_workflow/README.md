# Owned HTTP Task-Workflow Target (`owned-http-task-workflow-v1`)

Independent, stateful HTTP API reference target, end-to-end evidence-driven pipeline integration, and evaluation harness for Second Source **G4** multi-target generalization.

## Purpose

Unlike the G3 CLI JSONL ledger fixtures (`fixtures/owned_ledger/` and `fixtures/owned_ledger_variant/`), this fixture exposes an HTTP/1.1 task-workflow service with:
- Stateful CRUD and workflow transitions across `todo`, `in_progress`, `blocked`, `done`, and `cancelled`
- Role- and ownership-based access control via synthetic actors (`X-Synthetic-Actor`: `alice`, `bob`, `viewer`, `admin`)
- Filtering, ordering, and cursor/offset pagination (`GET /v1/tasks`)
- Deterministic HTTP status codes (`200`, `201`, `400`, `401`, `403`, `404`, `405`, `409`, `422`), headers (`Content-Type`, `Location`, `X-Task-Revision`, `Allow`, `WWW-Authenticate`), and structured error envelopes
- Loopback-only deterministic reset (`POST /__admin/reset`) excluded from model `ScopeContract`

## Files

- `public_contract.json`: Model-safe public observation contract (endpoints, synthetic roles, observable headers, allowed methods). Does **not** contain hidden transition rules, validation precedence, or held-out test cases.
- `reference_server.py`: Bounded loopback HTTP/1.1 server (`RunningTaskWorkflowServer`) and deterministic state machine (`TaskWorkflowReferenceState`).
- `harness.py`: `HTTPReferenceAdapter` (implementing `ReferenceProtocol`), `SafeHTTPExperimentRunner` (enforcing `ScopeGuard` for both `run(ProposedAction)` and `run_actions(dict)`), `PinnedHTTPEvaluatorRun` (implementing `prepare()`, `generate()`, `evaluate()`, `repair_feedback()`, and `inspection_manifest()`), `HTTPCandidateSpec` / `HTTPCandidateInterpreter`, `HTTPDifferentialEvaluator`, `seal_http_task_workflow_suite`, `prepare_http_generation_request`, `derive_fill_from_observations`, and `run_competitive_benchmark`.
- `src/second_source/g4_http_reconstruct.py`: Reproducible CLI operator workflow connecting `Scope -> Observe -> Hypothesize -> Experiment -> Candidate Generation Contract -> Admission -> Independent Verification -> Bounded Repair -> Provenance-Correct Report`.

## Reproducible Local CLI Demonstration (`NON_AI`)

```powershell
# 1. Run built-in reference server self-test
$env:PYTHONPATH="src;."
.\.venv\Scripts\python.exe -m fixtures.owned_http_task_workflow.reference_server --self-test

# 2. Run end-to-end G4 HTTP reconstruction pipeline in mock mode (25/30 on 30-case sealed suite)
$env:PYTHONPATH="src;."
.\.venv\Scripts\python.exe -m second_source.g4_http_reconstruct --mode mock

# 3. Run end-to-end G4 HTTP pipeline with 1 bounded repair round (25/30 -> 30/30, verdict="improved")
$env:PYTHONPATH="src;."
.\.venv\Scripts\python.exe -m second_source.g4_http_reconstruct --mode mock --repair-rounds 1

# 4. Run the complete 12-step API -> Worker -> Verification -> Export -> Offline Verifier journey
$env:PYTHONPATH="src;."
.\.venv\Scripts\python.exe -m second_source.g4_http_reconstruct --mode journey

# 5. Run all G4 HTTP reference, evaluation, benchmark, pipeline, adversarial, and backend/worker acceptance tests
$env:PYTHONPATH="src;."
.\.venv\Scripts\python.exe -B -m pytest `
  tests/test_g4_http_task_workflow_reference.py `
  tests/test_g4_http_task_workflow_evaluation.py `
  tests/test_g4_http_task_workflow_benchmark.py `
  tests/test_g4_http_pipeline_and_adversarial.py `
  tests/test_g4_backend_worker_acceptance.py -v -p no:cacheprovider
```

## Isolation Rules

1. Model-facing generation prompts (`prepare_http_generation_request`) may include `public_contract.json`, active experiment observations, and hypotheses, but **never** `reference_server.py`, `harness.py`, or sealed evaluation suites.
2. Sealed evaluation suites (`seal_http_task_workflow_suite`) must be written outside the repository tree (`--seal-dir` in temp/external storage) so candidate admission or prompt assembly cannot read expected outputs.
3. All local demonstrations and benchmark results generated without live provider credentials are labeled `origin="mock", real=False` (`NON_AI`). Genuine Meta model G4 evaluation remains **BLOCKED** pending owner spend approval.
