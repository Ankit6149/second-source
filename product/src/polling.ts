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
