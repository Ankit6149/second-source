# Second Source — Final Technical Report

**Project:** Second Source — evidence-first software reconstruction
**Competition:** Meta Global AI Developer Hackathon (Indie track)
**Report date:** 4 November 2026
**Codebase:** `github.com/Ankit6149/second-source` at `a0c8bdd` (main, 4 Nov 2026)
**Production:** https://second-source-alpha.vercel.app/ (`/`, `/app/`)

---

## 1. Executive summary

Second Source investigates authorized software, records what it actually does,
compiles that evidence into an independent candidate implementation, scores
the candidate against the reference, and shows the user the code, the
differences, and a technical report. Every number in this report is measured;
every result carries a provenance label that is never merged or relabeled:

- **REAL_MODEL** — genuinely model-authored (Meta Muse Spark 1.3), independently scored.
- **NON_AI** — deterministic evidence compilation, zero model calls.
- **Recorded** — a historical result replayed as evidence, never presented as a live run.

Headline outcomes (AI first; the compiler is the labeled control):

- Genuine Muse results lead: **14/25** on the owned ledger (sealed suite),
  **2/6** grounded and **1/6** active-probing on Vikunja, **3/7** on
  File Browser, and a per-route Muse hybrid whose raw candidate scored
  **6/6 + 6/6** in a single post-gate evaluation while the deployable gated
  candidate remained the compiler (Section 6). Muse alone, asked to guess
  every observed fact, is the weakest arm - that is the problem Second
  Source's evidence grounding exists to fix.
- Control baseline (no AI): the deterministic compiler reaches **6/6** on
  the frozen Vikunja suite, **6/6** on the extended suite, **7/7** on File
  Browser. It transcribes observed facts; it does not reason about
  unobserved behavior, and its scores are never reported as model scores.
- On a first-ever test of **Gitea 1.22.6**, the same pipeline scored **2/6**;
  after a generic route-generalization fix measured against that baseline,
  **6/6** on the same public cases (Section 7.6). Held-out Gitea cases
  remain sealed and unrun.
- The browser/motion slice passes its held-out evaluation: trajectory RMSE
  **2.505px** against an 8px threshold, layout difference **0px**.

## 2. The problem

Teams depend on software they can run but cannot see inside. Documentation
drifts, vendors disappear, and the only specification left is behavior. Hiring
someone to reconstruct a system from observation is slow and rarely verified.
Second Source treats observed behavior as the specification: probe the
reference, write down exactly what it does, rebuild from that evidence, and
prove or disprove equivalence with an independent evaluator.

## 3. How it works

```
Input (instruction + authorized target)
  → Scope approval (exact operations, digest-pinned, owner-approved)
  → Observe (public probes against a fresh reference; inputs/outputs recorded)
  → Compile (evidence → versioned behavioral IR → candidate specification)
  → Construct (candidate artifacts + report + verifiable proof bundle)
  → Verify (independent evaluator: frozen held-out, public ladder, differential)
  → Compare & deliver (side-by-side results, runnable downloads, provenance)
```

Design commitments:

- **Observed facts are protected.** Model proposals must justify overriding
  evidence-derived values; the compiler never guesses constants it has seen.
- **Decomposition.** Behavior is compiled per resource/operation, then merged
  under a public-conformance gate. Held-out cases are never in prompts.
- **Provenance discipline.** REAL_MODEL, NON_AI, and recorded results are
  labeled per artifact and per row, and never averaged together.
- **Failures stay visible.** Negative results, provider failures (unscored),
  and divergences are kept in the record.

## 4. System components

| Component | What it does |
|---|---|
| Investigation engine (`scripts/investigation_engine.py`) | Local, loopback-only (127.0.0.1:8765). Probes a fresh disposable reference, compiles evidence, scores public conformance. Targets: Vikunja, File Browser, Gitea. |
| Evidence compiler (`scripts/evidence_compiler.py`) | Transcribes observations into a candidate specification (routes, auth, validation, errors, relationships). Target-agnostic. |
| Candidate interpreter (`scripts/vikunja_candidate_server.py`) | Executes a compiled specification as a real HTTP service for differential scoring. |
| Orchestration service (`src/second_source/orchestration/`) | Durable, owner-isolated investigations: create → authorize → enqueue → execute → workspace/candidate/verification/export artifacts, ordered persisted events. |
| Product (`product/`) | The web app: chat-first workspace, sign-in (Google via Supabase), candidate inspector, Compare (two-software test bench), Reports & exports (scoreboard + downloads). |
| Experiment registry (`scripts/experiment_registry.py`) | Every genuine run with provenance, budgets, hashes, failure class. Negative results retained. |

## 5. Methodology

- References are pinned (Vikunja v2.4.0, File Browser v2.63.23, Gitea 1.22.6,
  owned fixtures by scope digest) and started fresh per run.
- Public observations have a fixed budget; evaluation suites are frozen
  before any model sees related prompts and are imported only inside
  scoring code (AST-isolation tested).
- Scores are exact-match behavioral comparisons (status, body fields,
  state transitions) executed by an evaluator independent of the candidate.
- Infrastructure/provider failures are recorded as unscored, never as 0.
- Frontend sessions were recorded separately per software in Chromium
  (`demos/software-tests/`).

## 6. AI alone vs AI + Second Source vs Second Source alone

Different suites have different denominators; they are not averaged.

| Method | Target / suite | Result | Provenance |
|---|---|---|---|
| Muse prior-only (zero-shot) | Vikunja frozen | 0/6 (historical dev baseline family) | REAL_MODEL |
| Muse coverage-grounded, alone | Vikunja frozen | **2/6** | REAL_MODEL |
| Muse active probing, alone | Vikunja frozen | **1/6** | REAL_MODEL |
| Muse per-route hybrid + compiler (raw candidate, single post-gate evaluation) | Vikunja frozen + extended | **6/6 + 6/6** | REAL_MODEL |
| Muse per-route hybrid + compiler (deployable, after public-conformance gate) | Vikunja | compiler candidate retained — **no model improvement claimed** | NON_AI |
| Muse genuine candidate | Owned ledger, sealed 25-case | **14/25** | REAL_MODEL |
| Evidence compiler alone | Vikunja frozen | **6/6** | NON_AI |
| Evidence compiler alone | Vikunja extended (frozen pre-prompt, SHA-pinned) | **6/6** | NON_AI |
| Evidence compiler alone | File Browser differential (6 cases + mutated control) | **7/7** | NON_AI |
| Deterministic baseline candidate | Owned ledger 25-case | 22/25 | NON_AI |

Why the gate matters: model edits that break already-correct observed
behavior are rejected by public conformance (never by held-out outcomes).
On Vikunja the compiler was already at ceiling, so the hybrid could only
tie — Second Source therefore claims the tie honestly and uses the extended
suite, not prompt tuning, to look for headroom.

## 7. Per-software results

Full detail: [PER_SOFTWARE_RESULTS.md](PER_SOFTWARE_RESULTS.md) and
machine-readable [results.json](results.json).

### 7.1 Owned HTTP task-workflow (fixture)
UI job (target → scope → authorize → queue → start): independent verification
**30 passed / 30**, 0 failed, 0 indeterminate. Candidate `repair-1` selected
as improved. Video: `demos/software-tests/http/http.webm`.

### 7.2 Owned ledger (CLI fixture)
Separate UI job: verification **22 passed / 25** for the deterministic
baseline candidate (`initial · no change`). The genuine Muse candidate on
the same sealed suite is recorded separately at **14/25** (REAL_MODEL).
Video: `demos/software-tests/ledger/ledger.webm`.

### 7.3 Vikunja v2.4.0 (professional)
- Frozen held-out: compiler **6/6**; extended frozen suite: **6/6**.
- Live engine rebuild (probe → compile → public ladder): **11/19** with
  divergences listed in the panel (read-after-share routes).
- Muse alone: 2/6 grounded, 1/6 active (Section 6).
Video: `demos/software-tests/vikunja/vikunja.webm`.

### 7.4 File Browser v2.63.23 (professional)
Differential benchmark against the real reference: **7/7** — login, wrong
password (401), user create/read, non-admin 403, duplicate-user contract,
plus a mutated-spec negative control that correctly differs. The same result
reproduces live from the UI engine button.
Video: `demos/software-tests/filebrowser/filebrowser.webm`.

### 7.5 Browser / motion — Flowboard spring slice
Candidate inferred from held-out drag/scroll observations (never fitted to
them): trajectory RMSE **2.505px** (pass ≤ 8px), overshoot present like the
reference, settling parity, layout max diff **0px**. Fresh evaluation run
4 Nov 2026; `browser-slice-v2/verdict.json`.
Video: `demos/software-tests/motion/motion.webm`.

### 7.6 Gitea 1.22.6 (professional, first-ever test)
First contact, same generic pipeline, bounded subsystem (version,
repositories, issues, auth boundary): **2/6**.
- Pass: `GET /version`, repo creation.
- Fail: repo read, issue create/list — compiled route templates keep the
  probed repo name (`ss-demo`) literal instead of generalizing the segment,
  so reads of a differently-named repo 404 on the candidate.
- Fail: unauthenticated boundary — candidate returns 404 where the
  reference returns 401 (error-only routes are not compiled).
These divergences are stored verbatim in the investigation record.
Video: pending the production UI session; engine result reproducible with
`python scripts/investigation_engine.py` and target `gitea-v1`.

## 8. Reports, artifacts, and reproducibility

Every completed investigation produces: the exact candidate specification
(JSON), `report.md`, `report.json`, `manifest.json` (file SHA-256 digests),
and a deterministic proof-bundle ZIP — each artifact SHA-256 addressed and
downloadable from the workspace/Reports. The frontend additionally exports
the scoreboard and per-run report/readme/manifest built from the same
sanitized backend data.

Reproduce the headline numbers:

```text
python scripts/investigation_engine.py            # local engine (NON_AI)
# UI: choose a target, confirm scope, authorize, queue, start
python -m pytest tests/test_investigation_engine.py tests/test_orchestration_gate_a.py
node browser/per-software.mjs <http|ledger|vikunja|filebrowser>   # recorded sessions
```

## 9. Limitations (explicit)

- The hosted investigations backend (Render blueprint in `render.yaml`) is
  not yet activated; production sign-in works, but starting a saved
  investigation on the hosted site requires that deployment. Locally, the
  full flow runs today.
- The engine executes the deterministic NON_AI pipeline. Model reasoning
  enters through recorded, packet-authorized experiments with durable
  receipts — never as unattributed live calls, and never in these videos.
- Gitea support is a first-contact probe result (2/6), not a benchmark.
- Motion support is a bounded spring/layout slice; no Canvas/WebGL/3D claim.
- Provider attestation for the historical 14/25 Muse run is incomplete
  (locally consistent artifacts); it is labeled accordingly everywhere.

## 10. Submission status

- Production site live and verified (landing, app, sign-in, redirects).
- This report, per-software results, machine-readable results, and raw
  per-software videos are stored in the repository (`docs/reports/`,
  `demos/software-tests/`).
- Demonstration video upload and hackathon portal submission are owner
  actions; **no submission receipt exists yet**, so the submission is not
  claimed as complete.
