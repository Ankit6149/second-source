# G4 Owned HTTP Task-Workflow Reference Target & Evaluation Contract

**Target ID:** `owned-http-task-workflow-v1`  
**Subsystem ID:** `http_task_workflow` (`REQ-HTTP-TASKS`)  
**Owner:** Argon (G4 Independent Engineering Stream)  
**Branch:** `feat/g4-owned-http-reference-argon`  
**Base Commit:** `951ed681ab707a54e9e76a3377546235c98a0369` (`origin/main`)

---

## 1. Repository Reconnaissance & Documentation Audit

Before implementing this fixture, the repository documentation, issues, pull requests, and source code across `origin/main` (`951ed681`), Muse PR #23 (`d7508ce`), and Codex PR #24 (`ee81f37`) were audited.

### Verified Document vs. Implementation Discrepancies

1. **G3 Live Attempt Count & Admitted Candidate Status:**
   - `README.md`, `docs/G3_DELIVERY_BOARD.md`, and `docs/G3_ACCEPTANCE.md` on `origin/main` state that only 2 real paid G3 attempts have been made with `0` admitted candidates.
   - On PR #23 (`d7508ce`), `docs/G3_AUTHORIZATION_PACKET.md` and `docs/G3_RECONSTRUCT.md` record **Attempt 5 (rev-6)** admitted on `2026-10-31` and independently scored on the 25-case sealed CLI suite at **14/25 match (`0.56`), 11 mismatched (9 `schema`, 2 `error`), 0 indeterminate**.
2. **Branch HEAD Pointers in Governance Docs:**
   - `docs/G3_DELIVERY_BOARD.md` lists `main` as `1ba8905` and `docs/G3_ACCEPTANCE.md` lists `main` as `2dd919b`, whereas `origin/main` is at `951ed681` (PR #21 merged).
3. **Repair Loop Implementation Status:**
   - `docs/G3_REPAIR_CONTRACT.md` on `origin/main` states that `G3MockEngine` does not integrate `--repair-rounds` and feedback-conditioned synthesis is unimplemented. In code, `origin/main` (`2eca165`) already wires bounded mock repair into the durable worker, and PR #23 (`07553b8`) implements feedback-conditioned repair (`synthesize-v2-repair1`), though no live paid repair attempt has been executed yet.
4. **Referenced Documents Not Present in Repo:**
   - `docs/MASTER_PRD.md` (§2.4, §5.6) references `docs/ARCHITECTURE.md`, `docs/RESEARCH_PROTOCOL.md`, `docs/SECURITY.md`, and `research/experiments/`, which do not exist as separate files; their substance is consolidated in `docs/MASTER_PRD.md`, `docs/G3_VERIFIER_ACCEPTANCE.md`, and `docs/G3_RECONSTRUCT.md`.
5. **Protocol Generalization Gap in Core Engine:**
   - `ScopeContract` (`src/second_source/contracts.py`) and `ScopeGuard` (`src/second_source/scope_guard.py`) already support `TargetKind.HTTP` (allowed URL patterns, permitted HTTP action kinds, roles, and exclusions).
   - However, `SafeCLIExperimentRunner`, `CandidateSpec`, `CandidateReferenceAdapter`, and `PinnedEvaluatorRun` on `origin/main` assume `TargetKind.CLI` (`cli_ledger`).
   - `fixtures/owned_ledger_variant/` (on PR #23) changes three internal ledger rules (`round_half_up`, per-tag running balance, `remove` return value) while keeping the exact same JSONL `add`/`list`/`total`/`remove` CLI protocol. It therefore tests rule variation within the CLI ledger family rather than protocol generalization to a stateful HTTP API.

---

## 2. Public Observation Contract (`public_contract.json`)

The public observation contract (`fixtures/owned_http_task_workflow/public_contract.json`) is the **only** target metadata provided to the reconstruction planner or model generation prompt.

### Allowed Endpoints & Methods (`create_http_scope`)
- **Target Kind:** `TargetKind.HTTP`
- **Scheme / Host:** `http://127.0.0.1:<ephemeral_port>`
- **Allowed URL Patterns:** `("/v1/tasks", "/v1/tasks/*")`
- **Permitted Action Kinds:** `{"http_get", "http_post", "http_patch", "http_delete"}`
- **Excluded Control Plane:** `("/__admin/**",)` is used exclusively by `HTTPReferenceAdapter` between sequences (`POST /__admin/reset`) and is blocked by both `ScopeGuard` (`EXCLUDED_ROUTE`) and `HTTPReferenceAdapter` (`control_plane_access_denied`).

### Synthetic Identities (`X-Synthetic-Actor`)
| Actor Header | Role | Capabilities |
|---|---|---|
| `alice` | `member` | Read all tasks; create tasks (`owner="alice"`); update/transition/delete own tasks |
| `bob` | `member` | Read all tasks; create tasks (`owner="bob"`); update/transition/delete own tasks |
| `viewer` | `viewer` | Read all tasks (`GET /v1/tasks`, `GET /v1/tasks/{id}`); all mutations rejected (`403 insufficient_role`) |
| `admin` | `admin` | Read all tasks; create tasks; update/transition/delete any task regardless of owner |
| *(missing / unknown)* | *(none)* | Rejected on all `/v1/tasks` endpoints with `401 unauthenticated` and `WWW-Authenticate: SyntheticActor realm="owned-task-workflow"` |

---

## 3. Hidden Reference Rules (Oracle Specification)

These rules are implemented in `fixtures/owned_http_task_workflow/reference_server.py` (`TaskWorkflowReferenceState`) and must be inferred through black-box experimentation rather than leaked in prompts:

1. **Authentication & Authorization Precedence:**
   - Route & HTTP method checks run first (`404 unknown_endpoint` for unknown routes; `405 method_not_allowed` with deterministic `Allow` header for unsupported verbs).
   - Every `/v1/tasks` request next validates `X-Synthetic-Actor`. Missing or unrecognized actors return `401` (`error = "unauthenticated"`).
   - Role checks (`viewer` attempting `POST`, `PATCH`, or `DELETE`) return `403` (`error = "insufficient_role"`) **before** body validation or resource lookup.
   - Ownership checks on `PATCH /v1/tasks/{task_id}` and `DELETE /v1/tasks/{task_id}` run after confirming the task exists (`404 not_found` if absent) and before applying field validation or state transitions (`403 not_owner` if `actor != task.owner` and `role != "admin"`).
2. **Task Creation (`POST /v1/tasks`):**
   - Body must be a finite JSON object (`<= 32,768` bytes) with no duplicate keys (`400 invalid_json`).
   - Validation precedence:
     1. `title`: required string; trimmed of leading/trailing whitespace; post-trim length must be `1..64` (`422 invalid_title`).
     2. `priority`: required strict integer (`bool` rejected) in `1..5` (`422 invalid_priority`).
     3. **Per-Owner Case-Insensitive Active Duplicate Title Rule:** An owner cannot have two non-cancelled tasks with the same `title.strip().casefold()`. Conflicts return `409 duplicate_title`. Once a task transitions to `cancelled`, its title reservation is released for that owner.
   - Assigns monotonic ID `tsk-1`, `tsk-2`, ..., `status="todo"`, `owner=actor`, `revision=1`, and returns `201 Created` with `location: /v1/tasks/{id}` and `x-task-revision: 1`.
3. **Workflow State Transitions (`PATCH /v1/tasks/{task_id}`):**
   - Requires at least one of `title`, `priority`, `status` (`422 empty_update`).
   - **Terminal State Lock:** Tasks in `done` or `cancelled` reject any `PATCH` (even metadata edits or self-transitions) with `409 terminal_state_locked`.
   - **Allowed Non-Terminal Transitions:**
     - `todo -> in_progress | blocked | cancelled` (`todo -> done` is **forbidden** with `409 invalid_transition`; a task must pass through `in_progress` before `done`).
     - `in_progress -> todo | blocked | done | cancelled`
     - `blocked -> todo | in_progress | cancelled` (`blocked -> done` is **forbidden** with `409 invalid_transition`).
   - Every accepted `PATCH` increments `revision` by `+1` and updates `x-task-revision`.
4. **Deletion Rule (`DELETE /v1/tasks/{task_id}`):**
   - Tasks in `in_progress` cannot be deleted directly (`409 task_in_progress`); they must first transition out of `in_progress`.
   - Tasks in `todo`, `blocked`, `done`, or `cancelled` can be deleted by their owner or `admin`, returning `200 OK` with `{"ok": true, "deleted": "tsk-..."}` (monotonic ID counter does not rewind).
5. **Collection Filtering, Ordering & Pagination (`GET /v1/tasks`):**
   - Unknown or repeated query parameters return `422 invalid_filter`.
   - Filters: `status` (valid status enum), `owner` (`^[a-z][a-z0-9_-]{0,31}$`), `min_priority` (`1..5`), `max_priority` (`1..5`), with `min_priority <= max_priority` (`422 invalid_filter`).
   - Ordering (`order_by`): `id_asc` (default), `id_desc`, `priority_desc` (`(-priority, seq)`), `priority_asc` (`(priority, seq)`), or `422 invalid_order`.
   - Pagination: `limit` (`1..50`, default `10`), `offset` (`>= 0`, default `0`), or `422 invalid_pagination`.

---

## 4. Typed Observable Request, Response, and State-Transition Representation

Implemented in `fixtures/owned_http_task_workflow/harness.py`:
- **`HTTPRequestAction`**: Typed single HTTP interaction (`operation`, `method`, `path`, `actor`, `query`, `body`, `raw_body`, `seed_tasks`).
- **`HTTPResponseEnvelope`**: Normalized observable HTTP response (`ok`, `error`, `http_status`, `headers`, `body`) preserving `content-type`, `location`, `x-task-revision`, `allow`, and `www-authenticate`.
- **`HTTPStateTransition`**: Extracted per-step transition record (`step_index`, `actor`, `method`, `path`, `http_status`, `outcome`: `mutated | read_only | rejected`, `task_id`, `prior_status`, `post_status`, `prior_revision`, `post_revision`) via `extract_state_transitions()`.

---

## 5. Independent Differential Evaluation & Isolation Boundaries

### Differential Classification (`HTTPDifferentialEvaluator` & `classify_http_difference`)
Each held-out `SealedCase` executes deterministically against a freshly reset reference server (`HTTPReferenceAdapter`) and candidate interpreter (`HTTPCandidateInterpreter`), classifying outcomes across both HTTP-specific dimensions (`http_mismatch_dimension`) and core engine categories (`engine_EvaluationReport`):
- `passed`: Status code, observable headers, and JSON body match across all sequence steps.
- `error` / `http_status`: Mismatched `ok`, `error` code, or HTTP status code.
- `headers` (mapped to `schema` in engine `EvaluationReport`): Mismatched protocol headers (`location`, `x-task-revision`, `allow`, `www-authenticate`).
- `schema`: Mismatched JSON response keys or types.
- `state`: Divergent task `status`, `revision`, or sequence observation count.
- `value`: Same status, headers, and schema, but differing field values (e.g., pagination slice or priority value).
- `candidate_timeout` / `candidate_protocol_error` / `reference_unavailable`: Timing uncertainty or transport errors.

Additionally, both `HTTPReferenceAdapter` and `HTTPCandidateInterpreter` satisfy `second_source.verifier.ReferenceProtocol` (`execute_sequence`), so the core `DifferentialVerifier.verify()` scores the 30-case suite directly without modification.

### Three-Layer Isolation Gate
1. **Runtime Network Scope (`ScopeGuard` + `SafeHTTPExperimentRunner`):** Validates every `ProposedAction` against `create_http_scope()` before execution, blocking disallowed HTTP methods (`ACTION_NOT_ALLOWED`) and `/__admin/**` (`EXCLUDED_ROUTE`).
2. **External Sealed Suite Storage (`seal_http_task_workflow_suite`):** Verifies via `_safe_external_path` that sealed suites are written outside any `.git` checkout and without traversing symlinks/junctions, binding the suite to `scope_digest_of(contract)` with `O_CREAT | O_EXCL`.
3. **Generation Wire Canary Gate (`prepare_http_generation_request`):** Verifies that every observation digest exists in `EvidenceLedger` (via `ledger.model_view(digest)`), validates `HypothesisStore` citations, restricts repair feedback to aggregate counts only, and scans the serialized `ModelRequest` for built-in reference/sealed canaries (`TaskWorkflowReferenceState`, `_BoundedHTTPServer`, `__admin/reset`, `G4-HTTP-`, plus caller-supplied `forbidden_markers`).

---

## 6. Fair Competitive Benchmark (`run_competitive_benchmark`)

`fixtures/owned_http_task_workflow/harness.py` provides a controlled 4-arm comparison on the **same 30-case held-out stateful suite** (`build_heldout_http_cases`):

| Arm | Strategy | Allowed Evidence | Experiment Budget | Score on 30-Case Suite (`NON_AI` Mock) |
|---|---|---|---:|---:|
| **`A_direct_synthesis`** | Direct synthesis from public contract + 2 basic examples | `public_contract.json` + 1 seed sequence | `1` exp (`2` actions) | **19 / 30 (`63.3%`)** |
| **`B_passive_fixed_probes`** | Fixed sequential happy-path probes | `public_contract.json` + 5 passive sequences | `5` exps (`12` actions) | **26 / 30 (`86.7%`)** |
| **`C_active_evidence_driven`** | Hypothesis-discriminating boundary probes | `public_contract.json` + 5 active sequences | `5` exps (`15` actions) | **30 / 30 (`100.0%`)** |
| **`D_bounded_repair`** | 1-round aggregate-feedback repair from Arm B | Aggregate failure counts + 5 active sequences | `5` exps + `1` repair round | **26 / 30 -> 30 / 30 (`+13.3%`)** |

> **Honesty Guardrail:** All results produced by `run_competitive_benchmark()` carry `origin="mock", real=False` and `claim="NON_AI_DETERMINISTIC_SCAFFOLDING_NOT_MODEL_QUALITY"`. They verify benchmark discrimination, equal-budget active vs. passive evidence sufficiency, and zero-leakage repair wiring without paid API calls.

---

## 7. Integration Handoff Contracts

### 7.1 Handoff for Muse (Shared Scientific Engine — PR #23)

Muse can wire `owned-http-task-workflow-v1` into `src/second_source/reconstruct.py` and `src/second_source/g3_verification.py` without modifying any internal fixture logic:

```python
from fixtures.owned_http_task_workflow import (
    HTTPCandidateInterpreter,
    HTTPDifferentialEvaluator,
    HTTPReferenceAdapter,
    SafeHTTPExperimentRunner,
    create_http_scope,
    load_http_candidate,
    load_public_contract,
    prepare_http_generation_request,
    seal_http_task_workflow_suite,
    start_reference_server,
)
```
- **Experiment Execution:** Start the local server with `with start_reference_server() as srv:`, build `contract = create_http_scope(srv.base_url)`, and run proposed HTTP action sequences through `SafeHTTPExperimentRunner(contract, HTTPReferenceAdapter(srv), ledger)`.
- **Wire Assembly & Isolation:** Build the `ModelRequest` via `prepare_http_generation_request(...)` before calling `ModelGateway`.
- **Candidate Admission & Verification:** Validate the model's JSON output with `load_http_candidate(raw_doc, contract)` and evaluate against the sealed 30-case suite using `HTTPDifferentialEvaluator(ref, HTTPCandidateInterpreter(loaded.spec)).evaluate(cases)` (or `DifferentialVerifier(ref, cand).verify(cases)`).

### 7.2 Handoff for Codex (Backend / Product Surface — PR #24)

Codex can expose `owned-http-task-workflow-v1` in `src/second_source/backend/service.py` and `src/second_source/backend/worker.py` while preserving all authentication and sandbox guarantees:
1. **Target Catalog Registration:** Register `target_id = "owned-http-task-workflow-v1"` (`target_type = "HTTP"`) and expose only `fixtures/owned_http_task_workflow/public_contract.json` in target discovery responses.
2. **Worker Execution Boundary:** Inside `backend/worker.py`, launch `start_reference_server()` only within the isolated worker job context (binding strictly to `127.0.0.1:0`), never exposing the loopback port externally or accepting arbitrary user-supplied target URLs in hosted mode.
3. **Provenance Labeling:** Persist `HTTPDifferentialReport.engine_EvaluationReport` and `run_competitive_benchmark()` artifacts with `provenance.origin = "mock"` and `provenance.real = False` whenever `NON_AI` mode is used.
