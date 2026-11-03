// evaluate.mjs — held-out comparison: reference vs candidate (+ adversarial variants).
// Held-out drag is +140px (capture used +240px). Also a scroll sequence.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const require = createRequire(path.join(root, 'product', 'package.json'));
let chromium;
try { ({ chromium } = require('playwright')); } catch { ({ chromium } = require('@playwright/test')); }
const VIEWPORT = { width: 1280, height: 800 };
const HELD_OUT_DRAG = 140;

async function runTrial(browser, file, dragPx) {
  const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(file).href, { waitUntil: 'load' });
  await page.waitForTimeout(120);
  const layout = await page.evaluate(() => {
    const pick = (s) => { const e = document.querySelector(s); const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    return { card: pick('#card'), chip: pick('#hover-chip'), layer: pick('#parallax-layer') };
  });
  const title = await page.title();
  const status0 = await page.locator('#status').textContent();
  // scroll sequence
  const scrollSeq = await page.evaluate(async () => {
    const layer = document.getElementById('parallax-layer'); const out = [];
    for (const y of [0, 200, 400, 600]) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 90)); out.push({ scrollY: window.scrollY, layerRectY: +layer.getBoundingClientRect().y.toFixed(2) }); }
    window.scrollTo(0, 0); await new Promise((r) => setTimeout(r, 60)); return out;
  });
  // drag trajectory
  await page.evaluate(() => {
    const card = document.getElementById('card');
    window.__o = card.getBoundingClientRect().x; window.__s = []; window.__f = 0; window.__on = true;
    (function loop() { if (!window.__on) return; const r = card.getBoundingClientRect(); window.__s.push({ frame: window.__f++, tMs: performance.now(), x: +(r.x - window.__o).toFixed(3) }); requestAnimationFrame(loop); })();
  });
  const box = await page.locator('#card').boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy); await page.mouse.down();
  for (let i = 1; i <= 10; i++) { await page.mouse.move(cx + (dragPx * i) / 10, cy); await page.waitForTimeout(18); }
  const rel = await page.evaluate(() => performance.now());
  await page.mouse.up(); await page.waitForTimeout(1800);
  const traj = await page.evaluate((r) => { window.__on = false; return { rel: r, samples: window.__s }; }, rel);
  const statusFinal = await page.locator('#status').textContent();
  await page.screenshot({ path: path.join(here, `eval-${path.basename(file, '.html')}.png`) });
  await page.close();
  const ret = traj.samples.filter((s) => s.tMs >= traj.rel - 5);
  // re-zero time at max-x sample near release
  let pi = 0; ret.forEach((s, i) => { if (s.x > ret[pi].x) pi = i; });
  const aligned = ret.slice(pi).map((s) => ({ t: (s.tMs - ret[pi].tMs) / 1000, x: s.x }));
  const minX = Math.min(...aligned.map((s) => s.x));
  let settle = null;
  for (let i = 0; i < aligned.length; i++) if (aligned.slice(i).every((s) => Math.abs(s.x) < 2)) { settle = aligned[i].t; break; }
  return { layout, title, status0, statusFinal, scrollSeq, aligned, minX, overshoot: minX < -2, settlingS: settle, finalX: aligned.at(-1)?.x };
}
function trajRmse(a, b) {
  const tMax = Math.min(a.at(-1).t, b.at(-1).t); let se = 0, n = 0;
  for (const s of a) { if (s.t > tMax) break; let best = b[0], bd = 1e9; for (const p of b) { const d = Math.abs(p.t - s.t); if (d < bd) { bd = d; best = p; } } se += (best.x - s.x) ** 2; n++; }
  return Math.sqrt(se / Math.max(1, n));
}
async function main() {
  const candHtml = fs.readFileSync(path.join(here, 'candidate.html'), 'utf8');
  const mK = candHtml.match(/const SPRING_K = ([0-9.]+)/), mC = candHtml.match(/const SPRING_C = ([0-9.]+)/);
  const K = parseFloat(mK[1]), C = parseFloat(mC[1]);
  const noOver = candHtml.replace(/const SPRING_C = [0-9.]+/, `const SPRING_C = ${(2 * Math.sqrt(K) * 2.5).toFixed(2)}`);
  const wrongEase = candHtml.replace('const RETURN_MODE = "spring"', 'const RETURN_MODE = "linear"');
  fs.writeFileSync(path.join(here, '_variant-no-overshoot.html'), noOver);
  fs.writeFileSync(path.join(here, '_variant-wrong-easing.html'), wrongEase);

  const browser = await chromium.launch({ headless: true });
  const ref = await runTrial(browser, path.join(here, 'reference.html'), HELD_OUT_DRAG);
  const cand = await runTrial(browser, path.join(here, 'candidate.html'), HELD_OUT_DRAG);
  const vNo = await runTrial(browser, path.join(here, '_variant-no-overshoot.html'), HELD_OUT_DRAG);
  const vEase = await runTrial(browser, path.join(here, '_variant-wrong-easing.html'), HELD_OUT_DRAG);
  await browser.close();

  const rmseCand = trajRmse(ref.aligned, cand.aligned);
  const rmseNo = trajRmse(ref.aligned, vNo.aligned);
  const rmseEase = trajRmse(ref.aligned, vEase.aligned);
  const geomDiff = Math.max(Math.abs(ref.layout.card.width - cand.layout.card.width), Math.abs(ref.layout.card.height - cand.layout.card.height), Math.abs(ref.layout.card.x - cand.layout.card.x), Math.abs(ref.layout.card.y - cand.layout.card.y));
  const parallaxErr = Math.max(...ref.scrollSeq.map((r, i) => Math.abs(r.layerRectY - cand.scrollSeq[i].layerRectY)));
  // Detection rule: RMSE > max(8px, 2x candidate RMSE) OR overshoot mismatch
  const thresh = Math.max(8, rmseCand * 2);
  const verdict = {
    heldOutDragPx: HELD_OUT_DRAG, captureDragPx: 240,
    functional: { refFinalStatus: ref.statusFinal, candFinalStatus: cand.statusFinal, refFinalX: ref.finalX, candFinalX: cand.finalX, match: ref.statusFinal === cand.statusFinal && Math.abs(cand.finalX) < 2 },
    layout: { maxCardBoxDiffPx: +geomDiff.toFixed(2), tolerancePx: 4, pass: geomDiff <= 4 },
    trajectory: { rmseCandidatePx: +rmseCand.toFixed(3), settlingRefS: ref.settlingS, settlingCandS: cand.settlingS, settlingDiffS: (ref.settlingS != null && cand.settlingS != null) ? +Math.abs(ref.settlingS - cand.settlingS).toFixed(3) : null },
    overshoot: { refMinX: +ref.minX.toFixed(2), candMinX: +cand.minX.toFixed(2), refPresent: ref.overshoot, candPresent: cand.overshoot, match: ref.overshoot === cand.overshoot },
    parallax: { maxLayerRectDiffPx: +parallaxErr.toFixed(2), refSeq: ref.scrollSeq, candSeq: cand.scrollSeq, pass: parallaxErr <= 6 },
    adversarial: {
      thresholdRmsePx: +thresh.toFixed(3),
      noOvershootVariant: { rmsePx: +rmseNo.toFixed(3), overshootPresent: vNo.overshoot, detectedDifferent: rmseNo > thresh || vNo.overshoot !== ref.overshoot },
      wrongEasingVariant: { rmsePx: +rmseEase.toFixed(3), overshootPresent: vEase.overshoot, detectedDifferent: rmseEase > thresh || vEase.overshoot !== ref.overshoot },
    },
  };
  verdict.pass = verdict.functional.match && verdict.layout.pass && verdict.parallax.pass && verdict.overshoot.match && rmseCand <= 12 && verdict.adversarial.noOvershootVariant.detectedDifferent && verdict.adversarial.wrongEasingVariant.detectedDifferent;
  fs.writeFileSync(path.join(here, 'verdict.json'), JSON.stringify(verdict, null, 2));
  console.log(JSON.stringify(verdict, null, 2));
}
main().catch((e) => { console.error(e); process.exit(1); });
