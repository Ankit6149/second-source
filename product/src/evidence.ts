/**
 * Genuine-evidence records for the workbench.
 *
 * Labels are exact and never interchangeable:
 * - GEMMA_TEST: Gemma development arms (gemma-test provider). Not Meta, not REAL_MODEL.
 * - NON_AI: deterministic / hand-written controls. Never a model result.
 * - REAL_MODEL: genuine Meta muse-spark-1.3 only (Vikunja arms in metaArms; historical 14/25 ledger separate target/suite).
 *
 * The Vikunja summary is a committed, sanitized build-time import. The app
 * never fetches `.runs/` at runtime; if the summary is missing or malformed,
 * callers must show an honest unavailable state instead of fabricated data.
 */
import summaryJson from './evidence-summary.json' with { type: 'json' };

export type EvidenceLabel = 'GEMMA_TEST' | 'NON_AI' | 'REAL_MODEL';

/**
 * How a record came to exist. Never interchangeable:
 * - model-authored: a model wrote the candidate (Gemma arms, REAL_MODEL ledger).
 * - evidence-compiled: deterministically compiled from recorded observations
 *   (EVIDENCE_COMPILED, a NON_AI entry). No model inference is involved.
 * - runtime-supplied: the trusted runtime/interpreter supplies the behavior
 *   (oracle plumbing control). Never a model result.
 */
export type EvidenceProvenance = 'model-authored' | 'evidence-compiled' | 'runtime-supplied';

export const PROVENANCE_META: Record<EvidenceProvenance, { label: string; description: string }> = {
  'model-authored': { label: 'Model-authored', description: 'Candidate authored by a model; scored blind by the pinned evaluator.' },
  'evidence-compiled': { label: 'Evidence-compiled', description: 'Deterministically compiled from recorded observations (NON_AI). No model inference.' },
  'runtime-supplied': { label: 'Runtime-supplied', description: 'Behavior supplied by the trusted interpreter/runtime, not by a model.' },
};

export interface MetaArm { arm: string; label: 'REAL_MODEL'; provenance: 'model-authored'; model: 'muse-spark-1.3'; condition: string; status: 'scored'; passed: number; total: number; passedCases: number[]; selectedProbes?: string[]; probeObservations?: number; }
export interface MetaArmsResult { label: 'REAL_MODEL'; provenance: 'model-authored'; model: 'muse-spark-1.3'; callsTotal: number; packetDigestsMatched: true; reservationCapUsd: number; artifact: string; arms: MetaArm[]; }
export interface GemmaRepairResult { arm: string; label: 'GEMMA_TEST'; provenance: 'model-authored'; model: string; condition: string; status: 'scored'; passed: number; total: number; outcome: 'admitted_but_regressed'; note: string; }
export interface GateAudit { label: 'NON_AI'; provenance: 'runtime-supplied'; kind: 'PUBLIC_VERIFICATION_GATE_AUDIT'; isModelScore: false; description: string; editsConsidered: number; kept: number; regressed: number; tied: number; gatedCandidate: { label: 'EVIDENCE_COMPILED'; parentLabel: 'NON_AI'; provenance: 'evidence-compiled'; passed: number; total: number }; }
export interface GemmaArm {
  arm: string;
  label: 'GEMMA_TEST';
  provenance: 'model-authored';
  condition: string;
  status: 'scored' | 'provider_failure';
  passed: number | null;
  total: number;
  failureClass: string | null;
  passedCases?: number[];
  selectionVerified?: boolean;
  probeCount?: number;
  probeObservations?: number;
}

export interface CompiledEvidence {
  label: 'EVIDENCE_COMPILED';
  parentLabel: 'NON_AI';
  provenance: 'evidence-compiled';
  status: 'pending' | 'available';
  /** Required when pending; explains why no score is shown. */
  reason: string | null;
  passed: number | null;
  total: number | null;
  artifact: string | null;
  artifactSha256: string | null;
}

/** Honest pending state used until the coordinator adds a compiled artifact. */
export const PENDING_COMPILED: CompiledEvidence = {
  label: 'EVIDENCE_COMPILED', parentLabel: 'NON_AI', provenance: 'evidence-compiled',
  status: 'pending',
  reason: 'No evidence-compiled artifact has been added by the coordinator yet. No compiled score is shown rather than a fabricated one.',
  passed: null, total: null, artifact: null, artifactSha256: null,
};

export interface VikunjaRecord {
  benchmark: string;
  provider: string;
  classification: string;
  model: string;
  modelAuthorship: string;
  interpreterSupplies: string;
  interpreterSha256: string;
  evaluatorSha256: string;
  heldOutSha256: string;
  arms: GemmaArm[];
  metaArms: MetaArmsResult | null;
  gemmaRepair: GemmaRepairResult | null;
  gateAudit: GateAudit | null;
  oracle: { label: 'NON_AI'; provenance: 'runtime-supplied'; description: string; passed: number; total: number };
  compiled: CompiledEvidence;
  limitations: string[];
  sourceArtifacts: string[];
}

export interface HistoricalLedgerRecord {
  label: 'REAL_MODEL';
  provenance: 'model-authored';
  model: string;
  passed: number;
  failed: number;
  indeterminate: number;
  total: number;
  candidateSha256: string;
  suiteSha256: string;
  note: string;
}

/** Historical genuine Meta ledger result. Kept separate from Vikunja. */
export const HISTORICAL_LEDGER: HistoricalLedgerRecord = {
  label: 'REAL_MODEL',
  provenance: 'model-authored',
  model: 'muse-spark-1.3',
  passed: 14,
  failed: 11,
  indeterminate: 0,
  total: 25,
  candidateSha256: 'ee1f3f32e66050bbdf2dde86aaba09e56d17b25c21c35762eeea6208c2a146cd',
  suiteSha256: '0423935021db574bb68f654c1c37896c6ad4f6e5c40707c1bbe38459178b015b',
  note: 'Historical ledger result on a frozen 25-case sealed suite (9 schema, 2 error mismatches). Not comparable to the Vikunja 6-case benchmark. A provider signature and the ephemeral broker signature could not be verified. The original local receipts passed consistency checks, and an offline replay reproduced the score on the recorded suite and source revision.',
};

const SHA = /^sha256:[a-f0-9]{64}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

/**
 * Validate the optional compiled-evidence block. Absent means the coordinator
 * has not added an artifact yet, so the honest pending state is synthesized.
 * A present block is validated strictly: pending must carry a reason and no
 * score; available must carry a bounded score, artifact path and digest.
 * Returns null only when a present block is malformed.
 */
export function parseCompiled(value: unknown): CompiledEvidence | null {
  if (value === undefined || value === null) return { ...PENDING_COMPILED };
  if (!isRecord(value)) return null;
  if (value.label !== 'EVIDENCE_COMPILED' || value.parentLabel !== 'NON_AI') return null;
  if (value.provenance !== 'evidence-compiled') return null;
  if (value.status === 'pending') {
    if (typeof value.reason !== 'string' || !value.reason) return null;
    if (value.passed !== null || value.total !== null) return null;
    return {
      label: 'EVIDENCE_COMPILED', parentLabel: 'NON_AI', provenance: 'evidence-compiled',
      status: 'pending', reason: value.reason, passed: null, total: null,
      artifact: null, artifactSha256: null,
    };
  }
  if (value.status === 'available') {
    if (!Number.isSafeInteger(value.passed) || !Number.isSafeInteger(value.total)) return null;
    if ((value.passed as number) < 0 || (value.total as number) <= 0 || (value.passed as number) > (value.total as number)) return null;
    if (typeof value.artifact !== 'string' || !value.artifact) return null;
    if (typeof value.artifactSha256 !== 'string' || !SHA.test(value.artifactSha256)) return null;
    return {
      label: 'EVIDENCE_COMPILED', parentLabel: 'NON_AI', provenance: 'evidence-compiled',
      status: 'available', reason: null,
      passed: value.passed as number, total: value.total as number,
      artifact: value.artifact, artifactSha256: value.artifactSha256,
    };
  }
  return null;
}

/**
 * Validate an untrusted summary value. Returns null on any defect so the UI
 * can show an unavailable state rather than partial fabricated evidence.
 */
function validCases(v: unknown, passed: number, total: number): v is number[] { return Array.isArray(v) && v.length === passed && v.every(x => Number.isSafeInteger(x) && (x as number) >= 0 && (x as number) < total) && new Set(v).size === v.length; }
type Opt<T> = { ok: true; value: T | null } | { ok: false };
export function parseMetaArms(v: unknown): Opt<MetaArmsResult> { if (v === undefined || v === null) return { ok: true, value: null }; if (!isRecord(v) || v.label !== 'REAL_MODEL' || v.provenance !== 'model-authored' || v.model !== 'muse-spark-1.3') return { ok: false }; if (!Number.isSafeInteger(v.callsTotal) || (v.callsTotal as number) < 1 || v.packetDigestsMatched !== true || typeof v.reservationCapUsd !== 'number' || !Number.isFinite(v.reservationCapUsd) || (v.reservationCapUsd as number) <= 0 || typeof v.artifact !== 'string' || !v.artifact || !Array.isArray(v.arms) || v.arms.length < 1 || v.arms.length > 4) return { ok: false }; const arms: MetaArm[] = []; for (const r of v.arms) { if (!isRecord(r) || r.label !== 'REAL_MODEL' || r.provenance !== 'model-authored' || r.model !== 'muse-spark-1.3' || r.status !== 'scored' || typeof r.arm !== 'string' || typeof r.condition !== 'string' || !Number.isSafeInteger(r.passed) || !Number.isSafeInteger(r.total) || (r.total as number) <= 0 || (r.passed as number) < 0 || (r.passed as number) > (r.total as number) || !validCases(r.passedCases, r.passed as number, r.total as number)) return { ok: false }; if (r.selectedProbes !== undefined && (!Array.isArray(r.selectedProbes) || !r.selectedProbes.every(x => typeof x === 'string' && x))) return { ok: false }; if (r.probeObservations !== undefined && (!Number.isSafeInteger(r.probeObservations) || (r.probeObservations as number) < 0)) return { ok: false }; arms.push({ arm: r.arm, label: 'REAL_MODEL', provenance: 'model-authored', model: 'muse-spark-1.3', condition: r.condition, status: 'scored', passed: r.passed as number, total: r.total as number, passedCases: [...(r.passedCases as number[])], ...(r.selectedProbes !== undefined ? { selectedProbes: [...(r.selectedProbes as string[])] } : {}), ...(r.probeObservations !== undefined ? { probeObservations: r.probeObservations as number } : {}) }); } return { ok: true, value: { label: 'REAL_MODEL', provenance: 'model-authored', model: 'muse-spark-1.3', callsTotal: v.callsTotal as number, packetDigestsMatched: true, reservationCapUsd: v.reservationCapUsd as number, artifact: v.artifact, arms } }; }
export function parseGemmaRepair(v: unknown): Opt<GemmaRepairResult> { if (v === undefined || v === null) return { ok: true, value: null }; if (!isRecord(v) || v.label !== 'GEMMA_TEST' || v.provenance !== 'model-authored' || v.status !== 'scored' || v.outcome !== 'admitted_but_regressed' || typeof v.arm !== 'string' || typeof v.condition !== 'string' || typeof v.model !== 'string' || !v.model || typeof v.note !== 'string' || !v.note || !Number.isSafeInteger(v.passed) || !Number.isSafeInteger(v.total) || (v.total as number) <= 0 || (v.passed as number) < 0 || (v.passed as number) > (v.total as number)) return { ok: false }; return { ok: true, value: { arm: v.arm, label: 'GEMMA_TEST', provenance: 'model-authored', model: v.model, condition: v.condition, status: 'scored', passed: v.passed as number, total: v.total as number, outcome: 'admitted_but_regressed', note: v.note } }; }
export function parseGateAudit(v: unknown): Opt<GateAudit> { if (v === undefined || v === null) return { ok: true, value: null }; if (!isRecord(v) || v.label !== 'NON_AI' || v.provenance !== 'runtime-supplied' || v.kind !== 'PUBLIC_VERIFICATION_GATE_AUDIT' || v.isModelScore !== false || typeof v.description !== 'string' || !v.description) return { ok: false }; for (const k of ['editsConsidered', 'kept', 'regressed', 'tied'] as const) { if (!Number.isSafeInteger(v[k]) || (v[k] as number) < 0) return { ok: false }; } if ((v.kept as number) + (v.regressed as number) + (v.tied as number) !== v.editsConsidered) return { ok: false }; if (!isRecord(v.gatedCandidate) || v.gatedCandidate.label !== 'EVIDENCE_COMPILED' || v.gatedCandidate.parentLabel !== 'NON_AI' || v.gatedCandidate.provenance !== 'evidence-compiled' || !Number.isSafeInteger(v.gatedCandidate.passed) || !Number.isSafeInteger(v.gatedCandidate.total) || (v.gatedCandidate.total as number) <= 0 || (v.gatedCandidate.passed as number) < 0 || (v.gatedCandidate.passed as number) > (v.gatedCandidate.total as number)) return { ok: false }; return { ok: true, value: { label: 'NON_AI', provenance: 'runtime-supplied', kind: 'PUBLIC_VERIFICATION_GATE_AUDIT', isModelScore: false, description: v.description, editsConsidered: v.editsConsidered as number, kept: v.kept as number, regressed: v.regressed as number, tied: v.tied as number, gatedCandidate: { label: 'EVIDENCE_COMPILED', parentLabel: 'NON_AI', provenance: 'evidence-compiled', passed: v.gatedCandidate.passed as number, total: v.gatedCandidate.total as number } } }; }
export function parseVikunjaSummary(value: unknown): VikunjaRecord | null {
  if (!isRecord(value)) return null;
  if (value.kind !== 'VIKUNJA_GEMMA_SANITIZED_SUMMARY_V1') return null;
  if (value.provider !== 'gemma-test' || value.classification !== 'PIPELINE_SMOKE_NOT_META') return null;
  if (typeof value.model !== 'string' || !value.model) return null;
  if (typeof value.benchmark !== 'string' || !value.benchmark) return null;
  for (const key of ['interpreterSha256', 'evaluatorSha256', 'heldOutSha256'] as const) {
    if (typeof value[key] !== 'string' || !SHA.test(value[key] as string)) return null;
  }
  if (!Array.isArray(value.arms) || value.arms.length < 4 || value.arms.length > 8) return null;
  const arms: GemmaArm[] = [];
  for (const raw of value.arms) {
    if (!isRecord(raw)) return null;
    // Gemma arms must never be relabeled as NON_AI or REAL_MODEL.
    if (raw.label !== 'GEMMA_TEST') return null;
    if (typeof raw.arm !== 'string' || typeof raw.condition !== 'string') return null;
    if (!Number.isSafeInteger(raw.total) || (raw.total as number) <= 0) return null;
    if (raw.status === 'scored') {
      if (!Number.isSafeInteger(raw.passed) || (raw.passed as number) < 0 || (raw.passed as number) > (raw.total as number)) return null;
    } else if (raw.status === 'provider_failure') {
      // Provider failures are unscored: a numeric score here would fabricate a result.
      if (raw.passed !== null) return null;
    } else return null;
    // Provenance is part of the claim: a model arm relabeled as compiled or
    // runtime-supplied would misstate authorship, so reject it outright.
    if (raw.provenance !== undefined && raw.provenance !== 'model-authored') return null;
    if (raw.passedCases !== undefined && !(raw.status === 'scored' && validCases(raw.passedCases, raw.passed as number, raw.total as number))) return null;
    if (raw.selectionVerified !== undefined && typeof raw.selectionVerified !== 'boolean') return null;
    if (raw.probeCount !== undefined && (!Number.isSafeInteger(raw.probeCount) || (raw.probeCount as number) < 0)) return null;
    if (raw.probeObservations !== undefined && (!Number.isSafeInteger(raw.probeObservations) || (raw.probeObservations as number) < 0)) return null;
    arms.push({
      arm: raw.arm, label: 'GEMMA_TEST', provenance: 'model-authored', condition: raw.condition,
      status: raw.status, passed: raw.passed as number | null,
      total: raw.total as number,
      failureClass: typeof raw.failureClass === 'string' ? raw.failureClass : null,
      ...(raw.passedCases !== undefined ? { passedCases: [...(raw.passedCases as number[])] } : {}),
      ...(raw.selectionVerified !== undefined ? { selectionVerified: raw.selectionVerified as boolean } : {}),
      ...(raw.probeCount !== undefined ? { probeCount: raw.probeCount as number } : {}),
      ...(raw.probeObservations !== undefined ? { probeObservations: raw.probeObservations as number } : {}),
    });
  }
  if (!isRecord(value.oracle) || value.oracle.label !== 'NON_AI') return null;
  if (value.oracle.provenance !== undefined && value.oracle.provenance !== 'runtime-supplied') return null;
  const metaArms = parseMetaArms(value.metaArms); if (!metaArms.ok) return null;
  const gemmaRepair = parseGemmaRepair(value.gemmaRepair); if (!gemmaRepair.ok) return null;
  const gateAudit = parseGateAudit(value.gateAudit); if (!gateAudit.ok) return null;
  const compiled = parseCompiled(value.compiled);
  if (compiled === null) return null;
  if (!Number.isSafeInteger(value.oracle.passed) || !Number.isSafeInteger(value.oracle.total)) return null;
  if ((value.oracle.passed as number) < 0 || (value.oracle.passed as number) > (value.oracle.total as number)) return null;
  if (!Array.isArray(value.limitations) || !value.limitations.every(item => typeof item === 'string')) return null;
  if (!Array.isArray(value.sourceArtifacts) || !value.sourceArtifacts.every(item => typeof item === 'string')) return null;
  return {
    benchmark: value.benchmark,
    provider: value.provider,
    classification: value.classification,
    model: value.model,
    modelAuthorship: typeof value.modelAuthorship === 'string' ? value.modelAuthorship : '',
    interpreterSupplies: typeof value.interpreterSupplies === 'string' ? value.interpreterSupplies : '',
    interpreterSha256: value.interpreterSha256 as string,
    evaluatorSha256: value.evaluatorSha256 as string,
    heldOutSha256: value.heldOutSha256 as string,
    arms,
    metaArms: metaArms.value,
    gemmaRepair: gemmaRepair.value,
    gateAudit: gateAudit.value,
    oracle: {
      label: 'NON_AI',
      provenance: 'runtime-supplied',
      description: typeof value.oracle.description === 'string' ? value.oracle.description : '',
      passed: value.oracle.passed as number,
      total: value.oracle.total as number,
    },
    compiled,
    limitations: value.limitations as string[],
    sourceArtifacts: value.sourceArtifacts as string[],
  };
}

/** Build-time sanitized record, or null when unavailable/malformed. */
export function vikunjaRecord(): VikunjaRecord | null {
  try {
    return parseVikunjaSummary(summaryJson);
  } catch {
    return null;
  }
}

/** One-line honest score text for an arm; provider failures are never 0/total. */
export function metaArmScoreText(arm: MetaArm): string { return `${arm.passed}/${arm.total}`; }
export function gateAuditText(audit: GateAudit): string { return `${audit.kept}/${audit.editsConsidered} kept, ${audit.regressed} regressed, ${audit.tied} tied (NON_AI audit, not a model score)`; }
export function armScoreText(arm: GemmaArm): string {
  return arm.status === 'scored' ? `${arm.passed}/${arm.total}` : 'Not scored — provider failure';
}

/** One-line honest score text for compiled evidence; pending is never a score. */
export function compiledScoreText(compiled: CompiledEvidence): string {
  return compiled.status === 'available' ? `${compiled.passed}/${compiled.total}` : 'Pending — no compiled artifact yet';
}

/** CSS hook + accessible name for a provenance kind, for distinct rendering. */
export function provenanceClass(provenance: EvidenceProvenance): string {
  return `prov-${provenance}`;
}
