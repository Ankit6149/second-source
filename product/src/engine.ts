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
export const ENGINE_BASE = 'http://127.0.0.1:8765';

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
    return await fetch(ENGINE_BASE + path, { ...init, signal: controller.signal, cache: 'no-store' });
  } finally {
    clearTimeout(timer);
  }
}

export async function checkEngine(): Promise<boolean> {
  try {
    const resp = await engineFetch('/engine/v1/health');
    if (!resp.ok) return false;
    const body = await resp.json() as { ok?: boolean };
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

export function engineCandidateUrl(id: string): string {
  return `${ENGINE_BASE}/engine/v1/investigations/${encodeURIComponent(id)}/candidate`;
}

/** Only a completed local run can return the evidence-backed Markdown report. */
export function engineReportUrl(id: string): string {
  return `${ENGINE_BASE}/engine/v1/investigations/${encodeURIComponent(id)}/report`;
}
