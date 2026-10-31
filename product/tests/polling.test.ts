import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ApiError } from '../src/api.ts';
import { pollFailureMessage, pollRetryDelay } from '../src/polling.ts';

test('polling failures label stale status and rate limits receive a longer delay', () => {
  const limited = new ApiError(429, 'RATE_LIMITED', 'Too many requests. Wait before trying again.');
  assert.match(pollFailureMessage(limited.message), /displayed status may be out of date/);
  assert.match(pollFailureMessage(limited.message), /Too many requests/);
  assert.equal(pollRetryDelay(limited.status), 60_000);
  assert.equal(pollRetryDelay(503), 15_000);
  assert.match(pollFailureMessage(), /service could not be reached/);
});
