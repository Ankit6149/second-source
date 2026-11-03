import assert from 'node:assert/strict';
import test from 'node:test';
import { checkEngine, engineCandidateUrl } from '../src/engine.ts';

test('engine candidate URL targets the local engine and encodes the id', () => {
  assert.equal(
    engineCandidateUrl('inv-abc 123'),
    'http://127.0.0.1:8765/engine/v1/investigations/inv-abc%20123/candidate');
});

test('checkEngine reports unavailable when the engine is offline', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('offline'); };
  try {
    assert.equal(await checkEngine(), false);
  } finally {
    globalThis.fetch = original;
  }
});

test('checkEngine reports available only on an ok health payload', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ ok: true }), { status: 200 });
  try {
    assert.equal(await checkEngine(), true);
  } finally {
    globalThis.fetch = original;
  }
  globalThis.fetch = async () => new Response(JSON.stringify({ ok: false }), { status: 200 });
  try {
    assert.equal(await checkEngine(), false);
  } finally {
    globalThis.fetch = original;
  }
});
