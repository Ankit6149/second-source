// Real Chromium, synthetic identity and the local NON_AI worker only. No provider traffic.
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, devices } from 'playwright';
import { createServer } from 'vite';

const token = 'a'.repeat(32) + '.' + 'b'.repeat(32) + '.' + 'c'.repeat(48);
const otherToken = 'x'.repeat(32) + '.' + 'y'.repeat(32) + '.' + 'z'.repeat(48);
const owner = 'a186fb18-72b4-4071-9794-e8746c3e4231';
const otherOwner = '194d8e1f-b8d2-4b59-a387-92698d47678c';
const sessionKey = 'sb-jpqcqqbzriizxhigvjki-auth-token';
const output = path.resolve('../.runs/browser-acceptance');
await mkdir(output, { recursive: true });
const backend = spawn(process.env.PYTHON || 'python', ['integration/local_backend.py'], { stdio: ['ignore', 'pipe', 'pipe'] });
let backendErrors = '';
backend.stderr.on('data', chunk => { backendErrors += String(chunk).slice(0, 4000); });
let server, browser;
try {
  const [chunk] = await Promise.race([
    once(backend.stdout, 'data'),
    once(backend, 'exit').then(() => { throw new Error(`Local backend exited: ${backendErrors}`); }),
    new Promise((_, reject) => setTimeout(() => reject(new Error('Local backend startup timed out')), 15000)),
  ]);
  const port = /^PORT=(\d+)/.exec(String(chunk))?.[1];
  assert.ok(port, 'local backend advertised its port');
  server = await createServer({ configFile: false, envFile: false, logLevel: 'error',
    define: {
      'import.meta.env.VITE_API_ORIGIN': JSON.stringify('https://backend.test'),
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify('https://jpqcqqbzriizxhigvjki.supabase.co'),
      'import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY': JSON.stringify('sb_publishable_' + 'x'.repeat(30)),
    },
    server: { host: '127.0.0.1', port: 0, strictPort: false },
  });
  await server.listen();
  const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
  browser = await chromium.launch({ headless: true, ...(process.env.SS_BROWSER_PATH ? { executablePath: process.env.SS_BROWSER_PATH } : {}) });
  let dispatches = 0;
  let firstRunId = '';
  let failNextRunRead = false;
  let rejectSession = false;
  let loseExecutionAck = true, lostAcknowledgements = 0;
  let holdReport = false, reportSeen, releaseReport;
  const reportRequested = new Promise(resolve => { reportSeen = resolve; });
  const reportMayFinish = new Promise(resolve => { releaseReport = resolve; });
  async function context(options = {}, identity = null) {
    const ctx = await browser.newContext({ ...options, acceptDownloads: true, reducedMotion: 'reduce' });
    // Block every external request. Route the synthetic API origin only to the local test server.
    await ctx.route('**/*', async route => {
      const req = route.request(); const url = new URL(req.url());
      if (url.origin === origin) return route.continue();
      if (url.origin !== 'https://backend.test') return route.abort('blockedbyclient');
      console.log('Local API:', req.method(), url.pathname);
      if (holdReport && req.method() === 'GET' && url.pathname.endsWith('/report')) {
        reportSeen(); await reportMayFinish;
      }
      const cors = { 'access-control-allow-origin': origin, 'access-control-allow-methods': 'GET,POST,OPTIONS', 'access-control-allow-headers': 'authorization,content-type,idempotency-key' };
      if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors });
      if (rejectSession && url.pathname === '/v1/session') return route.fulfill({ status: 401, headers: cors, body: '{}' });
      if (req.method() === 'POST' && url.pathname.endsWith('/execute')) { dispatches++; firstRunId ||= url.pathname.split('/')[3]; }
      if (failNextRunRead && req.method() === 'GET' && /^\/v1\/runs\/[^/]+$/.test(url.pathname)) {
        failNextRunRead = false; return route.fulfill({ status: 429, headers: cors, body: '{}' });
      }
      const headers = { ...req.headers() }; delete headers.host; delete headers.origin; delete headers['content-length'];
      const response = await fetch(`http://127.0.0.1:${port}${url.pathname}${url.search}`, {
        method: req.method(), headers, body: req.postDataBuffer() || undefined,
      });
      if (loseExecutionAck && req.method() === 'POST' && url.pathname.endsWith('/execute')) {
        loseExecutionAck = false; lostAcknowledgements++; await response.arrayBuffer(); return route.abort('failed');
      }
      const responseHeaders = Object.fromEntries(response.headers); delete responseHeaders['content-encoding'];
      console.log('Local API status:', response.status);
      return route.fulfill({ status: response.status, headers: { ...responseHeaders, ...cors }, body: Buffer.from(await response.arrayBuffer()) });
    });
    if (identity) await ctx.addInitScript(({ key, userId, accessToken }) => {
      sessionStorage.setItem(key, JSON.stringify({ access_token: accessToken, refresh_token: 'synthetic-refresh',
        expires_at: Math.floor(Date.now() / 1000) + 3600, expires_in: 3600, token_type: 'bearer', user: { id: userId } }));
    }, { key: sessionKey, ...identity });
    return ctx;
  }
  const desktop = await context({ viewport: { width: 1440, height: 900 } });
  const page = await desktop.newPage();
  await page.goto(origin); await page.getByRole('heading', { name: /software, understood/i }).waitFor();
  await page.screenshot({ path: path.join(output, 'desktop-home.png') });
  assert.equal(await page.locator('#scrollArea').evaluate((el) => el.contains(document.querySelector('#composer'))), false);
  await page.keyboard.press('Tab'); assert.equal(await page.evaluate(() => document.activeElement?.className), 'skip-link');
  await page.getByRole('button', { name: 'Close navigation' }).click();
  assert.equal(await page.locator('#sidebar').evaluate(el => el.inert), true);
  assert.equal(await page.getByRole('button', { name: 'Toggle navigation' }).getAttribute('aria-expanded'), 'false');
  await page.getByRole('button', { name: 'Toggle navigation' }).click();
  await page.locator('[data-action="account"]').click();
  assert.match(await page.locator('dialog').innerText(), /sign in to save/i);
  await page.keyboard.press('Escape'); assert.equal(await page.locator('dialog').isVisible(), false);
  const composer = page.locator('#promptInput');
  await composer.fill('A long investigation note'); await composer.press('Shift+Enter'); await composer.type('second line');
  assert.match(await composer.inputValue(), /\nsecond line/); await composer.press('Enter');
  assert.match(await page.locator('#content').innerText(), /A long investigation note/);
  await desktop.close();

  const mobile = await context({ ...devices['iPhone 13'], defaultBrowserType: undefined });
  const phone = await mobile.newPage(); await phone.goto(origin);
  await phone.getByRole('heading', { name: /software, understood/i }).waitFor();
  await phone.screenshot({ path: path.join(output, 'mobile-home.png') });
  assert.equal(await phone.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'no horizontal page overflow');
  assert.equal(await phone.locator('#sidebar').evaluate(el => el.inert), true, 'closed mobile navigation cannot receive focus');
  await phone.getByRole('button', { name: 'Toggle navigation' }).click();
  assert.equal(await phone.locator('#sidebar').evaluate(el => el.inert), false);
  assert.equal(await phone.getByRole('button', { name: 'Toggle navigation' }).getAttribute('aria-expanded'), 'true');
  await phone.getByRole('button', { name: 'Close navigation' }).click();
  assert.equal(await phone.getByRole('button', { name: 'Toggle navigation' }).getAttribute('aria-expanded'), 'false');
  assert.equal(await phone.locator('#sidebar').evaluate(el => el.inert), true);
  await mobile.close();

  rejectSession = true;
  const expired = await context({ viewport: { width: 1280, height: 800 } }, { userId: owner, accessToken: token });
  const expiredPage = await expired.newPage(); await expiredPage.goto(origin);
  await expiredPage.getByText(/session has expired/i).waitFor({ timeout: 15000 });
  await expired.close(); rejectSession = false;

  const user = await context({ viewport: { width: 1440, height: 900 } }, { userId: owner, accessToken: token });
  const app = await user.newPage();
  app.on('requestfailed', request => console.error('Browser request failed:', new URL(request.url()).origin, request.failure()?.errorText));
  app.on('console', message => { if (message.type() === 'error') console.error('Browser console:', message.text()); });
  await app.goto(origin);
  try { await app.getByText('Available here: the owned ledger NON_AI fixture.', { exact: false }).waitFor({ timeout: 15000 }); }
  catch (error) { console.error('Workspace state:', (await app.locator('body').innerText()).slice(0, 1600)); throw error; }
  await app.locator('#promptInput').fill('Real browser fixture acceptance'); await app.locator('#promptInput').press('Enter');
  await app.getByRole('button', { name: 'Choose a supported target' }).click();
  await app.locator('#scopeConsent').check(); await app.getByRole('button', { name: 'Create investigation' }).click();
  await app.getByRole('button', { name: 'Confirm scope' }).click(); await app.locator('#scopeConsent').check();
  await app.getByRole('button', { name: 'Authorize scope' }).click(); await app.getByRole('button', { name: 'Queue mock run' }).click();
  await app.getByRole('button', { name: 'Start NON_AI run' }).waitFor({ state: 'visible' });
  failNextRunRead = true;
  await app.getByRole('button', { name: 'Start NON_AI run' }).click();
  await app.getByText(/displayed status may be out of date/i).waitFor({ timeout: 20000 });
  await app.screenshot({ path: path.join(output, 'desktop-recovery.png') });
  await app.locator('.inline-note').filter({ hasText: /status may be out of date/i }).getByRole('button', { name: 'Check status' }).click();
  await app.getByRole('button', { name: 'View verification' }).waitFor({ timeout: 200000 });
  assert.equal(dispatches, 1, 'browser must not retry a dispatched execution');
  assert.equal(lostAcknowledgements, 1, 'the execution acknowledgement was deliberately lost');
  await app.getByRole('button', { name: 'View verification' }).click();
  assert.match(await app.locator('dialog').innerText(), /22 passed/);
  assert.match(await app.locator('dialog').innerText(), /NON_AI fixture comparison/);
  await app.screenshot({ path: path.join(output, 'desktop-verification.png') });
  await app.getByRole('button', { name: 'Close', exact: true }).last().click();
  await app.getByRole('button', { name: 'Open report' }).click();
  await app.getByRole('heading', { name: 'Sanitized report' }).waitFor();
  assert.match(await app.locator('dialog').innerText(), /NON_AI fixture result/);
  await app.getByRole('button', { name: 'Close', exact: true }).last().click();
  const downloadPromise = app.waitForEvent('download'); await app.getByRole('button', { name: 'Download integrity export' }).click();
  const download = await downloadPromise; const exportPath = path.join(output, 'fixture-export.zip'); await download.saveAs(exportPath);
  const verified = spawnSync(process.env.PYTHON || 'python', ['-c', 'import sys; sys.path.insert(0,"../src"); from second_source.backend.artifacts import verify_bundle; print(verify_bundle(open(sys.argv[1],"rb").read())["valid"])', exportPath], { encoding: 'utf8' });
  assert.equal(verified.status, 0, verified.stderr); assert.equal(verified.stdout.trim(), 'True');
  await app.reload(); await app.getByRole('button', { name: 'View verification' }).waitFor();
  assert.match(await app.locator('#content').innerText(), /Real browser fixture acceptance/);
  holdReport = true;
  await app.getByRole('button', { name: 'Open report' }).click();
  await Promise.race([reportRequested, new Promise((_, reject) => setTimeout(() => reject(new Error('Delayed report was not requested')), 15000))]);
  await app.getByRole('button', { name: 'New investigation' }).first().click();
  releaseReport(); await app.waitForTimeout(500);
  assert.equal(await app.locator('dialog[open]').count(), 0, 'a stale report cannot appear after navigation');
  const other = await context({ ...devices['iPhone 13'], defaultBrowserType: undefined }, { userId: otherOwner, accessToken: otherToken });
  const second = await other.newPage(); await second.goto(origin);
  await second.getByText('Available here: the owned ledger NON_AI fixture.', { exact: false }).waitFor();
  await second.getByRole('button', { name: 'Toggle navigation' }).click();
  await second.getByRole('button', { name: 'Your work' }).click();
  assert.match(await second.locator('#content').innerText(), /No investigations yet/);
  assert.doesNotMatch(await second.locator('#content').innerText(), /Real browser fixture acceptance/);
  const forbidden = await second.evaluate(async ({ id, accessToken }) => {
    const response = await fetch(`https://backend.test/v1/runs/${id}`, { headers: { Authorization: `Bearer ${accessToken}` } });
    return response.status;
  }, { id: firstRunId, accessToken: otherToken });
  assert.equal(forbidden, 404, 'second owner cannot read the first owner run');
  await second.getByRole('button', { name: 'Close navigation' }).click();
  await second.locator('.topbar [data-action="new"]').click();
  await second.getByRole('button', { name: 'Choose a supported target' }).click();
  await second.locator('#scopeConsent').check(); await second.getByRole('button', { name: 'Create investigation' }).click();
  await second.getByRole('button', { name: 'Confirm scope' }).click(); await second.locator('#scopeConsent').check();
  await second.getByRole('button', { name: 'Authorize scope' }).click(); await second.getByRole('button', { name: 'Queue mock run' }).click();
  assert.equal(await second.locator('.top-left').evaluate(el => el.getBoundingClientRect().right <= document.querySelector('.top-right').getBoundingClientRect().left), true, 'mobile title and connection status do not overlap');
  assert.ok(await second.locator('.toast-stack .toast').count() <= 1, 'notifications cannot stack over the composer');
  assert.equal(await second.locator('.toast-stack').evaluate(el => el.getBoundingClientRect().bottom <= document.querySelector('#composer').getBoundingClientRect().top), true, 'mobile notifications do not obscure the composer');
  await second.screenshot({ path: path.join(output, 'mobile-queued.png') });
  await second.getByRole('button', { name: 'Cancel queued run' }).click();
  await second.getByText('cancelled', { exact: true }).waitFor();
  assert.equal(await second.getByRole('button', { name: 'View verification' }).count(), 0);
  rejectSession = true; await second.reload();
  await second.getByText(/session has expired/i).waitFor();
  assert.doesNotMatch(await second.locator('#content').innerText(), /cancelled/i);
  await other.close(); await user.close();
  await writeFile(path.join(output, 'README.txt'), 'Real headless Chromium; synthetic local identities, local NON_AI worker, fake storage. No live Auth or cloud acceptance. Mobile uses device emulation.\n');
  console.log(`PASS: real Chromium desktop, mobile emulation, keyboard, local NON_AI worker, report/export, reload and two synthetic owners. Evidence: ${output}`);
} finally {
  await browser?.close(); await server?.close(); backend.kill();
}
