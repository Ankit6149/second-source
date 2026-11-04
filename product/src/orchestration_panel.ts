import type { OrchestrationWorkspace, OrchestrationEvent } from './api';

export interface OrchestrationEvidenceView {
  id: string;
  workspace: OrchestrationWorkspace | null;
  events: OrchestrationEvent[];
}

const escapeHtml = (v: unknown): string => String(v ?? '').replace(/[&<>"']/g,
  c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c] || c));

/** Strictly source-backed NON_AI scope construction; never invent observations. */
export function renderOrchestrationEvidence(evidence: OrchestrationEvidenceView | null): string {
  if (!evidence) return '';
  const candidate = evidence.workspace?.candidate;
  const verification = evidence.workspace?.verification;
  const artifacts = evidence.workspace?.artifacts ?? [];
  const eventRows = [...evidence.events].sort((a,b) => a.event_id - b.event_id);
  const routes = candidate?.routes ?? [];
  const routeBody = candidate
    ? routes.length
      ? `<ol class="orch-routes">${routes.map(route => `<li><code>${escapeHtml(route.method)} ${escapeHtml(route.path_template)}</code><span>${escapeHtml(route.kind)}</span></li>`).join('')}</ol>`
      : '<p class="work-empty">The generated declarative specification contains no routes.</p>'
    : '<p class="work-empty">A candidate has not been returned by the connected engine. The event record below may still be available.</p>';
  const countBody = verification
    ? `<p class="orch-checks"><strong>${verification.passed} / ${verification.total}</strong> structural checks · ${verification.failed} failed · ${verification.indeterminate} indeterminate</p>`
    : '<p class="work-small">Verification is not yet available. No score is inferred.</p>';
  return `<section class="work-panel work-wide orch-inspector" aria-label="Scope-derived engine artifacts">
    <div class="work-panel-head"><div><span class="work-eyebrow">06 / ACTUAL CONSTRUCTION</span>
      <h2>What the engine built</h2></div><span class="work-tag">NON_AI · SCOPE-DERIVED</span></div>
    <p class="work-small">These items come from an authorized orchestration run, not simulated chat output. The candidate is a <strong>declarative scope-derived specification</strong>, not a complete website or recovered source. This executor performed no live reference probing and no Meta-model inference.</p>
    <div class="orch-summary">
      <div><span>Candidate identity</span><code>${escapeHtml(candidate?.candidate_id || 'Not returned')}</code></div>
      <div><span>Routes generated</span><strong>${candidate ? routes.length : 'Unavailable'}</strong></div>
      <div><span>Verification type</span><strong>Structural only</strong></div>
    </div>
    <div class="orch-two-column">
      <div><h3>Generated specification</h3>${routeBody}
        <p class="work-small">Route matching alone does not establish behavioral equivalence.</p>
        ${candidate ? '<button type="button" class="pill-btn" data-action="candidate">Inspect exact candidate JSON</button>' : ''}
      </div>
      <div><h3>Recorded construction events</h3>
        ${eventRows.length ? `<ol class="orch-events">${eventRows.slice(-30).map(event => `<li><span class="orch-event-id">#${event.event_id}</span><div><strong>${escapeHtml(event.event_type.replaceAll('_',' '))}</strong><small>${escapeHtml(event.status || 'UNSPECIFIED')} · ${escapeHtml(event.stage || 'lifecycle')}${event.detail ? ' · ' + escapeHtml(event.detail) : ''}</small></div></li>`).join('')}</ol>` : '<p class="work-empty">No engine events have been returned.</p>'}
      </div>
    </div>
    <div><h3>Structural verification</h3>${countBody}</div>
    <div class="orch-downloads"><h3>Actual generated artifacts</h3>
    ${artifacts.length ? `<ul>${artifacts.map(a => `<li><div><strong>${escapeHtml(a.name)}</strong><small>${escapeHtml(a.kind)} · ${a.size_bytes} bytes · SHA-256 ${escapeHtml(a.sha256.slice(0,16))}…</small></div><button type="button" class="pill-btn" data-action="download-orch-artifact" data-artifact-id="${escapeHtml(a.artifact_id)}">Download</button></li>`).join('')}</ul>` : '<p class="work-empty">The engine has not returned any downloadable artifacts yet.</p>'}
    </div>
  </section>`;
}
