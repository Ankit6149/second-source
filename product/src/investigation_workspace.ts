import type { Investigation, Target, Run, RunEvent, Verification } from './api';
import { runOutcome, OUTCOME_LABEL } from './workbench.ts';

export interface WorkspaceView {
  investigation: Investigation;
  target: Target | null;
  run: Run | null;
  events: RunEvent[];
  verification: Verification | null;
  notes: string[];
  actionsHtml: string;
}

const escapeHtml = (v: unknown): string => String(v ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] || c));

const orderedStages = ['capture', 'organize', 'distill', 'execute'] as const;
const titleStage: Record<string,string> = {
  capture: 'Capture observations', organize: 'Organize evidence',
  distill: 'Distill behavior', execute: 'Execute & verify'
};
const eventLabels: Record<string,string> = {
  run_queued: 'Run queued', run_claimed: 'Worker claimed the run',
  stage_started: 'Stage started', repair_started: 'Bounded control retry started',
  repair_completed: 'Bounded control retry finished', run_completed: 'Run completed',
  run_failed: 'Run failed', run_cancelled: 'Run cancelled',
  run_needs_reconciliation: 'Run needs reconciliation'
};

/** All data comes from actual saved backend responses. This is NOT an AI simulation. */
export function renderInvestigationWorkspace(view: WorkspaceView): string {
  const { investigation: item, target, run, verification, notes, actionsHtml } = view;
  const events = [...view.events].sort((a,b) => a.event_id - b.event_id);
  const evaluation = verification?.evaluation ?? run?.result?.evaluation ?? null;
  const outcome = runOutcome(run?.status, evaluation);
  const currentStage = run?.stage || null;
  const startedStages = new Set(events.filter(e => e.event_type === 'stage_started' && e.stage).map(e => e.stage));
  const stages = orderedStages.map((stage, index) => {
    const observed = startedStages.has(stage);
    const current = run?.status === 'running' && currentStage === stage;
    return `<div class="run-step ${current ? 'is-current' : observed ? 'is-observed' : ''}">
      <span class="run-step-number">0${index+1}</span>
      <span class="run-step-copy"><strong>${titleStage[stage]}</strong><small>${current ? 'Active in backend' : observed ? 'Stage event recorded' : 'Not observed'}</small></span>
      <span class="run-step-indicator" aria-label="${current ? 'Current stage' : observed ? 'Recorded stage' : 'Not started'}"></span></div>`;
  }).join('');

  const activity = events.length ? `<ol class="run-event-list">${events.slice(-40).map(event => `
      <li class="run-event"><span class="run-event-sequence">#${event.event_id}</span><div>
        <strong>${escapeHtml(eventLabels[event.event_type] || event.event_type.replaceAll('_', ' '))}</strong>
        <span>${event.stage ? escapeHtml(event.stage) + ' · ' : ''}${escapeHtml(event.created_at || 'Timestamp unavailable')}</span>
      </div></li>`).join('')}</ol>`
    : '<p class="work-empty">No execution events have been recorded for this run yet. Nothing is simulated.</p>';

  const countView = evaluation
    ? `<div class="work-metrics"><div><strong>${evaluation.passed}</strong><span>Passed</span></div><div><strong>${evaluation.failed}</strong><span>Failed</span></div><div><strong>${evaluation.indeterminate}</strong><span>Indeterminate</span></div><div><strong>${evaluation.total}</strong><span>Evaluated</span></div></div>`
    : '<p class="work-empty">An independent evaluation has not been returned by the backend for this run.</p>';

  const repair = verification?.repair;
  const versions = repair?.versions.length
    ? `<ol class="work-versions">${repair.versions.map(version => `<li><span>Candidate round ${version.round}</span><strong>${version.evaluation.passed}/${version.evaluation.total} passed</strong><code title="Candidate digest">${escapeHtml(version.candidate_digest.slice(0, 22))}…</code></li>`).join('')}</ol>
      <p class="work-small">Selected: ${escapeHtml(repair.selected_version)} · ${escapeHtml(repair.verdict.replaceAll('_', ' '))}</p>`
    : '<p class="work-empty">Candidate lineage is not yet available. This interface will not invent generated code or hidden test cases.</p>';

  return `<section class="investigation-workspace" aria-label="Investigation workspace">
    <div class="work-hero">
      <div><div class="work-eyebrow">AUTHORIZED INVESTIGATION / CONTROL WORKSPACE</div>
        <h1>${escapeHtml(item.title)}</h1>
        <p>${escapeHtml(target?.label || 'Supported target not connected')} · ${escapeHtml(item.status)} scope · Candidate origin: <strong>NON_AI fixture</strong></p>
      </div>
      <div class="work-status"><span class="work-status-label">ACTUAL BACKEND STATE</span><strong>${run ? `Run: ${escapeHtml(run.status)}` : 'Not started'}</strong><span class="artifact-tag">${escapeHtml(run?.status || 'not started')}</span><small>${escapeHtml(OUTCOME_LABEL[outcome])}</small></div>
    </div>
    <div class="work-context" aria-label="Investigation boundaries">
      <div><span>Approved scope digest</span><code title="${escapeHtml(item.scope_digest)}">${escapeHtml(item.scope_digest.slice(0,20))}…</code></div>
      <div><span>Investigation ID</span><code>${escapeHtml(item.investigation_id)}</code></div>
      <div><span>Run ID</span><code>${run ? escapeHtml(run.run_id) : 'Not queued'}</code></div>
    </div>
    <div class="work-grid">
      <section class="work-panel work-progress" aria-label="Execution progression">
        <div class="work-panel-head"><div><span class="work-eyebrow">01 / PROCESS</span><h2>Execution stages</h2></div><span class="work-tag">BACKEND EVENTS</span></div>
        <div class="run-steps">${stages}</div>
        ${run?.error_code ? `<p class="work-error" role="alert">Backend error: ${escapeHtml(run.error_code)}</p>` : ''}
        ${run?.status === 'needs_reconciliation' ? '<p class="work-error" role="status">Execution is uncertain and requires operator reconciliation. No automatic retry.</p>' : ''}
        <div class="work-action-region">${run?.status === 'completed' ? '<p class="work-small">Execution completed. Review the evidence, inspect available candidate lineage, and export the report below.</p>' : actionsHtml}</div>
      </section>
      <section class="work-panel" aria-label="Observed backend activity">
        <div class="work-panel-head"><div><span class="work-eyebrow">02 / OBSERVATIONS</span><h2>Execution log</h2></div><span class="work-tag">${events.length} EVENTS</span></div>
        ${events.length ? `<details class="activity work-activity" open><summary>Recorded activity (${events.length})</summary>${activity}</details>` : activity}
        <p class="work-small">Only persisted lifecycle events are shown. Detailed reference inputs or outputs cannot be inferred from these status events alone.</p>
      </section>
      <section class="work-panel work-wide" aria-label="Independent verification">
        <div class="work-panel-head"><div><span class="work-eyebrow">03 / EVALUATION</span><h2>Independent verification</h2></div><span class="work-tag">NON_AI · RECORDED BY SERVICE</span></div>
        ${countView}
        <div class="work-action-row">${verification?.evaluation ? '<button type="button" class="pill-btn" data-action="verification">View verification details</button>' : '<span class="work-small">Detailed verification unlocks when the service returns its verification record.</span>'}<button type="button" class="pill-btn" data-action="compare">Compare results</button>${run?.status === 'completed' ? '<button type="button" class="pill-btn" data-action="report">Open report</button>' : ''}<button type="button" class="pill-btn" data-action="reports">Reports &amp; exports</button></div>
      </section>
      <section class="work-panel" aria-label="Generated candidate status">
        <div class="work-panel-head"><div><span class="work-eyebrow">04 / OUTPUT</span><h2>Candidate &amp; lineage</h2></div><span class="work-tag">SCOPE-BOUND</span></div>
        ${versions}
        <div class="work-action-row">${repair?.versions.length ? '<button type="button" class="pill-btn" data-action="candidate">Inspect available candidate</button>' : '<span class="work-small">No candidate lineage is exposed for inspection yet.</span>'}${run?.status === 'completed' ? '<button type="button" class="pill-btn" data-action="export">Download integrity export</button>' : ''}</div>
        <p class="work-small">Private candidate source, sealed evaluator cases and credentials are not exposed by this service. Preview shows only authorized data.</p>
      </section>
      <section class="work-panel" aria-label="Investigation notes">
        <div class="work-panel-head"><div><span class="work-eyebrow">05 / YOUR NOTES</span><h2>Investigation notebook</h2></div><span class="work-tag">THIS TAB ONLY</span></div>
        ${notes.length ? `<ol class="work-notes">${notes.slice(-30).map(note => `<li>${escapeHtml(note)}</li>`).join('')}</ol>` : '<p class="work-empty">Your notes appear here. The note field below does not send prompts to a model.</p>'}
        <p class="work-small">Notes are private to this browser tab, not persisted by the investigation backend and not AI responses.</p>
      </section>
    </div>
  </section>`;
}
