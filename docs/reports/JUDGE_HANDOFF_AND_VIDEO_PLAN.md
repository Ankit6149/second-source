# Second Source — Judge Handoff Report & 3-Minute Video Plan

**Date:** 4 Nov 2026 · **Production:** https://second-source-alpha.vercel.app/
**Repo:** github.com/Ankit6149/second-source · **API:** https://second-source-api.onrender.com/health/ready

## 1. What Second Source is

An AI scientist for software behavior: give it an authorized application,
and it observes what the software does, compiles that evidence into an
independent candidate implementation, runs the candidate, scores it
against the reference with an independent evaluator, and hands back the
candidate, the differences, and a technical report.

**End goal (explicit):** any authorized link → automatic rebuild, with
proof. This submission is the verified core of that machine: the
investigation engine, the independent evaluator, Muse wired inside the
pipeline under a strict gate, and a working product around them.

## 2. Verified results (provenance never merged)

| Target | Method | Result |
|---|---|---|
| Vikunja v2.4.0 (public ladder, 19 probes) | NON_AI evidence compiler | **19/19** |
| Vikunja frozen suite / extended suite | NON_AI | **6/6 · 6/6** |
| Vikunja default-project rule | Muse Spark 1.3 (REAL_MODEL) | Muse identified `Inbox`, `My Open Tasks`; rule now derived generically by the compiler; 18/19 → 19/19 |
| File Browser v2.63.23 | NON_AI | **7/7** (incl. mutated control) |
| File Browser | Muse alone / gated route reviews | 3/7 alone · 7/7 preserved under gate |
| Gitea 1.22.6 (public subsystem) | NON_AI | **6/6** |
| Owned ledger benchmark (sealed, 25 cases) | Muse Spark 1.3 (REAL_MODEL) | **14/25** (11 failures kept) |
| Owned ledger | NON_AI compiler | 22/25 |
| Owned HTTP workflow | NON_AI | **30/30** |
| Browser motion (Flowboard held-out) | NON_AI fitter | **PASS, RMSE 2.505px (≤8px), layout 0px** |
| Muse whole-route repair experiment | REAL_MODEL | 11→2, **gate-rejected** (recorded, not hidden) |

Key measurement lesson: an early "divergence" was the ladder being
replayed on an already-probed reference (duplicate project created).
Baseline conformance now always uses a fresh reference.

## 3. How it works (30 seconds)

Probe (public actions only) → evidence compiler (observed facts,
immutable) → Muse reasons only about unknowns under a gate
(strict-improvement or exit) → candidate interpreter executes the spec →
independent evaluator scores → report + ZIP export. Muse Spark 1.3 is
also available inside a live investigation via opt-in `muse-repair`
(1 call, $0.50 cap, consent, receipts persisted).

## 4. Product state

- Landing, App (input → process → output workspace; no dashboard
  overview), Reports, Experiments, Challenge, Architecture (interactive,
  click any component for why/solves/details).
- Sign-in (Supabase Auth incl. Google) as a modal; chat stays simple;
  technical detail lives in Compare/Reports/Settings.
- Hosted backend (Render + Supabase): auth, investigations, queue,
  events, verification, report, export — all verified live. Bounded
  NON_AI execution enabled for judges (real worker, honestly labeled;
  no model call is claimed where none happens).
- Local engine (`scripts/investigation_engine.py`, port 8765) runs the
  full professional-target pipeline; raw UI test videos per target are
  in `demos/software-tests/`.

## 5. Honest limitations

- Supported targets are pinned and bounded (Vikunja, File Browser,
  Gitea, owned fixtures, one motion slice) — not arbitrary URLs yet.
- Hosted execution is the bounded NON_AI worker; the full local
  professional-target engine is not hosted (Render cannot reach a
  user's local references).
- Muse's 14/25 ledger attestation is incomplete (provider signature
  unverifiable); reported as recorded, never upgraded.
- Held-out Gitea suite sealed and unrun.

## 6. Why this took ~10 days

Arbitrary rebuild is worthless without proof. The time built the
substrate: a game-proof independent evaluator, provenance discipline,
a generic compiler/interpreter that crosses three real products, gated
Muse integration with receipts, and only then the product surface.

---

# 3-Minute Video — Shot List (target 2:50–3:00)

Voice style: calm, factual, no hype words. Screen-record at 1080p,
cursor visible, real time (no speed-ups on runs).

| # | Time | Shot | Direction / narration |
|---|---|---|---|
| 1 | 0:00–0:15 | Landing page hero | "Second Source investigates authorized software, rebuilds it independently, and proves how close the rebuild is. End goal: any authorized link in, verified software out." |
| 2 | 0:15–0:35 | The problem, Architecture page | Click 2–3 components; side card opens. "A rebuild you can't verify is a guess. So we built the proof first: independent evaluator, frozen tests, provenance that never merges." |
| 3 | 0:35–1:20 | App: New investigation → Vikunja (local engine) | Type a plain instruction, run. Show real stages: probes, compile, conformance climbing to **19/19**. "Every step here is a real execution event — no replay, no mock." |
| 4 | 1:20–1:45 | Candidate + comparison + download | Open candidate spec, one field-level diff view, download ZIP/report. "You get runnable code, the evidence, and the differences — not a demo." |
| 5 | 1:45–2:15 | Reports page scoreboard | Pan the Muse-first table. "Muse alone: 14 of 25 on a sealed ledger suite. Muse inside Second Source, gated: it found the exact default-project rule that took Vikunja to 19 of 19. Whole-route rewrites failed — the gate rejected them, and that failure is published too." |
| 6 | 2:15–2:40 | Cross-target proof | Experiments view: File Browser 7/7, Gitea 6/6, motion PASS 2.5px. "Same engine, three professional products, one browser-motion target. Nothing is hardcoded per app." |
| 7 | 2:40–3:00 | Close on landing + live URL | "Live now: sign in and run a bounded investigation yourself. Second Source — observe, rebuild, verify." Show URL on screen. |

**Do not show:** secrets, env vars, local file paths with usernames,
the sealed held-out data, or any unmerged branch name.
**Captions:** burn in the score chips (19/19 · 7/7 · 6/6 · 14/25) at the
moments they are spoken.
