# G2 Acceptance Log — Real Meta-powered behavioral discovery

**Gate under test:** PRD FR-020..028 — a real Muse model selects a valid
experiment and its result is observed and recorded.

**Verdict: G2 NOT COMPLETE.** The operator attempted one real Meta model
request on 27 Oct 2026, but the model/planner failed before selecting an
experiment; the confirmed response, token usage and error classification are
still unknown. The G2 engine has passing non-billable tests. Acceptance requires
a valid model-selected experiment and its recorded observation. The earlier
attempt must not be presented as successful inference.

## Design (integrated, no G0 duplication)

G0 files (`contracts`, `scope_guard`, `evidence`, `reference`, `runner`,
`verifier`, `demo`, all G0 tests, fixtures, acceptance record) are preserved
untouched. G2 adds six modules that build on G0 types:

| # | Requirement | Implementation | Tests |
|---|---|---|---|
| 1 | Typed Meta gateway, Muse Spark 1.3 | `src/second_source/model_gateway.py` (`MetaProvider`, `MockProvider` script-or-responder, `ModelGateway` receipts with real-vs-mock flags and ok/failed outcomes) | `tests/test_g2_gateway.py` |
| 2 | Schema-validated hypotheses + evidence digests | `src/second_source/hypotheses.py` (pydantic batch, unknown-digest rejection, store) | `tests/test_g2_hypotheses.py` |
| 3 | Discriminating planner through the guard | `src/second_source/planner.py` (closed wire shapes + strict per-item checks, heuristic utility, `ScopeGuard.validate_action` on EVERY action, ranked/rejected split; emits `ProposedAction` lists, the runner's only input) | `tests/test_g2_planner.py` |
| 4 | Bounded observe→hypothesize→experiment→update loop | `src/second_source/loop.py` (model zone = redacted ledger views only; one proposal = one fresh-process sequence; prediction/outcome reconciliation updates hypothesis statuses; stops `stalled`/`budget`/`guard_blocked`) | `tests/test_g2_loop.py` |
| 5 | Model-call / token / cost limits with failure booking | `src/second_source/budgets.py` (`reserve` worst case before the call, `commit` actuals on success, `fail` books uncertain spend; per-model pricing; reuses the runner's `BudgetExhausted`) | `tests/test_g2_budgets.py` |
| 6 | Structured-output enforcement | `src/second_source/model_gateway.py` (Meta `json_schema` with `strict: false`, full schema instructions and server-side revalidation) plus `schema_validate.py` (closed-subset checker) | `tests/test_g2_schema.py`, `tests/test_g2_gateway.py`, `tests/test_g2_live_entry.py` |
| 7 | Separation + adversarial edge cases | gateway forbidden-marker guard + HTTPS/host allowlist, `redact()` on all model context, no subprocess/shell in G2, injection-as-data | `tests/test_g2_adversarial.py` |
| 8 | Real-provider smoke | `tests/test_g2_smoke_real.py` (skips as `BLOCKED_REAL_MODEL` without key + budget) | run with `MODEL_API_KEY` + `SECOND_SOURCE_MAX_RUN_USD` |

Budgets honor the repo's existing `SECOND_SOURCE_MAX_RUN_USD` variable; no new
credential names were introduced. No billable request is sent unless that
variable is positive AND `MODEL_API_KEY` is set.

## Review findings → fixes (all with regression tests)

| Review # | Fix | Evidence |
|---|---|---|
| P0-1 model self-approval | `approval_granted` removed from the model schema; `_to_action` strips smuggled values and forces `False`; external mutations always hit `HUMAN_APPROVAL_REQUIRED` | `test_model_approval_is_stripped_and_external_denied`, `test_smuggled_approval_never_authorizes` (seed-only ledger proves nothing executed) |
| P0-2 multi-action sequences | proposals carry bounded action lists (≤8) with declared `reset_boundary`; every action guard-validated; one sequence per fresh process; `add A → add A → total` demo vs fresh reset | `test_propose_returns_ordered_action_sequence`, `test_second_action_denial_rejects_sequence`, `test_stateful_sequence_vs_fresh_reset`, `test_wrong_reset_boundary_rejected` |
| P0-3 hypothesis resolution | checkable predictions (`expects_ok` + optional `expects_contains`) reconciled against the final-step output; `supported`/`contradicted` update the store; timeouts/protocol leave hypotheses open (never punished for harness faults) | `test_mock_loop_resolves_hypotheses` (1 supported + 1 contradicted), `test_conclusive_error_contradicts`, `test_timeout_leaves_hypotheses_unresolved`, `test_reconcile_*` |
| P0-4 billing hard stop | `reserve` worst case before the call; `commit` actuals; `fail` books uncertain spend and a failed receipt; per-model pricing table; unknown models fail closed unless explicit rates are given | `test_failure_books_uncertain_spend`, `test_commit_releases_reservation`, `test_mock_schema_violation_rejected_and_booked`, `test_unknown_model_pricing_fail_closed`, `test_wire_format_and_usage_reconciled` (monkeypatched transport) |
| P1-5 strict schemas | Meta-documented `json_schema` with `strict: false` (open params do not conform to the stricter subset), schema guidance included in prompts, and closed server-side enforcement via `schema_validate` | `tests/test_g2_schema.py`, `test_mock_schema_violation_rejected_and_booked` |
| P1-6 credential boundary | `MetaProvider` rejects non-HTTPS and non-allowlisted hosts; loopback only with explicit `test_mode=True` (hermetic tests); key travels only on that TLS request | `test_http_endpoint_rejected`, `test_unexpected_host_rejected`, `test_loopback_requires_test_mode`, `test_meta_error_never_echoes_key` |
| Gate-7 real call + CI | Operator attempted one real call but no experiment was selected; inspect the existing local error note before spending again. GitHub Actions runs on Linux/Python 3.11 and Windows/Python 3.12 (latest workflow result should be checked). | — |

## Observed suite result (27 Oct 2026, this branch)

`python -m pytest` → **101 passed, 2 skipped, exit 0** (≈5s; 43 G0 + 58 G2).
The 2 skips are `test_g2_smoke_real.py` (no key/budget configured).

## Unresolved limitations (honest)

- No guaranteed billing hard cap: the ledger bounds what WE attempt and books
  uncertainty fail-closed; provider-side charges are authoritative.
- Provider uses Meta structured output with `strict: false` for flexible JSON schema,
  plus server-side validation. A live call must confirm compatibility for this account.
- Hypothesis contradiction is single-step (final observation vs prediction);
  multi-step trajectory attribution is future work.
- GitHub Actions CI exists on the integration branch. The first run (ID 40555328796)
  was independently verified successful on Linux/Python 3.11 and Windows/Python 3.12;
  recheck subsequent run results before marking the final branch green.
- Cross-sequence state persistence is unavailable on the current fixture by
  design (fresh process per sequence); the loop never claims otherwise.

## How to complete the gate

1. `python -m pytest` — full suite green (real smoke reports SKIPPED).
2. Set `MODEL_API_KEY` and `SECOND_SOURCE_MAX_RUN_USD=0.25`.
3. `python -m pytest tests/test_g2_smoke_real.py -v` — check a real Meta ping
   and schema-constrained hypothesis request; record only redacted receipt data.
4. `python -m second_source.live_experiment --max-usd 0.25 --rounds 1` —
   run one **real Muse-selected in-scope experiment** against the owned fixture.
   This requires BOTH `MODEL_API_KEY` and `SECOND_SOURCE_MAX_RUN_USD=0.25`
   in the local trusted environment and writes a sanitized report beneath `.runs/`.
   The command exits nonzero if the model cannot propose a safe executable experiment.
5. Attach the sanitized receipt, scope-run report and verifier `model_feedback()`
   summary (observed values only). Do not commit keys, raw private data or gold cases.

## Real-provider attempt — operator-observed 27 Oct 2026 (incomplete)

- Run ID: `real-g2-20261027T184607Z-73bbd66a`.
- Result: `REAL_EXPERIMENT_INCOMPLETE`; reported stop `guard_blocked`, but code review shows a `GatewayError` was previously misclassified as a scope guard denial.
- Provider receipts: 1 real-model *attempt* in stage `hypothesize` (`muse-spark-1.3`), outcome `failed`, detail `model output violated JSON schema: not JSON`. The generated content was not retained; therefore whether it was truncated, fenced, or freeform remains unproven.
- Guard-approved model-selected experiments executed: **0**.
- Actual provider-reported successful usage estimate: **$0.00**.
- Accounting reserve recorded as **uncertain**: **$0.006048**. This is **not proof of a provider charge**.
- The operator did not share their key. Updated gateway now requests low reasoning effort and larger completion budgets; it reports sanitized `finish_reason`, token usage, and response metadata if validation fails. Re-run only after these changes pass CI and with explicit user approval. This change is a mitigation, not proof the root cause was truncation.

## Third owner-run evidence — 27 October 2026

- Run ID: `real-g2-20261027T190454Z-f43553c6`.
- Observed result: `REAL_EXPERIMENT_INCOMPLETE`; `guard_blocked`; two *successful* model calls, zero reference experiment actions.
- Internal estimated provider usage: **$0.012054**, uncertain spend **$0**. Provider billing has not been independently checked.
- Operator subsequently supplied the rejection: `schema: unknown side_effect 'mutating: creates two ledger records within isolated se...'`. This confirms a descriptive effect label instead of a canonical policy category; it does **not** indicate a prohibited mutation was executed.
- G2 still **NOT ACCEPTED**. New code adds explicit owner-CLI scope hints and **at most one model-proposed corrective experiment** after the first rejected proposal. Budget remains bounded by an explicit `max_model_calls` limit and `SECOND_SOURCE_MAX_RUN_USD`.
- Never substitute a hard-coded fallback sequence as if Muse selected it; the scope guard validates every model-selected action.

## Latest status

**G2 NOT COMPLETE.** The first real attempt made progress past the key/budget gate but failed before experiment execution. New code distinguishes `model_error` from `guard_blocked` and outputs a safe failure category; re-run only after confirming the precise error from the existing report.

## Integration acceptance addendum (27 Oct 2026)

- The owned fixture now has `fixtures/owned_ledger/public_contract.json`, listing only operator-approved CLI signatures; hidden business rules remain outside model context.
- The planner may pass this public schema to Muse; raw reference source and evaluator-only cases remain outside prompts.
- An explicit operator entrypoint `second_source.live_experiment` now bridges real Muse reasoning to bounded, approved reference execution. Its exit status distinguishes observed experiments from missing-key and model failures.
- The same run also performs an evaluator-only negative-control using an intentionally faulty synthetic candidate and stores **only aggregated** `model_feedback()`; this is a harness check, not a reconstructed candidate result.
- Test coverage adds no-credential, overspend rejection and schema-prompt assertions in `tests/test_g2_live_entry.py`.
- These changes are not proof of a live model run; G2 stays **NOT COMPLETE** until an observed real receipt and an executed experiment are recorded.

## 28 October fix — operator-owned effect classification

- Public owned-ledger command manifest now declares canonical `side_effect` per command: `add`/`remove` = `owned_mutation`, `list`/`total` = `read_only`. These are authorized policy declarations, not observations of hidden rules.
- The planner derives the effective effect from this **trusted manifest**, even when Muse writes a verbose explanatory side-effect string. It never lets a model downgrade an owned mutation to read-only. An explicit `external`/`prohibited` model declaration remains restricted by ScopeGuard.
- Missing/unknown commands and invalid trusted manifest effects fail closed. All chosen actions still require requirement, role, command and scope authorization.
- Added no-network regression tests reproducing the exact real-model wording and observing the owned reference from a model-selected proposal. No new real model request has been made in this fix.
- **G2 remains unaccepted** until the operator runs the updated code once and supplies a genuine reference-action receipt. Billable retries require explicit owner approval.
