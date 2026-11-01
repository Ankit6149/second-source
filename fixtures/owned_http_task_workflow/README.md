# Owned HTTP Task-Workflow Target (`owned-http-task-workflow-v1`)

Independent, stateful HTTP API reference target and evaluation harness for Second Source **G4** multi-target generalization.

## Purpose

Unlike the G3 CLI JSONL ledger fixtures (`fixtures/owned_ledger/` and `fixtures/owned_ledger_variant/`), this fixture exposes an HTTP/1.1 task-workflow service with:
- Stateful CRUD and workflow transitions across `todo`, `in_progress`, `blocked`, `done`, and `cancelled`
- Role- and ownership-based access control via synthetic actors (`X-Synthetic-Actor`: `alice`, `bob`, `viewer`, `admin`)
- Filtering, ordering, and cursor/offset pagination (`GET /v1/tasks`)
- Deterministic HTTP status codes (`200`, `201`, `400`, `401`, `403`, `404`, `405`, `409`, `422`), headers (`Content-Type`, `Location`, `X-Task-Revision`, `Allow`, `WWW-Authenticate`), and structured error envelopes
- Loopback-only deterministic reset (`POST /__admin/reset`) excluded from model `ScopeContract`

## Files

- `public_contract.json`: Model-safe public observation contract (endpoints, synthetic roles, observable headers, allowed methods). Does **not** contain hidden transition rules, validation precedence, or held-out test cases.
- `reference_server.py`: Bounded loopback HTTP/1.1 server (`TaskWorkflowHTTPServer`) and deterministic state machine (`TaskWorkflowReferenceState`).
- `harness.py`: `HTTPReferenceAdapter` (implementing `ReferenceProtocol`), `SafeHTTPExperimentRunner` (enforcing `ScopeGuard`), `HTTPCandidateSpec` / `HTTPCandidateInterpreter`, `HTTPDifferentialEvaluator`, `seal_http_task_workflow_suite`, `prepare_http_generation_request`, and `run_competitive_benchmark`.

## Standalone Verification

Run the built-in reference server self-test:

```powershell
$env:PYTHONPATH="src;."
.\.venv\Scripts\python.exe -m fixtures.owned_http_task_workflow.reference_server --self-test
```

Run the G4 HTTP test suites:

```powershell
$env:PYTHONPATH="src;."
.\.venv\Scripts\python.exe -B -m pytest tests/test_g4_http_task_workflow_reference.py tests/test_g4_http_task_workflow_evaluation.py tests/test_g4_http_task_workflow_benchmark.py -q -p no:cacheprovider
```

## Isolation Rules

1. Model-facing generation prompts (`prepare_http_generation_request`) may include `public_contract.json`, active experiment observations, and hypotheses, but **never** `reference_server.py`, `harness.py`, or sealed evaluation suites.
2. Sealed evaluation suites (`seal_http_task_workflow_suite`) must be written outside the repository tree (`--sealed-dir` in temp/external storage) so candidate admission or prompt assembly cannot read expected outputs.
3. All benchmark results generated without live provider credentials are labeled `origin="mock", real=False` (`NON_AI`).
