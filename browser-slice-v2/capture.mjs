// capture.mjs — load reference.html in Chromium; record DOM/a11y/layout/styles,
// screenshots, frame-indexed drag trajectory, scroll + filter observations.
// FIT interactions here: drag 260px, scroll points [0,300], filter 'work'.
// Held-out interactions (different values) live only in evaluate.mjs.
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
const FIT_DRAG_PX = 260;
const FIT_SCROLLS = [0, 300];
const FIT_FILTER = 'work';

async function dragAndSample(page, dragPx) {
  await page.evaluate(() => {
    const card = document.getElementById('card');
    window.__originX = card.getBoundingClientRect().x;
    window.__samples = []; window.__sampling = true;
    const readX = () => {
      const m = new DOMMatrixReadOnly(getComputedStyle(card).transform);
      return m.e;
    };
    function loop(t) {
      if (!window.__sampling) return;
      window.__samples.push({ tMs: t, x: readX() });
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  });
  const box = await page.locator('#card').boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  const steps = 20;
  for (let i = 1; i <= steps; i++) { await page.mouse.move(cx + (dragPx * i) / steps, cy); await page.waitForTimeout(16); }
  await page.waitForTimeout(120);
  const releaseMarkMs = await page.evaluate(() => performance.now());
  await page.mouse.up();
  // wait until settled (status back to "At rest") or timeout
  try { await page.waitForFunction(() => document.getElementById('status').textContent === 'At rest', null, { timeout: 4000 }); }
  catch { /* keep whatever samples we have */ }
  await page.waitForTimeout(150);
  const data = await page.evaluate(() => {
    window.__sampling = false;
    return { samples: window.__samples, originX: window.__originX };
  });
  return { ...data, releaseMarkMs };
}

async function scrollSeq(page, scrolls) {
  return page.evaluate(async (ys) => {
    const layer = document.getElementById('parallax-layer');
    const out = [];
    for (const y of ys) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 130));
      out.push({ scrollY: window.scrollY, layerRectY: layer.getBoundingClientRect().y, transform: getComputedStyle(layer).transform });
    }
    window.scrollTo(0, 0);
    await new Promise((r) => setTimeout(r, 100));
    return out;
  }, scrolls);
}

async function visibleTasks(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll('.task')].filter((t) => t.offsetParent !== null || getComputedStyle(t).display !== 'none')
      .filter((t) => getComputedStyle(t).display !== 'none').map((t) => t.id));
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(path.join(here, 'reference.html')).href, { waitUntil: 'load' });
  await page.waitForTimeout(200);

  const domSummary = await page.evaluate(() => ({
    title: document.title, lang: document.documentElement.lang,
    elementCount: document.querySelectorAll('*').length,
    ids: [...document.querySelectorAll('[id]')].map((e) => e.id),
    headings: [...document.querySelectorAll('h1,h2')].map((e) => e.textContent.trim()),
    buttons: [...document.querySelectorAll('button')].map((b) => ({ id: b.id, text: b.textContent.trim(), filter: b.dataset.filter })),
    tasks: [...document.querySelectorAll('.task')].map((t) => ({ id: t.id, cat: t.dataset.cat })),
  }));
  const a11y = await page.evaluate(() => {
    const implicit = { BUTTON: 'button', H1: 'heading', H2: 'heading', MAIN: 'main', HEADER: 'banner', FOOTER: 'contentinfo', SECTION: 'region' };
    return [...document.querySelectorAll('body *')].map((e) => ({
      tag: e.tagName.toLowerCase(), id: e.id || null,
      role: e.getAttribute('role') || implicit[e.tagName] || null,
      ariaLabel: e.getAttribute('aria-label'), text: (e.textContent || '').trim().slice(0, 40),
    })).filter((r) => r.role || r.id);
  });

  const layout = await page.evaluate(() => {
    const pick = (sel) => {
      const el = document.querySelector(sel); if (!el) return null;
      const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      return { selector: sel, box: { x: r.x, y: r.y, width: r.width, height: r.height },
        styles: { backgroundColor: cs.backgroundColor, borderRadius: cs.borderRadius, cursor: cs.cursor,
          position: cs.position, fontSize: cs.fontSize, transform: cs.transform } };
    };
    return ['header', '#parallax-layer', '#card', '#task-1', '#task-3', '#filter-all', '#hover-chip', '#status', 'main', '.board']
      .map(pick).filter(Boolean);
  });

  // Hover transition target
  const chip = page.locator('#hover-chip');
  const hoverBefore = await chip.evaluate((e) => getComputedStyle(e).transform);
  await chip.hover(); await page.waitForTimeout(500);
  const hoverAfter = await chip.evaluate((e) => { const cs = getComputedStyle(e);
    return { transform: cs.transform, transitionDuration: cs.transitionDuration, transitionTimingFunction: cs.transitionTimingFunction }; });
  await page.mouse.move(5, 5); await page.waitForTimeout(350);

  const parallaxFit = await scrollSeq(page, FIT_SCROLLS);

  // Filter (fit choice: work)
  await page.click('#filter-' + FIT_FILTER);
  await page.waitForTimeout(120);
  const visibleAfterFitFilter = await visibleTasks(page);
  const activeAfterFitFilter = await page.evaluate(() => document.querySelector('.filter-btn.active')?.id);
  await page.click('#filter-all'); await page.waitForTimeout(120);
  const visibleAfterAll = await visibleTasks(page);

  await page.screenshot({ path: path.join(here, 'reference-viewport.png') });
  await page.screenshot({ path: path.join(here, 'reference-full.png'), fullPage: true });

  const traj = await dragAndSample(page, FIT_DRAG_PX);
  const finalStatus = await page.evaluate(() => document.getElementById('status').textContent);

  const obs = { viewport: VIEWPORT, fitDragPx: FIT_DRAG_PX, fitScrolls: FIT_SCROLLS, fitFilter: FIT_FILTER,
    domSummary, a11y, layout, hover: { before: hoverBefore, after: hoverAfter },
    parallaxFit, filterFit: { choice: FIT_FILTER, visible: visibleAfterFitFilter, activeButton: activeAfterFitFilter, visibleAfterAll },
    trajectory: { dragPx: FIT_DRAG_PX, originX: traj.originX, releaseMarkMs: traj.releaseMarkMs, samples: traj.samples },
    finalStatus };
  fs.writeFileSync(path.join(here, 'observations.json'), JSON.stringify(obs, null, 2));
  console.log(`capture: ${traj.samples.length} samples, drag=${FIT_DRAG_PX}px, parallaxFit=${JSON.stringify(parallaxFit.map(p=>p.layerRectY))}, visible(work)=${visibleAfterFitFilter.join(',')}, status=${finalStatus}`);
  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
