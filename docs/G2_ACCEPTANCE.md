# G2 Acceptance Log — Real Meta-powered behavioral discovery

**Gate under test:** PRD FR-020..028 — a real Muse model selects a valid
experiment and its result is observed and recorded.

**Verdict: G2 NOT COMPLETE.** No real provider call has been executed. The G2
engine below is implemented on top of the preserved G0 foundation and covered
by mocked tests; the real-model leg is explicitly pending an API key and run
budget. This log must not claim completion without a recorded receipt (model
id, response id, latency, token usage).

## Design (integrated, no G0 duplication)

G0 files (`contracts`, `scope_guard`, `evidence`, `reference`, `runner`,
`verifier`, `demo`, all G0 tests, fixtures, acceptance record) are preserved
untouched. G2 adds five modules that build on G0 types:

| # | Requirement | Implementation | Tests |
|---|---|---|---|
| 1 | Typed Meta gateway, Muse Spark 1.3 | `src/second_source/model_gateway.py` (`MetaProvider`, `MockProvider` script-or-responder, `ModelGateway` receipts with real-vs-mock flags) | `tests/test_g2_gateway.py` |
| 2 | Schema-validated hypotheses + evidence digests | `src/second_source/hypotheses.py` (pydantic batch, unknown-digest rejection, store) | `tests/test_g2_hypotheses.py` |
| 3 | Discriminating planner through the guard | `src/second_source/planner.py` (closed JSON schemas, heuristic utility, `ScopeGuard.validate_action` dry-run, ranked/rejected split; emits `ProposedAction`, the runner's only input) | `tests/test_g2_planner.py` |
| 4 | Bounded observe→hypothesize→experiment→update loop | `src/second_source/loop.py` (model zone = redacted ledger views only; stops `stalled`/`budget`/`guard_blocked`) | `tests/test_g2_loop.py` (2-round mock loop on `owned_ledger`) |
| 5 | Model-call / token / cost limits | `src/second_source/budgets.py` (`RunBudget` over contract `Budgets` + `TokenCaps`; reuses the runner's `BudgetExhausted`) | `tests/test_g2_budgets.py` |
| 6 | Separation + adversarial edge cases | gateway forbidden-marker guard, `redact()` on all model context, no subprocess/shell in G2, injection-as-data | `tests/test_g2_adversarial.py` |
| 7 | Real-provider smoke | `tests/test_g2_smoke_real.py` (skips as `BLOCKED_REAL_MODEL` without key + budget) | run with `MODEL_API_KEY` + `SECOND_SOURCE_MAX_RUN_USD` |

Budgets honor the repo's existing `SECOND_SOURCE_MAX_RUN_USD` variable; no new
credential names were introduced. No billable request is sent unless that
variable is positive AND `MODEL_API_KEY` is set.

## How to complete the gate

1. `python -m pytest` — full suite green (real smoke reports SKIPPED).
2. Set `MODEL_API_KEY` and `SECOND_SOURCE_MAX_RUN_USD=0.25`.
3. `python -m pytest tests/test_g2_smoke_real.py -v` — record model id,
   response id, latency, tokens, estimated cost below.
4. Run a budgeted real loop and attach the receipt + loop report + verifier
   `model_feedback()` output (observed values only).

## Real-usage record (empty until observed)

- Meta usage this session: **none — zero billable requests sent.**
- Receipts: none.
