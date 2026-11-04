import test from 'node:test';
import assert from 'node:assert/strict';
import { renderInvestigationWorkspace, type WorkspaceView } from '../src/investigation_workspace.ts';

const digest = 'a'.repeat(64);
const initial = (): WorkspaceView => ({
  investigation: { investigation_id: 'inv-1', title: 'Ledger reconstruction', scope: {}, scope_digest: digest, status: 'authorized', revision: 1, created_at: '2026-11-04T10:00:00Z' },
  target: { target_id: 'owned-ledger-v1', label: 'Owned ledger', run_kind: 'g3_mock', origin: 'mock', real: false, execution_enabled: true, scope: {}, scope_digest: digest },
  run: null, events: [], verification: null, notes: [], actionsHtml: '<button data-action="queue">Queue</button>'
});

test('workspace with no run does not pretend construction, evaluation or stage completion', () => {
  const html = renderInvestigationWorkspace(initial());
  assert.match(html, /Not started/);
  assert.doesNotMatch(html, /data-action="verification"/, 'verification must not be clickable before the evaluator returns a result');
  assert.match(html, /No execution events have been recorded/);
  assert.match(html, /No independent evaluation has been returned|An independent evaluation has not been returned/);
  assert.match(html, /Candidate lineage is not yet available/);
  assert.match(html, /Not observed/);
  assert.doesNotMatch(html, /<strong>6<\/strong><span>Passed/);
});

test('workspace shows only actual backend event progression and counts', () => {
  const view = initial();
  view.run = { run_id:'run-1', investigation_id:'inv-1', status:'completed', stage:'execute', revision:3, created_at:'2026-11-04T10:01:00Z', cancel_requested:false, error_code:null, result:{ origin:'mock', real:false, evaluation:{passed:22,failed:3,indeterminate:0,total:25}} };
  view.events = [
    {event_id:5,event_type:'run_completed',stage:'execute',created_at:'2026-11-04T10:02:00Z'},
    {event_id:1,event_type:'run_claimed',stage:null,created_at:'2026-11-04T10:01:00Z'},
    {event_id:3,event_type:'stage_started',stage:'execute',created_at:'2026-11-04T10:01:10Z'},
  ];
  const html = renderInvestigationWorkspace(view);
  assert.match(html, /22<\/strong><span>Passed/);
  assert.match(html, /data-action="verification"/, 'completed evaluated run exposes the real verification control');
  assert.match(html, /3<\/strong><span>Failed/);
  assert.match(html, /NON_AI fixture/);
  assert.ok(html.indexOf('#1') < html.indexOf('#3'));
  assert.ok(html.indexOf('#3') < html.indexOf('#5'));
  assert.match(html, /Stage event recorded/);
  assert.match(html, /Not observed/);
  assert.match(html, /No independent evaluation has been returned|<div class="work-metrics"/);
});

test('workspace retains explicit reconciliation and escaped untrusted titles and notes', () => {
  const view = initial();
  view.investigation.title = '<img src=x onerror=alert(1)>';
  view.notes = ['<script>bad</script>'];
  view.run = {run_id:'run-2',investigation_id:'inv-1',status:'needs_reconciliation',stage:'distill',revision:2,created_at:'2026-11-04T10:00:00Z',cancel_requested:false,error_code:'NETWORK_UNCERTAIN',result:null};
  const html = renderInvestigationWorkspace(view);
  assert.doesNotMatch(html, /<img|<script>/);
  assert.match(html, /&lt;img/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /requires operator reconciliation/);
  assert.match(html, /class="artifact-tag">needs_reconciliation<\/span>/);
  assert.match(html, /NETWORK_UNCERTAIN/);
});

test('candidate lineage exposes digests and evaluated rounds without private source', () => {
  const view = initial();
  view.verification = { origin:'mock', real:false, evaluation:{ passed:4, failed:1, indeterminate:0, total:5 }, repair_history_availability:'available', repair:{
    verdict:'partial', stop_reason:'budget', selected_version:'v2', selected_digest:'b'.repeat(64),
    versions:[{ round:1, candidate_digest:'c'.repeat(64), evaluation:{passed:3,failed:2,indeterminate:0,total:5} },
              { round:2, candidate_digest:'d'.repeat(64), evaluation:{passed:4,failed:1,indeterminate:0,total:5} }]
  }};
  const html=renderInvestigationWorkspace(view);
  assert.match(html,/Candidate round 1/);
  assert.match(html,/Candidate round 2/);
  assert.match(html,/4\/5 passed/);
  assert.match(html,/Selected: v2/);
  assert.doesNotMatch(html, /sealed case input|private source contents/);
});
