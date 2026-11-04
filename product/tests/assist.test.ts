import assert from 'node:assert/strict';
import test from 'node:test';
import { requestAssist, requestCapture } from '../src/engine.ts';

test('requestAssist posts text and returns the reply', async () => {
  const original = globalThis.fetch;
  let seen: { url: string; body: unknown } | null = null;
  globalThis.fetch = (async (url: string, init: { body?: string }) => {
    seen = { url, body: JSON.parse(init.body || '{}') };
    return new Response(JSON.stringify({ reply: 'Do this.', model: 'muse-spark-1.3', receipt: { estimated_cost_usd: 0.01 } }), { status: 200 });
  }) as typeof fetch;
  try {
    const res = await requestAssist('rebuild notes?', 'ctx');
    assert.equal(res.reply, 'Do this.');
    assert.equal((seen!.body as { text: string }).text, 'rebuild notes?');
    assert.ok(seen!.url.endsWith('/engine/v1/assist'));
  } finally {
    globalThis.fetch = original;
  }
});

test('requestAssist surfaces engine detail on failure', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({ detail: 'Session AI spend cap reached' }), { status: 402 })) as typeof fetch;
  try {
    await assert.rejects(() => requestAssist('hi'), /Session AI spend cap reached/);
  } finally {
    globalThis.fetch = original;
  }
});

test('requestCapture posts url and permission', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({
    host: 'example.com', status: 200, content_type: 'text/html', size_bytes: 90,
    surface: { kind: 'html', title: 'T', forms: 0, links: 1, inputs: 0 },
    summary: null, model: null, note: 'Capture only.',
  }), { status: 200 })) as typeof fetch;
  try {
    const res = await requestCapture('https://example.com', true, false);
    assert.equal(res.host, 'example.com');
    assert.equal(res.surface.kind, 'html');
  } finally {
    globalThis.fetch = original;
  }
});
