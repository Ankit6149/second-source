# Browser slice v2 — multi-element workflow reconstruction

A second, harder authorized reconstruction slice. It goes beyond the single
spring card of `browser-slice/`: the reference is an original, owned
task-board page ("Flowboard") combining four behaviours at once — a
spring-draggable card, a scroll-linked parallax header, filter buttons that
show/hide tasks, and hover transitions.

## What the reference does (`reference.html`, original/owned)

- **Drag + spring:** `#card` follows the pointer; on release a damped spring
  (`requestAnimationFrame`, semi-implicit Euler) returns it to rest.
  Status text cycles `At rest → Dragging… → Settling… → At rest`.
- **Parallax:** `#parallax-layer` gets `translateY(scrollY × factor)` on scroll.
- **Filters:** `#filter-all|work|personal` toggle `.task` visibility by
  `data-cat` and move the `.active` pill.
- **Hover:** `#hover-chip` scales via a CSS transition; buttons lift on hover.

## Method

1. **`node capture.mjs`** — Playwright/Chromium (reused from
   `../product/node_modules`, nothing installed) loads the reference and saves
   `observations.json`: DOM/a11y summary, layout boxes + computed styles,
   hover before/after, and three *fitting* interactions:
   drag **260 px** (frame-indexed `translateX` samples), scroll points
   **[0, 300]**, filter **work**. Screenshots saved alongside.
2. **`node fit.mjs`** — reads **only `observations.json`** (verify: its single
   `readFileSync` target is `observations.json`; it never opens
   `reference.html`). It grid-searches spring `(k, c)` against the
   post-release trajectory, derives the parallax transform factor from the
   observed rect slope (`factor = slope + 1`, since
   `rectY = top − scrollY + factor·scrollY`), and takes layout/filter facts
   from the observations. It then **generates `candidate.html`** — an
   independently written page whose constants are the fitted values.
   Results land in `inferred.json`.
3. **`node evaluate.mjs`** — re-runs reference and candidate on **held-out
   interactions never used for fitting**: drag **150 px**, scroll sequence
   **[0, 150, 450, 750]**, filter **personal**. It compares functional state
   (final status, visible task ids, active button), layout boxes, trajectory
   RMSE (common 8 ms time grid from release), overshoot sign, settling time,
   and parallax rect positions. It also builds two **adversarial variants**
   from the candidate — wrong spring (overdamped `k=120, c=42`) and wrong
   parallax (factor `0.02`) — which must be detected as different.
   Writes `verdict.json`.

## Real results (this run)

| Check | Value | Threshold | Result |
|---|---|---|---|
| Fitted spring | k=164, c=14 (true: 180, 14), fit RMSE 4.37 px | — | fitted from data only |
| Fitted parallax factor | 0.3000 (true: 0.3) | — | exact |
| Held-out trajectory RMSE (drag 150 px) | **1.741 px** | ≤ 8 px | pass |
| Overshoot | ref −18.51 px, cand −15.97 px (both present) | sign match | pass |
| Settling time | ref 0.567 s, cand 0.433 s (Δ 0.134 s) | reported | — |
| Layout max box diff | 0 px | ≤ 4 px | pass |
| Parallax max rect diff (held-out scrolls) | 0 px | ≤ 6 px | pass |
| Filter `personal` (held-out) | visible `[task-3, task-5, task-6]` both | exact match | pass |
| Adversarial wrong spring | RMSE 44.35 px, no overshoot | > 8 px | detected |
| Adversarial wrong parallax | max rect diff 210 px | > 18 px | detected |
| **Overall verdict** | | | **PASS** (`verdict.json`) |

## Limitations (explicit)

- The fitted stiffness (164) differs from the true value (180): frame-timing
  quantisation in the sampled trajectory biases the grid search. Behaviour
  still matches within 1.74 px RMSE on held-out drags, but the parameters are
  an approximation, not the ground truth.
- Settling times differ by 0.134 s on the held-out drag — visible in
  `verdict.json`; the pass gate is RMSE + overshoot, not settling equality.
- Only one draggable element, one parallax layer, and three filter states are
  exercised. No keyboard interaction, touch gestures, resize behaviour, or
  reduced-motion preferences are covered.
- Layout comparison covers four boxes (`#card`, `#task-1`, `header`,
  `#filter-all`) at one viewport (1280×800); other viewports are untested.
- Both pages share the same Chromium/Playwright harness; cross-browser
  behaviour is out of scope.
- The candidate intentionally reproduces the reference's visible copy and
  structure because the DOM summary is part of the observations; this is an
  authorized reconstruction of our own page, not a general copying method.

## Files

`reference.html`, `capture.mjs`, `fit.mjs`, `evaluate.mjs`,
`candidate.html` (generated), `observations.json`, `inferred.json`,
`verdict.json`, screenshots, `_variant-*.html` (adversarial, generated).

Run order: `node capture.mjs && node fit.mjs && node evaluate.mjs`.
No installs, no network, no paid APIs, no commits.
