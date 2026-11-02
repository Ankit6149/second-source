import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ApiError } from '../src/api.ts';
import { acceptsRunRevision, executionDefinitelyRefused, outcomeConfirmed, pollFailureMessage, pollRetryDelay } from '../src/polling.ts';

test('polling failures label stale status and rate limits receive a longer delay', () => {
  const limited = new ApiError(429, 'RATE_LIMITED', 'Too many requests. Wait before trying again.');
  assert.match(pollFailureMessage(limited.message), /displayed status may be out of date/);
  assert.match(pollFailureMessage(limited.message), /Too many requests/);
  assert.equal(pollRetryDelay(limited.status), 60_000);
  assert.equal(pollRetryDelay(503), 15_000);
  assert.match(pollFailureMessage(), /service could not be reached/);
});

test('run snapshots cannot move backward or cross run identities', () => {
  const current = { run_id: 'run-a', revision: 5 };
  assert.equal(acceptsRunRevision(current, { run_id: 'run-a', revision: 4 }), false);
  assert.equal(acceptsRunRevision(current, { run_id: 'run-a', revision: 5 }), true);
  assert.equal(acceptsRunRevision(current, { run_id: 'run-a', revision: 6 }), true);
  assert.equal(acceptsRunRevision(current, { run_id: 'run-b', revision: 6 }), false);
  assert.equal(acceptsRunRevision(current, { run_id: 'run-a', revision: NaN }), false);
});

test('only known pre-dispatch refusals release execution uncertainty', () => {
  assert.equal(executionDefinitelyRefused(429, 'RATE_LIMITED'), true);
  assert.equal(executionDefinitelyRefused(409, 'REVISION_CONFLICT'), true);
  assert.equal(executionDefinitelyRefused(409, 'EXECUTION_DISABLED'), true);
  assert.equal(executionDefinitelyRefused(401, 'UNAUTHENTICATED'), true);
  for (const [status, code] of [[429, 'OTHER'], [408, 'TIMEOUT'], [503, 'BUSY'], [0, 'NETWORK_UNCERTAIN']] as const)
    assert.equal(executionDefinitelyRefused(status, code), false);
});

test('quarantined and active runs never resolve an uncertain outcome', () => {
  assert.equal(outcomeConfirmed('needs_reconciliation'), false);
  assert.equal(outcomeConfirmed('running'), false);
  assert.equal(outcomeConfirmed('queued'), false);
  for (const status of ['completed', 'failed', 'cancelled']) assert.equal(outcomeConfirmed(status), true);
});
