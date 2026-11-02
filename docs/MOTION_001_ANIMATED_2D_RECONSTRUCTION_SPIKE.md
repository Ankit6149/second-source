# MOTION-001 — Evidence-based 2D animation reconstruction (optional spike)
**Status: RESEARCH PROPOSAL — NOT IMPLEMENTED OR ACCEPTED.** Date: 2026-11-02 IST. Does not authorize new model calls, copyrighted-site copying, production migrations or changes to the submission-critical working product.

## Hypothesis and contribution
Second Source currently demonstrates controlled **CLI and HTTP behavioral** reconstruction. A compelling but **unimplemented** third adapter could investigate *authorized moving 2D webpages*: from bounded interaction/video observations, infer a compact motion law, emit an independent implementation, and score it on held-out timestamps and interactions. Unlike a static screenshot-to-code tool, the desired output must match **motion and behavior**, not just final pixels.

**Do NOT market this as shipped.** Only attempt if final integrated release, original Meta evidence, and public 3-minute submission are already secured, with a strict stop gate.

## Clarification: complete 2D experience reconstruction, not a physics-only demo

**Owner's intended future capability:** faithfully reconstruct sophisticated, rights-cleared **2D web experiences**, including composition, typography, licensed visual assets, visual depth, masks, overlapping layers, section transitions, scroll-pinned video and image sequences, gesture and pointer effects, responsive layout, timing, interactive state and accessibility. “Physics” means *the observed behavior of elements* (including simulated physics), not an assumption that the website uses a literal gravity engine. Awwwards-grade visual choreography is the motivating class, **not** a claim we currently support.

**Fundamental differentiation: measurements before generation.** Existing reconstruction workflows commonly synthesize plausible layouts from a prompt/screenshots. The proposed Second Source adapter should intervene systematically and measure reference responses, then reconstruct a version whose outputs are compared on unseen conditions. It must not treat confident model explanations as observations.

For an explicitly authorized site, build a **measurement plane** with versioned target fingerprint and repeatable browser environment:
- **Spatial/compositing:** at each controlled viewport and scroll coordinate record visible element bounding boxes, transforms, opacity, clipping, overlap/occlusion order, image/text masks, text layout, and raster frame; distinguish directly inspected DOM/computed styles from pixels inferred visually.
- **Temporal:** record monotonic frame timestamp, frame duration, element trajectories, video `currentTime` where observable, animation milestones, pin/unpin thresholds and event-to-render latency. Identify requestAnimationFrame versus CSS/Web Animations versus media synchronization only when directly evidenced; otherwise keep them as competing hypotheses.
- **Intervention:** step through controlled scroll offsets and direction reversals, wheel and touch velocities, pointer paths, click/hover/focus, reloads, back/forward navigation, reduced-motion preference and viewport changes. Reset reference state between sequences and verify repeatability.
- **Assets/rights:** visually relevant images, fonts, video segments, SVGs and sprites require licensed or user-supplied access. Without them, report an asset-fidelity ceiling rather than quietly substituting imagery and claiming exact reconstruction.
- **Multiresolution sampling:** use coarse observations to locate transitions and finer probes around suspected thresholds, discontinuities, easing changes and frame-boundaries. An active sampler should choose the next most discriminating safe probe, instead of blindly capturing thousands of adjacent frames.
- **Separated evaluation:** withheld scroll positions, timestamps, input sequences and viewports measure trajectory/duration error, compositing/visual difference and functional-state conformance separately. A synchronized reference/candidate viewer must show measurable residuals and explain confidence and missing observability.

**Exactness caveat:** Black-box observations can precisely characterize *sampled observable behavior* subject to browser/clock precision. They generally cannot uniquely recover an original site's internal source, exact rendering mechanism, hidden state or all continuous behavior. Two different implementations may be observationally equivalent on the sampled probes. Report uncertainty, untested states and fidelity tolerances; prefer “behaviorally faithful under these conditions” over “identical implementation.”

**Access modes:** (1) pixels/video-only observation; (2) permitted browser-level DOM/computed-style/runtime inspection; (3) owner-provided source/assets. These provide different evidence and different levels of achievable fidelity. Never bypass controls to move from one access mode to another. Explicitly report which was used.

**Hackathon priority:** this is a *future adapter*. Only a very small owned, rights-cleared, measured scroll-scene spike is optional **after** current working CLI/HTTP release, public video and submission are secured. Do not shift the core release schedule to build a general Awwwards-site copier.

## Reality check
- “Gravity” is often a design illusion. Real browser effects also include CSS cubic-bezier transitions, keyframes, springs, scroll-based parallax, mouse-following, transforms, SVG paths, canvas, sprites and JS physics. **Identify the model class from evidence; do not presume physical gravity.**
- 2D still hides font/rendering variation, asset rights, interaction state, browser timing and animations driven by network responses.
- True 3D/WebGL is a different adapter/renderer and out of this spike's scope; it is not inherently impossible to build with web tooling.
- Meta Muse Spark 1.3 supports visual and video understanding per official docs, but the existing Second Source `MetaProvider` implements **text-message-only** chat payloads and G4 local product is **NON_AI**. Video inference would require an independently approved and tested media-capable provider transport and exact-input spending packet. No automatic model fallback or synthetic “real AI” label.

## Single owned target (not arbitrary competitor website)
Create **one rights-cleared local web fixture** with:
1. A hero orb entering on page load with a damped spring or cubic-bezier curve.
2. Two layered shapes moving under scroll at different parallax coefficients.
3. An interactive pointer-triggered or click-triggered animation with a visible state change.
4. Stable synthetic assets/fonts and a `prefers-reduced-motion` alternate behavior.

Candidate cannot read fixture HTML, JS, stylesheets, source maps or prefit parameters during strict black-box experimentation. The measurement program has separate reference-only access.

## Pipeline and trust boundaries

`owner authorization → isolated browser session → intervention plan → timestamped frames + allowed accessibility/network summary → feature tracks → evidence-cited hypotheses → motion class/parameter estimation → candidate HTML/CSS/JS → withheld timeline tests → error report`.

All sessions fixed to loopback and explicit permission. No login, privileged cookies, arbitrary URLs or external effects. Redact incidental secrets from screenshots. Reject external fetch/redirect/iframe. A bounded observer controls viewport, DPR, fonts, locale, reduced-motion setting, interaction sequence, scroll offsets, reset and asset loading. Unstable asynchronous references report `CANNOT_VERIFY`.

**No leakage:** model/candidate agent sees permitted observations only; evaluator controls sealed reference cases, random seeds and motion parameters. If reference parameters are in candidate prompt or rules, mark as seeded rather than learned.

## Measurable experiments (minimum)
- **Load animation:** observe frames at time 0, 150, 300, 600, 1000 ms, fixed viewport, then query an unseen 750 ms checkpoint.
- **Scroll parallax:** sample 3–5 scroll offsets; estimate `screen_y = y0 - k*scroll + residual`. Test unseen offset and one different viewport.
- **Pointer/click event:** replay a fixed sequence, observe bounding boxes, opacity, transforms, state; test a held-out interaction order.
- **Motion-model selection:** candidate classes (a) cubic-bezier/easing, (b) ballistic `y(t)=y0+v0*t+0.5*g*t*t`, (c) damped spring `y(t)=y_eq+A*exp(-lambda*t)*cos(omega*t+phi)`, (d) scroll-linked piecewise transforms. Models are **hypotheses**, not presumptions. Select via residuals, complexity penalty, repeatability and information-gain experiments.
- **Time control:** Playwright clock `install` before page initialization, `pauseAt` and `runFor` to tick RAF/timers if compatible; verify capture against real-time run for external timelines (e.g., CSS animations may not obey virtual clock equally). Record fallback timings; never assume universal determinism.
- **Model role:** Muse can propose competing hypotheses / distinguishing interventions, structured animation primitives and candidate code. Deterministic numerical fitting computes parameters, and a separately controlled evaluator scores outcomes. Zero-prompt leakage and receipts mandatory.

## Report metrics (separate)
1. **Functional state correctness:** percentage of held-out interactions yielding expected semantic state, focus, navigation, element visibility (N and failure classes shown).
2. **Trajectory error:** normalized position RMSE (pixels/viewport dimensions) per tracked element against reference frames.
3. **Timing:** transition onset/duration error (ms) and overshoot/settling time where relevant.
4. **Visual similarity:** per-frame SSIM or perceptual difference under fixed rendering context, reported **separately** from semantics; note font/antialiasing sensitivity.
5. **Evidence cost:** probe count, video/frame count, model calls, token cost and wall-clock time. No single flattering combined score.

**Baselines:** static screenshot clone, fixed 5-sample observation and active-probing treatment at identical action/frame budget. A real Muse-generated candidate must be labeled as such with provider response metadata and independently evaluated. A deterministic code-fit is NON_AI even if Muse is used elsewhere in the pipeline.

## Acceptance / stop rule
A *credible* demo only exists if all are independently measured:
- Closed-loop reference → allowed observations → generated candidate → held-out dynamic verification. Show **reference left / candidate right / synchronized playback and motion residual**.
- At least one truly unseen timestamp and one unseen interaction or viewport condition.
- No hardcoded reference parameters/gold frames in candidate prompt.
- Honest Meta-model provenance when model contribution is claimed.
- Existing ledger+HTTP acceptance remains green, and repo/default-branch/submission essentials remain ready.
- User-visible 3-minute video remains within mandatory submission limit.

**Timebox suggestion:** first 2–4 hours for authorized synthetic fixture + frame capture + trajectory scoring. **GO** to model-assisted candidate only if the independent capture/comparison works with held-out points and a coding budget is available. Otherwise **STOP**; retain the proven CLI/HTTP submission rather than replace it with an unverified animation demo. The 2–4h is a planning cap, not a promise of autonomous completion.

## Competing entries / relevance (public signals, not head-to-head scores)
- RE:GOV (`rockyru/regov`): already targets legacy website rebuilding with Muse Spark and SAM 3.1. The sharper differentiation would be reconstructing **behavior over time**, not general website migration.
- Nightshift (`seanudeke/Nightshift`): visual and behavioral evaluation of game repairs; benchmark discipline is a competitive minimum, not itself unique.
- SnapLab NG (`sproutjeph/snapLabNg`): photographed school lab → interactive 3D, attractive visual proposition. Again, no verified common benchmark against Second Source.

**Decision:** `SPEC_ONLY` until owner opts in and the final submission path is secure. Never claim general animated-website reconstruction just because an owned 2D fixture passes.
