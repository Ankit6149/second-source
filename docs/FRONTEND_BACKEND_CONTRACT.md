# Backend integration contract — version 1

The existing OpenAPI document at `/openapi.json` is authoritative for the
configured app. No UI changes are part of this backend branch. All `/v1` routes
require one bearer token accepted by the configured Supabase identity boundary.
Local hashed-token mode remains an explicit separate construction; authorities
cannot be mixed. A browser sends no service-role/database/model/sandbox key.

| Client task | Supported typed route and behavior |
|---|---|
| Validate session | GET `/v1/session`: verified immutable owner ID;401 for rejected identity. Ordinary sign-out does not prove immediate JWT revocation; clear browser tokens and respect expiry |
| Availability | GET `/v1/capabilities`: only `g3_mock`, real/paid false; `execution_mode: on_demand_mock` appears only when configured/enabled. Legacy queued capabilities remain unchanged |
| Choose a supported target | GET `/v1/targets`: the exact owned-ledger mock scope and digest, plus whether on-demand execution is enabled. This discovery response does not create or authorize an investigation; browser, arbitrary URL and real-model targets are not advertised |
| Capture/list | POST/GET `/v1/investigations`: title + existing ScopeContract, Idempotency-Key; server assigns owner |
| Scope review/authorize | GET investigation, then POST `/{id}/authorize` with expected_revision, exact scope_digest, mode mock and maximum_model_spend_usd0 |
| Queue | POST investigation `/{id}/runs` with kind g3_mock and Idempotency-Key.201 means queued, never completed |
| Start bounded job | POST `/v1/runs/{id}/execute` with expected_revision.409 when disabled,503 when occupied,200 with actual durable state after execution; active/terminal states never replay |
| Progress | GET run plus `/v1/runs/{id}/events?after=...&limit=...`; `repair_started` and `repair_completed` are fenced engine progress events; polling does not execute a run |
| Cancel | POST run `/{id}/cancel`, expected_revision; distinguish cancellation requested from confirmed terminal cancellation |
| Interrupted worker | POST run `/{id}/reconcile`, expected_revision: expired execution becomes needs_reconciliation, not requeued/successful |
| Verification | GET run `/{id}/verification`: independent mock summary or null; `real` remains false, candidates remain private, and `repair` exposes bounded aggregate lineage when available |
| Evidence/report | GET run `/{id}/report`: hash-checked sanitized JSON only; missing report404, not a fabricated empty score |
| Export | GET run `/{id}/export.zip`: bounded existing integrity bundle, no raw model/secret/sealed content |

Run events use opaque integer cursors over the investigation's committed log;
the cursor can advance over unrelated run events that are omitted from the
response. Empty items with an advanced cursor does not imply completion.

Use exact configured HTTPS Origin and Authorization/Content-Type/Idempotency-Key
headers. CORS does not confer authorization; cookies/credentialed cross-origin
requests and wildcard origins are disabled. Capture X-Correlation-ID on failures.
Error bodies have fixed code/message/correlation_id and never echo credentials.
Return-to-login versus retry-status handling should preserve401,409,429,503
distinctions; do not retry execute automatically after a timeout. Read run state
and reconcile uncertain operations explicitly.

No SSE, live OAuth browser flow, public candidate download or genuine Meta
execution is claimed. Repair history is a sanitized NON_AI projection; raw
candidate and evaluator materials remain private.
Expose supported capabilities progressively and preserve NON_AI labels.
