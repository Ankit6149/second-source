/** Polling is read-only; a failed poll never repeats execution. */
export function pollFailureMessage(safeDetail?: string): string {
  const detail = safeDetail || 'The service could not be reached.';
  return `Could not refresh progress. The displayed status may be out of date. ${detail}`;
}

export function pollRetryDelay(status?: number): number {
  return status === 429 ? 60_000 : 15_000;
}

export function outcomeConfirmed(status: string): boolean {
  return ['completed', 'failed', 'cancelled'].includes(status);
}

/** An older response must never replace a later state for the same durable run. */
export function acceptsRunRevision(current: { run_id: string; revision: number }, incoming: { run_id: string; revision: number }): boolean {
  return current.run_id === incoming.run_id && Number.isSafeInteger(incoming.revision) && incoming.revision >= current.revision;
}

/** Only these backend responses are known to reject execution before dispatch. */
export function executionDefinitelyRefused(status: number, code: string): boolean {
  return status === 429 && code === 'RATE_LIMITED'
    || status === 409 && (code === 'REVISION_CONFLICT' || code === 'EXECUTION_DISABLED')
    || status === 401 && code === 'UNAUTHENTICATED';
}
