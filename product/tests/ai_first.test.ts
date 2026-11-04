import assert from 'node:assert/strict';
import test from 'node:test';
import { getEngineHealth, resolveEngineBase, resolveEngineEnv } from '../src/engine.ts';

test('resolveEngineEnv accepts only https or loopback hosts', () => {
  assert.equal(resolveEngineEnv('https://ss-engine.onrender.com'), 'https://ss-engine.onrender.com');
  assert.equal(resolveEngineEnv('https://ss-engine.onrender.com/'), 'https://ss-engine.onrender.com');
  assert.equal(resolveEngineEnv('http://127.0.0.1:8770'), 'http://127.0.0.1:8770');
  assert.equal(resolveEngineEnv(''), null);
  assert.equal(resolveEngineEnv('http://evil.example/'), null);
  assert.equal(resolveEngineEnv('https://evil.example/path'), null);
});

test('resolveEngineBase allows only loopback ?engine= overrides', () => {
  assert.equal(resolveEngineBase('?engine=http://127.0.0.1:8770'), 'http://127.0.0.1:8770');
  assert.equal(resolveEngineBase(''), 'http://127.0.0.1:8765');
  assert.equal(resolveEngineBase('?engine=https://evil.example:9999'), 'http://127.0.0.1:8765');
  assert.equal(resolveEngineBase('?engine=http://127.0.0.1:8770/extra'), 'http://127.0.0.1:8765');
});

test('getEngineHealth parses the full AI-first payload', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    ok: true, model_calls: true, muse_repair_targets: ['vikunja-v1', 'pocketbase-v1'],
    vision: { regions: 'unconfigured', regions_endpoint_host: null, motion_physics: 'local-non-ai' },
    spend: { used_usd: 1.5, cap_usd: 15 },
  }), { status: 200 });
  try {
    const h = await getEngineHealth();
    assert.equal(h?.model_calls, true);
    assert.deepEqual(h?.muse_repair_targets, ['vikunja-v1', 'pocketbase-v1']);
    assert.equal(h?.spend.used_usd, 1.5);
    assert.equal(h?.vision.motion_physics, 'local-non-ai');
  } finally {
    globalThis.fetch = original;
  }
});

test('getEngineHealth fills safe defaults and nulls when offline', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ ok: true }), { status: 200 });
  try {
    const h = await getEngineHealth();
    assert.equal(h?.model_calls, false);
    assert.deepEqual(h?.spend, { used_usd: 0, cap_usd: 15 });
  } finally {
    globalThis.fetch = original;
  }
  globalThis.fetch = async () => { throw new Error('offline'); };
  try {
    assert.equal(await getEngineHealth(), null);
  } finally {
    globalThis.fetch = original;
  }
});
