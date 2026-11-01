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
  let refuseNextExecution = true, refusedExecutions = 0, queuedSnapshot, latestQueuedSnapshot;
  let holdSyntheticExecution = false, syntheticTerminal = null, executionSeen, releaseExecution;
  const executionRequested = new Promise(resolve => { executionSeen = resolve; });
  const executionMayFinish = new Promise(resolve => { releaseExecution = resolve; });
  let holdOldPoll = false, oldPollSeen, releaseOldPoll;
  const oldPollRequested = new Promise(resolve => { oldPollSeen = resolve; });
  const oldPollMayFinish = new Promise(resolve => { releaseOldPoll = resolve; });
  let holdList = false, listSeen, releaseList;
  const listRequested = new Promise(resolve => { listSeen = resolve; });
  const listMayFinish = new Promise(resolve => { releaseList = resolve; });
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
      let testResponse = '';
      if (url.origin === origin) return route.continue();
      if (url.origin === 'https://jpqcqqbzriizxhigvjki.supabase.co' && url.pathname === '/auth/v1/logout') {
        return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': origin, 'access-control-allow-headers': '*' } });
      }
      if (url.origin !== 'https://backend.test') return route.abort('blockedbyclient');
      console.log('Local API:', req.method(), url.pathname);
      if (holdReport && req.method() === 'GET' && url.pathname.endsWith('/report')) {
        reportSeen(); await reportMayFinish; testResponse = 'delayed-report';
      }
      const cors = { 'access-control-allow-origin': origin, 'access-control-allow-methods': 'GET,POST,OPTIONS', 'access-control-allow-headers': 'authorization,content-type,idempotency-key' };
      if (req.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors });
      if (rejectSession && url.pathname === '/v1/session') return route.fulfill({ status: 401, headers: cors, body: '{}' });
      if (holdList && req.method() === 'GET' && url.pathname === '/v1/investigations') {
        holdList = false; listSeen(); await listMayFinish; testResponse = 'delayed-list';
      }
      if (holdOldPoll && req.method() === 'GET' && /^\/v1\/runs\/[^/]+$/.test(url.pathname)) {
        holdOldPoll = false; oldPollSeen(); await oldPollMayFinish;
        return route.fulfill({ status: 200, headers: { ...cors, 'content-type': 'application/json', 'x-ss-test-response': 'old-poll' }, body: JSON.stringify(queuedSnapshot) });
      }
      if (req.method() === 'POST' && url.pathname.endsWith('/execute')) {
        if (refuseNextExecution) { refuseNextExecution = false; refusedExecutions++; return route.fulfill({ status: 429, headers: cors, body: '{"code":"RATE_LIMITED"}' }); }
        if (holdSyntheticExecution) {
          holdSyntheticExecution = false;
          syntheticTerminal = { ...latestQueuedSnapshot, status: 'failed', revision: latestQueuedSnapshot.revision + 1, error_code: 'ENGINE_FAILED' };
          executionSeen(); await executionMayFinish;
          return route.fulfill({ status: 429, headers: { ...cors, 'x-ss-test-response': 'held-execute' }, body: '{"code":"RATE_LIMITED"}' });
        }
        dispatches++; firstRunId ||= url.pathname.split('/')[3];
      }
      if (failNextRunRead && req.method() === 'GET' && /^\/v1\/runs\/[^/]+$/.test(url.pathname)) {
        failNextRunRead = false; return route.fulfill({ status: 429, headers: cors, body: '{}' });
      }
      if (syntheticTerminal && req.method() === 'GET' && url.pathname === `/v1/runs/${syntheticTerminal.run_id}`)
        return route.fulfill({ status: 200, headers: { ...cors, 'content-type': 'application/json' }, body: JSON.stringify(syntheticTerminal) });
      const headers = { ...req.headers() }; delete headers.host; delete headers.origin; delete headers['content-length'];
      const response = await fetch(`http://127.0.0.1:${port}${url.pathname}${url.search}`, {
        method: req.method(), headers, body: req.postDataBuffer() || undefined,
      });
      if (loseExecutionAck && req.method() === 'POST' && url.pathname.endsWith('/execute')) {
        loseExecutionAck = false; lostAcknowledgements++; await response.arrayBuffer(); return route.abort('failed');
      }
      const responseHeaders = Object.fromEntries(response.headers); delete responseHeaders['content-encoding'];
      console.log('Local API status:', response.status);
      const body = Buffer.from(await response.arrayBuffer());
      if (req.method() === 'POST' && /^\/v1\/investigations\/[^/]+\/runs$/.test(url.pathname) && response.status === 201) {
        latestQueuedSnapshot = JSON.parse(body.toString()); queuedSnapshot ||= latestQueuedSnapshot;
      }
      return route.fulfill({ status: response.status, headers: { ...responseHeaders, ...cors, ...(testResponse ? { 'x-ss-test-response': testResponse } : {}) }, body });
    });
    if (identity) await ctx.addInitScript(({ key, userId, accessToken }) => {
      sessionStorage.setItem(key, JSON.stringify({ access_token: accessToken, refresh_token: 'synthetic-refresh',
        expires_at: Math.floor(Date.now() / 1000) + 3600, expires_in: 3600, token_type: 'bearer', user: { id: userId } }));
    }, { key: sessionKey, ...identity });
    return ctx;
  }
  const desktop = await context({ viewport: { width: 1440, height: 900 } });
  const page = await desktop.newPage();
  await page.goto(origin); await page.getByRole('heading', { name: /understand how software really works/i }).waitFor();
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
  await phone.getByRole('heading', { name: /understand how software really works/i }).waitFor();
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

  const switching = await context({ viewport: { width: 1280, height: 800 } }, { userId: owner, accessToken: token });
  const switchPage = await switching.newPage(); await switchPage.goto(origin);
  await switchPage.getByText('Available here: owned ledger and HTTP task-workflow NON_AI fixtures.', { exact: false }).waitFor();
  await switchPage.locator('#promptInput').fill('Private stale list marker'); await switchPage.locator('#promptInput').press('Enter');
  await switchPage.getByRole('button', { name: 'Choose a supported target' }).click(); await switchPage.locator('[data-target-id="owned-ledger-v1"]').click(); await switchPage.locator('#scopeConsent').check();
  holdList = true; await switchPage.getByRole('button', { name: 'Create investigation' }).click();
  await Promise.race([listRequested, new Promise((_, reject) => setTimeout(() => reject(new Error('Delayed investigation list was not requested')), 15000))]);
  await switchPage.locator('[data-action="account"]').click(); await switchPage.getByRole('button', { name: 'Sign out' }).click();
  await switchPage.getByText('Not signed in', { exact: true }).waitFor();
  const listResponse = switchPage.waitForResponse(response => response.headers()['x-ss-test-response'] === 'delayed-list');
  releaseList(); await (await listResponse).finished(); await switchPage.evaluate(() => new Promise(resolve => setTimeout(resolve, 0)));
  await switchPage.locator('.topbar [data-action="new"]').click();
  assert.doesNotMatch(await switchPage.locator('#history').innerText(), /Private stale list marker/, 'a previous owner list must not reappear after sign-out and subsequent rendering');
  await switching.close();

  const user = await context({ viewport: { width: 1440, height: 900 } }, { userId: owner, accessToken: token });
  const app = await user.newPage();
  app.on('requestfailed', request => console.error('Browser request failed:', new URL(request.url()).origin, request.failure()?.errorText));
  app.on('console', message => { if (message.type() === 'error') console.error('Browser console:', message.text()); });
  await app.goto(origin);
  try { await app.getByText('Available here: owned ledger and HTTP task-workflow NON_AI fixtures.', { exact: false }).waitFor({ timeout: 15000 }); }
  catch (error) { console.error('Workspace state:', (await app.locator('body').innerText()).slice(0, 1600)); throw error; }
  await app.locator('#promptInput').fill('Real browser fixture acceptance'); await app.locator('#promptInput').press('Enter');
  await app.getByRole('button', { name: 'Choose a supported target' }).click();
  await app.locator('[data-target-id="owned-ledger-v1"]').click();
  await app.locator('#scopeConsent').check(); await app.getByRole('button', { name: 'Create investigation' }).click();
  await app.getByRole('button', { name: 'Confirm scope' }).click(); await app.locator('#scopeConsent').check();
  await app.getByRole('button', { name: 'Authorize scope' }).click(); await app.getByRole('button', { name: 'Queue mock run' }).click();
  await app.getByRole('button', { name: 'Start NON_AI run' }).waitFor({ state: 'visible' });
  await app.getByRole('button', { name: 'Start NON_AI run' }).click();
  await app.getByText(/too many requests/i).waitFor();
  await app.waitForFunction(() => { const button = document.querySelector('[data-action="execute"]'); return button && !button.disabled; }, null, { timeout: 15000 });
  assert.equal(await app.getByRole('button', { name: 'Start NON_AI run' }).isEnabled(), true, 'definitive refusal permits a later manual start');
  assert.equal(refusedExecutions, 1); assert.equal(dispatches, 0, 'pre-dispatch refusal does not automatically retry');
  failNextRunRead = true;
  await app.getByRole('button', { name: 'Start NON_AI run' }).click();
  await app.getByText(/displayed status may be out of date/i).waitFor({ timeout: 20000 });
  await app.screenshot({ path: path.join(output, 'desktop-recovery.png') });
  await app.locator('.inline-note').filter({ hasText: /status may be out of date/i }).getByRole('button', { name: 'Check status' }).click();
  await app.getByText('running', { exact: true }).waitFor({ timeout: 20000 });
  holdOldPoll = true;
  await app.getByRole('button', { name: 'Check status' }).last().click();
  await Promise.race([oldPollRequested, new Promise((_, reject) => setTimeout(() => reject(new Error('Old poll was not requested')), 15000))]);
  const freshResponse = app.waitForResponse(response => /^\/v1\/runs\/[^/]+$/.test(new URL(response.url()).pathname) && response.request().method() === 'GET' && response.status() === 200);
  await app.getByRole('button', { name: 'Check status' }).last().click();
  await (await freshResponse).finished();
  const staleResponse = app.waitForResponse(response => response.headers()['x-ss-test-response'] === 'old-poll');
  releaseOldPoll(); await (await staleResponse).finished(); await app.evaluate(() => new Promise(resolve => setTimeout(resolve, 0)));
  assert.notEqual((await app.locator('.artifact-tag').innerText()).trim(), 'queued', 'an older queued poll cannot regress a running run');
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
  const reportResponse = app.waitForResponse(response => response.headers()['x-ss-test-response'] === 'delayed-report');
  releaseReport(); await (await reportResponse).finished(); await app.evaluate(() => new Promise(resolve => setTimeout(resolve, 0)));
  assert.equal(await app.locator('dialog[open]').count(), 0, 'a stale report cannot appear after navigation');

  // The separate HTTP fixture is discovered from the real local API and remains NON_AI.
  await app.locator('#promptInput').fill('HTTP task workflow acceptance'); await app.locator('#promptInput').press('Enter');
  await app.getByRole('button', { name: 'Choose a supported target' }).click();
  await app.locator('[data-target-id="owned-http-task-workflow-v1"]').click();
  assert.match(await app.locator('dialog').innerText(), /loopback/);
  await app.locator('#scopeConsent').check(); await app.getByRole('button', { name: 'Create investigation' }).click();
  await app.getByRole('button', { name: 'Confirm scope' }).click(); await app.locator('#scopeConsent').check();
  await app.getByRole('button', { name: 'Authorize scope' }).click();
  const g4QueuedResponse = app.waitForResponse(response => response.request().method() === 'POST' && /\/investigations\/[^/]+\/runs$/.test(new URL(response.url()).pathname) && response.status() === 201);
  await app.getByRole('button', { name: 'Queue mock run' }).click();
  const g4RunId = (await (await g4QueuedResponse).json()).run_id;
  assert.notEqual(g4RunId, firstRunId, 'HTTP isolation must use the actual HTTP run identity');
  await app.getByRole('button', { name: 'Start NON_AI run' }).click();
  await app.getByRole('button', { name: 'View verification' }).waitFor({ timeout: 200000 });
  await app.getByRole('button', { name: 'View verification' }).click();
  assert.match(await app.locator('dialog').innerText(), /30 passed/);
  assert.match(await app.locator('dialog').innerText(), /previously collected active evidence/);
  await app.screenshot({ path: path.join(output, 'g4-desktop-verification.png') });
  await app.getByRole('button', { name: 'Close', exact: true }).last().click();
  await app.getByRole('button', { name: 'Open report' }).click();
  await app.getByRole('heading', { name: 'Sanitized report' }).waitFor();
  assert.match(await app.locator('dialog').innerText(), /NON_AI fixture result/);
  await app.getByRole('button', { name: 'Close', exact: true }).last().click();
  const g4DownloadPromise = app.waitForEvent('download');
  await app.getByRole('button', { name: 'Download integrity export' }).click();
  const g4ExportPath = path.join(output, 'g4-fixture-export.zip');
  await (await g4DownloadPromise).saveAs(g4ExportPath);
  const g4Verified = spawnSync(process.env.PYTHON || 'python', ['-c', 'import sys; sys.path.insert(0,"../src"); from second_source.backend.artifacts import verify_bundle; print(verify_bundle(open(sys.argv[1],"rb").read())["valid"])', g4ExportPath], { encoding: 'utf8' });
  assert.equal(g4Verified.status, 0, g4Verified.stderr); assert.equal(g4Verified.stdout.trim(), 'True');
  await app.reload(); await app.getByRole('button', { name: 'View verification' }).waitFor();
  assert.match(await app.locator('#content').innerText(), /HTTP task-workflow fixture/);

  const other = await context({ ...devices['iPhone 13'], defaultBrowserType: undefined }, { userId: otherOwner, accessToken: otherToken });
  const second = await other.newPage(); await second.goto(origin);
  await second.getByText('Available here: owned ledger and HTTP task-workflow NON_AI fixtures.', { exact: false }).waitFor();
  await second.getByRole('button', { name: 'Toggle navigation' }).click();
  await second.getByRole('button', { name: 'Your work' }).click();
  assert.match(await second.locator('#content').innerText(), /No investigations yet/);
  assert.doesNotMatch(await second.locator('#content').innerText(), /Real browser fixture acceptance/);
  const forbidden = await second.evaluate(async ({ id, accessToken }) => {
    const response = await fetch(`https://backend.test/v1/runs/${id}`, { headers: { Authorization: `Bearer ${accessToken}` } });
    return response.status;
  }, { id: firstRunId, accessToken: otherToken });
  assert.equal(forbidden, 404, 'second owner cannot read the first owner run');
  for (const suffix of ['', '/report', '/export.zip']) {
    const status = await second.evaluate(async ({ id, accessToken, suffix }) => (await fetch(`https://backend.test/v1/runs/${id}${suffix}`, { headers: { Authorization: `Bearer ${accessToken}` } })).status,
      { id: g4RunId, accessToken: otherToken, suffix });
    assert.equal(status, 404, 'second owner cannot read the HTTP run or its artifacts');
  }
  await second.getByRole('button', { name: 'Close navigation' }).click();
  await second.locator('.topbar [data-action="new"]').click();
  await second.getByRole('button', { name: 'Choose a supported target' }).click();
  await second.locator('[data-target-id="owned-ledger-v1"]').click();
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
  await second.waitForFunction(() => document.querySelector('details.activity')?.textContent?.includes('Run cancelled'), null, { timeout: 15000 });
  await second.getByRole('button', { name: 'Queue a new mock run' }).click();
  await second.getByText('queued', { exact: true }).waitFor();
  assert.equal(await second.locator('details.activity').count(), 0, 'a new queued run must not display the prior run activity');
  // Synthetic terminal polling while an execution acknowledgement is held: no worker is dispatched.
  holdSyntheticExecution = true;
  await second.getByRole('button', { name: 'Start NON_AI run' }).click();
  await Promise.race([executionRequested, new Promise((_, reject) => setTimeout(() => reject(new Error('Held execution was not requested')), 15000))]);
  await second.getByText('failed', { exact: true }).waitFor({ timeout: 20000 });
  assert.equal(await second.getByRole('button', { name: 'Queue a new mock run' }).isDisabled(), true, 'a prior execution request must settle before another run is queued');
  const executionResponse = second.waitForResponse(response => response.headers()['x-ss-test-response'] === 'held-execute');
  releaseExecution(); await (await executionResponse).finished();
  await second.waitForFunction(() => { const button = document.querySelector('[data-action="queue"]'); return button && !button.disabled; }, null, { timeout: 15000 });
  syntheticTerminal = null;
  await second.locator('.topbar [data-action="new"]').click();
  await second.locator('#promptInput').fill('Mobile HTTP fixture'); await second.locator('#promptInput').press('Enter');
  await second.getByRole('button', { name: 'Choose a supported target' }).click();
  await second.locator('[data-target-id="owned-http-task-workflow-v1"]').click();
  await second.locator('#scopeConsent').check(); await second.getByRole('button', { name: 'Create investigation' }).click();
  await second.getByRole('button', { name: 'Confirm scope' }).click(); await second.locator('#scopeConsent').check();
  await second.getByRole('button', { name: 'Authorize scope' }).click();
  const mobileG4QueuedResponse = second.waitForResponse(response => response.request().method() === 'POST' && /\/investigations\/[^/]+\/runs$/.test(new URL(response.url()).pathname) && response.status() === 201);
  await second.getByRole('button', { name: 'Queue mock run' }).click();
  const mobileG4RunId = (await (await mobileG4QueuedResponse).json()).run_id;
  assert.notEqual(mobileG4RunId, g4RunId, 'mobile isolation must use the second HTTP run identity');
  await second.getByRole('button', { name: 'Start NON_AI run' }).click();
  await second.getByRole('button', { name: 'View verification' }).waitFor({ timeout: 200000 });
  await second.getByRole('button', { name: 'View verification' }).click();
  assert.match(await second.locator('dialog').innerText(), /30 passed/);
  await second.screenshot({ path: path.join(output, 'g4-mobile-verification.png') });
  await second.getByRole('button', { name: 'Close', exact: true }).last().click();
  const mobileG4Download = second.waitForEvent('download');
  await second.getByRole('button', { name: 'Download integrity export' }).click();
  const mobileG4ExportPath = path.join(output, 'g4-mobile-export.zip');
  await (await mobileG4Download).saveAs(mobileG4ExportPath);
  const mobileG4Verified = spawnSync(process.env.PYTHON || 'python', ['-c', 'import sys; sys.path.insert(0,"../src"); from second_source.backend.artifacts import verify_bundle; print(verify_bundle(open(sys.argv[1],"rb").read())["valid"])', mobileG4ExportPath], { encoding: 'utf8' });
  assert.equal(mobileG4Verified.status, 0, mobileG4Verified.stderr); assert.equal(mobileG4Verified.stdout.trim(), 'True');
  await second.reload(); await second.getByRole('button', { name: 'View verification' }).waitFor();
  const reverseOwner = await app.evaluate(async ({ id, accessToken }) => (await fetch(`https://backend.test/v1/runs/${id}/report`, { headers: { Authorization: `Bearer ${accessToken}` } })).status,
    { id: mobileG4RunId, accessToken: token });
  assert.equal(reverseOwner, 404, 'first owner cannot read the second owner HTTP report');
  await second.locator('.topbar [data-action="new"]').click();
  await second.locator('#promptInput').fill('Mobile ledger fixture'); await second.locator('#promptInput').press('Enter');
  await second.getByRole('button', { name: 'Choose a supported target' }).click();
  await second.locator('[data-target-id="owned-ledger-v1"]').click();
  await second.locator('#scopeConsent').check(); await second.getByRole('button', { name: 'Create investigation' }).click();
  await second.getByRole('button', { name: 'Confirm scope' }).click(); await second.locator('#scopeConsent').check();
  await second.getByRole('button', { name: 'Authorize scope' }).click(); await second.getByRole('button', { name: 'Queue mock run' }).click();
  await second.getByRole('button', { name: 'Start NON_AI run' }).click();
  await second.getByRole('button', { name: 'View verification' }).waitFor({ timeout: 200000 });
  await second.getByRole('button', { name: 'View verification' }).click();
  assert.match(await second.locator('dialog').innerText(), /22 passed/);
  await second.screenshot({ path: path.join(output, 'ledger-mobile-verification.png') });
  await second.getByRole('button', { name: 'Close', exact: true }).last().click();
  const mobileLedgerDownload = second.waitForEvent('download');
  await second.getByRole('button', { name: 'Download integrity export' }).click();
  const mobileLedgerExportPath = path.join(output, 'ledger-mobile-export.zip');
  await (await mobileLedgerDownload).saveAs(mobileLedgerExportPath);
  const mobileLedgerVerified = spawnSync(process.env.PYTHON || 'python', ['-c', 'import sys; sys.path.insert(0,"../src"); from second_source.backend.artifacts import verify_bundle; print(verify_bundle(open(sys.argv[1],"rb").read())["valid"])', mobileLedgerExportPath], { encoding: 'utf8' });
  assert.equal(mobileLedgerVerified.status, 0, mobileLedgerVerified.stderr); assert.equal(mobileLedgerVerified.stdout.trim(), 'True');
  rejectSession = true; await second.reload();
  await second.getByText(/session has expired/i).waitFor();
  assert.doesNotMatch(await second.locator('#content').innerText(), /cancelled/i);
  await other.close(); await user.close();
  await writeFile(path.join(output, 'README.txt'), 'Real headless Chromium; synthetic local identities, local NON_AI worker, fake storage. No live Auth or cloud acceptance. Mobile uses device emulation.\n');
  console.log(`PASS: real Chromium desktop, mobile emulation, keyboard, local NON_AI worker, report/export, reload and two synthetic owners. Evidence: ${output}`);
} finally {
  await browser?.close(); await server?.close(); backend.kill();
}
