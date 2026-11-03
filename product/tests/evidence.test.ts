import { test } from 'node:test';
import assert from 'node:assert/strict';
import { HISTORICAL_LEDGER, PROVENANCE_META, armScoreText, compiledScoreText, gateAuditText, metaArmScoreText, parseCompiled, parseVikunjaSummary, provenanceClass, vikunjaRecord } from '../src/evidence.ts';
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
  assert.equal(armScoreText(byArm.get('H_hybrid')!), '3/6');
  assert.equal(byArm.get('H_hybrid')!.provenance, 'model-authored');
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
  assert.match(present.detail, /bounded browser slice is recorded/);
  assert.match(present.detail, /execution remains unavailable/);
  assert.equal(present.status, 'unavailable');
  assert.equal(capabilityEnabled(present), false);
  assert.notEqual(present.detail, absent.detail);
  // Picker resolution keeps API/CLI untouched and never enables browser execution.
  const caps = targetCapabilities(false);
  assert.equal(caps.length, 3);
  assert.equal(capabilityEnabled(caps.find(cap => cap.id === 'browser-motion')!), false);
});

test('Meta REAL_MODEL Vikunja arms: C 2/6 (1,3), D 1/6 (3), 3 calls, packet matched', () => {
  const r = vikunjaRecord(); assert.ok(r); assert.ok(r.metaArms);
  assert.equal(r.metaArms.label, 'REAL_MODEL'); assert.equal(r.metaArms.model, 'muse-spark-1.3');
  assert.equal(r.metaArms.callsTotal, 3); assert.equal(r.metaArms.packetDigestsMatched, true);
  assert.equal(r.metaArms.reservationCapUsd, 0.5); assert.equal(r.metaArms.artifact, '.runs/vikunja-model/meta_arms_result.json');
  const by = new Map(r.metaArms.arms.map(a => [a.arm, a]));
  assert.equal(metaArmScoreText(by.get('C_grounded')!), '2/6'); assert.deepEqual(by.get('C_grounded')!.passedCases, [1, 3]);
  assert.equal(metaArmScoreText(by.get('D_active')!), '1/6'); assert.deepEqual(by.get('D_active')!.passedCases, [3]);
  assert.deepEqual(by.get('D_active')!.selectedProbes, ['D1', 'D4', 'D5', 'D6', 'D7']); assert.equal(by.get('D_active')!.probeObservations, 22);
  for (const a of r.metaArms.arms) { assert.equal(a.label, 'REAL_MODEL'); assert.equal(a.provenance, 'model-authored'); }
  // Never conflated with Gemma arms or the 14/25 ledger.
  for (const a of r.arms) assert.equal(a.label, 'GEMMA_TEST');
  assert.equal(HISTORICAL_LEDGER.total, 25);
});
test('Gemma H re-measured 3/6 (0,2,3), repair regressed to 2/6, D selection verified but unscored', () => {
  const r = vikunjaRecord(); assert.ok(r);
  const by = new Map(r.arms.map(a => [a.arm, a]));
  assert.deepEqual(by.get('H_hybrid')!.passedCases, [0, 2, 3]); assert.equal(armScoreText(by.get('H_hybrid')!), '3/6');
  assert.ok(r.gemmaRepair); assert.equal(r.gemmaRepair.label, 'GEMMA_TEST'); assert.equal(r.gemmaRepair.passed, 2); assert.equal(r.gemmaRepair.total, 6);
  assert.equal(r.gemmaRepair.outcome, 'admitted_but_regressed');
  const d = by.get('D_active')!; assert.equal(d.selectionVerified, true); assert.equal(d.probeCount, 6); assert.equal(d.probeObservations, 27);
  assert.equal(d.status, 'provider_failure'); assert.equal(d.passed, null); assert.equal(d.failureClass, 'INFRASTRUCTURE'); assert.match(armScoreText(d), /Not scored/);
});
test('gate audit is NON_AI damage-prevention, never a model score: 0/8 kept, 5 regressed, 3 tied', () => {
  const r = vikunjaRecord(); assert.ok(r); assert.ok(r.gateAudit);
  assert.equal(r.gateAudit.label, 'NON_AI'); assert.equal(r.gateAudit.isModelScore, false);
  assert.equal(r.gateAudit.editsConsidered, 8); assert.equal(r.gateAudit.kept, 0); assert.equal(r.gateAudit.regressed, 5); assert.equal(r.gateAudit.tied, 3);
  assert.equal(r.gateAudit.gatedCandidate.label, 'EVIDENCE_COMPILED'); assert.equal(r.gateAudit.gatedCandidate.parentLabel, 'NON_AI');
  assert.equal(r.gateAudit.gatedCandidate.passed, 6); assert.equal(r.gateAudit.gatedCandidate.total, 6);
  assert.match(gateAuditText(r.gateAudit), /not a model score/);
});
test('new sections fail closed when relabeled or distorted', () => {
  const metaBad = structuredClone(summary) as Record<string, unknown>;
  ((metaBad.metaArms as Record<string, unknown>).arms as Record<string, unknown>[])[0]!.label = 'GEMMA_TEST';
  assert.equal(parseVikunjaSummary(metaBad), null);
  const gateBad = structuredClone(summary) as Record<string, unknown>;
  (gateBad.gateAudit as Record<string, unknown>).isModelScore = true;
  assert.equal(parseVikunjaSummary(gateBad), null);
  const gateSum = structuredClone(summary) as Record<string, unknown>;
  (gateSum.gateAudit as Record<string, unknown>).kept = 1;
  assert.equal(parseVikunjaSummary(gateSum), null);
  const repairBad = structuredClone(summary) as Record<string, unknown>;
  (repairBad.gemmaRepair as Record<string, unknown>).label = 'REAL_MODEL';
  assert.equal(parseVikunjaSummary(repairBad), null);
  const casesBad = structuredClone(summary) as Record<string, unknown>;
  (((casesBad.metaArms as Record<string, unknown>).arms as Record<string, unknown>[])[0]).passedCases = [1];
  assert.equal(parseVikunjaSummary(casesBad), null);
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
