// fit.mjs — infer parameters FROM observations.json ONLY and generate candidate.html.
// This file never opens the reference page: its only input path is observations.json
// (grep this file — there is no other readFileSync target).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const obs = JSON.parse(fs.readFileSync(path.join(here, 'observations.json'), 'utf8'));

// ---------- Spring fit: grid search (k, c) on the post-release return ----------
const samples = obs.trajectory.samples;
const relT = obs.trajectory.releaseMarkMs;
let startIdx = samples.findIndex((s) => s.tMs >= relT - 5);
if (startIdx < 0) startIdx = 0;
let peakIdx = startIdx;
for (let i = startIdx; i < Math.min(samples.length, startIdx + 10); i++)
  if (samples[i].x > samples[peakIdx].x) peakIdx = i;
const ret = samples.slice(peakIdx).map((s) => ({ t: (s.tMs - samples[peakIdx].tMs) / 1000, x: s.x }));
const x0 = ret[0].x;
const v0 = ret.length > 1 ? (ret[1].x - ret[0].x) / Math.max(1e-6, ret[1].t - ret[0].t) : 0;

function simulate(k, c, tMax) {
  const dt = 0.0005; let x = x0, v = v0; const out = [{ t: 0, x }];
  const steps = Math.ceil(tMax / dt);
  for (let i = 1; i <= steps; i++) { const a = -k * x - c * v; v += a * dt; x += v * dt; if (i % 10 === 0) out.push({ t: i * dt, x }); }
  return out;
}
function rmseFor(k, c) {
  const sim = simulate(k, c, ret.at(-1).t);
  let se = 0;
  for (const s of ret) {
    let best = sim[0], bd = Infinity;
    for (const p of sim) { const d = Math.abs(p.t - s.t); if (d < bd) { bd = d; best = p; } }
    se += (best.x - s.x) ** 2;
  }
  return Math.sqrt(se / ret.length);
}
let best = { k: 0, c: 0, rmse: Infinity };
for (let k = 60; k <= 400; k += 10)
  for (let c = 2; c <= 40; c += 1) { const r = rmseFor(k, c); if (r < best.rmse) best = { k, c, rmse: r }; }
for (let k = Math.max(20, best.k - 12); k <= best.k + 12; k += 2)
  for (let c = Math.max(0.5, best.c - 2); c <= best.c + 2; c += 0.25) { const r = rmseFor(k, c); if (r < best.rmse) best = { k, c, rmse: r }; }

// ---------- Parallax fit: least squares rectY = a + factor * scrollY ----------
const pf = obs.parallaxFit;
const n = pf.length, mx = pf.reduce((s, p) => s + p.scrollY, 0) / n, my = pf.reduce((s, p) => s + p.layerRectY, 0) / n;
let num = 0, den = 0;
for (const p of pf) { num += (p.scrollY - mx) * (p.layerRectY - my); den += (p.scrollY - mx) ** 2; }
const rectSlope = den ? num / den : 0; // rectY = top - scrollY + factor*scrollY  =>  slope = factor - 1
const parallaxFactor = rectSlope + 1;
const parallaxIntercept = my - rectSlope * mx;

// ---------- Layout / filter facts taken from observations ----------
const boxOf = (sel) => obs.layout.find((l) => l.selector === sel);
const headerH = Math.round(boxOf('header').box.height);
const layerH = Math.round(boxOf('#parallax-layer').box.height);
const tasks = obs.domSummary.tasks;
const buttons = obs.domSummary.buttons;

const inferred = {
  spring: { stiffness: best.k, damping: best.c, fitRmsePx: +best.rmse.toFixed(3), releaseX: +x0.toFixed(2), releaseV: +v0.toFixed(1) },
  parallax: { factor: +parallaxFactor.toFixed(4), interceptRectY: +parallaxIntercept.toFixed(2), fromScrolls: obs.fitScrolls },
  filterFit: obs.filterFit,
  headerHeightPx: headerH, layerHeightPx: layerH,
  cardBorderRadius: boxOf('#card').styles.borderRadius,
  sourceNote: 'All numbers above derive only from observations.json (capture of the reference). No reference source was read.',
};
fs.writeFileSync(path.join(here, 'inferred.json'), JSON.stringify(inferred, null, 2));

// ---------- Generate the independent candidate from fitted values ----------
const taskCards = tasks.map((t) => {
  const isCard = t.id === 'card';
  const title = obs.domSummary.headings[tasks.indexOf(t) + 1] || t.id;
  return `    <article class="task" id="${t.id}" data-cat="${t.cat}"><h2>${title}</h2><p>${isCard ? 'Drag me sideways, then let go.' : 'Task on the Flowboard.'}</p><span class="tag${t.cat === 'personal' ? ' personal' : ''}">${t.cat}</span></article>`;
}).join('\n');
const btnHtml = buttons.map((b) =>
  `    <button id="${b.id}" class="filter-btn${b.filter === 'all' ? ' active' : ''}" data-filter="${b.filter}">${b.text}</button>`).join('\n');

const candidate = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Flowboard — Task Board</title>
<style>
  * { box-sizing: border-box; margin: 0; }
  body { font-family: Segoe UI, Arial, sans-serif; background: #f4f5fb; color: #1c2130; }
  header { position: relative; height: ${headerH}px; overflow: hidden; background: #232946; color: #fff; }
  #parallax-layer { position: absolute; left: 0; top: ${Math.round(parallaxIntercept)}px; width: 100%; height: ${layerH}px;
    background: linear-gradient(160deg, #6c63ff, #232946 70%); will-change: transform; }
  header .inner { position: relative; padding: 64px 40px; }
  header h1 { font-size: 34px; }
  header p { opacity: .85; margin-top: 8px; }
  main { padding: 28px 40px 40px; max-width: 1100px; margin: 0 auto; }
  .toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 18px; flex-wrap: wrap; }
  .filter-btn { border: 1px solid #c9cde0; background: #fff; padding: 8px 16px; border-radius: 999px;
    cursor: pointer; font-size: 14px; transition: background-color .25s ease, transform .25s ease; }
  .filter-btn:hover { transform: translateY(-1px); }
  .filter-btn.active { background: #6c63ff; color: #fff; border-color: #6c63ff; }
  #status { margin-left: auto; font-size: 14px; color: #555b73; }
  .board { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .task { background: #fff; border: 1px solid #e2e5f1; border-radius: ${inferred.cardBorderRadius}; padding: 18px; }
  .task h2 { font-size: 17px; margin-bottom: 6px; }
  .task p { font-size: 14px; color: #555b73; }
  .tag { display: inline-block; margin-top: 10px; font-size: 12px; padding: 3px 10px; border-radius: 999px; background: #eceaff; color: #4a43b8; }
  .tag.personal { background: #e6f7ee; color: #1d7a4c; }
  #card { cursor: grab; touch-action: none; user-select: none; border: 2px solid #6c63ff; }
  #card:active { cursor: grabbing; }
  .spacer { height: 900px; }
  footer { padding: 30px 40px; color: #555b73; font-size: 13px; }
  #hover-chip { display: inline-block; margin-top: 14px; background: #ffb703; color: #3a2c00;
    padding: 8px 14px; border-radius: 999px; font-size: 13px; cursor: pointer;
    transition: transform .3s cubic-bezier(.34,1.56,.64,1); }
  #hover-chip:hover { transform: scale(1.12); }
</style>
</head>
<body>
<header>
  <div id="parallax-layer" aria-hidden="true"></div>
  <div class="inner">
    <h1>Flowboard</h1>
    <p>Your week at a glance. Drag the launch card — it springs home.</p>
    <span id="hover-chip">Hover me</span>
  </div>
</header>
<main>
  <div class="toolbar" role="toolbar" aria-label="Filter tasks">
${btnHtml}
    <span id="status" role="status">At rest</span>
  </div>
  <section class="board" aria-label="Task board">
${taskCards}
  </section>
  <div class="spacer" aria-hidden="true"></div>
</main>
<footer>Flowboard demo — scroll to see the parallax header.</footer>
<script>
  var PARALLAX_FACTOR = ${parallaxFactor.toFixed(4)};
  var layerEl = document.getElementById('parallax-layer');
  function applyScroll() { layerEl.style.transform = 'translateY(' + (window.scrollY * PARALLAX_FACTOR) + 'px)'; }
  window.addEventListener('scroll', applyScroll, { passive: true }); applyScroll();

  document.querySelectorAll('.filter-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.filter-btn').forEach(function (b) { b.classList.toggle('active', b === btn); });
      var f = btn.dataset.filter;
      document.querySelectorAll('.task').forEach(function (t) {
        t.style.display = (f === 'all' || t.dataset.cat === f) ? '' : 'none';
      });
    });
  });

  var SPRING_K = ${best.k};
  var SPRING_C = ${best.c};
  var cardEl = document.getElementById('card');
  var statusEl = document.getElementById('status');
  var px = 0, pv = 0, isDown = false, downX = 0, downCardX = 0, handle = null, prevT = 0;
  function step(now) {
    var dt = Math.min(0.032, (now - prevT) / 1000 || 0.016); prevT = now;
    pv += (-SPRING_K * px - SPRING_C * pv) * dt; px += pv * dt;
    cardEl.style.transform = 'translateX(' + px + 'px)';
    if (Math.abs(px) < 0.05 && Math.abs(pv) < 1) {
      px = 0; pv = 0; cardEl.style.transform = 'translateX(0px)';
      statusEl.textContent = 'At rest'; handle = null; return;
    }
    handle = requestAnimationFrame(step);
  }
  cardEl.addEventListener('pointerdown', function (e) {
    isDown = true; downX = e.clientX; downCardX = px;
    if (handle) cancelAnimationFrame(handle); handle = null;
    cardEl.setPointerCapture(e.pointerId); statusEl.textContent = 'Dragging\\u2026';
  });
  cardEl.addEventListener('pointermove', function (e) {
    if (!isDown) return;
    px = downCardX + (e.clientX - downX); pv = 0;
    cardEl.style.transform = 'translateX(' + px + 'px)';
  });
  cardEl.addEventListener('pointerup', function () {
    if (!isDown) return; isDown = false;
    statusEl.textContent = 'Settling\\u2026'; prevT = performance.now();
    handle = requestAnimationFrame(step);
  });
</script>
</body>
</html>
`;
fs.writeFileSync(path.join(here, 'candidate.html'), candidate);
console.log(`fit: k=${best.k} c=${best.c} fitRMSE=${best.rmse.toFixed(3)}px parallax=${parallaxFactor.toFixed(4)} intercept=${parallaxIntercept.toFixed(1)} -> candidate.html written`);
