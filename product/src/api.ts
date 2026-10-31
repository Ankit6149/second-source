/** Browser contract for the reviewed v1 OpenAPI. No privileged credentials. */
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'needs_reconciliation';
export type Scope = Record<string, unknown>;
export interface Target { target_id: 'owned-ledger-v1'; label: string; run_kind: 'g3_mock'; origin: 'mock'; real: false; execution_enabled: boolean; scope: Scope; scope_digest: string }
export interface Investigation { investigation_id: string; title: string; scope: Scope; scope_digest: string; status: 'created' | 'authorized'; revision: number; created_at: string }
export interface Evaluation { passed: number; failed: number; indeterminate: number; total: number }
export interface Run { run_id: string; investigation_id: string; status: RunStatus; stage: string | null; revision: number; created_at: string; cancel_requested: boolean; error_code: string | null; result: { origin: 'mock'; real: false; evaluation: Evaluation | null } | null }
export interface RunEvent { event_id: number; event_type: string; stage: string | null; created_at: string }
export interface Repair { verdict: string; stop_reason: string; selected_version: string; selected_digest: string; versions: { round: number; candidate_digest: string; evaluation: Evaluation }[] }
export interface Verification { origin: 'mock'; real: false; evaluation: Evaluation | null; repair_history_availability: 'available' | 'unavailable'; repair: Repair | null }
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public correlationId = '', public uncertain = false) { super(message); }
}

export function validatedOrigin(value: string, allowLocal = false): string {
  if (!value) return '';
  try {
    const u = new URL(value);
    const local = allowLocal && (u.hostname === '127.0.0.1' || u.hostname === 'localhost') && u.protocol === 'http:';
    if ((!local && u.protocol !== 'https:') || u.username || u.password || u.pathname !== '/' || u.search || u.hash) return '';
    return u.origin;
  } catch { return ''; }
}
const identifier = (value: string) => {
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(value)) throw new Error('Invalid resource identity');
  return encodeURIComponent(value);
};

export class Api {
  constructor(private origin: string, private token: () => string | null, private transport: typeof fetch = fetch) {}
  private async read(response: Response, maximum: number): Promise<Uint8Array> {
    const size = response.headers.get('content-length');
    if (size && (!/^\d+$/.test(size) || Number(size) > maximum)) throw new Error('Response too large');
    if (!response.body) return new Uint8Array();
    const reader = response.body.getReader(); const chunks: Uint8Array[] = []; let total = 0;
    try {
      while (true) {
        const part = await reader.read(); if (part.done) break;
        total += part.value.byteLength; if (total > maximum) { await reader.cancel(); throw new Error('Response too large'); }
        chunks.push(part.value);
      }
    } finally { reader.releaseLock(); }
    const bytes = new Uint8Array(total); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
    return bytes;
  }
  private async request(path: string, init: RequestInit = {}, mutation = false, maximum = 2_000_000): Promise<Uint8Array> {
    const token = this.token();
    if (!this.origin || !token) throw new ApiError(401, 'SESSION_REQUIRED', 'Sign in to continue.');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), mutation && path.endsWith('/execute') ? 240_000 : 20_000);
    try {
      const response = await this.transport(this.origin + path, {
        ...init, headers: { Authorization: `Bearer ${token}`, ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
        signal: controller.signal, cache: 'no-store', credentials: 'omit', redirect: 'error'
      });
      if (!response.ok) {
        let body: { code?: string; message?: string; correlation_id?: string } = {};
        try { body = JSON.parse(new TextDecoder().decode(await this.read(response, 4096))); } catch { /* preserve a safe fallback */ }
        const message = response.status === 401 ? 'Your session has expired. Sign in again.' : response.status === 409 ? 'The investigation changed or this action is unavailable. Refresh its status.' : response.status === 429 ? 'Too many requests. Wait before trying again.' : response.status === 503 ? 'The service is temporarily unavailable. Check its status before retrying.' : 'The request could not be completed.';
        const correlation = typeof body.correlation_id === 'string' && /^[a-f0-9]{32}$/.test(body.correlation_id) ? body.correlation_id : '';
        throw new ApiError(response.status, body.code || 'REQUEST_FAILED', message, correlation, mutation && response.status >= 500);
      }
      return await this.read(response, maximum);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(0, 'NETWORK_UNCERTAIN', mutation ? 'The outcome is unknown. Check the current status before taking another action.' : 'Unable to reach the service. Check your connection.', '', mutation);
    } finally { clearTimeout(timer); }
  }
  private async json<T>(path: string, init?: RequestInit, mutation = false): Promise<T> {
    const bytes = await this.request(path, init, mutation);
    try { return JSON.parse(new TextDecoder().decode(bytes)) as T; }
    catch { throw new ApiError(0, 'INVALID_RESPONSE', 'The service returned an invalid response.', '', mutation); }
  }
  session() { return this.json<{ owner_id: string; authenticated: true }>('/v1/session'); }
  capabilities() { return this.json<{ enabled_run_kinds: string[]; real_inference_enabled: false; execution_mode?: string }>('/v1/capabilities'); }
  targets() { return this.json<Target[]>('/v1/targets'); }
  investigations(after?: string) { return this.json<{ items: Investigation[]; next_after: string | null }>(`/v1/investigations?limit=100${after ? `&after=${identifier(after)}` : ''}`); }
  investigation(id: string) { return this.json<Investigation>(`/v1/investigations/${identifier(id)}`); }
  create(title: string, scope: Scope, key: string) { return this.json<Investigation>('/v1/investigations', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ title, scope }) }, true); }
  authorize(item: Investigation) { return this.json<Investigation>(`/v1/investigations/${identifier(item.investigation_id)}/authorize`, { method: 'POST', body: JSON.stringify({ expected_revision: item.revision, scope_digest: item.scope_digest, mode: 'mock', maximum_model_spend_usd: 0 }) }, true); }
  runs(id: string, after?: string) { return this.json<{ items: Run[]; next_after: string | null }>(`/v1/investigations/${identifier(id)}/runs?limit=100${after ? `&after=${identifier(after)}` : ''}`); }
  queue(id: string, key: string) { return this.json<Run>(`/v1/investigations/${identifier(id)}/runs`, { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ kind: 'g3_mock' }) }, true); }
  run(id: string) { return this.json<Run>(`/v1/runs/${identifier(id)}`); }
  execute(run: Run) { return this.json<Run>(`/v1/runs/${identifier(run.run_id)}/execute`, { method: 'POST', body: JSON.stringify({ expected_revision: run.revision }) }, true); }
  cancel(run: Run) { return this.json<Run>(`/v1/runs/${identifier(run.run_id)}/cancel`, { method: 'POST', body: JSON.stringify({ expected_revision: run.revision }) }, true); }
  reconcile(run: Run) { return this.json<Run>(`/v1/runs/${identifier(run.run_id)}/reconcile`, { method: 'POST', body: JSON.stringify({ expected_revision: run.revision }) }, true); }
  events(id: string, after = 0) {
    if (!Number.isSafeInteger(after) || after < 0) throw new Error('Invalid event cursor');
    return this.json<{ items: RunEvent[]; next_after: number }>(`/v1/runs/${identifier(id)}/events?after=${after}&limit=500`);
  }
  verification(id: string) { return this.json<Verification>(`/v1/runs/${identifier(id)}/verification`); }
  report(id: string) { return this.json<Record<string, unknown>>(`/v1/runs/${identifier(id)}/report`); }
  async export(id: string) { const bytes = await this.request(`/v1/runs/${identifier(id)}/export.zip`, {}, false, 8_000_000); return new Blob([bytes.buffer as ArrayBuffer], { type: 'application/zip' }); }
}
