import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { Api, ApiError } from '../src/api.ts';

const token = 'a'.repeat(32) + '.' + 'b'.repeat(32) + '.' + 'c'.repeat(48);
const other = 'x'.repeat(32) + '.' + 'y'.repeat(32) + '.' + 'z'.repeat(48);

test('typed client completes the owned NON_AI HTTP journey against the local worker', { timeout: 240_000 }, async () => {
  const server = spawn(process.env.PYTHON || 'python', ['integration/local_backend.py'], { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  server.stderr.on('data', chunk => { stderr += String(chunk).slice(0, 4000); });
  try {
    const [chunk] = await Promise.race([
      once(server.stdout, 'data'),
      once(server, 'exit').then(() => { throw new Error(`Local test server exited: ${stderr}`); }),
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error('Local test server did not start')), 15_000)),
    ]);
    const port = /^PORT=(\d+)/.exec(String(chunk))?.[1];
    assert.ok(port, 'local test server returned a port');
    const origin = `http://127.0.0.1:${port}`;
    const api = new Api(origin, () => token);
    const outsider = new Api(origin, () => other);
    let ready = false;
    for (let attempt = 0; attempt < 30 && !ready; attempt++) {
      try { await api.session(); ready = true; } catch { await new Promise(resolve => setTimeout(resolve, 100)); }
    }
    assert.ok(ready, 'local API is ready');
    const [target] = await api.targets();
    assert.equal(target.execution_enabled, true);
    assert.equal(target.real, false);
    const created = await api.create('Local client acceptance', target.scope, 'client-create-1');
    assert.equal(created.scope_digest, target.scope_digest);
    const authorized = await api.authorize(created);
    assert.equal(authorized.status, 'authorized');
    const queued = await api.queue(created.investigation_id, 'client-run-1');
    assert.equal((await api.queue(created.investigation_id, 'client-run-1')).run_id, queued.run_id);
    assert.equal(queued.status, 'queued');
    await assert.rejects(outsider.run(queued.run_id), (error: unknown) => error instanceof ApiError && error.status === 404);
    const completed = await api.execute(queued);
    assert.equal(completed.status, 'completed');
    assert.equal(completed.result?.real, false);
    const verification = await api.verification(queued.run_id);
    assert.deepEqual(verification.evaluation, completed.result?.evaluation);
    assert.equal(verification.repair_history_availability, 'available');
    assert.ok((await api.events(queued.run_id)).items.length > 0);
    assert.ok((await api.report(queued.run_id)));
    assert.ok((await api.export(queued.run_id)).size > 0);
    await assert.rejects(outsider.export(queued.run_id), (error: unknown) => error instanceof ApiError && error.status === 404);
  } finally {
    server.kill();
  }
});
