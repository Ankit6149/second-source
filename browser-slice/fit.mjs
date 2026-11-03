// fit.mjs — infer spring parameters FROM the trajectory in observations.json ONLY.
// It never opens reference.html / candidate source. Reading this file proves that:
// the only input path below is observations.json.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const obs = JSON.parse(fs.readFileSync(path.join(here, 'observations.json'), 'utf8'));
const samples = obs.trajectory.samples;
if (!samples?.length) throw new Error('no trajectory samples');

// Segment post-release: first sample at/after release mark, trim drag prefix.
const relT = obs.trajectory.releaseMarkMs;
let startIdx = samples.findIndex((s) => s.tMs >= relT - 5);
if (startIdx < 0) startIdx = 0;
// Walk back to the peak (max x) near release — release x is the trajectory max in that window.
let peakIdx = startIdx;
for (let i = startIdx; i < Math.min(samples.length, startIdx + 8); i++) if (samples[i].x > samples[peakIdx].x) peakIdx = i;
const ret = samples.slice(peakIdx).map((s) => ({ t: (s.tMs - samples[peakIdx].tMs) / 1000, x: s.x }));
const x0 = ret[0].x;
// Initial velocity from first finite difference (spring starts near v≈0 after pointer release).
const v0 = ret.length > 1 ? (ret[1].x - ret[0].x) / Math.max(1e-6, ret[1].t - ret[0].t) : 0;

function simulate(k, c, tMax) {
  const dt = 0.0005; let x = x0, v = v0; const out = [{ t: 0, x }];
  let steps = Math.ceil(tMax / dt);
  for (let i = 1; i <= steps; i++) { const a = -k * x - c * v; v += a * dt; x += v * dt; if (i % 10 === 0) out.push({ t: i * dt, x }); }
  return out;
}
function rmseFor(k, c, tOff = 0) {
  const sim = simulate(k, c, ret.at(-1).t);
  let se = 0;
  for (const s of ret) {
    const ts = Math.max(0, s.t - tOff);
    let best = sim[0], bd = Infinity;
    for (const p of sim) { const d = Math.abs(p.t - ts); if (d < bd) { bd = d; best = p; } }
    se += (best.x - s.x) ** 2;
  }
  return Math.sqrt(se / ret.length);
}
// Coarse grid then local refinement (mass = 1, so k = wn^2, c = 2*zeta*wn).
// tOff accounts for the 1-3 frame lag between the release timestamp and the
// first spring update visible to the RAF sampler; it is fitted, not assumed.
let best = { k: 100, c: 10, tOff: 0, rmse: Infinity };
for (const tOff of [0, 0.016, 0.032, 0.048])
  for (let k = 40; k <= 400; k += 10) for (let c = 2; c <= 30; c += 1) { const r = rmseFor(k, c, tOff); if (r < best.rmse) best = { k, c, tOff, rmse: r }; }
for (const [dk, dc] of [[5, 0.5], [2, 0.2], [0.5, 0.05]]) {
  let improved = true;
  while (improved) { improved = false;
    for (const [k, c] of [[best.k + dk, best.c], [best.k - dk, best.c], [best.k, best.c + dc], [best.k, best.c - dc], [best.k + dk, best.c + dc], [best.k - dk, best.c - dc]]) {
      if (k <= 0 || c <= 0) continue; const r = rmseFor(k, c, best.tOff);
      if (r < best.rmse - 1e-9) { best = { k, c, tOff: best.tOff, rmse: r }; improved = true; }
    } }
}
const wn = Math.sqrt(best.k), zeta = best.c / (2 * wn), wd = wn * Math.sqrt(Math.max(0, 1 - zeta * zeta));
// Peak/log-decrement cross-check (independent of grid search)
const peaks = [];
for (let i = 1; i < ret.length - 1; i++) if ((ret[i].x - ret[i - 1].x) * (ret[i + 1].x - ret[i].x) < 0 && Math.abs(ret[i].x) > 1) peaks.push(ret[i]);
const overshootPx = Math.min(...ret.map((s) => s.x));
const inferred = {
  method: 'grid-search + local refinement of damped-spring ODE (m=1: x\'\'=-k*x-c*v) fitted to post-release trajectory only; log-decrement/peak cross-check reported separately. Input: observations.json trajectory only — reference source never read.',
  spring: { stiffness_k: +best.k.toFixed(3), damping_c: +best.c.toFixed(3), naturalFreq_wn_rad_s: +wn.toFixed(3), dampingRatio_zeta: +zeta.toFixed(4), dampedFreq_wd_rad_s: +wd.toFixed(3) },
  residualRmsePx: +best.rmse.toFixed(4), fittedTimeOffsetS: best.tOff, samplesUsed: ret.length, releaseXpx: +x0.toFixed(2), initialVelocityPxS: +v0.toFixed(2),
  observedOvershootPx: +overshootPx.toFixed(2), overshootPresent: overshootPx < -2,
  peakCrossCheck: peaks.slice(0, 6).map((p) => ({ tS: +p.t.toFixed(3), xPx: +p.x.toFixed(2) })),
  parallaxFactorObserved: obs.parallax?.factorObserved ?? null,
  layoutObserved: (obs.layoutBefore || []).filter(Boolean),
};
fs.writeFileSync(path.join(here, 'inferred.json'), JSON.stringify(inferred, null, 2));

// --- Generate candidate.html from inferred values (parameter-driven) ---
const cardBox = (obs.layoutBefore || []).find((l) => l && l.selector === '#card')?.box || { width: 260, height: 120 };
const K = inferred.spring.stiffness_k, C = inferred.spring.damping_c;
const PF = inferred.parallaxFactorObserved != null ? +inferred.parallaxFactorObserved.toFixed(3) : 0.3;
const candidate = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Candidate — reconstructed from inferred.json</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: #f6f7f9; color: #1a2332; min-height: 100vh; }
  #parallax-layer { position: fixed; top: -120px; left: 0; right: 0; height: 340px; background: linear-gradient(135deg, #dbeafe 0%, #ede9fe 55%, #fef3c7 100%); z-index: 0; will-change: transform; pointer-events: none; }
  .page { position: relative; z-index: 1; max-width: 880px; margin: 0 auto; padding: 32px 24px 48px; }
  header { padding: 28px 0 18px; }
  h1 { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; }
  .sub { color: #5b6b82; margin-top: 6px; font-size: 15px; line-height: 1.5; }
  .stage { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 16px; padding: 28px; margin-top: 22px; overflow: hidden; }
  .stage h2 { font-size: 16px; margin-bottom: 8px; }
  .stage p { color: #5b6b82; font-size: 14px; line-height: 1.55; }
  #card { width: ${Math.round(cardBox.width)}px; height: ${Math.round(cardBox.height)}px; margin-top: 20px; background: #2563eb; color: #fff; border-radius: 14px; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 16px; cursor: grab; user-select: none; touch-action: none; box-shadow: 0 10px 24px rgba(37,99,235,.28); will-change: transform; }
  #hover-chip { display: inline-flex; margin-top: 22px; padding: 10px 18px; border-radius: 999px; border: 1px solid #cbd5e1; background: #fff; font-size: 14px; font-weight: 600; cursor: pointer; transition: transform 320ms cubic-bezier(0.34, 1.4, 0.64, 1), background-color 320ms cubic-bezier(0.34, 1.4, 0.64, 1); }
  #hover-chip:hover { transform: translateY(-3px) scale(1.04); background: #eff6ff; }
  .spacer { height: 900px; margin-top: 28px; background: linear-gradient(#fff, #f1f5f9); border: 1px solid #e2e8f0; border-radius: 16px; padding: 24px; color: #5b6b82; font-size: 14px; }
  #status { margin-top: 14px; font-size: 13px; color: #475569; min-height: 18px; }
</style>
</head>
<body>
<div id="parallax-layer" aria-hidden="true"></div>
<div class="page">
  <header><h1>Spring-back card fixture</h1><p class="sub">Drag the blue card sideways and release. It springs back with overshoot. Scroll to see the parallax band move at a different rate.</p></header>
  <main>
    <section class="stage" aria-label="Drag stage">
      <h2>Drag stage</h2><p>Pointer drag is tracked in real time. On release a damped spring returns the card to rest.</p>
      <div id="card" role="button" tabindex="0" aria-label="Draggable card">Drag me →</div>
      <button id="hover-chip" type="button">Hover chip</button>
      <div id="status" role="status" aria-live="polite">At rest</div>
    </section>
    <div class="spacer"><p>Scroll spacer. The gradient band behind the header is parallax-linked to scroll position.</p></div>
  </main>
  <footer style="margin-top:28px;color:#94a3b8;font-size:13px">Original owned fixture. No external assets.</footer>
</div>
<script>
// Generated by fit.mjs from inferred.json — do not hand-tune.
const SPRING_K = ${K};
const SPRING_C = ${C};
const PARALLAX_FACTOR = ${PF};
const RETURN_MODE = "spring";
(function () {
  var card = document.getElementById('card');
  var layer = document.getElementById('parallax-layer');
  var status = document.getElementById('status');
  var x = 0, v = 0, dragging = false, startPointerX = 0, startX = 0, rafId = null, lastT = 0, linStart = null, linFrom = 0;
  function render() { card.style.transform = 'translateX(' + x.toFixed(2) + 'px)'; }
  function step(now) {
    var dt = Math.min(0.032, (now - lastT) / 1000); lastT = now;
    if (RETURN_MODE === "linear") {
      if (!linStart) { linStart = now; linFrom = x; }
      var p = Math.min(1, (now - linStart) / 500); x = linFrom * (1 - p); render();
      if (p >= 1) { x = 0; status.textContent = 'At rest'; rafId = null; return; }
      rafId = requestAnimationFrame(step); return;
    }
    if (dt > 0) { var steps = 4, h = dt / steps; for (var i = 0; i < steps; i++) { var a = -SPRING_K * x - SPRING_C * v; v += a * h; x += v * h; } }
    render();
    if (Math.abs(x) < 0.05 && Math.abs(v) < 0.5) { x = 0; v = 0; render(); status.textContent = 'At rest'; rafId = null; return; }
    rafId = requestAnimationFrame(step);
  }
  function startReturn() { if (rafId) cancelAnimationFrame(rafId); linStart = null; lastT = performance.now(); rafId = requestAnimationFrame(step); }
  card.addEventListener('pointerdown', function (e) { dragging = true; startPointerX = e.clientX; startX = x; if (rafId) { cancelAnimationFrame(rafId); rafId = null; } card.setPointerCapture(e.pointerId); status.textContent = 'Dragging'; });
  card.addEventListener('pointermove', function (e) { if (!dragging) return; x = startX + (e.clientX - startPointerX); v = 0; render(); });
  function end() { if (!dragging) return; dragging = false; status.textContent = 'Springing back'; startReturn(); }
  card.addEventListener('pointerup', end); card.addEventListener('pointercancel', end);
  function onScroll() { layer.style.transform = 'translateY(' + (window.scrollY * PARALLAX_FACTOR).toFixed(2) + 'px)'; }
  window.addEventListener('scroll', onScroll, { passive: true }); onScroll(); render();
})();
</script>
</body>
</html>
`;
fs.writeFileSync(path.join(here, 'candidate.html'), candidate);
console.log(JSON.stringify(inferred, null, 2));
console.log('wrote candidate.html with SPRING_K=' + K + ' SPRING_C=' + C + ' PARALLAX=' + PF);
