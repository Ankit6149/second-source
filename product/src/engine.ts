/**
 * Local investigation engine client.
 *
 * The engine is a separate local operator service
 * (scripts/investigation_engine.py, 127.0.0.1:8765) that runs the
 * deterministic NON_AI pipeline by default. An explicitly authorized
 * muse-repair run can make ONE bounded real Meta call and accept a
 * model edit only if a fresh PUBLIC replay improves conformance.
 * This is local-only; it is not the hosted control plane. No held-out
 * tests are sent to the model or evaluated by the local workbench.
 */
const DEFAULT_ENGINE_BASE = 'http://127.0.0.1:8765';
export const ENGINE_BASE = DEFAULT_ENGINE_BASE;

/** Dev-only override: ?engine=http://127.0.0.1:PORT (loopback, validated). */
export function resolveEngineBase(search: string): string {
  const raw = new URLSearchParams(search).get('engine') || '';
  return /^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(raw) ? raw : DEFAULT_ENGINE_BASE;
}

/** Hosted engine URL from build env (public value, never a key). */
export function resolveEngineEnv(value: string): string | null {
  const env = value.replace(/\/$/, '');
  if (/^https:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/.test(env)) return env;
  if (/^http:\/\/127\.0\.0\.1:\d{1,5}$/.test(env)) return env;
  return null;
}

function engineBase(): string {
  let search = '';
  try { search = typeof globalThis.location === 'undefined' ? '' : globalThis.location.search; } catch { search = ''; }
  const param = resolveEngineBase(search);
  if (param !== DEFAULT_ENGINE_BASE) return param;
  try {
    const fromEnv = resolveEngineEnv(import.meta.env?.VITE_ENGINE_URL || '');
    if (fromEnv) return fromEnv;
  } catch { /* fall through to loopback default */ }
  return DEFAULT_ENGINE_BASE;
}
export interface EngineHealth {
  ok: boolean;
  model_calls: boolean;
  muse_repair_targets: string[];
  vision: { regions: string; regions_endpoint_host: string | null; motion_physics: string };
  spend: { used_usd: number; cap_usd: number };
}

export async function getEngineHealth(): Promise<EngineHealth | null> {
  try {
    const resp = await engineFetch('/engine/v1/health');
    if (!resp.ok) return null;
    const body = await resp.json() as EngineHealth;
    if (body.ok !== true) return null;
    return {
      ok: true,
      model_calls: body.model_calls === true,
      muse_repair_targets: Array.isArray(body.muse_repair_targets) ? body.muse_repair_targets.filter(x => typeof x === 'string') : [],
      vision: body.vision && typeof body.vision === 'object' ? body.vision : { regions: 'unconfigured', regions_endpoint_host: null, motion_physics: 'local-non-ai' },
      spend: body.spend && typeof body.spend.used_usd === 'number' && typeof body.spend.cap_usd === 'number' ? body.spend : { used_usd: 0, cap_usd: 15 },
    };
  } catch {
    return null;
  }
}

export interface EngineInvestigation {
  id: string;
  target: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  stage: string;
  provenance: string;
  observations?: { count: number; sha256: string };
  compiled?: { routes: string[]; provenance: string; label: string };
  public_conformance?: { passed: number; total: number; divergences: string[] };
  held_out?: { status: string; reason: string };
  model?: {
    called: boolean; mode?: string; reason?: string; outcome?: string;
    accepted?: boolean; failure_class?: string; target_route?: string[];
    receipt?: { response_id?: string; input_tokens?: number; output_tokens?: number; estimated_cost_usd?: number };
    baseline?: { passed: number; total: number };
    gate_baseline?: { passed: number; total: number };
    gate_attempted?: { passed: number; total: number };
  };
  error?: string;
}

async function engineFetch(path: string, init: RequestInit = {}, timeoutMs = 3000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(engineBase() + path, { ...init, signal: controller.signal, cache: 'no-store' });
  } finally {
    clearTimeout(timer);
  }
}

export async function checkEngine(): Promise<boolean> {
  try {
    const resp = await engineFetch('/engine/v1/health');
    if (!resp.ok) return false;
    const body = await resp.json() as EngineHealth;
    return body.ok === true;
  } catch {
    return false;
  }
}

export async function createEngineInvestigation(target = 'vikunja-v1', modelMode: 'none' | 'muse-repair' = 'none'): Promise<EngineInvestigation> {
  const resp = await engineFetch('/engine/v1/investigations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target, model_mode: modelMode }),
  }, 10000);
  if (!resp.ok) {
    let reason = '';
    try { reason = (await resp.json() as { detail?: string }).detail || ''; }
    catch { /* preserve status on malformed responses */ }
    throw new Error(`Local engine refused the request (${resp.status})${reason ? ': ' + reason : ''}`);
  }
  return await resp.json() as EngineInvestigation;
}

export async function getEngineInvestigation(id: string): Promise<EngineInvestigation> {
  const resp = await engineFetch(`/engine/v1/investigations/${encodeURIComponent(id)}`, {}, 10000);
  if (!resp.ok) {
    let reason = '';
    try { reason = (await resp.json() as { detail?: string }).detail || ''; }
    catch { /* preserve status on malformed responses */ }
    throw new Error(`Local engine refused the request (${resp.status})${reason ? ': ' + reason : ''}`);
  }
  return await resp.json() as EngineInvestigation;
}

export interface AssistResult { reply: string; model: string; receipt: { response_id?: string; input_tokens?: number; output_tokens?: number; estimated_cost_usd?: number } }
export async function requestAssist(text: string, context = ''): Promise<AssistResult> {
  const resp = await engineFetch('/engine/v1/assist', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, context }) }, 90000);
  if (!resp.ok) throw new Error(await engineError(resp));
  return await resp.json() as AssistResult;
}
export interface CaptureResult { host: string; status: number; content_type: string; size_bytes: number; surface: Record<string, unknown>; summary: string | null; model: { model: string; receipt: AssistResult['receipt'] } | null; note: string }
export async function requestCapture(url: string, permission: boolean, summarize: boolean): Promise<CaptureResult> {
  const resp = await engineFetch('/engine/v1/capture', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, permission, summarize }) }, 120000);
  if (!resp.ok) throw new Error(await engineError(resp));
  return await resp.json() as CaptureResult;
}
async function engineError(resp: Response): Promise<string> {
  let reason = '';
  try { reason = (await resp.json() as { detail?: string }).detail || ''; }
  catch { /* keep status only */ }
  return `Local engine refused the request (${resp.status})${reason ? ': ' + reason : ''}`;
}
export function engineCandidateUrl(id: string): string {
  return `${engineBase()}/engine/v1/investigations/${encodeURIComponent(id)}/candidate`;
}

/** Only a completed local run can return the evidence-backed Markdown report. */
export function engineReportUrl(id: string): string {
  return `${engineBase()}/engine/v1/investigations/${encodeURIComponent(id)}/report`;
}
