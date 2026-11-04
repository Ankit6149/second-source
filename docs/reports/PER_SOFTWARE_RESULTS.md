# Per-software results — detail

Companion to [SECOND_SOURCE_FINAL_REPORT.md](SECOND_SOURCE_FINAL_REPORT.md).
Every row is measured. Provenance labels: `REAL_MODEL` (genuine Muse,
recorded), `NON_AI` (deterministic, zero model calls). Suites differ in
denominator and difficulty; rows are never averaged.

## Summary table

| # | Software (pinned) | Test | Result | Provenance | Video |
|---|---|---|---|---|---|
| 1 | Owned HTTP task-workflow v1 | Full UI job, independent verification | **30/30 passed** | NON_AI | `demos/software-tests/http/http.webm` |
| 2 | Owned ledger (CLI) | Full UI job, independent verification | **22/25 passed** | NON_AI | `demos/software-tests/ledger/ledger.webm` |
| 2b | Owned ledger (CLI) | Genuine model candidate, sealed 25-case (recorded) | **14/25** | REAL_MODEL | — (recorded evidence) |
| 3 | Vikunja v2.4.0 | Frozen held-out, compiler | **6/6** | NON_AI | — |
| 3b | Vikunja v2.4.0 | Extended frozen suite, compiler | **6/6** | NON_AI | — |
| 3c | Vikunja v2.4.0 | Live engine rebuild, public ladder | **11/19** | NON_AI | `demos/software-tests/vikunja/vikunja.webm` |
| 3d | Vikunja v2.4.0 | Muse grounded, alone (recorded) | **2/6** | REAL_MODEL | — |
| 3e | Vikunja v2.4.0 | Muse active probing, alone (recorded) | **1/6** | REAL_MODEL | — |
| 3f | Vikunja v2.4.0 | Muse hybrid raw candidate (single post-gate eval) | **6/6 + 6/6** | REAL_MODEL | — |
| 4 | File Browser v2.63.23 | Differential (6 cases + mutated control) | **7/7** | NON_AI | `demos/software-tests/filebrowser/filebrowser.webm` |
| 5 | Browser/motion — Flowboard spring | Held-out drag/scroll evaluation | **PASS** (RMSE 2.505px ≤ 8px; layout 0px) | NON_AI | `demos/software-tests/motion/motion.webm` |
| 6 | Gitea 1.22.6 | First contact: probe → compile → 6 differential cases | **2/6** | NON_AI | pending production session |

## Detail per software

### 1. Owned HTTP task-workflow
- Flow: choose target → review exact scope → consent → authorize (digest
  pinned) → queue → start → verification dialog.
- Verification: 30 passed, 0 failed, 0 indeterminate, 30 total.
- Candidate lineage: `repair-1 · improved` selected over the initial
  candidate by the same public suite; candidate preview exposes the exact
  backend-sanitized lineage (no private source).
- Orchestration candidate also constructed: 2 generated routes, proof
  bundle with hash-verified manifest.

### 2. Owned ledger (CLI)
- NON_AI baseline candidate (`initial · no change`): **22/25** — the three
  failures are recorded in the candidate lineage, not repaired silently.
- REAL_MODEL recorded run (separate target/suite provenance): **14/25** —
  a genuine muse-spark-1.3 candidate scored on the sealed 25-case suite;
  provider attestation incomplete, labeled as such.

### 3. Vikunja v2.4.0
- Suites: frozen 6-case held-out (continuity), extended suite frozen before
  any prompt use (SHA-pinned, AST-isolated imports), 19-step public ladder.
- Compiler: 6/6 frozen, 6/6 extended, 11/19 public ladder.
  Public-ladder divergences concentrate in read-after-share routes
  (`GET /projects/{pid}/tasks`, `GET /tasks/{tid}` after sharing).
- Muse arms (recorded, packet-authorized, receipts durable):
  grounded 2/6, active 1/6. Per-route hybrid: every proposed edit was
  rejected by the public-conformance gate (singles 1–2/19 vs compiler
  11/19); the raw merged candidate, evaluated once after gating, scored
  6/6 + 6/6. Deployable candidate = compiler; **no improvement claimed**.

### 4. File Browser v2.63.23
- Cases: login, wrong-password 401, non-admin user-create 403, admin
  user create/read, duplicate-user contract (500 reference), file/user
  surface from compiled routes — **6/6**, plus mutated-spec control
  (login error 200) correctly **differs** → **7/7** total.
- Transfer note: the same generic compiler/interpreter as Vikunja; the two
  initial failures (missing non-admin/duplicate public probes, a `_parent`
  fallback bug) were fixed generically, with public probes added — no
  per-product branches.

### 5. Browser / motion — Flowboard spring
- Setup: reference spring (stiffness 170, damping 26) inferred from
  held-out observations: drag 150px; scrolls 0/150/450/750. Fitting and
  evaluation use disjoint observation sets.
- Fresh run (4 Nov 2026): trajectory RMSE **2.505px** (threshold 8px),
  overshoot/settle behaviors pass, layout max diff **0px** → **PASS**.
  Full numbers: `browser-slice-v2/verdict.json`.

### 6. Gitea 1.22.6 — first contact (never previously tested)
- Setup: pinned 1.22.6, local sqlite, admin via CLI; bounded subsystem:
  version, repositories, issues, auth boundary.
- Probes (6): `GET /version`, `POST /user/repos`, `GET /repos/{owner}/{repo}`,
  `POST …/issues`, `GET …/issues`, unauthenticated `GET /user`.
- Differential cases vs compiled candidate:

| Case | Reference | Candidate | Verdict |
|---|---|---|---|
| version | 200 | 200 | pass |
| create_repo | 201, name matches | 201, name matches | pass |
| get_repo | 200 | 404 | **fail** — probed repo name stays literal in the route template |
| create_issue | 201 | 404 | **fail** — same template generalization gap |
| list_issues | 200, 1 issue | 404 | **fail** — same gap |
| unauth_user | 401 | 404 | **fail** — error-only routes are not compiled |

- Result **2/6**. Next fix (not yet done): generalize path segments that
  match created-entity names into templates, and compile error-boundary
  routes. Recorded here so the improvement, when made, is measurable
  against this baseline.
- **Follow-up (same day, measured against the baseline above):** the fix
  was implemented generically in the compiler/candidate - path segments
  matching observed usernames or created-entity names are templated
  (`/repos/{owner}/{id}`), name-addressed entities resolve by their
  observed `name`/`title`, the collection for owner-templated item routes
  is the nearest literal segment, non-dict list exemplars no longer crash
  the candidate, and the authenticated `GET /user` surface is probed so
  the unauthenticated boundary compiles. Re-run through the engine
  (investigation `inv-5e0d2dd1925d`): **6/6** on the same 6 public
  differential cases. This is public conformance, NON_AI. The sealed
  Gitea held-out set was **not** run, so no held-out improvement is
  claimed. Regression check after the fix: File Browser 7/7, Vikunja
  public ladder unchanged at 11/19.

### 7. Muse inside the pipeline - Vikunja public ladder repair (4 Nov 2026)
- Packet `muse-in-pipeline-20261104`: max 3 calls / $0.50 ceiling; actual
  3 calls, **$0.053** recorded (16,467 input / 7,635 output tokens).
  Receipts: `.runs/muse-in-pipeline-20261104/receipts.jsonl`.
- Compiler baseline on the public ladder: **11/19** (8 divergent routes).
- Muse received only the divergent routes' contracts and public
  divergence diffs (held-out data never in prompts) and proposed bounded
  contract repairs in 3 rounds. Every round's edits regressed the
  candidate to **2/19** when composed, so the public-conformance gate
  rejected all of them. Final candidate: compiler, **11/19** unchanged.
- Interpretation (measured, not spun): whole-route contract rewrites are
  too blunt - Muse changed route kinds/access beyond the divergent
  behavior. The gate did its job; Muse added no deployable improvement
  in this configuration, and that is the recorded result.

### 8. Muse route-level experiment repairs - Vikunja (4 Nov 2026)
- Packet `muse-exp-routes-20261104`: Muse worked inside the experiment,
  one divergent public-ladder route per call. Actual use: **5 calls**,
  **$0.031** recorded (7,620 input / 5,098 output tokens). Receipts:
  `.runs/muse-exp-routes-20261104/receipts.jsonl`.
- Compiler baseline remained **11/19**. Muse returned the compiled
  contract unchanged for `GET /projects/{pid}/tasks`, `GET /projects`,
  `GET /tasks/{tid}`, and `GET /user`; the concrete `/projects/999999`
  action has no separate candidate route. Its only proposed change, a
  validation edit to `POST /tasks/{tid}`, regressed the composed
  candidate initially appeared to fall to **2/19**, but isolated recheck proved a candidate port-reuse measurement race; the exact edit is neutral at **11/19** and was not kept under the strict-improvement gate.
- Checker correction: `public_conformance` now waits for the terminated candidate process to exit before any port reuse.
- Result: **no deployable improvement**. The remaining divergences are
  primarily candidate-interpreter/state semantics that the permitted
  route-contract fields cannot express; this is now the precise blocker,
  rather than a claim that Muse was not used.
