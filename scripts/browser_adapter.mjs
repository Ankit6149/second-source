// browser_adapter.mjs — generic Playwright/Chromium (CDP) observer.
// Usage: node scripts/browser_adapter.mjs <url> <plan.json> <out.json>
// Plan: {drag:{selector,px}, scrolls:[y], filterClick:selector,
//        hover:selector, focus:selector, keys:"text", form:{selector:value},
//        boxes:[selector], stateSelector:selector}
// Emits Evidence-style observations: DOM/a11y summary, layout boxes,
// computed styles, functional state, frame-indexed drag trajectory.
// No product-specific logic; selectors come from the plan.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const require = createRequire(path.join(root, 'product', 'package.json'));
let chromium;
try { ({ chromium } = require('playwright')); } catch { ({ chromium } = require('@playwright/test')); }

const [url, planPath, outPath] = process.argv.slice(2);
const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
const VIEWPORT = { width: 1280, height: 800 };

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: VIEWPORT });
await page.goto(url);
await page.waitForTimeout(300);

const dom = await page.evaluate(() => ({
  title: document.title,
  roles: [...document.querySelectorAll('[id]')].slice(0, 40).map(e => e.id),
  text: document.body.innerText.slice(0, 500),
}));
async function boxes() {
  const out = {};
  for (const sel of plan.boxes || []) {
    const b = await page.locator(sel).boundingBox().catch(() => null);
    if (b) out[sel] = [b.x, b.y, b.width, b.height];
  }
  return out;
}
const styles = {};
for (const sel of plan.boxes || []) {
  styles[sel] = await page.locator(sel).evaluate(e => {
    const s = getComputedStyle(e);
    return { transition: s.transition, transform: s.transform, display: s.display };
  }).catch(() => null);
}
// hover / focus / keyboard / form (state probes)
if (plan.hover) await page.locator(plan.hover).hover().catch(() => {});
if (plan.focus) await page.locator(plan.focus).focus().catch(() => {});
if (plan.form) for (const [sel, v] of Object.entries(plan.form)) await page.locator(sel).fill(v).catch(() => {});
if (plan.keys) await page.keyboard.type(plan.keys).catch(() => {});
// drag + trajectory
let trajectory = [];
if (plan.drag) {
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    window.__samples = []; window.__sampling = true;
    const read = () => new DOMMatrixReadOnly(getComputedStyle(el).transform).e;
    (function loop(t) { if (!window.__sampling) return; window.__samples.push({ tMs: t, x: read() }); requestAnimationFrame(loop); })(performance.now());
  }, plan.drag.selector);
  const box = await page.locator(plan.drag.selector).boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy); await page.mouse.down();
  for (let i = 1; i <= 20; i++) { await page.mouse.move(cx + plan.drag.px * i / 20, cy); await page.waitForTimeout(16); }
  await page.waitForTimeout(120);
  const rel = await page.evaluate(() => performance.now());
  await page.mouse.up();
  await page.waitForTimeout(1600);
  trajectory = await page.evaluate(() => { window.__sampling = false; return window.__samples; });
  trajectory = trajectory.map(s => ({ tMs: s.tMs - rel, x: s.x })).filter(s => s.tMs >= -50);
}
// scroll / parallax
const parallax = {};
for (const y of plan.scrolls || []) {
  await page.evaluate(v => window.scrollTo(0, v), y);
  await page.waitForTimeout(120);
  if (plan.parallaxSelector) {
    const b = await page.locator(plan.parallaxSelector).boundingBox().catch(() => null);
    if (b) parallax[y] = b.y;
  }
}
// filter / nav click last (functional state)
if (plan.filterClick) await page.locator(plan.filterClick).click().catch(() => {});
await page.waitForTimeout(200);
const state = plan.stateSelector
  ? await page.locator(plan.stateSelector).textContent().catch(() => null) : null;
const obs = { url, viewport: VIEWPORT, dom, styles, layout: await boxes(),
  functional: { state }, trajectory, parallax };
fs.writeFileSync(outPath, JSON.stringify(obs, null, 1));
await browser.close();
console.log('wrote', outPath, 'trajectory samples', trajectory.length);
