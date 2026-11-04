import assert from 'node:assert/strict';
import test from 'node:test';
import { renderOrchestrationEvidence, type OrchestrationEvidenceView } from '../src/orchestration_panel.ts';

test('missing engine evidence remains absent instead of a fabricated candidate', () => {
  assert.equal(renderOrchestrationEvidence(null), '');
});

test('only actual scoped routes, persisted stages and artifacts are rendered', () => {
  const item: OrchestrationEvidenceView = {
    id:'inv-123',
    workspace:{
      investigation_id:'inv-123',
      candidate:{candidate_id:'cand-123',source_observations_sha256:'a'.repeat(64),provenance:'NON_AI',routes:[
        {method:'HTTP',path_template:'/tasks',kind:'http-route'},
        {method:'HTTP',path_template:'/tasks/{id}',kind:'http-route'}]},
      verification:{passed:2,failed:0,indeterminate:0,total:2,origin:'mock',real:false},
      report:{report_id:'rep-123',stop_reason:'completed'},
      artifacts:[{artifact_id:'art-0123456789abcdef',name:'candidate.json',kind:'candidate',sha256:'b'.repeat(64),size_bytes:200,media_type:'application/json',created_at:'2026-11-04T10:00:00Z'}]
    },
    events:[{event_id:4,event_type:'delivery_ready',stage:null,created_at:'2026-11-04T10:01:00Z',status:'COMPLETED',provenance:'NON_AI',artifact_refs:['art-0123456789abcdef'],detail:'proof-bundle.zip'},
            {event_id:1,event_type:'stage_distill',stage:'distill',created_at:'2026-11-04T10:00:00Z',status:'RUNNING',provenance:'NON_AI',artifact_refs:[],detail:'routes=2'}]
  };
  const html = renderOrchestrationEvidence(item);
  assert.match(html,/What the engine built/);
  assert.match(html,/NON_AI · SCOPE-DERIVED/);
  assert.match(html,/not a complete website/);
  assert.match(html,/2 \/ 2/);
  assert.match(html,/structural checks/);
  assert.match(html,/HTTP \/tasks/);
  assert.match(html,/art-0123456789abcdef/);
  assert.match(html,/data-action="download-orch-artifact"/);
  assert.ok(html.indexOf('#1') < html.indexOf('#4'));
  assert.match(html,/Inspect exact candidate JSON/);
  assert.doesNotMatch(html,/Meta API call completed|Source code recovered/);
});

test('partial engine events never invent a candidate or score', () => {
  const item: OrchestrationEvidenceView = {
    id:'inv-pending',workspace:null,events:[{event_id:1,event_type:'stage_capture',stage:'capture',created_at:'',status:'RUNNING',provenance:'NON_AI',artifact_refs:[],detail:null}]
  };
  const html=renderOrchestrationEvidence(item);
  assert.match(html,/candidate has not been returned/);
  assert.match(html,/Verification is not yet available/);
  assert.doesNotMatch(html,/data-action="download-orch-artifact"/);
  assert.doesNotMatch(html,/data-action="candidate"/);
});

test('untrusted names and route paths are HTML-escaped', () => {
  const html=renderOrchestrationEvidence({
    id:'i',events:[],workspace:{investigation_id:'i',
      candidate:{candidate_id:'<img src=x>',source_observations_sha256:'a'.repeat(64),provenance:'NON_AI',routes:[
        {method:'GET',path_template:'<script>alert(1)</script>',kind:'http-route'}
      ]},
      verification:null,report:null,
      artifacts:[{artifact_id:'art-0123456789abcdef',name:'<img onerror=bad>',kind:'candidate',
        sha256:'b'.repeat(64),size_bytes:10,media_type:'application/json',created_at:''}]
    }});
  assert.doesNotMatch(html,/<script>|<img/);
  assert.match(html,/&lt;script&gt;/);
  assert.match(html,/&lt;img/);
});
