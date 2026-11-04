// Raw showcase recordings: the real product UI rebuilding Vikunja,
// File Browser and Gitea through the local engine, plus the motion /
// physics slice (reference vs candidate spring drag). Slow, readable
// pace; unedited Playwright video output.
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const OUT = resolve('../.runs/ui-videos');
await mkdir(OUT, { recursive: true });
const server = spawn('npx', ['vite', 'preview', '--port', '4173', '--host', '127.0.0.1'],
  { shell: true, stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
await sleep(5000);

const browser = await chromium.launch({ headless: true });
async function record(name, fn) {
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: resolve(OUT, name), size: { width: 1280, height: 720 } },
  });
  const page = await ctx.newPage();
  try { await fn(page); } finally { await ctx.close(); }
  console.log('recorded', name);
}

async function rebuild(page, action, label) {
  await page.goto('http://127.0.0.1:4173/', { waitUntil: 'networkidle' });
  await sleep(2500);
  await page.click('.side-nav [data-action="experiments"]');
  await sleep(2500);
  await page.click(`[data-action="${action}"]`);
  console.log(label, 'started');
  await page.waitForFunction(
    () => document.body.innerText.includes('Public-ladder conformance:'),
    null, { timeout: 300000 });
  await sleep(6000);
  await page.screenshot({ path: resolve(OUT, `${label}.png`) });
  console.log(label, 'done');
}

await record('vikunja', p => rebuild(p, 'engine-run', 'vikunja'));
await record('filebrowser', p => rebuild(p, 'engine-run-fb', 'filebrowser'));
await record('gitea', p => rebuild(p, 'engine-run-gitea', 'gitea'));

await record('motion', async page => {
  for (const [file, label] of [['reference.html', 'reference'], ['candidate.html', 'candidate']]) {
    await page.goto('file:///' + resolve('../browser-slice-v2', file).replaceAll('\\', '/'));
    await sleep(3000);
    const card = await page.locator('#card').boundingBox();
    const cx = card.x + card.width / 2, cy = card.y + card.height / 2;
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    for (let i = 1; i <= 24; i++) { await page.mouse.move(cx + i * 9, cy); await sleep(45); }
    await sleep(600);
    await page.mouse.up();
    await sleep(4500); // watch the spring settle
    await page.screenshot({ path: resolve(OUT, `motion-${label}.png`) });
    console.log('motion', label, 'done');
  }
});

await browser.close();
server.kill();
console.log('ALL_RECORDINGS_DONE');
