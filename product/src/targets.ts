import type { Target } from './api';

// This version is tied to the server-owned create_scope(0) fixture contract.
const fixtureScope = {
  scope_version: '1', target: { kind: 'cli', permission_ref: 'owned-fixture', reference_url: null, reference_command_id: 'owned-ledger-v1' },
  goal: 'Reconstruct only the synthetic ledger CLI behaviors', mode: 'selected_flows',
  observation: { allowed_url_patterns: [], allowed_roles: ['guest'], permitted_actions: ['cli'], allowed_commands: ['add', 'remove', 'total', 'list'], authenticated_access: 'not_required' },
  implementation: { route_patterns: [], required_flows: [], requirements: ['REQ-LEDGER'], allowed_subsystems: ['cli_ledger'], fidelity: ['behavioral'] },
  exclusions: { url_patterns: [], subsystems: [], external_side_effects: [] },
  budgets: { max_reference_experiments: 40, max_model_calls: 5, max_repair_rounds: 3, max_wall_seconds: 600, max_estimated_model_spend_usd: 0 },
};
const fixtureDigest = 'dbf5a0d74502ed6662f551e57ad25ecb902c8c15439186fa5173a54ad9c25c53';

function matchesScope(value: unknown, expected: unknown): boolean {
  if (Array.isArray(expected)) {
    return Array.isArray(value) && value.length === expected.length
      && value.every(item => typeof item === 'string') && expected.every(item => typeof item === 'string')
      && [...value].sort().every((item, index) => item === [...expected].sort()[index]);
  }
  if (expected && typeof expected === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    const actual = value as Record<string, unknown>, wanted = expected as Record<string, unknown>;
    return Object.keys(actual).length === Object.keys(wanted).length
      && Object.keys(wanted).every(key => Object.hasOwn(actual, key) && matchesScope(actual[key], wanted[key]));
  }
  return value === expected;
}

/** Only the currently implemented backend contract can enable a target action. */
export function supportedTarget(value: unknown): Target | null {
  if (!Array.isArray(value)) return null;
  if (value.filter(entry => entry && typeof entry === 'object' && !Array.isArray(entry) && entry.target_id === 'owned-ledger-v1').length !== 1) return null;
  const matches = value.filter((entry): entry is Target => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return false;
    const target = entry as Record<string, unknown>;
    return target.target_id === 'owned-ledger-v1' && target.label === 'Owned ledger fixture'
      && target.run_kind === 'g3_mock' && target.origin === 'mock' && target.real === false
      && typeof target.execution_enabled === 'boolean'
      && target.scope_digest === fixtureDigest && matchesScope(target.scope, fixtureScope);
  });
  return matches.length === 1 ? matches[0] : null;
}
