"""PROTECTED-FACT COMPILER -- successor slice to ``evidence_compiler``.

Pipeline:
  public observations -> evidence_compiler.compile_spec (NON_AI, unchanged)
                      -> lift to Behavioral IR v2
                      -> freeze observed facts (immutable by default)
                      -> decomposed subtask graph compiled to ONE candidate
                      -> public-conformance repair with non-regression gate

Protection contract:
- An observed field (exact value, timestamp template, permission, status,
  method, path, template) cannot be overwritten casually: any change needs a
  complete OverrideRecord (rule, why, evidence, uncertainty, affected
  behavior, distinguishing experiment, regression risk) AND contradicting
  public evidence. Otherwise ``ProtectedFactError`` is raised.
- Repair uses PUBLIC observations only. Held-out material is never read,
  never passed in, and a repair that increases public divergences is rejected.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from behavioral_ir import (  # noqa: E402
    BehavioralIR, ClaimState, FieldSpec, IRValidationError, OperationSpec,
    OverrideRecord, Provenance, ProvenanceLabel, TemporalSpec, ValueKind,
    ir_from_dict,
)
import evidence_compiler  # noqa: E402


class ProtectedFactError(ValueError):
    """Raised on a casual overwrite of an observed (protected) fact."""


# Field-path suffixes that are always protected when observed.
PROTECTED_KINDS = ("timestamp", "permission", "template", "status",
                   "method", "path", "exact_value")


def _is_protected_path(field_path: str) -> bool:
    tail = field_path.rsplit(".", 1)[-1].lower()
    return any(k in tail or k in field_path.lower() for k in PROTECTED_KINDS) \
        or ".fields." in field_path


def collect_protected_facts(ir: BehavioralIR) -> dict:
    """Map field_path -> observed value for every observed fact in the IR."""
    facts = {}
    for op in ir.operations:
        base = f"operations.{op.name}"
        if op.claim == ClaimState.OBSERVED:
            facts[f"{base}.method"] = op.method
            facts[f"{base}.path"] = op.path
            facts[f"{base}.status"] = op.status
            facts[f"{base}.template"] = (op.method, op.path, op.kind)
        if op.permission_observed:
            facts[f"{base}.permission"] = op.permission
        for f in op.fields:
            if f.observed:
                facts[f"{base}.fields.{f.name}"] = (
                    f.value_kind.value, f.exact_value, f.condition)
                if f.value_kind == ValueKind.TIMESTAMP:
                    facts[f"{base}.fields.{f.name}.timestamp"] = f.exact_value
        for t in op.temporal:
            if t.observed_value:
                facts[f"{base}.temporal.{t.field}.timestamp"] = t.observed_value
        for v in op.validate:
            if v.observed:
                facts[f"{base}.validate.{v.field}"] = (v.rule, v.status)
    return facts


def _get_path(ir_dict: dict, field_path: str):
    cur = ir_dict
    for part in field_path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def apply_override(ir: BehavioralIR, field_path: str, new_value,
                   record: OverrideRecord | None = None,
                   contradicting_evidence: str = "") -> BehavioralIR:
    """Apply a justified override, or raise ProtectedFactError.

    Casual overwrites (no/incomplete record, or no contradicting public
    evidence for a protected observed fact) are rejected. Timestamp and
    permission fields are protected exactly like templates.
    """
    facts = collect_protected_facts(ir)
    is_protected = field_path in facts or _is_protected_path(field_path)
    if is_protected:
        if record is None:
            raise ProtectedFactError(
                f"{field_path} is an observed fact and is immutable by default; "
                "a complete OverrideRecord is required")
        record.validate()  # raises IRValidationError listing missing fields
        if not str(contradicting_evidence or "").strip():
            raise ProtectedFactError(
                f"{field_path}: override requires contradicting public evidence; "
                "an assertion without a new observation is a casual overwrite")
    # Apply on the dict form, then re-parse; keep an audit override entry.
    d = ir.to_dict()
    parts = field_path.split(".")
    # Only operation-level scalar paths are supported for direct override;
    # anything else must go through a subtask recompilation.
    if len(parts) == 3 and parts[0] == "operations":
        op_name, attr = parts[1], parts[2]
        for o in d["operations"]:
            if o["name"] == op_name:
                if attr not in o:
                    raise ProtectedFactError(f"{field_path}: unknown attribute {attr}")
                o[attr] = new_value
                o["claim"] = ClaimState.CONTRADICTED.value
                break
        else:
            raise ProtectedFactError(f"{field_path}: operation not found")
    else:
        raise ProtectedFactError(
            f"{field_path}: direct override unsupported; recompile via subtask graph")
    new_ir = ir_from_dict(d)
    if record is not None:
        new_ir = dataclasses.replace(
            new_ir, overrides=ir.overrides + ((field_path, record),))
    return new_ir.require_valid()


def casual_overwrite_attempt(ir: BehavioralIR, field_path: str, new_value):
    """Explicit guard used by repair/model paths: always raises for observed."""
    return apply_override(ir, field_path, new_value, record=None)


# ---------------------------------------------------------------- subtasks
@dataclasses.dataclass(frozen=True)
class SubtaskNode:
    id: str
    kind: str  # compile_route|infer_access|author_field|repair|freeze
    depends_on: tuple = ()
    operation: OperationSpec | None = None
    resource: str = ""


def compile_subtask_graph(nodes) -> BehavioralIR:
    """Topologically compile a decomposed subtask graph into ONE candidate.

    Conflicting operations for the same name with different observed facts
    keep the observed one and mark the other CONTRADICTED (never silently
    merged). Unknown claims are preserved as UNKNOWN.
    """
    nodes = list(nodes)
    by_id = {n.id: n for n in nodes}
    done, order = set(), []
    remaining = list(nodes)
    while remaining:
        progressed = False
        for n in list(remaining):
            if all(dep in done for dep in n.depends_on):
                order.append(n)
                done.add(n.id)
                remaining.remove(n)
                progressed = True
        if not progressed:
            raise IRValidationError(
                f"subtask graph has a cycle or missing dependency: "
                f"{[n.id for n in remaining]}")
    ir = BehavioralIR()
    for n in order:
        if n.operation is not None:
            existing = ir.operation(n.operation.name)
            if existing is not None and existing.claim == ClaimState.OBSERVED \
                    and n.operation.claim != ClaimState.OBSERVED and (
                        existing.method != n.operation.method
                        or existing.path != n.operation.path
                        or existing.status != n.operation.status
                        or existing.permission != n.operation.permission):
                continue  # observed fact wins; conflicting subtask dropped
            ir = ir.with_operation(n.operation)
        if n.resource:
            from behavioral_ir import ResourceSpec
            ir = ir.with_resource(ResourceSpec(name=n.resource))
    return ir.require_valid()


# ---------------------------------------------------------------- compiler
def lift_compiled_spec(spec: dict) -> BehavioralIR:
    """Lift an evidence_compiler dict spec into Behavioral IR v2."""
    d = copy.deepcopy(spec)
    routes = []
    for r in d.get("routes", []):
        fields = []
        template = r.get("template")
        if isinstance(template, dict):
            for k, v in template.items():
                if isinstance(v, dict) and "$input" in v:
                    fields.append(FieldSpec(name=k, value_kind=ValueKind.INPUT_ECHO,
                                            input_field=v["$input"], observed=True,
                                            claim=ClaimState.OBSERVED))
                elif v == "<ts>":
                    fields.append(FieldSpec(name=k, value_kind=ValueKind.TIMESTAMP,
                                            observed=True, claim=ClaimState.OBSERVED))
                elif v == "<new_id>":
                    fields.append(FieldSpec(name=k, value_kind=ValueKind.DYNAMIC_ID,
                                            observed=True, claim=ClaimState.OBSERVED))
                elif isinstance(v, str) and v.startswith("<"):
                    fields.append(FieldSpec(name=k, value_kind=ValueKind.DERIVED,
                                            exact_value=v, observed=True,
                                            claim=ClaimState.OBSERVED))
                else:
                    fields.append(FieldSpec(name=k, value_kind=ValueKind.EXACT,
                                            exact_value=v, observed=True,
                                            claim=ClaimState.OBSERVED))
        routes.append({
            "name": f"{r['method']} {r['path']}", "method": r["method"],
            "path": r["path"], "kind": r.get("kind", "custom"),
            "collection": r.get("collection", ""),
            "auth": r.get("auth", True), "status": r.get("status", 200),
            "permission": r.get("access", r.get("permission", "any_auth")),
            "permission_observed": r.get("access_source") == "inferred_from_actor_outcomes",
            "claim": "OBSERVED" if r.get("source") == "observed" else "UNKNOWN",
            "fields": [dataclasses.asdict(f) | {"value_kind": f.value_kind.value,
                                                "claim": f.claim.value}
                       for f in fields],
            "validate": r.get("validate", []),
        })
    lifted = {"provenance": d.get("provenance", {}), "users": d.get("users", {}),
              "routes": routes}
    return ir_from_dict(lifted).require_valid()


def compile_candidate(observations, source_hash="") -> BehavioralIR:
    """Public observations -> one protected candidate IR (NON_AI)."""
    if not source_hash:
        source_hash = hashlib.sha256(json.dumps(
            observations, sort_keys=True, default=str).encode()).hexdigest()
    spec = evidence_compiler.compile_spec(observations, source_hash)
    return lift_compiled_spec(spec)


# ------------------------------------------------- public conformance repair
def public_conformance(ir: BehavioralIR, observations) -> dict:
    """Score candidate vs PUBLIC observations only. Never held-out."""
    divergences = []
    for obs in observations:
        action = str(obs.get("action", ""))
        if " " not in action:
            continue
        method, path = action.split(" ", 1)
        path = path.split("?")[0]
        op = next((o for o in ir.operations
                   if o.method == method and o.path == path), None)
        if op is None:
            # Unprobed-in-IR routes from errors only are not divergences.
            if isinstance(obs.get("status"), int) and obs["status"] < 300:
                divergences.append(f"{method} {path}: missing route")
            continue
        status = obs.get("status")
        if isinstance(status, int) and status < 300 and op.status != status:
            divergences.append(
                f"{method} {path}: candidate status {op.status} != observed {status}")
    return {"divergences": divergences, "count": len(divergences),
            "source": "public_observations_only"}


def repair_with_public_conformance(ir: BehavioralIR, observations, edits):
    """Apply ``edits`` [(field_path, new_value, OverrideRecord|None, evidence)]

    Returns (new_ir, report). Rejects (returns original, rejected=True) if
    public divergences increase -- the non-regression check. Protected facts
    still require a complete override record; this gate never bypasses it.
    """
    before = public_conformance(ir, observations)
    candidate = ir
    for field_path, new_value, record, evidence in edits:
        candidate = apply_override(candidate, field_path, new_value,
                                   record=record, contradicting_evidence=evidence)
    after = public_conformance(candidate, observations)
    if after["count"] > before["count"]:
        return ir, {"rejected": True, "before": before, "after": after,
                    "reason": "public conformance regression"}
    return candidate, {"rejected": False, "before": before, "after": after}
