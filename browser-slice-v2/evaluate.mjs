// evaluate.mjs — HELD-OUT evaluation: interactions never used for fitting.
//   held-out drag 150px (fit used 260), scrolls [0,150,450,750] (fit used [0,300]),
//   filter 'personal' (fit used 'work'). Plus adversarial variants that MUST differ.
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
const HELDOUT_DRAG = 150;
const HELDOUT_SCROLLS = [0, 150, 450, 750];
const HELDOUT_FILTER = 'personal';
const RMSE_PASS_PX = 8, ADVERSARIAL_MIN_RMSE_PX = 8, LAYOUT_TOL_PX = 4, PARALLAX_TOL_PX = 6;

async function dragAndSample(page, dragPx) {
  await page.evaluate(() => {
    const card = document.getElementById('card');
    window.__samples = []; window.__sampling = true;
    function loop(t) {
      if (!window.__sampling) return;
      const m = new DOMMatrixReadOnly(getComputedStyle(card).transform);
      window.__samples.push({ tMs: t, x: m.e });
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  });
  const box = await page.locator('#card').boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy); await page.mouse.down();
  for (let i = 1; i <= 20; i++) { await page.mouse.move(cx + (dragPx * i) / 20, cy); await page.waitForTimeout(16); }
  await page.waitForTimeout(120);
  const releaseMarkMs = await page.evaluate(() => performance.now());
  await page.mouse.up();
  try { await page.waitForFunction(() => document.getElementById('status').textContent === 'At rest', null, { timeout: 4000 }); } catch {}
  await page.waitForTimeout(150);
  return page.evaluate((rel) => {
    window.__sampling = false;
    const s = window.__samples;
    let pi = s.findIndex((p) => p.tMs >= rel - 5); if (pi < 0) pi = 0;
    for (let i = pi; i < Math.min(s.length, pi + 10); i++) if (s[i].x > s[pi].x) pi = i;
    const t0 = s[pi] ? s[pi].tMs : rel;
    return { post: s.slice(pi).map((p) => ({ t: (p.tMs - t0) / 1000, x: p.x })),
      finalStatus: document.getElementById('status').textContent };
  }, releaseMarkMs);
}
function interp(post, t) {
  if (!post.length) return 0;
  if (t <= post[0].t) return post[0].x;
  for (let i = 1; i < post.length; i++) {
    if (post[i].t >= t) { const a = post[i - 1], b = post[i];
      return a.x + (b.x - a.x) * ((t - a.t) / Math.max(1e-9, b.t - a.t)); }
  }
  return post.at(-1).x;
}
function compareTraj(ref, cand) {
  const dur = Math.min(ref.at(-1).t, cand.at(-1).t);
  let se = 0, cnt = 0;
  for (let t = 0; t <= dur; t += 0.008) { se += (interp(ref, t) - interp(cand, t)) ** 2; cnt++; }
  const settling = (post) => { let s = 0; for (const p of post) if (Math.abs(p.x) > 2) s = p.t; return s; };
  return { rmsePx: +(Math.sqrt(se / Math.max(1, cnt))).toFixed(3),
    refMinX: +Math.min(...ref.map((p) => p.x)).toFixed(2), candMinX: +Math.min(...cand.map((p) => p.x)).toFixed(2),
    settlingRefS: +settling(ref).toFixed(3), settlingCandS: +settling(cand).toFixed(3) };
}
async function scrollSeq(page, ys) {
  return page.evaluate(async (list) => {
    const layer = document.getElementById('parallax-layer'); const out = [];
    for (const y of list) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 130));
      out.push({ scrollY: window.scrollY, layerRectY: +layer.getBoundingClientRect().y.toFixed(2) }); }
    window.scrollTo(0, 0); await new Promise((r) => setTimeout(r, 100)); return out;
  }, ys);
}
async function runPage(browser, file) {
  const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(file).href, { waitUntil: 'load' });
  await page.waitForTimeout(200);
  const layout = await page.evaluate(() => {
    const pick = (sel) => { const el = document.querySelector(sel); const r = el.getBoundingClientRect();
      return { sel, x: r.x, y: r.y, w: r.width, h: r.height }; };
    return [pick('#card'), pick('#task-1'), pick('header'), pick('#filter-all')];
  });
  const scrolls = await scrollSeq(page, HELDOUT_SCROLLS);
  await page.click('#filter-' + HELDOUT_FILTER); await page.waitForTimeout(120);
  const filter = await page.evaluate(() => ({
    visible: [...document.querySelectorAll('.task')].filter((t) => getComputedStyle(t).display !== 'none').map((t) => t.id),
    active: document.querySelector('.filter-btn.active')?.id }));
  await page.click('#filter-all'); await page.waitForTimeout(120);
  const traj = await dragAndSample(page, HELDOUT_DRAG);
  return { page, layout, scrolls, filter, traj };
}

async function main() {
  const candSrc = fs.readFileSync(path.join(here, 'candidate.html'), 'utf8');
  // Adversarial variants: (a) wrong spring — heavily overdamped, no overshoot;
  // (b) wrong parallax — factor collapsed toward 0. Both derived from candidate.
  const wrongSpring = candSrc.replace(/var SPRING_K = [\d.]+;/, 'var SPRING_K = 120;')
                             .replace(/var SPRING_C = [\d.]+;/, 'var SPRING_C = 42;');
  const wrongParallax = candSrc.replace(/var PARALLAX_FACTOR = [\d.]+;/, 'var PARALLAX_FACTOR = 0.02;');
  if (wrongSpring === candSrc || wrongParallax === candSrc) throw new Error('variant generation failed');
  fs.writeFileSync(path.join(here, '_variant-wrong-spring.html'), wrongSpring);
  fs.writeFileSync(path.join(here, '_variant-wrong-parallax.html'), wrongParallax);

  const browser = await chromium.launch({ headless: true });
  const ref = await runPage(browser, path.join(here, 'reference.html'));
  await ref.page.screenshot({ path: path.join(here, 'eval-reference.png') });
  const cand = await runPage(browser, path.join(here, 'candidate.html'));
  await cand.page.screenshot({ path: path.join(here, 'eval-candidate.png') });
  const vSpring = await runPage(browser, path.join(here, '_variant-wrong-spring.html'));
  const vPar = await runPage(browser, path.join(here, '_variant-wrong-parallax.html'));
  await browser.close();

  const trajCmp = compareTraj(ref.traj.post, cand.traj.post);
  const trajSpring = compareTraj(ref.traj.post, vSpring.traj.post);
  const maxLayoutDiff = Math.max(...ref.layout.map((r, i) => {
    const c = cand.layout[i];
    return Math.max(Math.abs(r.x - c.x), Math.abs(r.y - c.y), Math.abs(r.w - c.w), Math.abs(r.h - c.h));
  }));
  const parDiffs = ref.scrolls.map((r, i) => Math.abs(r.layerRectY - cand.scrolls[i].layerRectY));
  const parDiffsAdv = ref.scrolls.map((r, i) => Math.abs(r.layerRectY - vPar.scrolls[i].layerRectY));
  const maxParDiff = Math.max(...parDiffs), maxParDiffAdv = Math.max(...parDiffsAdv);

  const functionalMatch = ref.traj.finalStatus === cand.traj.finalStatus
    && JSON.stringify(ref.filter.visible) === JSON.stringify(cand.filter.visible)
    && ref.filter.active === cand.filter.active;
  const overshootMatch = (trajCmp.refMinX < -1) === (trajCmp.candMinX < -1);
  const springDetected = trajSpring.rmsePx > ADVERSARIAL_MIN_RMSE_PX;
  const parallaxDetected = maxParDiffAdv > PARALLAX_TOL_PX * 3;

  const verdict = {
    heldOut: { dragPx: HELDOUT_DRAG, scrolls: HELDOUT_SCROLLS, filter: HELDOUT_FILTER },
    fitUsed: { dragPx: 260, scrolls: [0, 300], filter: 'work' },
    functional: { refFinalStatus: ref.traj.finalStatus, candFinalStatus: cand.traj.finalStatus,
      refVisiblePersonal: ref.filter.visible, candVisiblePersonal: cand.filter.visible,
      refActive: ref.filter.active, candActive: cand.filter.active, match: functionalMatch },
    layout: { maxBoxDiffPx: +maxLayoutDiff.toFixed(2), tolerancePx: LAYOUT_TOL_PX, pass: maxLayoutDiff <= LAYOUT_TOL_PX },
    trajectory: { rmseCandidatePx: trajCmp.rmsePx, thresholdPx: RMSE_PASS_PX,
      settlingRefS: trajCmp.settlingRefS, settlingCandS: trajCmp.settlingCandS,
      settlingDiffS: +Math.abs(trajCmp.settlingRefS - trajCmp.settlingCandS).toFixed(3),
      pass: trajCmp.rmsePx <= RMSE_PASS_PX },
    overshoot: { refMinX: trajCmp.refMinX, candMinX: trajCmp.candMinX,
      refPresent: trajCmp.refMinX < -1, candPresent: trajCmp.candMinX < -1, match: overshootMatch },
    parallax: { maxLayerRectDiffPx: +maxParDiff.toFixed(2), tolerancePx: PARALLAX_TOL_PX,
      refSeq: ref.scrolls, candSeq: cand.scrolls, pass: maxParDiff <= PARALLAX_TOL_PX },
    adversarial: { thresholdRmsePx: ADVERSARIAL_MIN_RMSE_PX,
      wrongSpring: { rmsePx: trajSpring.rmsePx, candMinX: trajSpring.candMinX, detectedDifferent: springDetected },
      wrongParallax: { maxLayerRectDiffPx: +maxParDiffAdv.toFixed(2), detectedDifferent: parallaxDetected },
      pass: springDetected && parallaxDetected },
  };
  verdict.pass = verdict.layout.pass && verdict.trajectory.pass && verdict.parallax.pass
    && verdict.adversarial.pass && functionalMatch && overshootMatch;
  fs.writeFileSync(path.join(here, 'verdict.json'), JSON.stringify(verdict, null, 2));
  console.log(JSON.stringify(verdict, null, 2));
  console.log(verdict.pass ? 'VERDICT: PASS' : 'VERDICT: FAIL');
}
main().catch((e) => { console.error(e); process.exit(1); });
