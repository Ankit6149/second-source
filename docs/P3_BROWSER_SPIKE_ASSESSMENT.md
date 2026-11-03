# P3 Advanced 2D Browser Reconstruction — GO/NO-GO Assessment (2026-11-02)

> **Update (2026-11-03):** A bounded slice now exists in `browser-slice/` — Chromium capture of a spring-drag trajectory, physics fit from observations only, held-out 140px drag passed at **1.05px trajectory RMSE**, adversarial variants detected. That validates one owned fixture's motion fidelity; it does **not** overturn the verdict below for general closed-loop website reconstruction, which remains unimplemented. Product UI keeps browser/motion execution unavailable (evidence review only).

**Verdict: NO-GO for the genuine closed loop in this submission window.**
The submission is not disturbed; Priorities 1–2 carry the entry.

## Gate conditions (from the assignment)

Attempt only after P1 (genuine second-target experiment) and P2
(Interactive Reconstruction Lab) are genuinely functional; stop if a
closed-loop browser reconstruction cannot pass a held-out test in a
short isolated spike.

## Evidence

- **P2 is functional**: `/lab/` (PR #34) with recorded probe differentials.
- **P1 is engineered, not yet genuine**: `--mode discover-real` + gated
  `--mode real` synthesis + sealed 30-case evaluator (PR #33, tests
  green). The genuine run awaits the owner's `MODEL_API_KEY` in the
  operator environment (authorized, $0.50 cap, zero calls made).
- **P3 prerequisites absent**: the PRD (line 211) approves CDP observation
  of DOM/attributes/URLs/screenshots/network metadata, and the product
  already drives Chromium via Playwright for acceptance. But the repo has
  **no** CDP observation engine, no visual/scroll candidate DSL, no
  scroll-trajectory or visual-fidelity evaluator, and no rights-cleared
  2D fixture. Each is a subsystem, not an edit.
- **Closed loop needs inference**: Muse behavior inference is the core
  of P3 and is blocked on the same credential gate as P1. A spike without
  genuine inference would only re-prove NON_AI plumbing — already proven
  twice (CLI 14/25 genuine + controls; HTTP 25→30/30 NON_AI).

## What would change the verdict

1. Genuine G4 completes (P1) with a measured result, and
2. ≥24h remain before the deadline after submission is secured, and
3. A spike is time-boxed to: build one original fixture page + CDP
   observation capture + held-out scroll positions, with Muse inference
   under a separate exact spend packet. If the candidate cannot beat a
   static-copy baseline on held-out positions, stop permanently for this
   entry and keep it as future work in the report.

## Honest public framing (already on the landing)

The scope contract and evaluator are target-agnostic; two owned targets
are implemented today. Arbitrary websites and browser reconstruction are
explicitly **not implemented** — see the landing Availability section.
