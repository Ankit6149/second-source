import { test } from 'node:test';
import assert from 'node:assert/strict';
import { HISTORICAL_LEDGER, armScoreText, parseVikunjaSummary, vikunjaRecord } from '../src/evidence.ts';
import { TARGET_CAPABILITIES, capabilityEnabled } from '../src/capabilities.ts';
import summary from '../src/evidence-summary.json' with { type: 'json' };

test('committed Vikunja summary parses with exact GEMMA_TEST / NON_AI labels', () => {
  const record = vikunjaRecord();
  assert.ok(record, 'sanitized summary must be available at build time');
  assert.equal(record.provider, 'gemma-test');
  assert.equal(record.classification, 'PIPELINE_SMOKE_NOT_META');
  assert.equal(record.oracle.label, 'NON_AI');
  assert.equal(record.oracle.passed, 6);
  assert.equal(record.oracle.total, 6);
  for (const arm of record.arms) assert.equal(arm.label, 'GEMMA_TEST');
});

test('Gemma arms: A scored 0/6, C scored 2/6, B and D are unscored provider failures', () => {
  const record = vikunjaRecord();
  assert.ok(record);
  const byArm = new Map(record.arms.map(arm => [arm.arm, arm]));
  assert.equal(armScoreText(byArm.get('A_prior')!), '0/6');
  assert.equal(armScoreText(byArm.get('C_grounded')!), '2/6');
  for (const id of ['B_observations', 'D_active']) {
    const arm = byArm.get(id)!;
    assert.equal(arm.status, 'provider_failure');
    assert.equal(arm.passed, null);
    assert.match(armScoreText(arm), /Not scored/);
    assert.doesNotMatch(armScoreText(arm), /^0\//);
  }
});

test('historical ledger stays REAL_MODEL 14/25 and is never conflated with Vikunja', () => {
  assert.equal(HISTORICAL_LEDGER.label, 'REAL_MODEL');
  assert.equal(HISTORICAL_LEDGER.passed, 14);
  assert.equal(HISTORICAL_LEDGER.total, 25);
  const record = vikunjaRecord();
  assert.ok(record);
  assert.notEqual(record.arms[0].total, HISTORICAL_LEDGER.total);
});

test('malformed or relabeled summaries fail closed to unavailable', () => {
  assert.equal(parseVikunjaSummary(null), null);
  assert.equal(parseVikunjaSummary({}), null);
  assert.equal(parseVikunjaSummary({ ...summary, provider: 'meta' }), null);
  const relabeledOracle = structuredClone(summary) as Record<string, unknown>;
  (relabeledOracle.oracle as Record<string, unknown>).label = 'GEMMA_TEST';
  assert.equal(parseVikunjaSummary(relabeledOracle), null);
  const scoredFailure = structuredClone(summary) as Record<string, unknown>;
  ((scoredFailure.arms as Record<string, unknown>[])[1]).passed = 0;
  assert.equal(parseVikunjaSummary(scoredFailure), null);
  const relabeledArm = structuredClone(summary) as Record<string, unknown>;
  ((relabeledArm.arms as Record<string, unknown>[])[0]).label = 'REAL_MODEL';
  assert.equal(parseVikunjaSummary(relabeledArm), null);
});

test('capability flags: API and CLI supported and bounded, browser/motion unavailable', () => {
  assert.equal(TARGET_CAPABILITIES.length, 3);
  const byId = new Map(TARGET_CAPABILITIES.map(cap => [cap.id, cap]));
  assert.equal(byId.get('api-professional')!.status, 'supported');
  assert.equal(byId.get('cli-fixtures')!.status, 'supported');
  assert.equal(capabilityEnabled(byId.get('api-professional')!), true);
  assert.equal(capabilityEnabled(byId.get('cli-fixtures')!), true);
  const browser = byId.get('browser-motion')!;
  assert.equal(browser.status, 'unavailable');
  assert.equal(browser.action, null);
  assert.equal(capabilityEnabled(browser), false);
  assert.match(browser.detail, /adapter absent/i);
});
