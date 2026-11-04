/**
 * Workbench helpers: honest source catalog, run outcomes and report
 * exports built only from backend-returned data. Nothing here invents
 * observations, scores or candidate code.
 */
export type SourceMode = 'source-assisted' | 'black-box';
export interface SourceOption {
  id: 'url' | 'github' | 'upload' | 'docs' | 'local' | 'recorded';
  label: string;
  /** How reconstruction would treat this source if it were supported. */
  mode: SourceMode;
  modeLabel: string;
  detail: string;
  /** True only when a real backend surface backs the action today. */
  available: boolean;
  unavailableReason: string | null;
}

export const SOURCE_OPTIONS: readonly SourceOption[] = [
  { id: 'url', label: 'Live URL', mode: 'black-box', modeLabel: 'Black-box (behavior only)', detail: 'Observe a running service over HTTP without its source.', available: false, unavailableReason: 'Unavailable — the connected service only advertises owned fixtures; arbitrary URLs are never visited or authorized from this app.' },
  { id: 'github', label: 'GitHub repository', mode: 'source-assisted', modeLabel: 'Source-assisted (source available)', detail: 'Reconstruct with repository source available as reference material.', available: false, unavailableReason: 'Unavailable — no repository import or source-assisted run is wired to the backend yet.' },
  { id: 'upload', label: 'Upload files', mode: 'source-assisted', modeLabel: 'Source-assisted (source available)', detail: 'Upload an archive or files to study.', available: false, unavailableReason: 'Unavailable — attachments and uploads are not supported by the backend yet.' },
  { id: 'docs', label: 'Documentation / spec', mode: 'source-assisted', modeLabel: 'Source-assisted (docs available)', detail: 'Start from API docs or a written specification.', available: false, unavailableReason: 'Unavailable — document ingestion is not wired to the backend yet.' },
  { id: 'local', label: 'Local fixture', mode: 'black-box', modeLabel: 'Black-box (behavior only)', detail: 'Owned fixtures on this machine, observed by behavior only.', available: true, unavailableReason: null },
  { id: 'recorded', label: 'Recorded evidence', mode: 'black-box', modeLabel: 'Black-box (recorded behavior)', detail: 'Previously recorded investigations and benchmark evidence.', available: true, unavailableReason: null },
];

export function sourceOption(id: SourceOption['id']): SourceOption {
  return SOURCE_OPTIONS.find(s => s.id === id) ?? SOURCE_OPTIONS[0];
}

export type RunOutcome = 'not-started' | 'queued' | 'running' | 'passed' | 'partial' | 'failed' | 'cancelled' | 'needs-attention';

export function runOutcome(status: string | null | undefined, evaluation: { passed: number; failed: number; indeterminate: number; total: number } | null | undefined): RunOutcome {
  if (!status) return 'not-started';
  if (status === 'queued') return 'queued';
  if (status === 'running') return 'running';
  if (status === 'cancelled') return 'cancelled';
  if (status === 'failed') return 'failed';
  if (status === 'needs_reconciliation') return 'needs-attention';
  if (status === 'completed') {
    if (!evaluation) return 'needs-attention';
    if (evaluation.failed === 0 && evaluation.indeterminate === 0 && evaluation.total > 0) return 'passed';
    if (evaluation.passed > 0) return 'partial';
    return 'failed';
  }
  return 'needs-attention';
}

/** Measured comparison scoreboard: same target, three ways. Scores are
 * recorded frozen results; unmeasured cells stay explicit, never zero. */
export interface ScoreRow { method: string; provenance: string; frozen: string; extended: string; status: string }
export interface ScoreTarget { target: string; rows: ScoreRow[] }
export const SCOREBOARD: readonly ScoreTarget[] = [
  { target: 'Vikunja v2.4.0', rows: [
    { method: 'AI alone (Muse grounded)', provenance: 'REAL_MODEL', frozen: '2/6', extended: 'unmeasured', status: 'Scored' },
    { method: 'AI + our software (Muse hybrid)', provenance: 'REAL_MODEL', frozen: '6/6', extended: '6/6', status: 'Scored; gate rejected edits' },
    { method: 'Our software alone (compiler)', provenance: 'NON_AI', frozen: '6/6', extended: '6/6', status: 'Scored; zero model calls' } ] },
  { target: 'File Browser v2.63.23', rows: [
    { method: 'AI alone (Muse)', provenance: 'REAL_MODEL', frozen: '3/7', extended: 'unmeasured', status: 'Scored - cross-app packet' },
    { method: 'Our software alone (compiler)', provenance: 'NON_AI', frozen: '7/7', extended: 'n/a', status: 'Scored' } ] },
  { target: 'Gitea 1.22.6', rows: [
    { method: 'Our software alone (compiler)', provenance: 'NON_AI', frozen: '6/6 public cases', extended: 'sealed, not run', status: 'Scored - first contact 2/6, generic fix measured after' } ] },
];

export const OUTCOME_LABEL: Record<RunOutcome, string> = {
  'not-started': 'Not started', queued: 'Queued', running: 'Running', passed: 'Passed',
  partial: 'Partial — some cases failed or indeterminate', failed: 'Failed', cancelled: 'Cancelled', 'needs-attention': 'Needs attention',
};

/** Backend lifecycle stages in pipeline order (no fabricated thinking). */
export const STAGE_ORDER = ['capture', 'organize', 'distill', 'execute'] as const;
export function stageIndex(stage: string | null | undefined): number {
  return stage ? (STAGE_ORDER as readonly string[]).indexOf(stage) : -1;
}

function escMd(value: unknown): string { return String(value ?? '').replace(/\|/g, '\\|'); }
function digestLines(report: Record<string, unknown>): string[] {
  const labels: Record<string, string> = { scope_digest: 'Authorized scope', suite_digest: 'Evaluation suite', spec_digest: 'Candidate specification', approved_context_digest: 'Approved context', plan_digest: 'Plan' };
  return Object.entries(labels).flatMap(([k, label]) => {
    const v = report[k];
    return typeof v === 'string' && /^(?:sha256:)?[a-f0-9]{64}$/.test(v) ? [`- ${label}: \`${v}\``] : [];
  });
}
function counts(report: Record<string, unknown>) {
  const e = report.evaluation as Record<string, unknown> | null | undefined;
  if (!e || !['passed', 'failed', 'indeterminate', 'total'].every(k => Number.isSafeInteger(e[k]))) return null;
  return { passed: e.passed as number, failed: e.failed as number, indeterminate: e.indeterminate as number, total: e.total as number };
}

export interface ExportMeta { runId: string; investigationTitle: string; generatedFrom: string }

export function buildReportMarkdown(report: Record<string, unknown>, meta: ExportMeta): string {
  const c = counts(report);
  const lines = [
    `# Second Source report`, ``,
    `- Run: \`${meta.runId}\``, `- Investigation: ${escMd(meta.investigationTitle)}`,
    `- Origin: ${report.origin === 'mock' ? 'mock (NON_AI fixture)' : escMd(report.origin)} · Real model: ${report.real === false ? 'no' : escMd(report.real)}`,
    `- Generated from: ${escMd(meta.generatedFrom)} (sanitized backend report; sealed cases are never included)`, ``,
    `## Verification`, c ? `- ${c.passed} passed · ${c.failed} failed · ${c.indeterminate} indeterminate · ${c.total} total` : `- Evaluation counts unavailable.`, ``,
    `## Provenance`, ...(digestLines(report).length ? digestLines(report) : ['- Provenance digests unavailable.']), ``,
    `## Sanitized report data`, '```json', JSON.stringify(report, null, 2), '```', ``,
  ];
  return lines.join('\n');
}

export function buildReportHtml(report: Record<string, unknown>, meta: ExportMeta): string {
  const esc = (v: unknown) => String(v ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch] || ch));
  const c = counts(report);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Second Source report ${esc(meta.runId)}</title><style>body{font-family:system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;line-height:1.6}code{background:#f2f2f0;padding:2px 5px;border-radius:4px}pre{overflow:auto;background:#f7f7f5;padding:16px;border-radius:8px}</style></head><body><h1>Second Source report</h1><p>Run <code>${esc(meta.runId)}</code> · ${esc(meta.investigationTitle)}<br>Origin: ${esc(report.origin)} · Real model: ${esc(report.real)}</p><h2>Verification</h2><p>${c ? `${c.passed} passed · ${c.failed} failed · ${c.indeterminate} indeterminate · ${c.total} total` : 'Evaluation counts unavailable.'}</p><h2>Sanitized report data</h2><pre>${esc(JSON.stringify(report, null, 2))}</pre></body></html>`;
}

export function buildManifest(report: Record<string, unknown>, meta: ExportMeta): string {
  return JSON.stringify({ format: 'second-source-export-manifest/v1', run_id: meta.runId, investigation: meta.investigationTitle, generated_from: meta.generatedFrom, origin: report.origin ?? null, real: report.real ?? null, evaluation: counts(report), digests: Object.fromEntries(digestLines(report).map(l => { const m = l.match(/^- (.+?): `(.+)`$/); return m ? [m[1], m[2]] : ['entry', l]; })) }, null, 2);
}

export function buildReadme(report: Record<string, unknown>, meta: ExportMeta): string {
  const c = counts(report);
  return `# Second Source export\n\nRun \`${meta.runId}\` — ${meta.investigationTitle}\n\nThis bundle was generated in your browser from the sanitized backend report for this run.\nIt contains no raw model output, secrets, candidate-private files or sealed evaluator cases.\n\n- Origin: ${report.origin === 'mock' ? 'mock (NON_AI fixture)' : String(report.origin ?? 'unknown')}\n- Verification: ${c ? `${c.passed}/${c.total} passed (${c.failed} failed, ${c.indeterminate} indeterminate)` : 'unavailable'}\n- Verify the ZIP separately with the backend integrity bundle (Download integrity export).\n\nFiles: report.md / report.html (human-readable), manifest.json (this run's digests), report.json (sanitized data).\n`;
}
