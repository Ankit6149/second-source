import './fonts.css';
import './design.css';
import './product.css';
import { createIcons, PanelLeft, PanelLeftClose, SquarePen, FolderOpen, SwatchBook, ChevronUp, ArrowUp, ShieldCheck, FileText, ListChecks, Download, CircleHelp, X, Play, Square, RefreshCw, Clock, Check, AlertTriangle, LogIn, LogOut, Link, FlaskConical, MessageSquare, ExternalLink, Search, GitBranch, Puzzle, Plus } from 'lucide';
import type { Session } from '@supabase/supabase-js';
import { auth, observeSession, signIn, signOut } from './auth';
import { Api, ApiError, validatedOrigin, type Target, type Investigation, type Run, type RunEvent, type Verification } from './api';
import { detectReference } from './reference';
import { supportedTargets } from './targets';
import { clearOwnerNotes, loadNotes, saveNotes } from './notes';
import { acceptsRunRevision, executionDefinitelyRefused, outcomeConfirmed, pollFailureMessage, pollRetryDelay } from './polling';
import { HISTORICAL_LEDGER, PROVENANCE_META, armScoreText, compiledScoreText, provenanceClass, vikunjaRecord, type EvidenceProvenance } from './evidence';
import { capabilityEnabled, targetCapabilities } from './capabilities';
import { checkEngine, createEngineInvestigation, getEngineInvestigation, engineCandidateUrl, type EngineInvestigation } from './engine';
import { SOURCE_OPTIONS, OUTCOME_LABEL, buildManifest, buildReadme, buildReportHtml, buildReportMarkdown, runOutcome, stageIndex } from './workbench';

const icons = { PanelLeft, PanelLeftClose, SquarePen, FolderOpen, SwatchBook, ChevronUp, ArrowUp, ShieldCheck, FileText, ListChecks, Download, CircleHelp, X, Play, Square, RefreshCw, Clock, Check, AlertTriangle, LogIn, LogOut, Link, FlaskConical, MessageSquare, ExternalLink, Search, GitBranch, Puzzle, Plus };
const icon = (name: string) => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const esc = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c] || c));
const el = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const apiOrigin = validatedOrigin(import.meta.env.VITE_API_ORIGIN || '', import.meta.env.DEV);
const state: {
  session: Session | null; ownerId: string | null; investigations: Investigation[]; targets: Target[]; target: Target | null; selected: Investigation | null;
  run: Run | null; events: RunEvent[]; verification: Verification | null; messages: string[]; draft: string;
  view: 'home' | 'conversation' | 'library' | 'system' | 'compare' | 'reports' | 'settings'; loading: boolean; error: string; pollError: string; uncertain: boolean; actionUncertain: string | null;
  executionError: { runId: string; message: string } | null;
  busy: boolean; executing: boolean; epoch: number;
} = { session: null, ownerId: null, investigations: [], targets: [], target: null, selected: null, run: null, events: [], verification: null,
  messages: [], draft: sessionStorage.getItem('ss-product-draft') || '', view: 'home', loading: false, error: '', pollError: '',
  uncertain: false, actionUncertain: null, executionError: null, busy: false, executing: false, epoch: 0 };
const api = new Api(apiOrigin, () => state.session?.access_token || null);
let pollTimer: number | undefined;
const engineState: { status: 'unknown' | 'available' | 'unavailable' | 'hosted'; record: EngineInvestigation | null; poll: number | undefined } =
  { status: 'unknown', record: null, poll: undefined };
let currentDialogReturn: HTMLElement | null = null;
let renderedRunId: string | undefined;

async function allPages<T>(fetchPage: (after?: string) => Promise<{ items: T[]; next_after: string | null }>): Promise<T[]> {
  const items: T[] = []; let cursor: string | undefined;
  for (let page = 0; page < 10; page++) {
    const result = await fetchPage(cursor); items.push(...result.items);
    if (!result.next_after) return items;
    if (result.next_after === cursor) throw new Error('The service returned an invalid page cursor.');
    cursor = result.next_after;
  }
  throw new Error('This account has too many records to display safely. Contact an operator.');
}
async function allEvents(id: string): Promise<RunEvent[]> {
  const items: RunEvent[] = []; let cursor = 0;
  for (let page = 0; page < 10; page++) {
    const result = await api.events(id, cursor); items.push(...result.items);
    if (result.next_after === cursor) return items;
    if (result.next_after < cursor) throw new Error('The service returned an invalid event cursor.');
    cursor = result.next_after;
  }
  throw new Error('This run has too many events to display safely. Contact an operator.');
}

function renderIcons() { createIcons({ icons }); }
function toast(message: string) {
  const item = document.createElement('div'); item.className = 'toast'; item.textContent = message;
  el('toasts').replaceChildren(item); window.setTimeout(() => item.remove(), 5000);
}
function describe(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      ++state.epoch; state.loading = false; state.busy = false; state.executing = false; state.uncertain = false; state.actionUncertain = null;
      state.session = null; state.ownerId = null; state.targets = []; state.target = null; state.investigations = []; state.selected = null;
      state.run = null; state.verification = null; state.events = []; state.messages = []; state.draft = ''; state.pollError = ''; state.executionError = null; state.view = 'home';
      sessionStorage.removeItem('ss-product-draft'); stopPolling();
    }
    return error.message + (error.correlationId ? ` Reference: ${error.correlationId}` : '');
  }
  return error instanceof Error ? error.message : 'Something went wrong. Try again.';
}
function stopPolling() { if (pollTimer) window.clearTimeout(pollTimer); pollTimer = undefined; }
function showDialog(title: string, content: string) {
  currentDialogReturn = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  el('dialogContent').innerHTML = `<div class="dialog-head"><h2 id="dialogTitle">${esc(title)}</h2><button class="icon-button" type="button" data-action="close-dialog" aria-label="Close">${icon('x')}</button></div>${content}`;
  const dialog = el<HTMLDialogElement>('dialog'); if (!dialog.open) dialog.showModal(); renderIcons();
}
function closeDialog() { const dialog = el<HTMLDialogElement>('dialog'); if (dialog.open) dialog.close(); if (currentDialogReturn?.isConnected) currentDialogReturn.focus(); else el('main').focus(); }
function setError(error: unknown) { state.error = describe(error); render(); }

function account() {
  if (!apiOrigin || !auth) {
    showDialog('Sign in', `<p>Sign-in and the backend are not configured for this deployment yet.</p><p class="component-note">You can explore the product, but saved investigations require a connected service and an account.</p><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>`);
  } else if (state.session) {
    showDialog('Account', `<p>Signed in. Your investigations are scoped to this account.</p><p class="component-note">Signing out clears this browser session. Existing access tokens can remain valid until they expire.</p><div class="dialog-actions"><button class="pill-btn" data-action="sign-out">${icon('log-out')} Sign out</button></div>`);
  } else {
    showDialog('Sign in', `<p>Sign in to save investigations and review their results.</p><div class="dialog-actions"><button class="pill-btn primary" data-action="sign-in">${icon('log-in')} Continue with Google</button></div>`);
  }
}

function composer() {
  const hint = detectReference(state.draft);
  return `<form class="composer" id="composer"><div id="draftContext"><div class="detection" id="detection" ${hint ? '' : 'hidden'}>${hint ? `${icon('link')} <span><strong>${esc(hint.label)}</strong><br><small>${esc(hint.description)}</small></span>` : ''}</div></div><label class="sr-only" for="promptInput">Describe the software behavior you want to investigate</label><textarea rows="2" id="promptInput" maxlength="4000" placeholder="Ask about a workflow, software, or a referenceâ€¦">${esc(state.draft)}</textarea><div class="composer-lower"><div class="tool-row"><button class="tool-icon" type="button" disabled title="Attachments are not supported yet" aria-label="Attachments unavailable">${icon('plus')}</button><button class="small-tool" type="button" data-action="select-target">${icon('flask-conical')} Choose a supported target</button></div><div class="send-area"><span class="kbd-help">Shift + Enter for new line</span><button class="send-btn" type="submit" aria-label="Send message">${icon('arrow-up')}</button></div></div></form>`;
}

function enginePanel() {
  const rec = engineState.record;
  let body = '';
  if (engineState.status === 'unknown') {
    body = `<p class="component-note">Checking for the local engine at 127.0.0.1:8765â€¦</p>`;
  } else if (engineState.status === 'hosted') {
    body = `<p class="component-note">The live engine runs on your own machine and is only probed when this page itself is served locally. This hosted page makes no request to your computer. To use it: clone the repo, run <code>python scripts/investigation_engine.py</code>, then open the local build (<code>npm run dev</code> in product/).</p>`;
  } else if (engineState.status === 'unavailable') {
    body = `<p class="component-note">Local engine not running. Start it with <code>python scripts/investigation_engine.py</code>, then check again. Nothing is faked while it is offline: no run can be started from here.</p><button class="pill-btn" data-action="engine-check">${icon('refresh-cw')} Check again</button>`;
  } else if (!rec) {
    body = `<p>Runs the real deterministic pipeline against a disposable local Vikunja reference: probe â†’ compile â†’ public conformance. No model is called.</p><button class="pill-btn primary" data-action="engine-run">${icon('play')} Run live investigation (NON_AI)</button>`;
  } else if (rec.status === 'running') {
    body = `<p>Runningâ€¦ stage: <strong>${esc(rec.stage)}</strong> (investigation ${esc(rec.id)}). This page refreshes itself; do not start another run meanwhile.</p>`;
  } else if (rec.status === 'failed') {
    body = `<p class="component-note">Investigation ${esc(rec.id)} failed: ${esc(rec.error || 'unknown error')}</p><button class="pill-btn" data-action="engine-run">${icon('play')} Run again</button>`;
  } else {
    body = `<p>Investigation <strong>${esc(rec.id)}</strong> completed against a fresh local reference.</p>
      <div class="artifact"><div class="artifact-top"><div class="artifact-symbol">${icon('file-text')}</div><div><strong>Vikunja v2.4.0 Â· EVIDENCE_COMPILED (NON_AI)</strong><small>${rec.observations ? `${rec.observations.count} observations Â· ${esc(rec.observations.sha256.slice(0, 19))}â€¦` : ''}</small></div><span class="artifact-tag">completed</span></div>
      <div class="artifact-bottom">Compiled routes: ${rec.compiled ? rec.compiled.routes.map(esc).join(' Â· ') : 'â€”'}<br>Public-ladder conformance: <strong>${rec.public_conformance ? `${rec.public_conformance.passed}/${rec.public_conformance.total}` : 'â€”'}</strong> (stateful public probe sequence; not the held-out score). Held-out: not run by the engine â€” evaluator-side only.</div></div>
      <div class="response-actions"><a class="pill-btn" href="${engineCandidateUrl(rec.id)}" download>${icon('download')} Download candidate spec</a><button class="pill-btn" data-action="engine-run">${icon('play')} Run again</button></div>`;
  }
  const heading = engineState.status === 'hosted' ? 'Local engine â€” not running on this hosted page' : engineState.status === 'unavailable' ? 'Local engine â€” not running' : engineState.status === 'unknown' ? 'Local engine â€” checkingâ€¦' : 'Live local engine';
  return `<section class="single-page engine-panel"><h2>${heading}</h2><p class="component-note">Local operator service on this machine only (127.0.0.1:8765). It executes the deterministic NON_AI pipeline for real; model-authored GEMMA_TEST results stay recorded evidence in the Lab and are never generated here.</p>${body}</section>`;
}
async function refreshEngine() {
  // Never probe a visitor's localhost from a hosted page: the engine
  // is only reachable (and only meaningful) when this page is itself
  // served locally. Hosted visitors get an explanatory state and the
  // page makes zero network requests to their machine.
  if (location.hostname !== '127.0.0.1' && location.hostname !== 'localhost') {
    engineState.status = 'hosted';
    render();
    return;
  }
  engineState.status = await checkEngine() ? 'available' : 'unavailable';
  render();
}
async function runEngineInvestigation() {
  try {
    engineState.record = await createEngineInvestigation();
    render();
    window.clearInterval(engineState.poll);
    engineState.poll = window.setInterval(async () => {
      if (!engineState.record || engineState.record.status !== 'running') { window.clearInterval(engineState.poll); return; }
      try {
        engineState.record = await getEngineInvestigation(engineState.record.id);
        if (engineState.record.status !== 'running') window.clearInterval(engineState.poll);
        render();
      } catch { window.clearInterval(engineState.poll); }
    }, 2000);
  } catch {
    engineState.status = 'unavailable';
    render();
  }
}
function renderHome() {
  return `<section class="empty-home"><h1>Understand how software <em>really works.</em></h1><p>Second Source observes software you own or are authorized to study, infers its hidden rules from behavior, builds an independent candidate, and scores that candidate against the reference â€” without seeing its source.</p><div class="home-evidence"><span class="prov-pill prov-model-authored">REAL_MODEL Â· Model-authored</span><p><strong>14/25</strong> â€” a genuine muse-spark-1.3 candidate for the owned ledger, independently scored on a sealed 25-case suite. Recorded evidence only: no live model inference runs in this app, and REAL_MODEL, GEMMA_TEST and NON_AI scores are never merged.</p><button class="pill-btn primary" type="button" data-action="research">Read the research record</button></div><div class="suggestion-row"><button class="suggestion" data-suggestion="Understand how the owned ledger handles repeated inputs.">${icon('search')} Understand behavior</button><button class="suggestion" data-suggestion="Compare the owned ledger with a scoped candidate.">${icon('git-branch')} Compare versions</button><button class="suggestion" data-suggestion="Explore how the owned ledger workflow could be reconstructed.">${icon('puzzle')} Reconstruct a workflow</button></div><p class="home-note">${state.session ? state.target ? (state.targets.length > 1 ? 'Available here: owned ledger and HTTP task-workflow NON_AI fixtures.' : 'Available here: the owned ledger NON_AI fixture.') : 'No supported target is currently available.' : 'Signed out: the research record above is open to everyone. Sign in only to save investigations against a connected service.'} Browser / motion execution is unavailable in this app; its recorded slice is evidence only.</p></section>` + enginePanel();
}
function controls() {
  if (!state.session) return `<button class="pill-btn primary" data-action="account">${icon('log-in')} Sign in to start</button>`;
  if (!state.selected) return state.target ? `<button class="pill-btn primary" data-action="review-scope" ${state.busy ? 'disabled' : ''}>${icon('shield-check')} Review scope</button>` : `<button class="pill-btn" disabled>Supported target unavailable</button>`;
  if (state.selected.status === 'created') return state.target && state.selected.scope_digest === state.target.scope_digest
    ? `<button class="pill-btn primary" data-action="authorize" ${state.busy ? 'disabled' : ''}>${icon('shield-check')} Confirm scope</button>`
    : `<p class="component-note">This stored scope differs from the currently supported scope. Authorization is unavailable; contact an operator.</p>`;
  if (!state.run) return `<button class="pill-btn primary" data-action="queue" ${state.busy || !state.target || state.selected.scope_digest !== state.target.scope_digest ? 'disabled' : ''}>${icon('clock')} Queue mock run</button>${!state.target ? '<p class="component-note">The supported target is unavailable.</p>' : ''}`;
  if (state.run.status === 'queued') return state.uncertain
    ? `<button class="pill-btn" data-action="refresh">${icon('refresh-cw')} Check status</button><p class="component-note">The execution request has an uncertain outcome. It will not be retried automatically.</p>`
    : `<button class="pill-btn primary" data-action="execute" ${state.busy || state.executing || state.actionUncertain || !state.target?.execution_enabled || state.selected.scope_digest !== state.target.scope_digest ? 'disabled' : ''}>${icon('play')} Start NON_AI run</button><button class="pill-btn" data-action="cancel" ${state.busy || state.actionUncertain ? 'disabled' : ''}>${icon('square')} Cancel queued run</button>${state.actionUncertain ? '<p class="component-note">The cancellation outcome is uncertain; check status before taking another action.</p><button class="pill-btn quiet" data-action="refresh">Check status</button>' : ''}${!state.target?.execution_enabled || state.selected.scope_digest !== state.target.scope_digest ? '<p class="component-note">Execution is disabled or unavailable for this scope on this backend.</p>' : ''}`;
  if (state.run.status === 'running') return `<button class="pill-btn" data-action="cancel" ${state.busy || state.run.cancel_requested || state.actionUncertain ? 'disabled' : ''}>${icon('square')} ${state.run.cancel_requested ? 'Cancellation requested' : 'Cancel run'}</button><button class="pill-btn quiet" data-action="refresh">${icon('refresh-cw')} Check status</button><button class="pill-btn quiet" data-action="reconcile" ${state.busy || state.actionUncertain ? 'disabled' : ''}>Check recovery</button>${state.actionUncertain ? '<p class="component-note">The previous request has an uncertain outcome; it will not be repeated automatically.</p>' : ''}`;
  if (state.run.status === 'needs_reconciliation') return `<p class="component-note">This run is quarantined after an uncertain or interrupted operation. It will not restart automatically; an operator must review it.</p><button class="pill-btn quiet" data-action="refresh">Check status</button>`;
  if (state.run.status === 'completed') return `<button class="pill-btn primary" data-action="verification">${icon('list-checks')} View verification</button><button class="pill-btn" data-action="candidate">${icon('search')} Candidate preview</button><button class="pill-btn" data-action="compare">${icon('git-branch')} Compare</button><button class="pill-btn" data-action="report">${icon('file-text')} Open report</button><button class="pill-btn" data-action="reports">${icon('download')} Reports &amp; exports</button><button class="pill-btn" data-action="export">${icon('download')} Download integrity export</button>`;
  return `<button class="pill-btn" data-action="refresh">${icon('refresh-cw')} Refresh status</button>${state.run.status === 'failed' || state.run.status === 'cancelled' ? `<button class="pill-btn" data-action="queue" ${state.busy || state.executing || !state.target ? 'disabled' : ''}>${icon('clock')} Queue a new mock run</button>${state.executing ? '<p class="component-note">Wait for the previous execution request to finish before queueing another run.</p>' : ''}` : ''}`;
}
function eventName(event: RunEvent) {
  const labels: Record<string,string> = { run_claimed: 'Worker claimed the run', stage_started: `Stage: ${event.stage || 'unknown'}`, repair_started: 'Bounded mock retry started', repair_completed: 'Bounded mock retry finished', run_completed: 'Run completed', run_failed: 'Run failed', run_cancelled: 'Run cancelled', run_needs_reconciliation: 'Run needs reconciliation', run_queued: 'Run queued' };
  return labels[event.event_type] || event.event_type.replaceAll('_', ' ');
}
function investigationCard() {
  const run = state.run;
  return `<div class="message assistant"><div class="assistant-mark">${icon('shield-check')}</div><div class="response"><h2>${state.selected ? esc(state.selected.title) : 'Choose what to investigate.'}</h2><p>${state.selected ? 'This investigation is limited to its approved fixture scope.' : !state.session ? 'Sign in to see the targets available from the connected service. A URL or software name does not grant permission or start an investigation.' : state.target ? 'Choose an available owned fixture. A URL or software name does not grant permission or start an investigation.' : 'No supported target is currently available from this service.'}</p>${state.selected ? `<div class="artifact"><div class="artifact-top"><div class="artifact-symbol">${icon('file-text')}</div><div><strong>${esc(state.target?.label || 'Unsupported fixture')} Â· NON_AI</strong><small>Scope ${esc(state.selected.scope_digest.slice(0, 12))}â€¦</small></div><span class="artifact-tag">${esc(run?.status || state.selected.status)}</span></div>${run ? `<div class="artifact-bottom">${esc(run.stage ? `Stage: ${run.stage}` : 'No stage reported')}${run.error_code ? ` Â· ${esc(run.error_code)}` : ''}</div>` : ''}</div>` : ''}${outcomeBanner()}${state.events.length ? `<details class="activity"><summary>Activity (${state.events.length}) â€” genuine backend events</summary><ol>${state.events.map(e => `<li>${esc(eventName(e))}</li>`).join('')}</ol></details>` : ''}<div class="response-actions">${controls()}</div><p class="component-note">Your notes are kept only in this browser tab and are cleared on sign-out. The backend does not yet save conversations or answer follow-up questions.</p></div></div>`;
}
function conversation() {
  const messages = state.messages.map(message => `<div class="message user"><div class="bubble">${esc(message)}</div></div>`).join('');
  return `<section class="conversation">${messages}${investigationCard()}</section>`;
}
function library() {
  if (!state.session) return `<section class="single-page"><h1>Your work</h1><p>Sign in to see your saved investigations.</p><button class="pill-btn primary" data-action="account">Sign in</button></section>`;
  return `<section class="single-page"><h1>Your work</h1><p>Investigations saved to your account.</p>${state.loading ? '<p>Loading investigationsâ€¦</p>' : state.investigations.length ? state.investigations.map(item => `<button class="list-row" data-investigation="${esc(item.investigation_id)}">${icon('message-square')}<span class="row-main"><strong>${esc(item.title)}</strong><small>${esc(item.status)} Â· ${esc(item.created_at)}</small></span></button>`).join('') : '<p>No investigations yet. Choose a supported target to start.</p>'}<p class="component-note">Rename, deletion and conversation search are not yet supported.</p></section>`;
}
function showroom() {
  return `<section class="single-page"><h1>Component showroom</h1><p>The v0.8 design language, presented separately from investigation data.</p><section class="system-section"><h2>Buttons and states</h2><div class="system-controls"><button class="pill-btn primary" data-action="sample-toast">Primary action</button><button class="pill-btn" data-action="sample-dialog">Open dialog</button><button class="pill-btn quiet" data-action="sample-toast">Quiet action</button><button class="pill-btn" disabled>Unavailable</button></div></section><section class="system-section"><h2>Inputs and status</h2><label for="showcaseInput">Reference</label><input id="showcaseInput" class="control-field" placeholder="A URL or software name"><div class="system-states"><span class="status-pill">Completed</span><span class="status-pill warn">Needs review</span><span class="status-pill fail">Failed</span><span class="status-pill muted">Unavailable</span></div></section><section class="system-section"><h2>Feedback</h2><p class="inline-note">These are component examples, not investigation results.</p><div class="skeleton" aria-label="Loading example"></div></section></section>`;
}
function render() {
  const content = el('content');
  const active = document.activeElement instanceof HTMLElement && content.contains(document.activeElement) ? document.activeElement : null;
  const focusedAction = active?.dataset.action;
  const activityOpen = renderedRunId === state.run?.run_id && !!content.querySelector<HTMLDetailsElement>('details.activity')?.open;
  const statusText = state.run ? `Run ${state.run.status.replaceAll('_', ' ')}${state.run.stage ? `, stage ${state.run.stage}` : ''}.` : state.loading ? 'Loading investigations.' : '';
  if (el('liveStatus').textContent !== statusText) el('liveStatus').textContent = statusText;
  el('accountState').textContent = state.session ? 'Signed in' : 'Not signed in';
  el('connectionLabel').textContent = !apiOrigin || !auth ? 'Service not configured' : state.session ? 'Signed in Â· NON_AI only' : 'Sign in to start';
  el('topName').textContent = state.view === 'library' ? 'Your work' : state.view === 'system' ? 'Component showroom' : state.selected?.title || 'Second Source';
  el('history').innerHTML = state.investigations.slice(0, 12).map(item => `<button class="history-item ${item.investigation_id === state.selected?.investigation_id ? 'active' : ''}" data-investigation="${esc(item.investigation_id)}">${icon('message-square')}<span class="history-title">${esc(item.title)}</span></button>`).join('');
  const message = state.error ? `<div class="inline-note error" role="alert">${icon('alert-triangle')}<span>${esc(state.error)}</span>${state.selected && state.session ? '<button class="pill-btn quiet" data-action="refresh">Check status</button>' : ''}<button class="quiet-dismiss" data-action="dismiss-error" aria-label="Dismiss error">Ã—</button></div>` : '';
  const polling = state.pollError ? `<div class="inline-note error" role="status">${icon('alert-triangle')}<span>${esc(state.pollError)}</span><button class="pill-btn quiet" data-action="refresh">Check status</button></div>` : '';
  el('content').innerHTML = message + polling + (state.view === 'home' ? renderHome() : state.view === 'conversation' ? conversation() : state.view === 'library' ? library() : state.view === 'compare' ? compareView() : state.view === 'reports' ? reportsView() : state.view === 'settings' ? settingsView() : showroom());
  renderedRunId = state.run?.run_id;
  const activity = content.querySelector<HTMLDetailsElement>('details.activity'); if (activity && activityOpen) activity.open = true;
  if (focusedAction) {
    const replacement = [...content.querySelectorAll<HTMLButtonElement>('[data-action]')].find(button => button.dataset.action === focusedAction && !button.disabled);
    replacement?.focus({ preventScroll: true });
  }
  el('dock').hidden = state.view === 'library' || state.view === 'system' || state.view === 'settings';
  if (!el('dock').hidden) {
    const existing = document.getElementById('promptInput') as HTMLTextAreaElement | null;
    if (!existing) el('dockInner').innerHTML = composer();
    else if (existing.value !== state.draft) existing.value = state.draft;
  }
  renderIcons();
}

async function hydrate(session: Session | null) {
  const generation = ++state.epoch;
  const previousUser = state.session?.user.id;
  if (previousUser && previousUser !== session?.user.id) {
    state.investigations = []; state.targets = []; state.target = null; state.selected = null; state.run = null; state.events = []; state.verification = null;
    state.messages = []; state.draft = ''; state.view = 'home';
  }
  state.session = session; state.ownerId = null; state.error = ''; state.pollError = ''; state.executionError = null; state.executing = false; state.busy = false; state.actionUncertain = null; stopPolling();
  if (!session || !apiOrigin) {
    state.investigations = []; state.targets = []; state.target = null; state.selected = null; state.run = null; state.events = []; state.verification = null;
    render(); return;
  }
  state.loading = true; render();
  try {
    const identity = await api.session();
    if (generation !== state.epoch) return;
    state.ownerId = identity.owner_id;
    const priorOwner = sessionStorage.getItem('ss-session-owner');
    if (priorOwner && priorOwner !== identity.owner_id) {
      sessionStorage.removeItem('ss-selected-investigation'); sessionStorage.removeItem('ss-create-pending');
      sessionStorage.removeItem('ss-product-draft'); state.messages = []; state.draft = '';
      state.investigations = []; state.targets = []; state.target = null; state.selected = null; state.run = null; state.events = []; state.verification = null; state.view = 'home';
    }
    sessionStorage.setItem('ss-session-owner', identity.owner_id);
    const [targets, items] = await Promise.all([api.targets(), allPages(after => api.investigations(after))]);
    if (generation !== state.epoch) return;
    state.targets = supportedTargets(targets);
    state.target = state.targets.find(target => target.target_id === 'owned-ledger-v1') || state.targets[0] || null;
    state.investigations = items.sort((a, b) => b.created_at.localeCompare(a.created_at));
    const saved = sessionStorage.getItem('ss-selected-investigation');
    if (saved && items.some(item => item.investigation_id === saved)) await openInvestigation(saved);
  } catch (error) { if (generation === state.epoch) { state.error = describe(error); render(); } }
  finally { if (generation === state.epoch) { state.loading = false; render(); } }
}
async function openInvestigation(id: string) {
  const generation = ++state.epoch; stopPolling(); state.executing = false; state.busy = false; state.loading = true; state.error = ''; state.pollError = ''; state.executionError = null; render();
  try {
    const item = await api.investigation(id);
    const runs = await allPages(after => api.runs(id, after));
    if (generation !== state.epoch) return;
    if (state.selected?.investigation_id !== id) state.messages = state.ownerId ? loadNotes(sessionStorage, state.ownerId, id) : [];
    state.selected = item; state.target = state.targets.find(target => target.scope_digest === item.scope_digest) || null;
    state.run = [...runs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0] || null; state.events = []; state.verification = null;
    state.uncertain = !!state.run && sessionStorage.getItem(`ss-execution-uncertain:${state.run.run_id}`) === '1';
    state.actionUncertain = state.run ? sessionStorage.getItem(`ss-action-uncertain:${state.run.run_id}`) : null;
    sessionStorage.setItem('ss-selected-investigation', id); state.view = 'conversation';
    if (state.run) await refresh(false);
  } catch (error) { if (generation === state.epoch) { state.error = describe(error); render(); } }
  finally { if (generation === state.epoch) { state.loading = false; render(); } }
}
async function refresh(showErrors = true) {
  if (!state.session) return;
  const generation = state.epoch;
  if (!state.run && state.selected) {
    const id = state.selected.investigation_id;
    try { const item = await api.investigation(id); if (generation === state.epoch && state.selected?.investigation_id === id) { state.selected = item; render(); } }
    catch (error) { if (generation === state.epoch && showErrors) setError(error); }
    return;
  }
  if (!state.run) return;
  const runId = state.run.run_id;
  try {
    const [run, events] = await Promise.all([api.run(runId), allEvents(runId)]);
    if (generation !== state.epoch || !state.run || !acceptsRunRevision(state.run, run)) return;
    state.run = run;
    if ((events.at(-1)?.event_id ?? 0) >= (state.events.at(-1)?.event_id ?? 0)) state.events = events;
    state.pollError = '';
    if (state.executionError?.runId === runId && outcomeConfirmed(run.status)) {
      if (state.error === state.executionError.message) state.error = '';
      state.executionError = null;
    }
    if (run.cancel_requested || !['queued', 'running'].includes(run.status)) {
      sessionStorage.removeItem(`ss-action-uncertain:${runId}`); state.actionUncertain = null;
    }
    if (run.status === 'completed') {
      const verification = await api.verification(runId);
      if (generation !== state.epoch || state.run?.run_id !== runId || state.run.status !== 'completed') return;
      state.verification = verification;
      sessionStorage.removeItem(`ss-execution-uncertain:${runId}`); state.uncertain = false;
    } else if (run.status !== 'queued' && run.status !== 'running') {
      sessionStorage.removeItem(`ss-execution-uncertain:${runId}`); state.uncertain = false;
    }
    render();
    if (run.status === 'running' || state.executing) { stopPolling(); pollTimer = window.setTimeout(() => { void refresh(false); }, 10000); }
  } catch (error) {
    if (generation !== state.epoch || !state.session || state.run?.run_id !== runId) return;
    if (showErrors || error instanceof ApiError && error.status === 401) state.error = describe(error);
    else state.pollError = pollFailureMessage(error instanceof ApiError ? error.message : undefined);
    render();
    if (state.session && (state.executing || state.run?.status === 'running')) {
      stopPolling(); pollTimer = window.setTimeout(() => { void refresh(false); }, pollRetryDelay(error instanceof ApiError ? error.status : undefined));
    }
  }
}
function provenancePill(provenance: EvidenceProvenance) {
  const meta = PROVENANCE_META[provenance];
  return `<span class="prov-pill ${provenanceClass(provenance)}" data-provenance="${esc(provenance)}" title="${esc(meta.description)}">${esc(meta.label)}</span>`;
}
function capabilityPicker() {
  const groups = targetCapabilities().map(cap => {
    const enabled = capabilityEnabled(cap);
    const note = enabled ? cap.detail : cap.detail;
    return `<div class="capability-row"><div class="capability-head"><strong>${esc(cap.title)}</strong><span class="status-pill ${enabled ? '' : 'muted'}">${enabled ? 'Supported Â· bounded' : 'Unavailable'}</span></div><p class="component-note">${esc(note)}</p>${enabled ? '' : `<button class="pill-btn" type="button" disabled aria-disabled="true">Unavailable â€” adapter absent</button>`}</div>`;
  }).join('');
  const sources = SOURCE_OPTIONS.map(s => `<div class="capability-row"><div class="capability-head"><strong>${esc(s.label)}</strong><span class="status-pill ${s.available ? '' : 'muted'}">${s.available ? 'Available' : 'Unavailable'}</span></div><p class="component-note">${esc(s.modeLabel)} â€” ${esc(s.detail)}${s.available ? '' : ` ${esc(s.unavailableReason || '')}`}</p>${s.available ? '' : `<button class="pill-btn" type="button" disabled aria-disabled="true" title="${esc(s.unavailableReason || 'Unavailable')}">Unavailable</button>`}</div>`).join('');
  return `<div class="capability-list" role="group" aria-label="Target capabilities">${groups}</div><h3>Source options</h3><p class="component-note">Source-assisted means source or docs would be available; black-box means behavior only. Only service-backed options can be chosen â€” the rest stay disabled with their reason.</p><div class="capability-list" role="group" aria-label="Source options">${sources}</div>`;
}
function showCandidate() {
  const rec = engineState.record;
  const repair = state.verification?.repair;
  if (rec?.compiled) {
    showDialog('Candidate preview', `<p><strong>${esc(rec.compiled.label || 'EVIDENCE_COMPILED')} (NON_AI)</strong> â€” compiled from recorded observations. Provenance: ${esc(rec.compiled.provenance)}.</p><h3>Compiled routes (source explorer)</h3><ul class="scope-list">${rec.compiled.routes.map(r => `<li><code>${esc(r)}</code> Â· frozen compiled fact</li>`).join('')}</ul><p class="component-note">Compiled template/method/path are frozen observed facts. Candidate-private files and sealed cases are not exposed. <a href="${engineCandidateUrl(rec.id)}" download>Download candidate spec</a></p><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>`);
    return;
  }
  if (repair) {
    showDialog('Candidate preview', `<p><strong>NON_AI fixture candidate</strong> â€” only the sanitized lineage the backend exposes is shown; candidate files stay private.</p><h3>Candidate lineage</h3><ol class="lineage">${repair.versions.map(v => `<li>Round ${v.round}: ${v.evaluation.passed}/${v.evaluation.total} passed Â· <code>${esc(v.candidate_digest.slice(0, 19))}â€¦</code></li>`).join('')}</ol><p>Selected: ${esc(repair.selected_version)} Â· ${esc(repair.verdict.replaceAll('_', ' '))} Â· <code>${esc(repair.selected_digest.slice(0, 19))}â€¦</code></p><p class="component-note">No candidate source is downloadable from this interface; use Reports &amp; exports for the integrity bundle.</p><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>`);
    return;
  }
  toast(state.run ? 'Candidate preview is unavailable until verification exposes a lineage for this run.' : 'Run an investigation first â€” there is no candidate to preview yet.');
}
function outcomeBanner() {
  const outcome = runOutcome(state.run?.status, state.verification?.evaluation ?? state.run?.result?.evaluation);
  if (!state.run) return '';
  const idx = stageIndex(state.run.stage);
  const stages = ['capture', 'organize', 'distill', 'execute'].map((s, i) => `<span class="status-pill ${state.run?.status === 'completed' || i < idx ? '' : i === idx ? 'warn' : 'muted'}">${esc(s)}</span>`).join(' ');
  return `<p class="component-note">Outcome: <strong>${esc(OUTCOME_LABEL[outcome])}</strong>${state.run.stage ? ` Â· stage ${esc(state.run.stage)}` : ''}</p><p>${stages}</p>`;
}
function compareView() {
  const v = state.verification; const rec = engineState.record;
  const left = v?.evaluation ? `<div class="scoreline"><strong>${v.evaluation.passed} passed</strong><span>${v.evaluation.failed} failed</span><span>${v.evaluation.indeterminate} indeterminate</span><span>${v.evaluation.total} total</span></div>` : '<p>No verification for the selected run yet. Complete a run, then return here.</p>';
  const right = rec?.public_conformance ? `<p>Local engine public ladder: <strong>${rec.public_conformance.passed}/${rec.public_conformance.total}</strong></p>${rec.public_conformance.divergences.length ? `<ul class="scope-list">${rec.public_conformance.divergences.map(d => `<li>${esc(d)}</li>`).join('')}</ul>` : '<p>No divergences on the public ladder.</p>'}` : '<p>No local-engine run in this tab. Start one from Home (NON_AI) to compare its public-ladder result here.</p>';
  return `<section class="single-page"><h1>Compare</h1><p>Side-by-side from genuine backend data only. Held-out and sealed cases are never shown.</p>${outcomeBanner()}<div class="compare-grid"><section><h2>Reference vs candidate (fixture verification)</h2>${left}${v?.repair ? `<p>Selected candidate: ${esc(v.repair.selected_version)} Â· ${esc(v.repair.verdict.replaceAll('_', ' '))}</p>` : ''}</section><section><h2>Candidate (local engine)</h2>${right}</section></div><div class="response-actions"><button class="pill-btn" data-action="candidate">${icon('search')} Candidate preview</button><button class="pill-btn" data-action="verification">${icon('list-checks')} Verification</button></div></section>`;
}
function reportsView() {
  const ready = state.run?.status === 'completed';
  return `<section class="single-page"><h1>Reports &amp; exports</h1><p>Generated from the sanitized backend report for the selected run. If a download fails, the error is shown and nothing is retried silently.</p>${outcomeBanner()}${ready ? `<div class="response-actions"><button class="pill-btn primary" data-action="export">${icon('download')} ZIP integrity bundle</button><button class="pill-btn" data-action="download-md">${icon('download')} report.md</button><button class="pill-btn" data-action="download-html">${icon('download')} report.html</button><button class="pill-btn" data-action="download-json">${icon('download')} report.json</button><button class="pill-btn" data-action="download-manifest">${icon('download')} manifest.json</button><button class="pill-btn" data-action="download-readme">${icon('download')} README.md</button></div>` : `<p class="component-note">${state.run ? `Exports unlock when the run completes (current: ${esc(state.run.status)}).` : 'Select or complete an investigation first â€” there is nothing to export yet.'}</p><button class="pill-btn" type="button" disabled aria-disabled="true" title="Complete a run to enable exports">Exports unavailable</button>`}<p class="component-note">ZIP is the backend integrity bundle (hash-checked). MD/HTML/JSON/README/manifest are built in your browser from the same sanitized report â€” no new data is invented.</p></section>`;
}
function settingsView() {
  return `<section class="single-page"><h1>Settings</h1><dl class="report-meta"><dt>Service</dt><dd>${apiOrigin ? esc(apiOrigin) : 'Not configured for this deployment'}</dd><dt>Account</dt><dd>${state.session ? 'Signed in' : 'Not signed in'}</dd><dt>Connection</dt><dd>${!apiOrigin || !auth ? 'Service not configured' : state.session ? 'Signed in Â· NON_AI only' : 'Sign in to start'}</dd><dt>Motion</dt><dd>Reduced-motion preference is respected (animations disabled when your system requests it).</dd></dl><div class="response-actions"><button class="pill-btn" data-action="account">${icon('log-in')} Account</button><button class="pill-btn" data-action="clear-notes">${icon('x')} Clear tab notes</button></div><p class="component-note">Notes live only in this browser tab and are cleared on sign-out. No browser setting here can enable real-model or browser/motion execution.</p></section>`;
}
function saveBlob(blob: Blob, name: string) { const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
async function downloadGenerated(kind: 'md' | 'html' | 'json' | 'manifest' | 'readme') {
  if (!state.run) return;
  const generation = state.epoch; const runId = state.run.run_id;
  try {
    const report = await api.report(runId);
    if (generation !== state.epoch || state.run?.run_id !== runId) return;
    if (report.origin !== 'mock' || report.real !== false) throw new Error('This report has an unsupported origin.');
    const meta = { runId, investigationTitle: state.selected?.title || 'Investigation', generatedFrom: 'GET /v1/runs/{id}/report' };
    const text = kind === 'md' ? buildReportMarkdown(report, meta) : kind === 'html' ? buildReportHtml(report, meta) : kind === 'manifest' ? buildManifest(report, meta) : kind === 'readme' ? buildReadme(report, meta) : JSON.stringify(report, null, 2);
    const type = kind === 'html' ? 'text/html' : kind === 'json' || kind === 'manifest' ? 'application/json' : 'text/markdown';
    const name = kind === 'md' ? 'report.md' : kind === 'html' ? 'report.html' : kind === 'manifest' ? 'manifest.json' : kind === 'readme' ? 'README.md' : 'report.json';
    saveBlob(new Blob([text], { type }), `second-source-${runId}-${name}`);
  } catch (error) { if (generation === state.epoch) setError(error); }
}
function chooseTarget() {
  if (!state.session) { account(); return; }
  if (state.selected) { toast('Start a new investigation to choose another target.'); return; }
  if (!state.targets.length) {
    showDialog('Choose what to investigate', `<p>No supported fixture target is available from this backend right now. Capability status is still shown honestly below; recorded evidence remains available from Research record.</p>${capabilityPicker()}<div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>`);
    return;
  }
  showDialog('Choose what to investigate', `<p>Pick a supported owned fixture. Browser / motion is listed only to state its boundary â€” it cannot be selected. Both fixtures run without AI inference (NON_AI).</p>${capabilityPicker()}<div class="target-options">${state.targets.map(target => `<button class="list-row" type="button" data-target-id="${esc(target.target_id)}">${icon('flask-conical')}<span class="row-main"><strong>${esc(target.label)}</strong><small>${target.target_id === 'owned-ledger-v1' ? 'CLI / fixtures Â· ledger Â· 25-case suite' : 'API / professional Â· loopback HTTP tasks Â· 30-case suite'} Â· NON_AI${target.execution_enabled ? '' : ' Â· execution unavailable'}</small></span></button>`).join('')}</div><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Cancel</button></div>`);
}
function reviewScope() {
  if (!state.session) { account(); return; }
  if (!state.target) { toast('No supported target is available from this backend.'); return; }
  const scope = state.target.scope;
  const http = state.target.target_id === 'owned-http-task-workflow-v1';
  showDialog('Review scope', `<p>Investigate the ${http ? 'owned HTTP task-workflow fixture on loopback' : 'owned ledger fixture'} using the NON_AI control. No external website will be visited and no model call or spending is authorized.</p><ul class="scope-list"><li>${http ? 'Observe scoped task creation, transitions and access rules on the owned local fixture.' : 'Observe the fixtureâ€™s add, list, total and remove behavior.'}</li><li>Evaluate a separate scripted candidate against the independent fixture suite.</li><li>Store the run and permitted evidence under your account.</li></ul><details><summary>View exact scope</summary><pre class="scope-json">${esc(JSON.stringify(scope, null, 2))}</pre><p>Scope digest: <code>${esc(state.target.scope_digest)}</code></p></details><label class="check-row"><input type="checkbox" id="scopeConsent"> I confirm this scope and understand the run is NON_AI.</label><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Cancel</button><button class="pill-btn primary" data-action="create">Create investigation</button></div>`);
}
function confirmAuthorization() {
  const item = state.selected; if (!item) return;
  if (!state.target || item.scope_digest !== state.target.scope_digest) { toast('The stored scope differs from the supported scope.'); return; }
  showDialog('Confirm authorization', `<p>Authorize this investigationâ€™s exact scope. This does not start a run.</p><details><summary>View exact scope</summary><pre class="scope-json">${esc(JSON.stringify(item.scope, null, 2))}</pre></details><p class="component-note">Scope digest: <code>${esc(item.scope_digest)}</code></p><label class="check-row"><input type="checkbox" id="scopeConsent"> I authorize this NON_AI fixture scope.</label><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Cancel</button><button class="pill-btn primary" data-action="confirm-authorization">Authorize scope</button></div>`);
}
async function mutate(action: string) {
  if (state.busy) return;
  const generation = state.epoch;
  state.busy = true; state.error = ''; render();
  try {
    if (action === 'create') {
      const checkbox = document.getElementById('scopeConsent') as HTMLInputElement | null;
      if (!checkbox?.checked) { checkbox?.focus(); return; }
      if (!state.target) throw new Error('The supported target is unavailable.');
      // Reuse both key and immutable payload after a lost acknowledgement.
      const pending = JSON.parse(sessionStorage.getItem('ss-create-pending') || 'null') as { key: string; title: string; digest: string } | null;
      if (pending && pending.digest !== state.target.scope_digest) throw new Error('The available scope changed. Resolve the previous request before creating another.');
      const title = pending?.title || (state.messages[0]?.trim().slice(0, 120) || `${state.target.label} investigation`);
      const key = pending?.key || crypto.randomUUID();
      sessionStorage.setItem('ss-create-pending', JSON.stringify({ key, title, digest: state.target.scope_digest }));
      const created = await api.create(title, state.target.scope, key);
      if (generation !== state.epoch) return;
      state.selected = created;
      try {
        const instruction = (state.messages.join('\n').trim() || title).slice(0, 4000);
        const orch = await api.orchCreate(title, instruction, state.target.target_id, state.target.scope, key);
        await api.orchAuthorize(orch.investigation_id, orch.revision, orch.scope_digest);
        const job = await api.orchEnqueue(orch.investigation_id, (key + '-job'));
        const done = await api.orchExecute(job.job_id);
        const ev = await api.orchEvents(orch.investigation_id);
        sessionStorage.setItem('ss-orch-investigation', orch.investigation_id);
        toast('Investigation created. Orchestration ' + done.status + ' (' + ev.items.length + ' genuine events). Confirm its scope to continue.');
      } catch (orchError) { toast('Investigation created. Orchestration unavailable: ' + (orchError instanceof Error ? orchError.message : 'unknown error') + '. Confirm its scope to continue.'); }
      if (state.ownerId && !saveNotes(sessionStorage, state.ownerId, created.investigation_id, state.messages)) toast('Notes could not be saved in this tab.');
      sessionStorage.removeItem('ss-create-pending'); sessionStorage.setItem('ss-selected-investigation', state.selected.investigation_id);
      state.view = 'conversation'; closeDialog();
      if (created.scope_digest !== state.target.scope_digest) throw new Error('The stored scope differs from the reviewed scope. Do not authorize it; contact an operator.');
      const items = await allPages(after => api.investigations(after));
      if (generation !== state.epoch) return;
      state.investigations = items.sort((a, b) => b.created_at.localeCompare(a.created_at)); toast('Investigation created. Confirm its scope to continue.');
    } else if (action === 'confirm-authorization') {
      const checkbox = document.getElementById('scopeConsent') as HTMLInputElement | null;
      if (!checkbox?.checked) { checkbox?.focus(); return; }
      if (!state.selected) return;
      const authorized = await api.authorize(state.selected); if (generation !== state.epoch) return;
      state.selected = authorized; closeDialog(); toast('Scope authorized.');
    } else if (action === 'queue') {
      if (!state.selected || state.executing) return;
      const storageKey = `ss-queue-key:${state.selected.investigation_id}`;
      const key = sessionStorage.getItem(storageKey) || crypto.randomUUID(); sessionStorage.setItem(storageKey, key);
      const queued = await api.queue(state.selected.investigation_id, key); if (generation !== state.epoch) return;
      if (state.run?.run_id !== queued.run_id) {
        state.events = []; state.verification = null; state.pollError = ''; state.executionError = null;
        state.uncertain = sessionStorage.getItem(`ss-execution-uncertain:${queued.run_id}`) === '1';
        state.actionUncertain = sessionStorage.getItem(`ss-action-uncertain:${queued.run_id}`);
      }
      state.run = queued; sessionStorage.removeItem(storageKey); toast('Run queued.');
    } else if (action === 'cancel') {
      if (!state.run) return;
      const actionKey = `ss-action-uncertain:${state.run.run_id}`; sessionStorage.setItem(actionKey, 'cancel'); state.actionUncertain = 'cancel';
      const cancelled = await api.cancel(state.run); if (generation !== state.epoch) return;
      sessionStorage.removeItem(actionKey); state.actionUncertain = null; if (state.run && acceptsRunRevision(state.run, cancelled)) state.run = cancelled; await refresh(false); if (generation === state.epoch) toast('Cancellation requested.');
    } else if (action === 'reconcile') {
      if (!state.run) return;
      const actionKey = `ss-action-uncertain:${state.run.run_id}`; sessionStorage.setItem(actionKey, 'reconcile'); state.actionUncertain = 'reconcile';
      const reconciled = await api.reconcile(state.run); if (generation !== state.epoch) return;
      sessionStorage.removeItem(actionKey); state.actionUncertain = null; if (state.run && acceptsRunRevision(state.run, reconciled)) state.run = reconciled; await refresh(false); if (generation === state.epoch) toast('Run status checked.');
    }
  } catch (error) { if (generation === state.epoch) { state.error = describe(error); render(); } }
  finally { if (generation === state.epoch) { state.busy = false; render(); } }
}
async function execute() {
  if (!state.run || !state.selected || !state.target?.execution_enabled || state.selected.scope_digest !== state.target.scope_digest || state.executing || state.uncertain) return;
  const run = state.run; const generation = state.epoch;
  state.executing = true; state.uncertain = true; sessionStorage.setItem(`ss-execution-uncertain:${run.run_id}`, '1'); render();
  pollTimer = window.setTimeout(() => { void refresh(false); }, 1000);
  try {
    const result = await api.execute(run);
    if (generation !== state.epoch || !state.run || state.run.run_id !== run.run_id) return;
    if (acceptsRunRevision(state.run, result)) state.run = result;
    if (state.run.status !== 'queued' && state.run.status !== 'running') { sessionStorage.removeItem(`ss-execution-uncertain:${run.run_id}`); state.uncertain = false; }
  } catch (error) {
    if (generation === state.epoch && state.run?.run_id === run.run_id) {
      if (error instanceof ApiError && executionDefinitelyRefused(error.status, error.code)) {
        sessionStorage.removeItem(`ss-execution-uncertain:${run.run_id}`); state.uncertain = false;
      }
      state.error = describe(error);
      if (error instanceof ApiError && error.uncertain) state.executionError = { runId: run.run_id, message: state.error };
      render();
    }
  } finally {
    if (generation === state.epoch && state.run?.run_id === run.run_id) {
      state.executing = false; await refresh(false);
      render();
    }
  }
}
function showVerification() {
  const v = state.verification;
  if (!v?.evaluation) { toast('Verification is not available for this run.'); return; }
  const e = v.evaluation;
  const repair = v.repair;
  showDialog('Independent verification', `<p><strong>NON_AI fixture comparison</strong> Â· not a genuine model score.</p><div class="scoreline"><strong>${e.passed} passed</strong><span>${e.failed} failed</span><span>${e.indeterminate} indeterminate</span><span>${e.total} total</span></div>${repair ? `<h3>Candidate lineage</h3><p>Selected: ${esc(repair.selected_version)} Â· ${esc(repair.verdict.replaceAll('_', ' '))}</p><ol class="lineage">${repair.versions.map(version => `<li>Round ${version.round}: ${version.evaluation.passed}/${version.evaluation.total} passed Â· ${esc(version.candidate_digest.slice(0, 19))}â€¦</li>`).join('')}</ol>${state.target?.target_id === 'owned-http-task-workflow-v1' ? '<p class="component-note">This deterministic repair control uses previously collected active evidence; it does not show AI independently discovering a fix.</p>' : ''}` : '<p>Repair history is unavailable.</p>'}<p class="component-note">Candidate files, detailed observations and sealed evaluator cases are not available in this interface.</p><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>`);
}
function vikunjaSection() {
  const record = vikunjaRecord();
  if (!record) {
    return `<h3>Vikunja professional benchmark â€” <span class="evidence-label">GEMMA_TEST</span></h3><p role="status">Recorded Vikunja evidence is unavailable in this build. No score is shown rather than a fabricated one. The sanitized summary is missing or failed validation.</p>`;
  }
  const rows = record.arms.map(arm => `<tr><th scope="row">${esc(arm.arm)}</th><td>${esc(arm.condition)}</td><td>${provenancePill(arm.provenance)}</td><td><span class="status-pill ${arm.status === 'scored' ? '' : 'fail'}">${arm.status === 'scored' ? 'Scored' : 'Provider failure'}</span></td><td>${esc(armScoreText(arm))}</td></tr>`).join('');
  const compiled = record.compiled;
  const compiledBlock = compiled.status === 'available'
    ? `<p>Compiled deterministically from recorded observations. Artifact: <code>${esc(compiled.artifact)}</code></p><div class="scoreline"><strong>${compiled.passed} passed</strong><span>${compiled.total} total</span><span>${esc(compiledScoreText(compiled))}</span></div><dl class="report-meta"><dt>Compiled artifact SHA-256</dt><dd><code>${esc(compiled.artifactSha256)}</code></dd></dl>`
    : `<p role="status"><span class="status-pill muted">Pending</span> ${esc(compiled.reason)} State: ${esc(compiledScoreText(compiled))}. This entry appears here so the coordinator-added artifact will render in place; until then no compiled score exists.</p>`;
  return `<h3>Vikunja professional benchmark â€” <span class="evidence-label">GEMMA_TEST</span> ${provenancePill('model-authored')}</h3><p>${esc(record.benchmark)}. Model: <strong>${esc(record.model)}</strong> via the gemma-test provider (${esc(record.classification)}). This is a Gemma development test, <strong>not</strong> Meta Muse and not <span class="evidence-label">REAL_MODEL</span>. Provenance is shown per row: model-authored candidates, the runtime-supplied oracle plumbing, and evidence-compiled (NON_AI) output are never merged. The model authored only a declarative candidate spec; the generic interpreter supplies ${esc(record.interpreterSupplies)}.</p><table class="evidence-table"><caption class="sr-only">Gemma Vikunja arms</caption><thead><tr><th scope="col">Arm</th><th scope="col">Condition</th><th scope="col">Provenance</th><th scope="col">Status</th><th scope="col">Held-out</th></tr></thead><tbody>${rows}</tbody></table><p class="component-note">Provider failures are unscored and are never reported as 0/6. A (prior only) vs C (grounded) does not isolate the coverage-gate effect.</p><h3>Oracle control â€” <span class="evidence-label">NON_AI</span> ${provenancePill(record.oracle.provenance)}</h3><p>${esc(record.oracle.description)}</p><div class="scoreline"><strong>${record.oracle.passed} passed</strong><span>${record.oracle.total} total</span><span>NON_AI control â€” never an AI result</span></div><dl class="report-meta"><dt>Interpreter SHA-256</dt><dd><code>${esc(record.interpreterSha256)}</code></dd><dt>Evaluator SHA-256</dt><dd><code>${esc(record.evaluatorSha256)}</code></dd><dt>Held-out suite SHA-256</dt><dd><code>${esc(record.heldOutSha256)}</code></dd></dl><h3>Compiled evidence â€” <span class="evidence-label">EVIDENCE_COMPILED</span> <span class="evidence-label">NON_AI</span> ${provenancePill(compiled.provenance)}</h3>${compiledBlock}<h3>Limitations</h3><ul class="scope-list">${record.limitations.map(item => `<li>${esc(item)}</li>`).join('')}</ul><p class="component-note">Sources: ${record.sourceArtifacts.map(item => esc(item)).join(' Â· ')}</p>`;
}
function showResearch() {
  const ledger = HISTORICAL_LEDGER;
  showDialog('Genuine evidence records', `<p>This is a previously recorded research result, not an investigation run from this application. Starting genuine model inference is not available here. Labels are exact: <span class="evidence-label">REAL_MODEL</span>, <span class="evidence-label">GEMMA_TEST</span> and <span class="evidence-label">NON_AI</span> are never interchangeable, and scores across targets are not comparable.</p><h3>Historical ledger â€” <span class="evidence-label">REAL_MODEL</span> ${provenancePill(ledger.provenance)}</h3><p>An admitted candidate generated by <strong>${esc(ledger.model)}</strong>, evaluated on the independent frozen ledger suite.</p><div class="scoreline"><strong>${ledger.passed} passed</strong><span>${ledger.failed} failed</span><span>${ledger.indeterminate} indeterminate</span><span>${ledger.total} total</span></div><p>${esc(ledger.note)}</p><dl class="report-meta"><dt>Candidate SHA-256</dt><dd><code>${esc(ledger.candidateSha256)}</code></dd><dt>Evaluation suite SHA-256</dt><dd><code>${esc(ledger.suiteSha256)}</code></dd></dl><p>No genuine repair was performed. This result does not establish general equivalence.</p><h3>Separate NON_AI ledger control</h3><p>A local deterministic mock test recorded 22 passed, 3 failed and 0 indeterminate out of 25. It is <span class="evidence-label">NON_AI</span>: not a Meta-generated candidate or a live result from this application. These figures are not a fair performance comparison.</p><p><a href="https://github.com/Ankit6149/second-source/issues/25#issuecomment-6547391799" target="_blank" rel="noopener noreferrer">Read the research review and limitations</a></p>${vikunjaSection()}<p><a href="https://github.com/Ankit6149/second-source/issues/25#issuecomment-6594846181" target="_blank" rel="noopener noreferrer">Read the product integration contract (issue #25)</a></p><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>`);
}
async function showReport() {
  if (!state.run) return;
  const generation = state.epoch; const runId = state.run.run_id;
  try {
    const report = await api.report(runId);
    if (generation !== state.epoch || state.run?.run_id !== runId) return;
    if (report.origin !== 'mock' || report.real !== false) throw new Error('This report has an unsupported origin.');
    const evaluation = report.evaluation;
    const counts = evaluation && typeof evaluation === 'object' ? evaluation as Record<string, unknown> : null;
    const validCounts = counts && ['passed', 'failed', 'indeterminate', 'total'].every(key => Number.isSafeInteger(counts[key]) && (counts[key] as number) >= 0)
      && (counts.passed as number) + (counts.failed as number) + (counts.indeterminate as number) === counts.total;
    const labels: Record<string, string> = { scope_digest: 'Authorized scope', suite_digest: 'Evaluation suite', spec_digest: 'Candidate specification', approved_context_digest: 'Approved context', plan_digest: 'Plan' };
    const digests = Object.entries(labels).flatMap(([key, label]) => {
      const value = report[key];
      return typeof value === 'string' && /^(?:sha256:)?[a-f0-9]{64}$/.test(value) ? [`<dt>${label}</dt><dd><code>${esc(value)}</code></dd>`] : [];
    }).join('');
    showDialog('Sanitized report', `<p><strong>NON_AI fixture result.</strong> This report is produced by the backend and does not represent a genuine model reconstruction.</p>${validCounts ? `<div class="scoreline"><strong>${counts.passed} passed</strong><span>${counts.failed} failed</span><span>${counts.indeterminate} indeterminate</span><span>${counts.total} total</span></div>` : '<p>Evaluation counts are unavailable.</p>'}${digests ? `<h3>Provenance</h3><dl class="report-meta">${digests}</dl>` : '<p>Provenance digests are unavailable.</p>'}<p class="component-note">These counts cover only the independent fixture suite. Detailed cases and mismatch explanations are not exposed by this API.</p><details><summary>View sanitized report data</summary><pre class="scope-json">${esc(JSON.stringify(report, null, 2))}</pre></details><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>`);
  }
  catch (error) { if (generation === state.epoch) setError(error); }
}
async function downloadExport() {
  if (!state.run) return;
  const generation = state.epoch; const runId = state.run.run_id;
  try { const blob = await api.export(runId); if (generation !== state.epoch || state.run?.run_id !== runId) return; const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `second-source-${runId}.zip`; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
  catch (error) { if (generation === state.epoch) setError(error); }
}

document.addEventListener('click', event => {
  const target = event.target instanceof Element ? event.target.closest<HTMLElement>('[data-action],[data-investigation],[data-suggestion],[data-target-id]') : null;
  if (!target) return;
  if (target.dataset.targetId) {
    const chosen = state.targets.find(item => item.target_id === target.dataset.targetId);
    if (chosen && !state.selected) { state.target = chosen; reviewScope(); }
    return;
  }
  if (target.dataset.investigation) { void openInvestigation(target.dataset.investigation); return; }
  if (target.dataset.suggestion) { state.draft = target.dataset.suggestion; sessionStorage.setItem('ss-product-draft', state.draft); render(); const input = el<HTMLTextAreaElement>('promptInput'); input?.dispatchEvent(new Event('input', { bubbles: true })); input?.focus(); return; }
  const action = target.dataset.action;
  if (action === 'new') { ++state.epoch; stopPolling(); state.executing = false; state.busy = false; state.view = 'home'; state.selected = null; state.run = null; state.events = []; state.verification = null; state.messages = []; state.pollError = ''; state.executionError = null; state.uncertain = false; state.actionUncertain = null; sessionStorage.removeItem('ss-selected-investigation'); render(); }
  else if (action === 'library') { state.view = 'library'; render(); }
  else if (action === 'account') account();
  else if (action === 'sign-in') { void signIn().catch(setError); }
  else if (action === 'sign-out') { const owner = state.ownerId; void signOut().then(() => { if (owner) clearOwnerNotes(sessionStorage, owner); sessionStorage.removeItem('ss-selected-investigation'); sessionStorage.removeItem('ss-create-pending'); sessionStorage.removeItem('ss-product-draft'); state.draft = ''; state.messages = []; closeDialog(); }).catch(setError); }
  else if (action === 'select-target' || action === 'review-scope') chooseTarget();
  else if (action === 'authorize') confirmAuthorization();
  else if (action === 'create' || action === 'confirm-authorization' || action === 'queue' || action === 'cancel' || action === 'reconcile') void mutate(action);
  else if (action === 'execute') void execute();
  else if (action === 'refresh') void refresh();
  else if (action === 'engine-check') void refreshEngine();
  else if (action === 'engine-run') void runEngineInvestigation();
  else if (action === 'candidate') showCandidate();
  else if (action === 'compare') { state.view = 'compare'; render(); }
  else if (action === 'reports') { state.view = 'reports'; render(); }
  else if (action === 'settings') { state.view = 'settings'; render(); }
  else if (action === 'clear-notes') { state.messages = []; state.draft = ''; sessionStorage.removeItem('ss-product-draft'); if (state.ownerId) clearOwnerNotes(sessionStorage, state.ownerId); toast('Tab notes cleared.'); render(); }
  else if (action === 'download-md') void downloadGenerated('md');
  else if (action === 'download-html') void downloadGenerated('html');
  else if (action === 'download-json') void downloadGenerated('json');
  else if (action === 'download-manifest') void downloadGenerated('manifest');
  else if (action === 'download-readme') void downloadGenerated('readme');
  else if (action === 'verification') showVerification();
  else if (action === 'research') showResearch();
  else if (action === 'report') void showReport();
  else if (action === 'export') void downloadExport();
  else if (action === 'close-dialog') closeDialog();
  else if (action === 'dismiss-error') { state.error = ''; render(); }
  else if (action === 'sample-toast') toast('Component example');
  else if (action === 'sample-dialog') showDialog('Dialog example', '<p>This is a component example.</p><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>');
});
document.addEventListener('submit', event => {
  if (!(event.target instanceof HTMLFormElement) || event.target.id !== 'composer') return;
  event.preventDefault(); const input = el<HTMLTextAreaElement>('promptInput'); const text = input.value.trim(); if (!text) { input.focus(); return; }
  if (text.length > 4000 || state.messages.length >= 100) {
    state.error = text.length > 4000 ? 'Keep each note within 4,000 characters.' : 'This tab can hold up to 100 notes. Start a new investigation to continue.';
    render(); input.focus(); return;
  }
  state.error = ''; state.messages.push(text); state.draft = ''; sessionStorage.removeItem('ss-product-draft'); state.view = 'conversation';
  if (state.ownerId && state.selected && !saveNotes(sessionStorage, state.ownerId, state.selected.investigation_id, state.messages)) toast('Notes could not be saved in this tab.');
  render();
  el<HTMLTextAreaElement>('promptInput').focus(); el('scrollArea').scrollTop = el('scrollArea').scrollHeight;
});
document.addEventListener('input', event => {
  if (!(event.target instanceof HTMLTextAreaElement) || event.target.id !== 'promptInput') return;
  const input = event.target; state.draft = input.value; sessionStorage.setItem('ss-product-draft', state.draft);
  input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  const hint = detectReference(input.value); const detection = el('detection'); detection.hidden = !hint;
  detection.innerHTML = hint ? `${icon('link')} <span><strong>${esc(hint.label)}</strong><br><small>${esc(hint.description)}</small></span>` : ''; renderIcons();
});
document.addEventListener('keydown', event => {
  if (event.target instanceof HTMLTextAreaElement && event.target.id === 'promptInput' && event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault(); el<HTMLFormElement>('composer').requestSubmit();
  }
});
const sidebarMedia = matchMedia('(max-width: 760px)');
function syncSidebar() {
  const shell = el('shell');
  const expanded = sidebarMedia.matches ? shell.classList.contains('mobile-open') : !shell.classList.contains('sidebar-collapsed');
  el('sidebar').inert = !expanded;
  el('toggleSide').setAttribute('aria-expanded', String(expanded));
}
el('toggleSide').addEventListener('click', () => { const shell = el('shell'); shell.classList.toggle(sidebarMedia.matches ? 'mobile-open' : 'sidebar-collapsed'); syncSidebar(); });
for (const id of ['closeSide', 'mobileScrim']) el(id).addEventListener('click', () => { const focusedInside = el('sidebar').contains(document.activeElement); const shell = el('shell'); if (sidebarMedia.matches) shell.classList.remove('mobile-open'); else shell.classList.add('sidebar-collapsed'); syncSidebar(); if (focusedInside) el('toggleSide').focus(); });
sidebarMedia.addEventListener('change', syncSidebar); syncSidebar();
el<HTMLDialogElement>('dialog').addEventListener('close', () => { if (currentDialogReturn?.isConnected) currentDialogReturn.focus(); else el('main').focus(); });
state.view = new URLSearchParams(location.search).get('screen') === 'system' ? 'system' : 'home';
render(); observeSession(session => { void hydrate(session); }); void refreshEngine();

