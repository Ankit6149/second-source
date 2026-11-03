// capture.mjs — load reference.html in Chromium, record DOM/a11y/layout/styles,
// screenshots, and a frame-indexed drag trajectory. Saves observations.json.
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const require = createRequire(path.join(root, 'product', 'package.json'));
let chromium;
try { ({ chromium } = require('playwright')); }
catch { ({ chromium } = require('@playwright/test')); }

const VIEWPORT = { width: 1280, height: 800 };
const DRAG_PX = 240;
const sha256 = (p) => createHash('sha256').update(fs.readFileSync(p)).digest('hex');

async function main() {
  const refPath = path.join(here, 'reference.html');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(refPath).href, { waitUntil: 'load' });
  await page.waitForTimeout(150);

  const domSummary = await page.evaluate(() => ({
    title: document.title, lang: document.documentElement.lang,
    elementCount: document.querySelectorAll('*').length,
    ids: [...document.querySelectorAll('[id]')].map((e) => e.id),
    headings: [...document.querySelectorAll('h1,h2')].map((e) => e.textContent.trim()),
  }));
  const a11y = await page.evaluate(() => {
    const implicit = { BUTTON: 'button', A: 'link', H1: 'heading', H2: 'heading', MAIN: 'main', HEADER: 'banner', FOOTER: 'contentinfo', SECTION: 'region' };
    return [...document.querySelectorAll('body *')].slice(0, 60).map((e) => ({
      tag: e.tagName.toLowerCase(), id: e.id || null,
      role: e.getAttribute('role') || implicit[e.tagName] || null,
      ariaLabel: e.getAttribute('aria-label'), text: (e.textContent || '').trim().slice(0, 40),
    })).filter((r) => r.role || r.id);
  });

  async function boxesAndStyles() {
    return page.evaluate(() => {
      const pick = (sel) => {
        const el = document.querySelector(sel); if (!el) return null;
        const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
        return { selector: sel, box: { x: r.x, y: r.y, width: r.width, height: r.height },
          styles: { transform: cs.transform, transitionProperty: cs.transitionProperty, transitionDuration: cs.transitionDuration, transitionTimingFunction: cs.transitionTimingFunction, backgroundColor: cs.backgroundColor, borderRadius: cs.borderRadius, cursor: cs.cursor, position: cs.position } };
      };
      return [pick('#card'), pick('#hover-chip'), pick('#parallax-layer'), pick('h1'), pick('.stage')];
    });
  }
  const layoutBefore = await boxesAndStyles();

  // Hover computed-style check (transition target)
  const chip = page.locator('#hover-chip');
  const hoverBefore = await chip.evaluate((e) => getComputedStyle(e).transform);
  await chip.hover(); await page.waitForTimeout(450);
  const hoverAfter = await chip.evaluate((e) => { const cs = getComputedStyle(e); return { transform: cs.transform, transitionTimingFunction: cs.transitionTimingFunction, transitionDuration: cs.transitionDuration }; });
  await page.mouse.move(10, 10);

  // Parallax at scroll 0 vs 400
  const parallax = await page.evaluate(async () => {
    const layer = document.getElementById('parallax-layer');
    const read = () => ({ scrollY: window.scrollY, transform: getComputedStyle(layer).transform, rectY: layer.getBoundingClientRect().y });
    const a = read();
    window.scrollTo(0, 400); await new Promise((r) => setTimeout(r, 120));
    const b = read(); window.scrollTo(0, 0); await new Promise((r) => setTimeout(r, 80));
    return { at0: a, at400: b, factorObserved: (b.rectY - a.rectY) / 400 };
  });

  await page.screenshot({ path: path.join(here, 'reference-viewport.png') });
  await page.screenshot({ path: path.join(here, 'reference-full.png'), fullPage: true });

  // --- Frame-indexed drag trajectory ---
  await page.evaluate(() => {
    const card = document.getElementById('card');
    window.__originX = card.getBoundingClientRect().x;
    window.__samples = []; window.__frame = 0; window.__sampling = true;
    function loop() {
      if (!window.__sampling) return;
      const r = card.getBoundingClientRect();
      window.__samples.push({ frame: window.__frame++, tMs: performance.now(), x: +(r.x - window.__originX).toFixed(3), transform: card.style.transform || getComputedStyle(card).transform });
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  });
  const cardBox = await page.locator('#card').boundingBox();
  const cx = cardBox.x + cardBox.width / 2, cy = cardBox.y + cardBox.height / 2;
  await page.mouse.move(cx, cy); await page.mouse.down();
  for (let i = 1; i <= 12; i++) { await page.mouse.move(cx + (DRAG_PX * i) / 12, cy); await page.waitForTimeout(20); }
  const releaseMark = await page.evaluate(() => performance.now());
  await page.mouse.up();
  await page.waitForTimeout(1800);
  const trajectory = await page.evaluate((rel) => {
    window.__sampling = false;
    return { releaseMark: rel, samples: window.__samples };
  }, releaseMark);
  // Tag phases relative to releaseMark (approx; release sample = first frame after mark)
  const samples = trajectory.samples.map((s) => ({ ...s, phase: s.tMs < trajectory.releaseMark - 5 ? 'drag' : 'return' }));

  const layoutAfter = await boxesAndStyles();
  const finalText = await page.locator('#status').textContent();
  await browser.close();

  const obs = {
    capturedAt: new Date().toISOString(), viewport: VIEWPORT, dragPx: DRAG_PX,
    sourceHashes: { 'reference.html': sha256(refPath), 'capture.mjs': sha256(path.join(here, 'capture.mjs')) },
    domSummary, accessibilityRoles: a11y, layoutBefore, layoutAfter,
    hover: { before: hoverBefore, after: hoverAfter },
    parallax, trajectory: { releaseMarkMs: trajectory.releaseMark, samples },
    finalStatusText: finalText,
    screenshots: ['reference-viewport.png', 'reference-full.png'],
  };
  fs.writeFileSync(path.join(here, 'observations.json'), JSON.stringify(obs, null, 2));
  const ret = samples.filter((s) => s.phase === 'return');
  console.log(JSON.stringify({ samples: samples.length, returnSamples: ret.length, minReturnX: Math.min(...ret.map((s) => s.x)), finalX: samples.at(-1).x, parallaxFactor: parallax.factorObserved, files: ['observations.json', 'reference-viewport.png', 'reference-full.png'] }, null, 2));
}
main().catch((e) => { console.error(e); process.exit(1); });
