import './fonts.css';
import './design.css';
import './product.css';
import { createIcons, PanelLeft, PanelLeftClose, SquarePen, FolderOpen, SwatchBook, ChevronUp, ArrowUp, ShieldCheck, FileText, ListChecks, Download, CircleHelp, X, Play, Square, RefreshCw, Clock, Check, AlertTriangle, LogIn, LogOut, Link, FlaskConical, MessageSquare, ExternalLink } from 'lucide';
import type { Session } from '@supabase/supabase-js';
import { auth, observeSession, signIn, signOut } from './auth';
import { Api, ApiError, validatedOrigin, type Target, type Investigation, type Run, type RunEvent, type Verification } from './api';
import { detectReference } from './reference';
import { clearOwnerNotes, loadNotes, saveNotes } from './notes';
import { outcomeConfirmed, pollFailureMessage, pollRetryDelay } from './polling';

const icons = { PanelLeft, PanelLeftClose, SquarePen, FolderOpen, SwatchBook, ChevronUp, ArrowUp, ShieldCheck, FileText, ListChecks, Download, CircleHelp, X, Play, Square, RefreshCw, Clock, Check, AlertTriangle, LogIn, LogOut, Link, FlaskConical, MessageSquare, ExternalLink };
const icon = (name: string) => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const esc = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c] || c));
const el = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const apiOrigin = validatedOrigin(import.meta.env.VITE_API_ORIGIN || '', import.meta.env.DEV);
const state: {
  session: Session | null; ownerId: string | null; investigations: Investigation[]; target: Target | null; selected: Investigation | null;
  run: Run | null; events: RunEvent[]; verification: Verification | null; messages: string[]; draft: string;
  view: 'home' | 'conversation' | 'library' | 'system'; loading: boolean; error: string; pollError: string; uncertain: boolean; actionUncertain: string | null;
  executionError: { runId: string; message: string } | null;
  busy: boolean; executing: boolean; epoch: number;
} = { session: null, ownerId: null, investigations: [], target: null, selected: null, run: null, events: [], verification: null,
  messages: [], draft: sessionStorage.getItem('ss-product-draft') || '', view: 'home', loading: false, error: '', pollError: '',
  uncertain: false, actionUncertain: null, executionError: null, busy: false, executing: false, epoch: 0 };
const api = new Api(apiOrigin, () => state.session?.access_token || null);
let pollTimer: number | undefined;
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
      state.session = null; state.ownerId = null; state.target = null; state.investigations = []; state.selected = null;
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
  return `<form class="composer" id="composer"><div id="draftContext"><div class="detection" id="detection" ${hint ? '' : 'hidden'}>${hint ? `${icon('link')} <span><strong>${esc(hint.label)}</strong><br><small>${esc(hint.description)}</small></span>` : ''}</div></div><label class="sr-only" for="promptInput">Describe the software behavior you want to investigate</label><textarea rows="2" id="promptInput" maxlength="4000" placeholder="Ask about a workflow, software, or a reference…">${esc(state.draft)}</textarea><div class="composer-lower"><div class="tool-row"><button class="small-tool" type="button" data-action="select-target">${icon('flask-conical')} Choose a supported target</button><button class="tool-icon" type="button" disabled title="Attachments are not supported yet" aria-label="Attachments unavailable">+</button></div><div class="send-area"><span class="kbd-help">Shift + Enter for new line</span><button class="send-btn" type="submit" aria-label="Send message">${icon('arrow-up')}</button></div></div></form>`;
}

function renderHome() {
  return `<section class="empty-home"><h1>Software, <em>understood.</em></h1><p>Investigate how authorized software behaves, then examine the evidence and an independent comparison.</p><div class="suggestion-row"><button class="suggestion" data-suggestion="Understand how the owned ledger handles repeated inputs.">${icon('circle-help')} Understand behavior</button><button class="suggestion" data-suggestion="Compare the owned ledger with a scoped candidate.">${icon('list-checks')} Compare behavior</button></div><p class="home-note">${state.session ? state.target ? 'Available here: the owned ledger NON_AI fixture.' : 'No supported target is currently available.' : 'Sign in to see the targets available from the connected service.'} Websites and genuine AI reconstruction are not yet available here.</p></section>`;
}
function controls() {
  if (!state.session) return `<button class="pill-btn primary" data-action="account">${icon('log-in')} Sign in to start</button>`;
  if (!state.selected) return state.target ? `<button class="pill-btn primary" data-action="review-scope" ${state.busy ? 'disabled' : ''}>${icon('shield-check')} Review scope</button>` : `<button class="pill-btn" disabled>Supported target unavailable</button>`;
  if (state.selected.status === 'created') return state.target && state.selected.scope_digest === state.target.scope_digest
    ? `<button class="pill-btn primary" data-action="authorize" ${state.busy ? 'disabled' : ''}>${icon('shield-check')} Confirm scope</button>`
    : `<p class="component-note">This stored scope differs from the currently supported scope. Authorization is unavailable; contact an operator.</p>`;
  if (!state.run) return `<button class="pill-btn primary" data-action="queue" ${state.busy || !state.target ? 'disabled' : ''}>${icon('clock')} Queue mock run</button>${!state.target ? '<p class="component-note">The supported target is unavailable.</p>' : ''}`;
  if (state.run.status === 'queued') return state.uncertain
    ? `<button class="pill-btn" data-action="refresh">${icon('refresh-cw')} Check status</button><p class="component-note">The execution request has an uncertain outcome. It will not be retried automatically.</p>`
    : `<button class="pill-btn primary" data-action="execute" ${state.busy || state.executing || state.actionUncertain || !state.target?.execution_enabled ? 'disabled' : ''}>${icon('play')} Start NON_AI run</button><button class="pill-btn" data-action="cancel" ${state.busy || state.actionUncertain ? 'disabled' : ''}>${icon('square')} Cancel queued run</button>${state.actionUncertain ? '<p class="component-note">The cancellation outcome is uncertain; check status before taking another action.</p><button class="pill-btn quiet" data-action="refresh">Check status</button>' : ''}${!state.target?.execution_enabled ? '<p class="component-note">Execution is disabled or unavailable on this backend.</p>' : ''}`;
  if (state.run.status === 'running') return `<button class="pill-btn" data-action="cancel" ${state.busy || state.run.cancel_requested || state.actionUncertain ? 'disabled' : ''}>${icon('square')} ${state.run.cancel_requested ? 'Cancellation requested' : 'Cancel run'}</button><button class="pill-btn quiet" data-action="refresh">${icon('refresh-cw')} Check status</button><button class="pill-btn quiet" data-action="reconcile" ${state.busy || state.actionUncertain ? 'disabled' : ''}>Check recovery</button>${state.actionUncertain ? '<p class="component-note">The previous request has an uncertain outcome; it will not be repeated automatically.</p>' : ''}`;
  if (state.run.status === 'needs_reconciliation') return `<p class="component-note">This run is quarantined after an uncertain or interrupted operation. It will not restart automatically; an operator must review it.</p><button class="pill-btn quiet" data-action="refresh">Check status</button>`;
  if (state.run.status === 'completed') return `<button class="pill-btn primary" data-action="verification">${icon('list-checks')} View verification</button><button class="pill-btn" data-action="report">${icon('file-text')} Open report</button><button class="pill-btn" data-action="export">${icon('download')} Download integrity export</button>`;
  return `<button class="pill-btn" data-action="refresh">${icon('refresh-cw')} Refresh status</button>${state.run.status === 'failed' || state.run.status === 'cancelled' ? `<button class="pill-btn" data-action="queue" ${state.busy || !state.target ? 'disabled' : ''}>${icon('clock')} Queue a new mock run</button>` : ''}`;
}
function eventName(event: RunEvent) {
  const labels: Record<string,string> = { run_claimed: 'Worker claimed the run', stage_started: `Stage: ${event.stage || 'unknown'}`, repair_started: 'Bounded mock retry started', repair_completed: 'Bounded mock retry finished', run_completed: 'Run completed', run_failed: 'Run failed', run_cancelled: 'Run cancelled', run_needs_reconciliation: 'Run needs reconciliation', run_queued: 'Run queued' };
  return labels[event.event_type] || event.event_type.replaceAll('_', ' ');
}
function investigationCard() {
  const run = state.run;
  return `<div class="message assistant"><div class="assistant-mark">${icon('shield-check')}</div><div class="response"><h2>${state.selected ? esc(state.selected.title) : 'Choose what to investigate.'}</h2><p>${state.selected ? 'This investigation is limited to the approved owned-ledger fixture.' : !state.session ? 'Sign in to see the targets available from the connected service. A URL or software name does not grant permission or start an investigation.' : state.target ? 'This service currently offers the owned-ledger fixture. A URL or software name does not grant permission or start an investigation.' : 'No supported target is currently available from this service.'}</p>${state.selected ? `<div class="artifact"><div class="artifact-top"><div class="artifact-symbol">${icon('file-text')}</div><div><strong>Owned ledger · NON_AI</strong><small>Scope ${esc(state.selected.scope_digest.slice(0, 12))}…</small></div><span class="artifact-tag">${esc(run?.status || state.selected.status)}</span></div>${run ? `<div class="artifact-bottom">${esc(run.stage ? `Stage: ${run.stage}` : 'No stage reported')}${run.error_code ? ` · ${esc(run.error_code)}` : ''}</div>` : ''}</div>` : ''}${state.events.length ? `<details class="activity"><summary>Activity (${state.events.length})</summary><ol>${state.events.map(e => `<li>${esc(eventName(e))}</li>`).join('')}</ol></details>` : ''}<div class="response-actions">${controls()}</div><p class="component-note">Your notes are kept only in this browser tab and are cleared on sign-out. The backend does not yet save conversations or answer follow-up questions.</p></div></div>`;
}
function conversation() {
  const messages = state.messages.map(message => `<div class="message user"><div class="bubble">${esc(message)}</div></div>`).join('');
  return `<section class="conversation">${messages}${investigationCard()}</section>`;
}
function library() {
  if (!state.session) return `<section class="single-page"><h1>Your work</h1><p>Sign in to see your saved investigations.</p><button class="pill-btn primary" data-action="account">Sign in</button></section>`;
  return `<section class="single-page"><h1>Your work</h1><p>Investigations saved to your account.</p>${state.loading ? '<p>Loading investigations…</p>' : state.investigations.length ? state.investigations.map(item => `<button class="list-row" data-investigation="${esc(item.investigation_id)}">${icon('message-square')}<span class="row-main"><strong>${esc(item.title)}</strong><small>${esc(item.status)} · ${esc(item.created_at)}</small></span></button>`).join('') : '<p>No investigations yet. Choose a supported target to start.</p>'}<p class="component-note">Rename, deletion and conversation search are not yet supported.</p></section>`;
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
  el('connectionLabel').textContent = !apiOrigin || !auth ? 'Service not configured' : state.session ? 'Signed in · NON_AI only' : 'Sign in to start';
  el('topName').textContent = state.view === 'library' ? 'Your work' : state.view === 'system' ? 'Component showroom' : state.selected?.title || 'Second Source';
  el('history').innerHTML = state.investigations.slice(0, 12).map(item => `<button class="history-item ${item.investigation_id === state.selected?.investigation_id ? 'active' : ''}" data-investigation="${esc(item.investigation_id)}">${icon('message-square')}<span class="history-title">${esc(item.title)}</span></button>`).join('');
  const message = state.error ? `<div class="inline-note error" role="alert">${icon('alert-triangle')}<span>${esc(state.error)}</span>${state.selected && state.session ? '<button class="pill-btn quiet" data-action="refresh">Check status</button>' : ''}<button class="quiet-dismiss" data-action="dismiss-error" aria-label="Dismiss error">×</button></div>` : '';
  const polling = state.pollError ? `<div class="inline-note error" role="status">${icon('alert-triangle')}<span>${esc(state.pollError)}</span><button class="pill-btn quiet" data-action="refresh">Check status</button></div>` : '';
  el('content').innerHTML = message + polling + (state.view === 'home' ? renderHome() : state.view === 'conversation' ? conversation() : state.view === 'library' ? library() : showroom());
  renderedRunId = state.run?.run_id;
  const activity = content.querySelector<HTMLDetailsElement>('details.activity'); if (activity && activityOpen) activity.open = true;
  if (focusedAction) {
    const replacement = [...content.querySelectorAll<HTMLButtonElement>('[data-action]')].find(button => button.dataset.action === focusedAction && !button.disabled);
    replacement?.focus({ preventScroll: true });
  }
  el('dock').hidden = state.view === 'library' || state.view === 'system';
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
    state.investigations = []; state.target = null; state.selected = null; state.run = null; state.events = []; state.verification = null;
    state.messages = []; state.draft = ''; state.view = 'home';
  }
  state.session = session; state.ownerId = null; state.error = ''; state.pollError = ''; state.executionError = null; state.executing = false; state.busy = false; state.actionUncertain = null; stopPolling();
  if (!session || !apiOrigin) {
    state.investigations = []; state.target = null; state.selected = null; state.run = null; state.events = []; state.verification = null;
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
      state.investigations = []; state.target = null; state.selected = null; state.run = null; state.events = []; state.verification = null; state.view = 'home';
    }
    sessionStorage.setItem('ss-session-owner', identity.owner_id);
    const [targets, items] = await Promise.all([api.targets(), allPages(after => api.investigations(after))]);
    if (generation !== state.epoch) return;
    state.target = targets.find(target => target.target_id === 'owned-ledger-v1' && target.origin === 'mock' && target.real === false) || null;
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
    state.selected = item; state.run = [...runs].sort((a, b) => b.created_at.localeCompare(a.created_at))[0] || null; state.events = []; state.verification = null;
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
    if (generation !== state.epoch || state.run?.run_id !== runId) return;
    state.run = run; state.events = events; state.pollError = '';
    if (state.executionError?.runId === runId && outcomeConfirmed(run.status)) {
      if (state.error === state.executionError.message) state.error = '';
      state.executionError = null;
    }
    if (run.cancel_requested || !['queued', 'running'].includes(run.status)) {
      sessionStorage.removeItem(`ss-action-uncertain:${runId}`); state.actionUncertain = null;
    }
    if (run.status === 'completed') {
      const verification = await api.verification(runId);
      if (generation !== state.epoch || state.run?.run_id !== runId) return;
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
function reviewScope() {
  if (!state.session) { account(); return; }
  if (!state.target) { toast('No supported target is available from this backend.'); return; }
  const scope = state.target.scope;
  showDialog('Review scope', `<p>Investigate the owned ledger fixture using the NON_AI control. No website will be visited and no model call or spending is authorized.</p><ul class="scope-list"><li>Observe the fixture’s add, list, total and remove behavior.</li><li>Evaluate a separate scripted candidate against the independent fixture suite.</li><li>Store the run and permitted evidence under your account.</li></ul><details><summary>View exact scope</summary><pre class="scope-json">${esc(JSON.stringify(scope, null, 2))}</pre><p>Scope digest: <code>${esc(state.target.scope_digest)}</code></p></details><label class="check-row"><input type="checkbox" id="scopeConsent"> I confirm this scope and understand the run is NON_AI.</label><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Cancel</button><button class="pill-btn primary" data-action="create">Create investigation</button></div>`);
}
function confirmAuthorization() {
  const item = state.selected; if (!item) return;
  if (!state.target || item.scope_digest !== state.target.scope_digest) { toast('The stored scope differs from the supported scope.'); return; }
  showDialog('Confirm authorization', `<p>Authorize this investigation’s exact scope. This does not start a run.</p><details><summary>View exact scope</summary><pre class="scope-json">${esc(JSON.stringify(item.scope, null, 2))}</pre></details><p class="component-note">Scope digest: <code>${esc(item.scope_digest)}</code></p><label class="check-row"><input type="checkbox" id="scopeConsent"> I authorize this NON_AI fixture scope.</label><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Cancel</button><button class="pill-btn primary" data-action="confirm-authorization">Authorize scope</button></div>`);
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
      const title = pending?.title || (state.messages[0]?.trim().slice(0, 120) || 'Owned ledger investigation');
      const key = pending?.key || crypto.randomUUID();
      sessionStorage.setItem('ss-create-pending', JSON.stringify({ key, title, digest: state.target.scope_digest }));
      const created = await api.create(title, state.target.scope, key);
      if (generation !== state.epoch) return;
      state.selected = created;
      if (state.ownerId && !saveNotes(sessionStorage, state.ownerId, created.investigation_id, state.messages)) toast('Notes could not be saved in this tab.');
      sessionStorage.removeItem('ss-create-pending'); sessionStorage.setItem('ss-selected-investigation', state.selected.investigation_id);
      state.view = 'conversation'; closeDialog();
      if (created.scope_digest !== state.target.scope_digest) throw new Error('The stored scope differs from the reviewed scope. Do not authorize it; contact an operator.');
      state.investigations = (await allPages(after => api.investigations(after))).sort((a, b) => b.created_at.localeCompare(a.created_at)); toast('Investigation created. Confirm its scope to continue.');
    } else if (action === 'confirm-authorization') {
      const checkbox = document.getElementById('scopeConsent') as HTMLInputElement | null;
      if (!checkbox?.checked) { checkbox?.focus(); return; }
      if (!state.selected) return;
      const authorized = await api.authorize(state.selected); if (generation !== state.epoch) return;
      state.selected = authorized; closeDialog(); toast('Scope authorized.');
    } else if (action === 'queue') {
      if (!state.selected) return;
      const storageKey = `ss-queue-key:${state.selected.investigation_id}`;
      const key = sessionStorage.getItem(storageKey) || crypto.randomUUID(); sessionStorage.setItem(storageKey, key);
      const queued = await api.queue(state.selected.investigation_id, key); if (generation !== state.epoch) return;
      state.run = queued; sessionStorage.removeItem(storageKey); toast('Run queued.');
    } else if (action === 'cancel') {
      if (!state.run) return;
      const actionKey = `ss-action-uncertain:${state.run.run_id}`; sessionStorage.setItem(actionKey, 'cancel'); state.actionUncertain = 'cancel';
      const cancelled = await api.cancel(state.run); if (generation !== state.epoch) return;
      sessionStorage.removeItem(actionKey); state.actionUncertain = null; state.run = cancelled; await refresh(false); toast('Cancellation requested.');
    } else if (action === 'reconcile') {
      if (!state.run) return;
      const actionKey = `ss-action-uncertain:${state.run.run_id}`; sessionStorage.setItem(actionKey, 'reconcile'); state.actionUncertain = 'reconcile';
      const reconciled = await api.reconcile(state.run); if (generation !== state.epoch) return;
      sessionStorage.removeItem(actionKey); state.actionUncertain = null; state.run = reconciled; await refresh(false); toast('Run status checked.');
    }
  } catch (error) { if (generation === state.epoch) { state.error = describe(error); render(); } }
  finally { if (generation === state.epoch) { state.busy = false; render(); } }
}
async function execute() {
  if (!state.run || !state.target?.execution_enabled || state.executing || state.uncertain) return;
  const run = state.run; const generation = state.epoch;
  state.executing = true; state.uncertain = true; sessionStorage.setItem(`ss-execution-uncertain:${run.run_id}`, '1'); render();
  pollTimer = window.setTimeout(() => { void refresh(false); }, 1000);
  try {
    const result = await api.execute(run);
    if (generation !== state.epoch) return;
    state.run = result;
    if (result.status !== 'queued' && result.status !== 'running') { sessionStorage.removeItem(`ss-execution-uncertain:${run.run_id}`); state.uncertain = false; }
  } catch (error) {
    if (generation === state.epoch) {
      state.error = describe(error);
      if (error instanceof ApiError && error.uncertain) state.executionError = { runId: run.run_id, message: state.error };
      render();
    }
  } finally {
    if (generation === state.epoch) {
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
  showDialog('Independent verification', `<p><strong>NON_AI fixture comparison</strong> · not a genuine model score.</p><div class="scoreline"><strong>${e.passed} passed</strong><span>${e.failed} failed</span><span>${e.indeterminate} indeterminate</span><span>${e.total} total</span></div>${repair ? `<h3>Candidate lineage</h3><p>Selected: ${esc(repair.selected_version)} · ${esc(repair.verdict.replaceAll('_', ' '))}</p><ol class="lineage">${repair.versions.map(version => `<li>Round ${version.round}: ${version.evaluation.passed}/${version.evaluation.total} passed · ${esc(version.candidate_digest.slice(0, 19))}…</li>`).join('')}</ol>` : '<p>Repair history is unavailable.</p>'}<p class="component-note">Candidate files, detailed observations and sealed evaluator cases are not available in this interface.</p><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>`);
}
function showResearch() {
  showDialog('Historical research record', `<p>This is a previously recorded research result, not an investigation run from this application. Starting genuine model inference is not available here.</p><h3>Meta-generated candidate</h3><p>The research record reports an admitted candidate generated by <strong>muse-spark-1.3</strong> and evaluated using the independent ledger suite.</p><div class="scoreline"><strong>14 passed</strong><span>11 failed</span><span>0 indeterminate</span><span>25 total</span></div><dl class="report-meta"><dt>Candidate SHA-256</dt><dd><code>ee1f3f32e66050bbdf2dde86aaba09e56d17b25c21c35762eeea6208c2a146cd</code></dd><dt>Evaluation suite SHA-256</dt><dd><code>0423935021db574bb68f654c1c37896c6ad4f6e5c40707c1bbe38459178b015b</code></dd></dl><p>No genuine repair was performed. The original private model and evaluator receipts have not yet received an independent artifact-level audit. This result does not establish general equivalence.</p><h3>Separate NON_AI control</h3><p>A local deterministic mock test recorded 22 passed, 3 failed and 0 indeterminate out of 25. It is not a Meta-generated candidate or a live result from this application. These figures are not a fair performance comparison.</p><p><a href="https://github.com/Ankit6149/second-source/issues/25#issuecomment-6547391799" target="_blank" rel="noopener noreferrer">Read the research review and limitations</a></p><div class="dialog-actions"><button class="pill-btn" data-action="close-dialog">Close</button></div>`);
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
  const target = event.target instanceof Element ? event.target.closest<HTMLElement>('[data-action],[data-investigation],[data-suggestion]') : null;
  if (!target) return;
  if (target.dataset.investigation) { void openInvestigation(target.dataset.investigation); return; }
  if (target.dataset.suggestion) { state.draft = target.dataset.suggestion; sessionStorage.setItem('ss-product-draft', state.draft); render(); const input = el<HTMLTextAreaElement>('promptInput'); input?.dispatchEvent(new Event('input', { bubbles: true })); input?.focus(); return; }
  const action = target.dataset.action;
  if (action === 'new') { ++state.epoch; stopPolling(); state.executing = false; state.busy = false; state.view = 'home'; state.selected = null; state.run = null; state.events = []; state.verification = null; state.messages = []; state.pollError = ''; state.executionError = null; state.uncertain = false; state.actionUncertain = null; sessionStorage.removeItem('ss-selected-investigation'); render(); }
  else if (action === 'library') { state.view = 'library'; render(); }
  else if (action === 'account') account();
  else if (action === 'sign-in') { void signIn().catch(setError); }
  else if (action === 'sign-out') { const owner = state.ownerId; void signOut().then(() => { if (owner) clearOwnerNotes(sessionStorage, owner); sessionStorage.removeItem('ss-selected-investigation'); sessionStorage.removeItem('ss-create-pending'); sessionStorage.removeItem('ss-product-draft'); state.draft = ''; state.messages = []; closeDialog(); }).catch(setError); }
  else if (action === 'select-target' || action === 'review-scope') reviewScope();
  else if (action === 'authorize') confirmAuthorization();
  else if (action === 'create' || action === 'confirm-authorization' || action === 'queue' || action === 'cancel' || action === 'reconcile') void mutate(action);
  else if (action === 'execute') void execute();
  else if (action === 'refresh') void refresh();
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
render(); observeSession(session => { void hydrate(session); });
