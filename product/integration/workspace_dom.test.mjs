/** DOM simulation + real loopback mock worker. No hosted Auth or provider transport. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, readFile, readdir, realpath, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { build } from 'vite';
import { Window } from 'happy-dom';

const token = 'a'.repeat(32) + '.' + 'b'.repeat(32) + '.' + 'c'.repeat(48);
const owner = 'a186fb18-72b4-4071-9794-e8746c3e4231';
const storageKey = 'sb-jpqcqqbzriizxhigvjki-auth-token';

async function until(predicate, label, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const result = predicate(); if (result) return result;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${label}`);
}

test('workspace controls drive an authorized NON_AI investigation through the local worker', { timeout: 240_000 }, async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'ss-dom-integration-'));
  const server = spawn(process.env.PYTHON || 'python', ['integration/local_backend.py'], { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = ''; let window;
  server.stderr.on('data', chunk => { stderr += String(chunk).slice(0, 4000); });
  try {
    const [chunk] = await Promise.race([
      once(server.stdout, 'data'),
      once(server, 'exit').then(() => { throw new Error(`Local test server exited: ${stderr}`); }),
      new Promise((_, reject) => setTimeout(() => reject(new Error('Local test server did not start')), 15_000)),
    ]);
    const port = /^PORT=(\d+)/.exec(String(chunk))?.[1]; assert.ok(port);
    const local = `http://127.0.0.1:${port}`;
    await build({ configFile: false, envFile: false, logLevel: 'silent',
      define: {
        'import.meta.env.VITE_API_ORIGIN': JSON.stringify('https://backend.test'),
        'import.meta.env.VITE_SUPABASE_URL': JSON.stringify('https://jpqcqqbzriizxhigvjki.supabase.co'),
        'import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY': JSON.stringify('sb_publishable_' + 'x'.repeat(30)),
      },
      build: { outDir: directory, emptyOutDir: true },
    });
    const html = await readFile(path.join(directory, 'index.html'), 'utf8');
    const assetDir = path.join(directory, 'assets');
    const asset = (await readdir(assetDir)).find(name => name.endsWith('.js')); assert.ok(asset);
    const bundle = await readFile(path.join(assetDir, asset), 'utf8');
    window = new Window({ url: 'https://preview.test/', settings: { disableJavaScriptFileLoading: true, disableCSSFileLoading: true } });
    // The simulator stringifies ArrayBuffers in Blob parts; use Node's standards-compliant Blob.
    window.Blob = globalThis.Blob;
    window.sessionStorage.setItem(storageKey, JSON.stringify({ access_token: token, refresh_token: 'synthetic-refresh',
      expires_at: Math.floor(Date.now() / 1000) + 3600, expires_in: 3600, token_type: 'bearer', user: { id: owner } }));
    // All transport is restricted to the local test server. No Supabase or model URL can be reached.
    window.fetch = (input, options) => {
      const url = new URL(typeof input === 'string' ? input : input.url);
      if (url.origin !== 'https://backend.test') throw new Error('External transport forbidden');
      return fetch(local + url.pathname + url.search, options);
    };
    let exported;
    window.URL.createObjectURL = blob => { exported = blob; return 'blob:https://preview.test/local-test'; };
    window.URL.revokeObjectURL = () => {};
    window.HTMLAnchorElement.prototype.click = function () {};
    window.document.write(html); window.eval(bundle);
    const doc = window.document;
    await until(() => doc.querySelector('.home-note')?.textContent.includes('Available here:'), 'target discovery');
    doc.querySelector('[data-action="select-target"]').click();
    doc.querySelector('#scopeConsent').checked = true;
    doc.querySelector('[data-action="create"]').click();
    (await until(() => doc.querySelector('[data-action="authorize"]'), 'created investigation')).click();
    doc.querySelector('#scopeConsent').checked = true;
    doc.querySelector('[data-action="confirm-authorization"]').click();
    (await until(() => doc.querySelector('[data-action="queue"]'), 'authorization')).click();
    (await until(() => {
      const button = doc.querySelector('[data-action="execute"]'); return button && !button.disabled ? button : null;
    }, 'queued run')).click();
    (await until(() => doc.querySelector('[data-action="verification"]'), 'completed run', 200_000)).click();
    assert.match(doc.querySelector('dialog').textContent, /NON_AI fixture comparison/);
    assert.match(doc.querySelector('dialog').textContent, /22 passed/);
    assert.match(doc.querySelector('dialog').textContent, /3 failed/);
    assert.match(doc.querySelector('dialog').textContent, /25 total/);
    doc.querySelector('[data-action="close-dialog"]').click();
    doc.querySelector('[data-action="export"]').click();
    await until(() => exported, 'export');
    const bytes = Buffer.from(await exported.arrayBuffer());
    assert.equal(bytes.subarray(0, 2).toString(), 'PK');
    const verifier = spawnSync(process.env.PYTHON || 'python', ['-c',
      'import sys; sys.path.insert(0, "../src"); from second_source.backend.artifacts import verify_bundle; print("valid" if verify_bundle(sys.stdin.buffer.read())["valid"] else "invalid")'],
    { input: bytes, encoding: 'utf8', timeout: 30_000 });
    assert.equal(verifier.status, 0, 'local integrity verifier completed');
    assert.equal(verifier.stdout.trim(), 'valid');
  } finally {
    window?.happyDOM.abort(); server.kill();
    const resolvedTemp = await realpath(os.tmpdir());
    const resolvedDirectory = await realpath(directory);
    if (path.dirname(resolvedDirectory) === resolvedTemp && path.basename(resolvedDirectory).startsWith('ss-dom-integration-')) {
      await rm(resolvedDirectory, { recursive: true, force: true });
    }
  }
});
