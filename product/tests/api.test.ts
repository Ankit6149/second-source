import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Api, ApiError, validatedOrigin, type Run } from '../src/api.ts';
import { detectReference } from '../src/reference.ts';
import { supportedTarget, supportedTargets } from '../src/targets.ts';

const run: Run = { run_id: '12345678-1234-1234-1234-123456789abc', investigation_id: '12345678-1234-1234-1234-123456789abc', status: 'queued', stage: null, revision: 1, created_at: '2026-01-01T00:00:00Z', cancel_requested: false, error_code: null, result: null };

test('target discovery fails closed for unknown, malformed and ambiguous capabilities', () => {
  const scope = { scope_version: '1', target: { kind: 'cli', permission_ref: 'owned-fixture', reference_url: null, reference_command_id: 'owned-ledger-v1' }, goal: 'Reconstruct only the synthetic ledger CLI behaviors', mode: 'selected_flows', observation: { allowed_url_patterns: [], allowed_roles: ['guest'], permitted_actions: ['cli'], allowed_commands: ['list', 'total', 'remove', 'add'], authenticated_access: 'not_required' }, implementation: { route_patterns: [], required_flows: [], requirements: ['REQ-LEDGER'], allowed_subsystems: ['cli_ledger'], fidelity: ['behavioral'] }, exclusions: { url_patterns: [], subsystems: [], external_side_effects: [] }, budgets: { max_reference_experiments: 40, max_model_calls: 5, max_repair_rounds: 3, max_wall_seconds: 600, max_estimated_model_spend_usd: 0 } };
  const valid = { target_id: 'owned-ledger-v1', label: 'Owned ledger fixture', run_kind: 'g3_mock', origin: 'mock', real: false, execution_enabled: false, scope, scope_digest: 'dbf5a0d74502ed6662f551e57ad25ecb902c8c15439186fa5173a54ad9c25c53' };
  assert.deepEqual(supportedTarget([valid]), valid);
  assert.equal(supportedTarget([valid, valid]), null);
  for (const input of [null, {}, [null], [valid, { ...valid, run_kind: 'g3_real' }], [{ ...valid, target_id: 'future-http' }], [{ ...valid, run_kind: 'g3_real' }], [{ ...valid, execution_enabled: 'true' }], [{ ...valid, scope_digest: 'bad' }], [{ ...valid, scope: [] }], [{ ...valid, scope: {} }], [{ ...valid, scope: { ...scope, budgets: { ...scope.budgets, max_estimated_model_spend_usd: 1 } } }]])
    assert.equal(supportedTarget(input), null);
});

test('HTTP target is accepted only for the exact nonbillable loopback scope', () => {
  const scope = { scope_version: '1', target: { kind: 'http', permission_ref: 'owned-http-task-workflow-v1', reference_url: 'http://127.0.0.1:8000/', reference_command_id: null }, goal: 'Reconstruct the owned stateful HTTP task-workflow API service', mode: 'selected_flows', observation: { allowed_url_patterns: ['/v1/tasks', '/v1/tasks/*'], allowed_roles: ['bob', 'admin', 'alice', 'viewer', 'guest'], permitted_actions: ['http_patch', 'http_delete', 'http_get', 'http_post'], allowed_commands: [], authenticated_access: 'authorized_test_account' }, implementation: { route_patterns: ['/v1/tasks', '/v1/tasks/*'], required_flows: ['task_crud', 'task_transitions', 'task_rbac', 'task_query'], requirements: ['REQ-HTTP-TASKS'], allowed_subsystems: ['http_task_workflow'], fidelity: ['behavioral'] }, exclusions: { url_patterns: ['/__admin/**'], subsystems: ['billing', 'external_webhooks', 'real_oauth'], external_side_effects: ['email', 'webhook'] }, budgets: { max_reference_experiments: 40, max_model_calls: 10, max_repair_rounds: 2, max_wall_seconds: 600, max_estimated_model_spend_usd: 0 } };
  const target = { target_id: 'owned-http-task-workflow-v1', label: 'Owned HTTP task-workflow fixture', run_kind: 'g3_mock', origin: 'mock', real: false, execution_enabled: true, scope, scope_digest: '190a19810a956c5626594bd6d48f7b6d37d3355e28ffaa50f177d6df6c85f8fe' };
  assert.deepEqual(supportedTargets([target]), [target]);
  assert.deepEqual(supportedTargets([target, target]), []);
  assert.deepEqual(supportedTargets([{ ...target, scope: { ...scope, target: { ...scope.target, reference_url: 'https://example.com/' } } }]), []);
  assert.deepEqual(supportedTargets([{ ...target, scope: { ...scope, budgets: { ...scope.budgets, max_estimated_model_spend_usd: 1 } } }]), []);
});

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
