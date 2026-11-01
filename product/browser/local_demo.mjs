// Isolated, interactive NON_AI demo. All identities and Storage are synthetic.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { chromium } from 'playwright';
import { createServer } from 'vite';

const smoke = process.argv.includes('--smoke');
const token = 'a'.repeat(32) + '.' + 'b'.repeat(32) + '.' + 'c'.repeat(48);
const owner = 'a186fb18-72b4-4071-9794-e8746c3e4231';
const identityOrigin = 'https://jpqcqqbzriizxhigvjki.supabase.co';
const backendOrigin = 'https://backend.test';
const env = Object.fromEntries(['SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH']
  .filter(key => process.env[key]).map(key => [key, process.env[key]]));
env.SECOND_SOURCE_MAX_RUN_USD = '0';
const backend = spawn(process.env.PYTHON || 'python', ['integration/local_backend.py'], { env, stdio: ['ignore', 'pipe', 'pipe'] });
let backendErrors = '', server, browser;
backend.stderr.on('data', chunk => { backendErrors = (backendErrors + String(chunk)).slice(-4000); });
try {
  const [chunk] = await Promise.race([
    once(backend.stdout, 'data'),
    once(backend, 'exit').then(() => { throw new Error(`Local backend exited: ${backendErrors}`); }),
    new Promise((_, reject) => setTimeout(() => reject(new Error('Local backend startup timed out')), 15000)),
  ]);
  const port = /^PORT=(\d+)/.exec(String(chunk))?.[1];
  assert.ok(port, 'local backend must advertise a loopback port');
  server = await createServer({ configFile: false, envFile: false, logLevel: 'error',
    define: {
      'import.meta.env.VITE_API_ORIGIN': JSON.stringify(backendOrigin),
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(identityOrigin),
      'import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY': JSON.stringify('sb_publishable_' + 'x'.repeat(30)),
    }, server: { host: '127.0.0.1', port: 0, strictPort: false },
  });
  await server.listen();
  const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
  browser = await chromium.launch({ headless: smoke, ...(process.env.SS_BROWSER_PATH ? { executablePath: process.env.SS_BROWSER_PATH } : {}) });
  const context = await browser.newContext({ acceptDownloads: true });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin === origin) return route.continue();
    const cors = { 'access-control-allow-origin': origin, 'access-control-allow-methods': 'GET,POST,OPTIONS',
      'access-control-allow-headers': 'authorization,content-type,idempotency-key' };
    if (url.origin === identityOrigin && url.pathname === '/auth/v1/logout') return route.fulfill({ status: 204, headers: cors });
    if (url.origin !== backendOrigin) return route.abort('blockedbyclient');
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: cors });
    const headers = { ...request.headers() }; delete headers.host; delete headers.origin; delete headers['content-length'];
    const response = await fetch(`http://127.0.0.1:${port}${url.pathname}${url.search}`, {
      method: request.method(), headers, body: request.postDataBuffer() || undefined,
    });
    const responseHeaders = Object.fromEntries(response.headers); delete responseHeaders['content-encoding'];
    return route.fulfill({ status: response.status, headers: { ...responseHeaders, ...cors }, body: Buffer.from(await response.arrayBuffer()) });
  });
  await context.addInitScript(({ accessToken, userId }) => {
    const key = 'sb-jpqcqqbzriizxhigvjki-auth-token';
    sessionStorage.setItem(key, JSON.stringify({ access_token: accessToken, refresh_token: 'synthetic-refresh',
      expires_at: Math.floor(Date.now() / 1000) + 3600, expires_in: 3600, token_type: 'bearer', user: { id: userId } }));
    document.addEventListener('DOMContentLoaded', () => {
      const notice = document.createElement('div'); notice.textContent = 'LOCAL DEMO · SYNTHETIC IDENTITY · FAKE STORAGE · NO AI';
      notice.setAttribute('role', 'status');
      Object.assign(notice.style, { position: 'fixed', top: '0', left: '50%', transform: 'translateX(-50%)',
        zIndex: '9999', padding: '4px 12px', borderRadius: '0 0 10px 10px', background: '#dbe8dd',
        color: '#183326', font: '600 10px sans-serif', pointerEvents: 'none', textAlign: 'center' });
      document.body.append(notice);
    });
  }, { accessToken: token, userId: owner });
  const page = await context.newPage();
  await page.goto(origin);
  await page.getByText('Available here: owned ledger and HTTP task-workflow NON_AI fixtures.', { exact: false }).waitFor({ timeout: 30000 });
  console.log('LOCAL DEMO: synthetic identity, temporary fake Storage, no model calls. Close the window to stop.');
  if (smoke) {
    await page.getByRole('button', { name: 'Choose a supported target' }).click();
    assert.equal(await page.locator('[data-target-id]').count(), 2);
    await page.locator('[data-target-id="owned-http-task-workflow-v1"]').click();
    await page.locator('#scopeConsent').check(); await page.getByRole('button', { name: 'Create investigation' }).click();
    await page.getByRole('button', { name: 'Confirm scope' }).click(); await page.locator('#scopeConsent').check();
    await page.getByRole('button', { name: 'Authorize scope' }).click(); await page.getByRole('button', { name: 'Queue mock run' }).click();
    await page.getByRole('button', { name: 'Start NON_AI run' }).click();
    await page.getByRole('button', { name: 'View verification' }).waitFor({ timeout: 200000 });
    await page.getByRole('button', { name: 'View verification' }).click();
    assert.match(await page.locator('dialog').innerText(), /30 passed/);
    console.log('PASS: local demo discovered both fixtures and ran the HTTP NON_AI worker to verification.');
    await context.close();
  } else {
    await new Promise(resolve => context.once('close', resolve));
  }
} finally {
  await browser?.close();
  await server?.close();
  backend.kill();
}
