import assert from 'node:assert/strict';
import test from 'node:test';
import { SCOREBOARD, SOURCE_OPTIONS, buildManifest, buildReadme, buildReportHtml, buildReportMarkdown, runOutcome, stageIndex } from '../src/workbench.ts';

test('source catalog labels assisted vs black-box and gates availability', () => {
  const url = SOURCE_OPTIONS.find(s => s.id === 'url')!;
  assert.equal(url.mode, 'black-box');
  assert.equal(url.available, false);
  assert.ok(url.unavailableReason?.length);
  const github = SOURCE_OPTIONS.find(s => s.id === 'github')!;
  assert.equal(github.mode, 'source-assisted');
  assert.equal(SOURCE_OPTIONS.find(s => s.id === 'local')!.available, true);
  assert.equal(SOURCE_OPTIONS.find(s => s.id === 'recorded')!.available, true);
});

test('runOutcome distinguishes passed partial failed cancelled', () => {
  assert.equal(runOutcome('completed', { passed: 6, failed: 0, indeterminate: 0, total: 6 }), 'passed');
  assert.equal(runOutcome('completed', { passed: 4, failed: 2, indeterminate: 0, total: 6 }), 'partial');
  assert.equal(runOutcome('completed', { passed: 0, failed: 6, indeterminate: 0, total: 6 }), 'failed');
  assert.equal(runOutcome('cancelled', null), 'cancelled');
  assert.equal(runOutcome('needs_reconciliation', null), 'needs-attention');
  assert.equal(runOutcome(null, null), 'not-started');
});

test('stageIndex follows pipeline order without inventing stages', () => {
  assert.equal(stageIndex('capture'), 0);
  assert.equal(stageIndex('execute'), 3);
  assert.equal(stageIndex(null), -1);
  assert.equal(stageIndex('thinking'), -1);
});

test('report builders use only supplied report data', () => {
  const report = { origin: 'mock', real: false, evaluation: { passed: 3, failed: 1, indeterminate: 0, total: 4 }, scope_digest: 'a'.repeat(64) };
  const meta = { runId: 'run-1', investigationTitle: 'Ledger check', generatedFrom: 'GET /v1/runs/{id}/report' };
  assert.match(buildReportMarkdown(report, meta), /3 passed/);
  assert.match(buildReportHtml(report, meta), /Ledger check/);
  assert.match(buildManifest(report, meta), /second-source-export-manifest/);
  assert.match(buildReadme(report, meta), /3\/4 passed/);
  const empty = buildReportMarkdown({ origin: 'mock', real: false }, meta);
  assert.match(empty, /counts unavailable/);
});

test('scoreboard separates AI, hybrid and NON_AI per target', () => {
  const vik = SCOREBOARD.find(t => t.target.startsWith('Vikunja'))!;
  const methods = vik.rows.map(r => r.method);
  assert.ok(methods.some(m => m.startsWith('AI alone')));
  assert.ok(methods.some(m => m.startsWith('AI + our software')));
  assert.ok(methods.some(m => m.startsWith('Our software alone')));
  assert.ok(vik.rows.every(r => ['REAL_MODEL', 'NON_AI'].includes(r.provenance))); assert.ok(vik.rows.every(r => !/gemma/i.test(r.method)));
  const fb = SCOREBOARD.find(t => t.target.startsWith('File Browser'))!;
  assert.equal(fb.rows[0].provenance, 'REAL_MODEL');
  assert.equal(fb.rows[0].frozen, '3/7');
  assert.equal(fb.rows[1].frozen, '7/7');
  const gt = SCOREBOARD.find(t => t.target.startsWith('Gitea'))!;
  assert.match(gt.rows[0].frozen, /6\/6/);
});
