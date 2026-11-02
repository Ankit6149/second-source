# HTTP Target Integration Contract (Muse-owned science side)

Version 1, for Codex (product integration) and Argon (HTTP fixture work).
Ledger contracts are unchanged; this is a parallel, file-disjoint surface.

## Owned fixture (do not reimplement; reuse or replace wholesale)

- `fixtures/owned_http_items/server.py` — stdlib JSON resource API.
  `python server.py --port-file <path>` binds 127.0.0.1 ephemeral, writes
  the port, serves until killed. Fresh process resets state.
- `fixtures/owned_http_items/public_contract.json` — model-visible surface:
  routes, methods, success shapes, error-code vocabulary. Bounds, folding,
  and code mappings are hidden by design.
- Rules: label 1..32 trimmed, case-SENSITIVE uniqueness, amount 1..250,
  codes `invalid_title` / `invalid_qty` / `duplicate_title` / `missing_id`,
  `unknown_route` 404, `method_not_allowed` 405.

## Science modules (stable)

- `src/second_source/http_target.py` — `HttpRequest`/`HttpResponse`/
  `HttpExchange` records; `HttpObservationAdapter` lifecycle
  (`start`/`stop`/`reset`/`exchange`/`observe`); `HttpTransportError` on
  any transport failure (never silent success).
- `src/second_source/http_candidate.py` — `HTTP_SPEC_VERSION = "1"`,
  subsystem `http_items`, requirement `REQ-HTTP-ITEMS`;
  `load_http_candidate(raw, scope)` strict admission
  (`HttpCandidateError` on any violation); `HttpCandidateApp`
  in-process interpreter (`handle`/`reset`). No sockets in candidates.
- `src/second_source/http_verification.py` — `HttpCase` (id + request
  tuple), `HttpDifferentialVerifier.verify` with per-case reset,
  categories `status` / `schema` / `value`
  (`HTTP_FAILURE_CATEGORIES`), aggregate `model_feedback()` shaped like
  the ledger verifier (counts plus category names only).

## Scope values for HTTP investigations

- `target.kind`: `http`, `reference_url` (fixture base), no command id.
- `observation.permitted_actions`: `{"http"}`,
  `allowed_url_patterns`: absolute paths (e.g. `/items`, `/items/*`).
- `implementation.requirements`: `{"REQ-HTTP-ITEMS"}`,
  `allowed_subsystems`: `{"http_items"}`.

## Seams for Argon

- Argon's fixture replaces `fixtures/owned_http_items/` wholesale if it
  honors the same transport (localhost HTTP, JSON bodies, deterministic
  reset). The adapter takes any base URL via `reference_url`; only the
  spawn command is fixture-specific.
- Per-target sealed suites and code pins are NOT yet integrated
  (control-plane work). Scaffolding tests use hand-built NON-SEALED cases.

## Provenance labels (mandatory in product surfaces)

- Genuine Muse ledger reconstruction: 14/25, `PINNED_REAL_MODEL_EVALUATION` (provider attestation incomplete; see JUDGE_EVIDENCE_G3.md).
- Deterministic NON_AI ledger fixture: 22/25, `MOCK_` prefixed.
- HTTP numbers in this branch are scaffolding checks, never sealed scores.
