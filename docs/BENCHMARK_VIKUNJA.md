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
