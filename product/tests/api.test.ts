import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Api, ApiError, validatedOrigin, type Run } from '../src/api.ts';
import { detectReference } from '../src/reference.ts';

const run: Run = { run_id: '12345678-1234-1234-1234-123456789abc', investigation_id: '12345678-1234-1234-1234-123456789abc', status: 'queued', stage: null, revision: 1, created_at: '2026-01-01T00:00:00Z', cancel_requested: false, error_code: null, result: null };

test('origins are fixed HTTPS origins, with localhost only in development', () => {
  assert.equal(validatedOrigin('https://api.example'), 'https://api.example');
  for (const value of ['https://user:pass@api.example', 'https://api.example/path', 'http://api.example', 'https://api.example?token=x']) assert.equal(validatedOrigin(value), '');
  assert.equal(validatedOrigin('http://127.0.0.1:8000', true), 'http://127.0.0.1:8000');
  assert.equal(validatedOrigin('http://127.0.0.1:8000'), '');
});

test('target hints never resolve or authorize a URL', () => {
  assert.match(detectReference('https://example.org/account')?.description || '', /not visited or authorized/);
  assert.match(detectReference('example.org')?.description || '', /not verified or visited/);
  assert.equal(detectReference('desktop application'), null);
});

test('run execution sends the current revision once and never a repair limit', async () => {
  const calls: { url: string; options: RequestInit }[] = [];
  const transport = (async (url: string | URL | Request, options?: RequestInit) => {
    calls.push({ url: String(url), options: options || {} });
    return new Response(JSON.stringify(run), { status: 200, headers: { 'content-type': 'application/json' } });
  }) as typeof fetch;
  const api = new Api('https://api.example', () => 'token', transport);
  await api.execute(run);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `https://api.example/v1/runs/${run.run_id}/execute`);
  assert.deepEqual(JSON.parse(String(calls[0].options.body)), { expected_revision: 1 });
  assert.equal((calls[0].options.headers as Record<string, string>).Authorization, 'Bearer token');
  assert.equal(calls[0].options.credentials, 'omit');
});

test('uncertain execution is surfaced without an automatic retry', async () => {
  let calls = 0;
  const transport = (async () => { calls++; throw new Error('connection lost'); }) as typeof fetch;
  const api = new Api('https://api.example', () => 'token', transport);
  await assert.rejects(api.execute(run), (error: unknown) => error instanceof ApiError && error.uncertain && error.code === 'NETWORK_UNCERTAIN');
  assert.equal(calls, 1);
});

test('authorization, conflicts, rate limits and outages stay distinct', async () => {
  for (const status of [401, 409, 429, 503]) {
    const api = new Api('https://api.example', () => 'token', (async () => new Response('{}', { status })) as typeof fetch);
    await assert.rejects(api.run(run.run_id), (error: unknown) => error instanceof ApiError && error.status === status);
  }
});

test('oversized response is refused and invalid resource identifiers never dispatch', async () => {
  let calls = 0;
  const api = new Api('https://api.example', () => 'token', (async () => { calls++; return new Response('x'.repeat(2_000_001)); }) as typeof fetch);
  await assert.rejects(api.session(), (error: unknown) => error instanceof ApiError);
  assert.throws(() => api.run('../private'));
  assert.equal(calls, 1);
});

test('pagination and event cursors use the documented bounded endpoints', async () => {
  const urls: string[] = [];
  const api = new Api('https://api.example', () => 'token', (async (url: string | URL | Request) => {
    urls.push(String(url));
    return new Response(JSON.stringify({ items: [], next_after: null }));
  }) as typeof fetch);
  await api.investigations('cursor-1');
  await api.runs(run.investigation_id, 'cursor-2');
  await api.events(run.run_id, 42);
  assert.deepEqual(urls.map(url => new URL(url).search), ['?limit=100&after=cursor-1', '?limit=100&after=cursor-2', '?after=42&limit=500']);
  assert.throws(() => api.investigations('../escape'));
  assert.throws(() => api.events(run.run_id, -1));
});

test('untrusted error correlation values are not reflected', async () => {
  const api = new Api('https://api.example', () => 'token', (async () => new Response(JSON.stringify({ correlation_id: 'private-content' }), { status: 500 })) as typeof fetch);
  await assert.rejects(api.execute(run), (error: unknown) => error instanceof ApiError && error.uncertain && error.correlationId === '');
});
