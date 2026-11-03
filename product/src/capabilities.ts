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

/** Repo-relative path whose existence gates the browser / motion entry. */
export const BROWSER_SLICE_OBSERVATIONS_PATH = 'browser-slice/observations.json';

/** Exact reason shown while no browser observations have been recorded. */
export const BROWSER_SLICE_ABSENT_REASON =
  `Unavailable — adapter absent. ${BROWSER_SLICE_OBSERVATIONS_PATH} not found: no browser observations have been recorded, so browser / motion reconstruction cannot be offered. No CDP observation, visual/motion candidate or temporal evaluator exists yet (P3 assessment: NO-GO).`;

/**
 * Resolve the browser / motion entry from whether recorded observations
 * exist. Absent observations always mean unavailable with the exact reason;
 * present observations are reported honestly but execution stays unavailable
 * until a CDP candidate/evaluator adapter exists. Nothing is faked either way.
 */
export function resolveBrowserMotionCapability(observationsPresent: boolean): TargetCapability {
  if (!observationsPresent) {
    return { id: 'browser-motion', title: 'Browser / UI / motion', status: 'unavailable', detail: BROWSER_SLICE_ABSENT_REASON, action: null };
  }
  return {
    id: 'browser-motion', title: 'Browser / UI / motion', status: 'unavailable',
    detail: `A bounded browser slice is recorded at ${BROWSER_SLICE_OBSERVATIONS_PATH} (spring-drag trajectory fit; held-out verdict in browser-slice/verdict.json), but it is not wired as a live in-app adapter — browser / motion execution remains unavailable here. Recorded observations can be reviewed as evidence only.`,
    action: null,
  };
}

/**
 * Presence of the committed browser-slice evidence. A static browser
 * bundle cannot inspect the repository filesystem at runtime (and must
 * not use import.meta, which the DOM test harness cannot eval), so this
 * is a plain constant tied to the committed artifact: observations.json
 * and verdict.json are in the repo under browser-slice/. If that slice
 * is removed, set this back to false.
 */
export const BROWSER_SLICE_OBSERVATIONS_PRESENT = true;

/** Capabilities with the browser entry resolved from recorded observations. */
export function targetCapabilities(observationsPresent: boolean = BROWSER_SLICE_OBSERVATIONS_PRESENT): TargetCapability[] {
  return TARGET_CAPABILITIES.map(cap => (cap.id === 'browser-motion' ? resolveBrowserMotionCapability(observationsPresent) : cap));
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
    detail: BROWSER_SLICE_ABSENT_REASON,
    action: null,
  },
];

/** A capability may enable a control only when supported with a real action. */
export function capabilityEnabled(capability: TargetCapability): boolean {
  return capability.status === 'supported' && capability.action !== null;
}
