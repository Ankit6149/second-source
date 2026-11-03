# Professional benchmark — Vikunja (decision record)

Status: reference verified running locally 2026-11-02. No model inference
has touched this benchmark. All results so far are NON_AI infrastructure
checks.

## Decision

**First professional benchmark: Vikunja v2.4.0** (2026-07-19),
`vikunja-v2.4.0-windows-4.0-amd64.exe-full.zip`, AGPL-3.0, run as a
black box through its frozen REST surface `/api/v1`.

Rejected for the first benchmark: **Medusa v2** — Node 20+ plus Postgres
plus Redis, multi-service setup, no Docker on this machine. It remains a
valid later target; it fails "reasonable setup cost" today, not merit.

Why Vikunja wins on the stated criteria:

| Criterion | Vikunja v2.4.0 | Medusa v2 |
|---|---|---|
| Real maintained software | Yes, task management | Yes, commerce |
| Local reproducible deploy | Single binary + SQLite file | Node + Postgres + Redis |
| Reset to known state | Delete SQLite file, restart | DB reseed across services |
| Auth / roles / sharing | Users, project sharing, rights | Admin/store roles |
| Business workflows | Projects → tasks → state, assignees, labels | Orders, inventory, payments |
| API boundary | REST `/api/v1`, frozen | REST, large surface |
| Docker required here | No (native binary) | Effectively yes |

## Why /api/v1 (and why its conventions are not defects)

Vikunja v2.4 ships `/api/v1` (frozen compatibility surface) and
`/api/v2` (evolving). We target v1 deliberately: a frozen contract is
the only fair reconstruction target — the reference cannot move while
the candidate is being measured. v1's conventions (PUT creates, POST
updates, 412 for project validation but 400 for task validation,
403 for wrong-password login) are **behavior to reproduce, not defects
to correct**. The candidate may be internally cleaner; externally it
must match the selected interface exactly.

## Independent review — findings verified and fixed (2026-11-02)

An external review of the first harness (commit `a0fe4f7`) raised eight
findings. Each was verified against code before fixing:

1. **Self-check overclaim** — ref-vs-ref proved determinism only, not
   discrimination. Fixed with adversarial mutation tests
   (`tests/test_vikunja_evaluator_adversarial.py`): wrong status,
   missing field, broken done-transition, and nulled `done_at` are all
   caught.
2. **Cross-response ID loss** — per-response canonicalization remapped
   ids inconsistently across steps. Fixed: one ID map per sequence.
3. **Normalization concealment** — positions are now rank-normalized
   inside lists (order kept, counter magnitude dropped); timestamps
   distinguish set vs unset; view sub-ids use a separate namespace.
4. **Shared database state** — confirmed real: one held-out case
   (listing another user's projects) was state-dependent and was
   replaced with a deterministic isolation case.
5. **Auth rate limiting (429)** — tokens are cached per process and
   login uses bounded backoff; documented evaluator constraint.
6. **Rejection as boundary proof** — a rejection another rule could
   have caused no longer evidences a boundary (`coverage.py`
   isolation check, sequence-aware).
7. **Equivalence gate too weak** — verified-equivalence language is
   now blocked by any UNKNOWN or ASSUMED claim, not only
   CONTRADICTED ones.
8. **Grounded ledger control is fixture-shaped** — acknowledged: the
   deterministic synthesizer in `coverage_experiment.py` knows ledger
   field names. It bounds the mechanism (probe ladder + evidence-only
   synthesis), and is not claimed to be a general synthesizer.

Also found by the harness itself: `run_actions` silently failed to
capture project ids (sequences ran against project 0 while the
self-check still passed) — the strongest argument for mutation tests.

## Measured results so far (all NON_AI)

- Reference self-check: 6/6 held-out cases (determinism +
  canonicalization soundness).
- Adversarial mutations: 4/4 caught; unmutated stub matches.
- Hand-written oracle spec (from public observations only), executed
  by the generic candidate interpreter: **6/6 held-out**. This proves
  the spec representation is expressive enough and the evaluator is
  discriminative. It is a plumbing control, **not** a model result.
- Evidence-compiled candidate (`scripts/evidence_compiler.py`,
  provenance EVIDENCE_COMPILED / NON_AI): a deterministic compiler
  transcribes the 20 lossless public observations (request + response
  + actor, file sha256 `40f23ce9…`) into a candidate spec
  (sha256 `a5c9104e…`; dynamic ids/timestamps/creator tokenized, zero
  literal `"none"` preserved, response-shape nulls/empty strings never
  persisted into entity state). Evaluated **6/6 held-out** against a
  fresh Vikunja reference; a response-status mutation of the compiled
  spec scores **2/6**, confirming the evaluator still discriminates.
  This validates the lossless-evidence → compilation path. It is
  **not** a model result and does not raise any model score.
- Genuine model arms (GEMMA_TEST, `gemma-4-26b-a4b-it`): A prior-only
  **0/6**, C coverage-grounded **2/6** (error-contract cases), B and D
  unmeasured due provider failure (recorded, never scored as 0).
  The genuine Meta (Muse) Vikunja experiment additionally requires
  separate owner authorization: the earlier $0.50 approval covered
  the G4 fixture only.

## Who generates what (authorship delimiter)

The model authors **only a declarative candidate spec**: routes,
methods, success statuses, validation rules, permission levels,
response fields, error bodies. The generic interpreter
(`scripts/vikunja_candidate_server.py`, hash recorded in every result)
supplies the state machine, in-memory storage, auth plumbing,
permission enforcement, and HTTP serving. Results are therefore
**spec-level reconstruction**, not autonomous full-software
generation, and must be described that way. The oracle 6/6 shows the
spec surface is expressive enough to reach full marks on the bounded
scope; it does not show a model can author such a spec — that is what
the A/B/C/D arms measure.

## Arm semantics (do not conflate)

- A/B/C: prompt-condition comparison over fixed observations
  (prior-only vs observations vs coverage-grounded). One synthesis
  call each. This is **not** active experimentation.
- D: active experiment-selection — the model picks probes from a
  menu (outcomes unseen), they are executed on a fresh reference,
  then it synthesizes. Two calls. The budget difference vs A/B/C is
  recorded in every result.
- Every arm runs against a fresh Vikunja instance (new SQLite DB,
  own port) and a fresh candidate process; scores are admitted only
  when the spec validates and the evaluator exits 0 with a parseable
  result. Failures are recorded by class, never silently scored.

## Bounded scope (v1)

In scope, through `/api/v1` only:

- Registration, login, wrong-password and unauthenticated rejection.
- Project create/read/update, title validation.
- Task create with title/description/priority, done state transition
  (`done` / `done_at`), assignees, labels.
- Second-user sharing with read vs write rights; cross-user isolation.
- Task list filtering (`filter=`), sorting, pagination headers.
- Error contracts: validation 400s, 404s, 403s, malformed JSON.

Out of scope: CalDAV, webhooks, migrations/importers, file attachments,
frontend rendering, Pro features, `/api/v2` surface.

## Authorization and separation

- The binary runs locally on `127.0.0.1:3456` with a throwaway SQLite
  database under `C:\tmp\vikunja-bench\data`. No production data, no
  external accounts, synthetic users only (`bench_*@bench.local`).
- The reconstruction agent receives only HTTP observations. It never
  receives Vikunja source, this file's held-out sequences, or evaluator
  internals. Reference source lives outside the repository.
- Contamination caveat: Vikunja is popular open source; a model may have
  memorized parts of it. A good score is therefore evidence of
  reconstruction *plus possible recall*, and must be reported with that
  limitation. Behavior must still be earned through observations;
  source recall is not accepted as evidence.

## Evaluation

- Public probe ladder (`--mode probe`): discovery sequences a model may
  see. Observations are saved as JSON.
- Held-out sequences (`--mode evaluate`): frozen sequences the model
  never sees, executed against reference and candidate. Full benchmark
  runs start from a deleted SQLite file; within a run, cases are
  isolated by fresh projects plus canonicalization (verified by the
  reference self-check, currently 5/5). A case passes only if status
  and canonical body match at every step.
- Canonicalization: server ids are replaced by first-appearance
  placeholders; `created`/`updated`/`done_at` timestamps are checked
  for presence, not equality; auth tokens are never compared.
- Scores on this benchmark are **not comparable** to the 14/25 ledger
  score. Different target, different suite, different denominator.

## Arms for the intelligence experiment

Same probe budget, same held-out suite, three synthesis arms:

- A: prior-only spec (engineering conventions, observations shown once).
- B: coverage ladder (dimension probes) + prior synthesis.
- C: coverage ladder + claim-grounded synthesis (coverage gate blocks
  verified-equivalence language while any claim is CONTRADICTED).

Metrics per arm: held-out pass rate, contradicted-claim count,
unsupported-assumption count, probes used, model calls and cost.

## Local run

```powershell
$env:VIKUNJA_DATABASE_TYPE="sqlite"
$env:VIKUNJA_DATABASE_PATH="C:\tmp\vikunja-bench\data\vikunja.db"
$env:VIKUNJA_SERVICE_SECRET="<local-only>"
$env:VIKUNJA_SERVICE_ENABLEREGISTRATION="true"
$env:VIKUNJA_SERVICE_PUBLICURL="http://127.0.0.1:3456/"
C:\tmp\vikunja-bench\bin\vikunja-v2.4.0-windows-4.0-amd64.exe
python scripts/vikunja_benchmark.py --mode probe
python scripts/vikunja_benchmark.py --mode evaluate   # reference self-check
```

## Gemma C_grounded failure diagnosis (2026-11-03, deterministic, no model calls)

Method: `spec_C_grounded.json` (genuine Gemma arm, 2/6 admitted held-out:
passed case 1 = 412 project validation, case 3 = 403 wrong-login; failed
cases 0, 2, 4, 5) was diffed field-by-field against the NON_AI oracle spec
(`spec_oracle_fresh.json`, 6/6) and the public observations, and run
through `scripts/vikunja_coverage.py`. No held-out material was read.

Coverage result: C and the oracle are **identical** under
`vikunja_coverage.py` — 13 OBSERVED, 0 ASSUMED, 0 CONTRADICTED, 2 UNKNOWN
(`GET /tasks/{tid}` shared-read and `PUT /projects/{pid}/users` non-owner
denial, unobserved for both), equivalence blocked for both. The coverage
gate classifies route status, validation, and permission claims only; it
does not inspect response-field values. That blind spot is exactly where
C failed. C's `auth` block, every route status, both validation rules
(412 project / 400 task, exact error bodies), and every permission level
match the oracle — which is why the two passing cases are the
validation/auth-only ones.

Failure taxonomy (claim classes, in impact order):

1. **Type-placeholder literals instead of concrete observed defaults**
   (dominant class). C fills response fields with schema type names —
   `"string"`, `"int"`, `"bool"`, `"array"`, `"object"`, `"null"`,
   `"timestamp"` — which the candidate interpreter inserts verbatim.
   Affected wherever the interpreter does not already supply the field:
   `due_date`/`start_date`/`end_date` (`"timestamp"` vs observed
   `0001-01-01T00:00:00Z`), `repeat_after`/`repeat_mode`/`percent_done`/
   `bucket_id`/`cover_image_attachment_id` (`"int"` vs `0`), `hex_color`
   (`"string"` vs `""`), `is_favorite` (`"bool"` vs `false`), and
   `reminders`/`labels`/`attachments`/`reactions` (the string `"null"`
   vs JSON `null`).
2. **Views and compaction-dropped project fields.** C has
   `views: "array"` vs the observed 4 view objects (List/Gantt/Table/
   Kanban with nested `filter`, bucket ids, positions), and omits
   `background_information`/`background_blur_hash` entirely. Contributing
   cause is prompt-side, not only model-side: `compact_observations`
   drops those keys and truncates view payloads in the model-visible
   observations.
3. **Context-dependent null-vs-`[]` and object shapes.** Observed:
   `assignees` is `[]` on task create/update but `null` on list/get;
   `related_tasks` is `null` on create/update but `{}` on list/get.
   C uses one uniform `"array"`/`"object"` placeholder for all routes.
4. **Identifier/index/created_by update semantics.** The tokens are
   correct on create/list/get, but the observed update (`POST
   /tasks/{tid}`) response resets `identifier` to `""` and `created_by`
   to `null`; the oracle encodes this with `fields_override: true`.
   C has no override, so the interpreter retains the created values.
5. **Route-specific permission bodies.** C relies on the global
   forbidden body (`{code: 0, message: "Forbidden"}`) everywhere and
   sets no per-route `forbidden_body`; the oracle sets
   `{code: 0, message: "You don't have the permission to see this"}` on
   `get_task`. Permission *levels* themselves are all correct.
6. **Share response target.** C has `username: "string"` vs the
   interpreter's `<target>` token (observed `"bench_bob"`).

Harmless-by-construction differences (not failure causes): field values
for keys the interpreter already supplies (`id`, `title`, `done`,
`priority`, `position`, `created`, `updated`) are ignored without
`fields_override`, and `created`/`updated` literals canonicalize as
volatile timestamps. `list_projects` and `get_user` route `fields` are
not applied by the interpreter at all, for C and the oracle alike.

Prompt improvement shipped with this diagnosis (general, no
benchmark-specific answers, no hardcoded field names): synthesis and
selection prompts now append the deterministic **FIELD INVENTORY** from
the generic extractor `scripts/field_inventory.py` (imported, not
duplicated — per method+route+status class: response field names,
value classes such as zero-time/null/empty-list, and one observed
exemplar per field, from whatever public observations exist for any
HTTP target; this also re-surfaces field names that
`compact_observations` drops), and end with a hard JSON-first
instruction (first character must be `{`, no analysis prose). The
prompt works unchanged if the observations file is swapped for a
different app's. Call budgets are unchanged (A/B/C 1 call, D 2 calls).
Per-case PASS/FAIL lines from the evaluator are now recorded in each
arm record, and a subset rerun
(`--arms B_observations,C_grounded,D_active`) writes
`gemma_arms_result_rerun.json` instead of overwriting the full-run
record. Unit tests: `tests/test_field_inventory.py` (extractor) and
`tests/test_vikunja_field_inventory.py` (prompt wiring, invented
non-Vikunja target).

Rerun status (2026-11-03): **not executed — blocked, zero model calls.**
`GEMMA_API_KEY` was not present in the rerun environment, and no key
was written to any file. Command when a rotated key is available
(process-local env var only):

```powershell
$env:GEMMA_API_KEY = "<rotated key>"
python scripts/vikunja_model_experiment.py --mode live --confirm-live --arms B_observations,C_grounded,D_active
```

Until that runs, whether C improves over 2/6 is **unknown**. The
inventory now supplies value classes and one observed exemplar per
field, so it addresses classes 1–3 in principle and JSON-first
addresses parse failures; class 4 (update-time override semantics)
and class 5 (route-specific permission bodies) still require the
model to choose the right spec mechanism, which no inventory supplies.
