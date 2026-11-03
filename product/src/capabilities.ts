/**
 * Honest target capability flags for the picker.
 *
 * - API/professional: supported, bounded (owned fixtures via the connected service).
 * - CLI/fixtures: supported (owned ledger fixture via the connected service).
 * - Browser/motion: unavailable — no CDP observation adapter exists
 *   (see docs/P3_BROWSER_SPIKE_ASSESSMENT.md). Never presented as supported.
 */
export type CapabilityStatus = 'supported' | 'unavailable';

export interface TargetCapability {
  id: 'api-professional' | 'cli-fixtures' | 'browser-motion';
  title: string;
  status: CapabilityStatus;
  /** Why the capability is limited or unavailable; always shown to the user. */
  detail: string;
  /** Present only when a real backend target can back the action. */
  action: 'choose-target' | null;
}

export const TARGET_CAPABILITIES: readonly TargetCapability[] = [
  {
    id: 'api-professional',
    title: 'API / professional software',
    status: 'supported',
    detail: 'Supported, bounded: owned HTTP task-workflow fixture on loopback when the connected service advertises its exact scope. Vikunja evidence is a recorded GEMMA_TEST benchmark, not a live run from this app.',
    action: 'choose-target',
  },
  {
    id: 'cli-fixtures',
    title: 'CLI / fixtures',
    status: 'supported',
    detail: 'Supported: owned ledger fixture (NON_AI control) when the connected service advertises its exact scope.',
    action: 'choose-target',
  },
  {
    id: 'browser-motion',
    title: 'Browser / UI / motion',
    status: 'unavailable',
    detail: 'Unavailable — adapter absent. No CDP observation, visual/motion candidate or temporal evaluator exists yet (P3 assessment: NO-GO). Controls for this mode stay disabled with this reason.',
    action: null,
  },
];

/** A capability may enable a control only when supported with a real action. */
export function capabilityEnabled(capability: TargetCapability): boolean {
  return capability.status === 'supported' && capability.action !== null;
}
