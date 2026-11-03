import { test } from 'node:test';
import assert from 'node:assert/strict';
import { HISTORICAL_LEDGER, PROVENANCE_META, armScoreText, compiledScoreText, parseCompiled, parseVikunjaSummary, provenanceClass, vikunjaRecord } from '../src/evidence.ts';
import { BROWSER_SLICE_ABSENT_REASON, BROWSER_SLICE_OBSERVATIONS_PATH, TARGET_CAPABILITIES, capabilityEnabled, resolveBrowserMotionCapability, targetCapabilities } from '../src/capabilities.ts';
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

test('provenance renders distinctly: model-authored vs evidence-compiled vs runtime-supplied', () => {
  const record = vikunjaRecord();
  assert.ok(record);
  for (const arm of record.arms) assert.equal(arm.provenance, 'model-authored');
  assert.equal(record.oracle.provenance, 'runtime-supplied');
  assert.equal(record.compiled.provenance, 'evidence-compiled');
  assert.equal(HISTORICAL_LEDGER.provenance, 'model-authored');
  assert.equal(provenanceClass('model-authored'), 'prov-model-authored');
  assert.equal(provenanceClass('evidence-compiled'), 'prov-evidence-compiled');
  assert.equal(provenanceClass('runtime-supplied'), 'prov-runtime-supplied');
  assert.notEqual(PROVENANCE_META['model-authored'].label, PROVENANCE_META['evidence-compiled'].label);
  assert.notEqual(PROVENANCE_META['evidence-compiled'].label, PROVENANCE_META['runtime-supplied'].label);
});

test('EVIDENCE_COMPILED (NON_AI) is measured 6/6 with digest and never a model score', () => {
  const record = vikunjaRecord();
  assert.ok(record);
  assert.equal(record.compiled.label, 'EVIDENCE_COMPILED');
  assert.equal(record.compiled.parentLabel, 'NON_AI');
  assert.equal(record.compiled.status, 'available');
  assert.equal(record.compiled.passed, 6);
  assert.equal(record.compiled.total, 6);
  assert.equal(record.compiled.reason, null);
  assert.match(record.compiled.artifactSha256 || '', /^sha256:[0-9a-f]{64}$/);
  assert.equal(compiledScoreText(record.compiled), '6/6');
  // Absent block synthesizes the same honest pending state.
  assert.equal(parseCompiled(undefined)?.status, 'pending');
  // A pending block carrying a score, or a mislabeled block, fails closed.
  assert.equal(parseCompiled({ label: 'EVIDENCE_COMPILED', parentLabel: 'NON_AI', provenance: 'evidence-compiled', status: 'pending', reason: 'waiting', passed: 6, total: 6 }), null);
  assert.equal(parseCompiled({ label: 'REAL_MODEL', parentLabel: 'NON_AI', provenance: 'evidence-compiled', status: 'pending', reason: 'waiting', passed: null, total: null }), null);
  assert.equal(parseCompiled({ label: 'EVIDENCE_COMPILED', parentLabel: 'NON_AI', provenance: 'model-authored', status: 'pending', reason: 'waiting', passed: null, total: null }), null);
  // A genuine coordinator artifact validates only with bounded score + digest.
  const sha = `sha256:${'a'.repeat(64)}`;
  const available = parseCompiled({ label: 'EVIDENCE_COMPILED', parentLabel: 'NON_AI', provenance: 'evidence-compiled', status: 'available', reason: null, passed: 5, total: 6, artifact: 'browser-slice/compiled.json', artifactSha256: sha });
  assert.equal(available?.status, 'available');
  assert.equal(compiledScoreText(available!), '5/6');
});

test('browser/motion capability is driven by browser-slice observations presence', () => {
  assert.equal(BROWSER_SLICE_OBSERVATIONS_PATH, 'browser-slice/observations.json');
  const absent = resolveBrowserMotionCapability(false);
  assert.equal(absent.status, 'unavailable');
  assert.equal(absent.action, null);
  assert.equal(capabilityEnabled(absent), false);
  assert.equal(absent.detail, BROWSER_SLICE_ABSENT_REASON);
  assert.match(absent.detail, /browser-slice\/observations\.json not found/);
  assert.match(absent.detail, /adapter absent/i);
  const present = resolveBrowserMotionCapability(true);
  assert.match(present.detail, /Observations present/);
  assert.notEqual(present.detail, absent.detail);
  // Picker resolution keeps API/CLI untouched and never enables browser execution.
  const caps = targetCapabilities(false);
  assert.equal(caps.length, 3);
  assert.equal(capabilityEnabled(caps.find(cap => cap.id === 'browser-motion')!), false);
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
