/**
 * Local investigation engine client.
 *
 * The engine is a separate local operator service
 * (scripts/investigation_engine.py, 127.0.0.1:8765) that runs the
 * deterministic NON_AI pipeline against a disposable local Vikunja
 * reference: probe -> compile -> public conformance. It is NOT the
 * hosted control plane and it never calls a model. When it is not
 * running, the workbench says so plainly instead of faking status.
 */
export const ENGINE_BASE = 'http://127.0.0.1:8765';

export interface EngineInvestigation {
  id: string;
  target: string;
  status: 'running' | 'completed' | 'failed';
  stage: string;
  provenance: string;
  observations?: { count: number; sha256: string };
  compiled?: { routes: string[]; provenance: string; label: string };
  public_conformance?: { passed: number; total: number; divergences: string[] };
  held_out?: { status: string; reason: string };
  model?: { called: boolean; reason: string };
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

export async function createEngineInvestigation(): Promise<EngineInvestigation> {
  const resp = await engineFetch('/engine/v1/investigations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target: 'vikunja-v1' }),
  }, 10000);
  if (!resp.ok) throw new Error(`engine returned ${resp.status}`);
  return await resp.json() as EngineInvestigation;
}

export async function getEngineInvestigation(id: string): Promise<EngineInvestigation> {
  const resp = await engineFetch(`/engine/v1/investigations/${encodeURIComponent(id)}`, {}, 10000);
  if (!resp.ok) throw new Error(`engine returned ${resp.status}`);
  return await resp.json() as EngineInvestigation;
}

export function engineCandidateUrl(id: string): string {
  return `${ENGINE_BASE}/engine/v1/investigations/${encodeURIComponent(id)}/candidate`;
}
