"""BEHAVIORAL IR v2 -- typed, composable candidate intermediate representation.

Generalises the ad-hoc dict spec of ``vikunja_candidate_server.py`` and the
output of ``evidence_compiler.compile_spec`` into a frozen, validated IR.

Design rules (from COMMON CONTRACT v1 / prior handoff):
- Observed fields are immutable by default (see ``protected_compiler``).
- Provenance label (NON_AI / REAL_MODEL / GEMMA_TEST) is never relabelled.
- Claims are OBSERVED / ASSUMED / UNKNOWN / CONTRADICTED; only public
  observations may mark a claim OBSERVED. Held-out material is never read.
- No application field names: resources/operations are generic.

Stdlib-only (dataclasses) so scripts run without the package installed.
"""
from __future__ import annotations

import copy
import enum
import json
from dataclasses import dataclass, field, replace


class IRValidationError(ValueError):
    """Raised when an IR fails validation."""


class ClaimState(str, enum.Enum):
    OBSERVED = "OBSERVED"
    ASSUMED = "ASSUMED"
    UNKNOWN = "UNKNOWN"
    CONTRADICTED = "CONTRADICTED"


class ProvenanceLabel(str, enum.Enum):
    NON_AI = "NON_AI"
    REAL_MODEL = "REAL_MODEL"
    GEMMA_TEST = "GEMMA_TEST"


class ValueKind(str, enum.Enum):
    EXACT = "exact"            # literal observed value preserved verbatim
    DYNAMIC_ID = "dynamic_id"  # server-generated id (<new_id>)
    TIMESTAMP = "timestamp"    # server-generated timestamp (<ts>)
    INPUT_ECHO = "input_echo"  # echoes a request field ($input)
    CREATOR = "creator"        # acting user object (<creator>)
    DERIVED = "derived"        # computed (index/identifier/entity ref)


@dataclass(frozen=True)
class Provenance:
    kind: str = "EVIDENCE_COMPILED"  # EVIDENCE_COMPILED|MODEL_AUTHORED|HYBRID
    label: ProvenanceLabel = ProvenanceLabel.NON_AI
    source_observations_sha256: str = ""
    per_field: tuple = ()  # tuple[tuple[str,str],...] field_path -> origin

    def field_origin(self, field_path: str) -> str:
        return dict(self.per_field).get(field_path, "unknown")

    def to_dict(self):
        return {"kind": self.kind, "label": self.label.value,
                "source_observations_sha256": self.source_observations_sha256,
                "per_field": dict(self.per_field)}


@dataclass(frozen=True)
class FieldSpec:
    """One response/request field. ``condition`` makes it conditional."""
    name: str
    schema_type: str = "string"  # string|integer|number|boolean|object|array|null
    value_kind: ValueKind = ValueKind.EXACT
    exact_value: object = None          # preserved verbatim when EXACT
    input_field: str = ""               # for INPUT_ECHO
    condition: str = ""                 # e.g. "permission>=1"; empty = always
    observed: bool = False
    claim: ClaimState = ClaimState.UNKNOWN
    nullable: bool = False

    @property
    def conditional(self) -> bool:
        return bool(self.condition)

    def to_dict(self):
        return {"name": self.name, "schema_type": self.schema_type,
                "value_kind": self.value_kind.value, "exact_value": self.exact_value,
                "input_field": self.input_field, "condition": self.condition,
                "observed": self.observed, "claim": self.claim.value,
                "nullable": self.nullable}


@dataclass(frozen=True)
class SchemaSpec:
    name: str
    fields: tuple = ()  # tuple[FieldSpec,...]
    required: tuple = ()

    def field(self, name):
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def to_dict(self):
        return {"name": self.name, "fields": [f.to_dict() for f in self.fields],
                "required": list(self.required)}


@dataclass(frozen=True)
class ValidationRule:
    field: str
    rule: str = "nonempty"  # nonempty|type|range|enum
    status: int = 400
    error_body: object = None
    observed: bool = False

    def to_dict(self):
        return {"field": self.field, "rule": self.rule, "status": self.status,
                "error_body": self.error_body, "observed": self.observed}


@dataclass(frozen=True)
class ErrorContract:
    status: int
    body: object = None
    kind: str = "error"  # unauthenticated|forbidden|not_found|login_error|validation
    observed: bool = False

    def to_dict(self):
        return {"status": self.status, "body": self.body, "kind": self.kind,
                "observed": self.observed}


@dataclass(frozen=True)
class AuthSpec:
    login_route: str = "/login"
    token_kind: str = "bearer"  # bearer|raw_header
    header_name: str = ""
    unauthenticated_status: int = 401
    login_error_status: int = 400
    errors: tuple = ()  # tuple[ErrorContract,...]

    def to_dict(self):
        return {"login_route": self.login_route, "token_kind": self.token_kind,
                "header_name": self.header_name,
                "unauthenticated_status": self.unauthenticated_status,
                "login_error_status": self.login_error_status,
                "errors": [e.to_dict() for e in self.errors]}


@dataclass(frozen=True)
class RelationshipSpec:
    name: str
    source: str          # collection
    target: str          # collection
    kind: str = "owns"   # owns|contains|shares|references
    foreign_key: str = ""
    permission: str = ""  # permission propagated along the relationship

    def to_dict(self):
        return {"name": self.name, "source": self.source, "target": self.target,
                "kind": self.kind, "foreign_key": self.foreign_key,
                "permission": self.permission}


@dataclass(frozen=True)
class TransitionSpec:
    field: str
    from_value: object = None
    to_value: object = None
    allowed: bool = True
    status_on_denied: int = 400

    def to_dict(self):
        return {"field": self.field, "from": self.from_value, "to": self.to_value,
                "allowed": self.allowed, "status_on_denied": self.status_on_denied}


@dataclass(frozen=True)
class TemporalSpec:
    field: str
    kind: str = "server_timestamp"  # server_timestamp|zero_time|monotonic|deadline
    format: str = "rfc3339"
    observed_value: str = ""  # exact observed literal (protected)

    def to_dict(self):
        return {"field": self.field, "kind": self.kind, "format": self.format,
                "observed_value": self.observed_value}


@dataclass(frozen=True)
class DependencySpec:
    operation: str       # operation name requiring the dependency
    requires: str        # resource/operation that must exist first
    kind: str = "exists"  # exists|authenticated|state_is

    def to_dict(self):
        return {"operation": self.operation, "requires": self.requires,
                "kind": self.kind}


@dataclass(frozen=True)
class ResourceSpec:
    name: str  # collection name, generic
    schema: SchemaSpec = None
    id_field: str = "id"

    def to_dict(self):
        return {"name": self.name,
                "schema": self.schema.to_dict() if self.schema else None,
                "id_field": self.id_field}


@dataclass(frozen=True)
class OperationSpec:
    name: str
    method: str
    path: str  # template, e.g. /projects/{pid}
    kind: str  # create|list|get|update|share|get_user|custom|compiled_*
    resource: str = ""
    auth: bool = True
    permission: str = "any_auth"  # owner|owner_or_read|owner_or_write|any_auth
    permission_observed: bool = False
    status: int = 200
    response_schema: str = ""
    fields: tuple = ()       # tuple[FieldSpec,...] response template fields
    validate: tuple = ()     # tuple[ValidationRule,...]
    errors: tuple = ()       # tuple[ErrorContract,...]
    transitions: tuple = ()  # tuple[TransitionSpec,...]
    temporal: tuple = ()     # tuple[TemporalSpec,...]
    dependencies: tuple = ()  # tuple[DependencySpec,...]
    claim: ClaimState = ClaimState.UNKNOWN

    def to_dict(self):
        return {"name": self.name, "method": self.method, "path": self.path,
                "kind": self.kind, "resource": self.resource, "auth": self.auth,
                "permission": self.permission,
                "permission_observed": self.permission_observed,
                "status": self.status, "response_schema": self.response_schema,
                "fields": [f.to_dict() for f in self.fields],
                "validate": [v.to_dict() for v in self.validate],
                "errors": [e.to_dict() for e in self.errors],
                "transitions": [t.to_dict() for t in self.transitions],
                "temporal": [t.to_dict() for t in self.temporal],
                "dependencies": [d.to_dict() for d in self.dependencies],
                "claim": self.claim.value}


@dataclass(frozen=True)
class OverrideRecord:
    """Justified-override record -- ALL fields required, non-empty."""
    rule: str
    why: str
    evidence: str
    uncertainty: str
    affected_behavior: str
    distinguishing_experiment: str
    regression_risk: str

    def validate(self):
        missing = [k for k in ("rule", "why", "evidence", "uncertainty",
                               "affected_behavior", "distinguishing_experiment",
                               "regression_risk")
                   if not str(getattr(self, k) or "").strip()]
        if missing:
            raise IRValidationError(
                f"override record missing required fields: {missing}")
        return True

    def to_dict(self):
        return {k: getattr(self, k) for k in
                ("rule", "why", "evidence", "uncertainty", "affected_behavior",
                 "distinguishing_experiment", "regression_risk")}


@dataclass(frozen=True)
class BehavioralIR:
    ir_version: int = 2
    provenance: Provenance = field(default_factory=Provenance)
    users: tuple = ()        # tuple[tuple[alias, username],...]
    auth: AuthSpec = field(default_factory=AuthSpec)
    resources: tuple = ()    # tuple[ResourceSpec,...]
    operations: tuple = ()   # tuple[OperationSpec,...]
    schemas: tuple = ()      # tuple[SchemaSpec,...]
    relationships: tuple = ()
    dependencies: tuple = ()
    overrides: tuple = ()    # tuple[tuple[field_path, OverrideRecord],...]

    # -- composition -------------------------------------------------
    def with_operation(self, op: OperationSpec) -> "BehavioralIR":
        ops = tuple(o for o in self.operations if o.name != op.name) + (op,)
        return replace(self, operations=ops)

    def with_resource(self, res: ResourceSpec) -> "BehavioralIR":
        rs = tuple(r for r in self.resources if r.name != res.name) + (res,)
        return replace(self, resources=rs)

    def operation(self, name):
        for o in self.operations:
            if o.name == name:
                return o
        return None

    def resource(self, name):
        for r in self.resources:
            if r.name == name:
                return r
        return None

    # -- validation --------------------------------------------------
    def validate(self):
        errors = []
        if self.ir_version != 2:
            errors.append(f"ir_version must be 2, got {self.ir_version}")
        names = [o.name for o in self.operations]
        if len(names) != len(set(names)):
            errors.append("duplicate operation names")
        known_resources = {r.name for r in self.resources}
        known_schemas = {s.name for s in self.schemas}
        for op in self.operations:
            if op.method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                errors.append(f"{op.name}: bad method {op.method}")
            if not op.path.startswith("/"):
                errors.append(f"{op.name}: path must start with /")
            if op.resource and known_resources and op.resource not in known_resources:
                errors.append(f"{op.name}: unknown resource {op.resource}")
            if op.response_schema and known_schemas and \
                    op.response_schema not in known_schemas:
                errors.append(f"{op.name}: unknown schema {op.response_schema}")
            for f in op.fields:
                if f.value_kind == ValueKind.INPUT_ECHO and not f.input_field:
                    errors.append(f"{op.name}.{f.name}: input_echo needs input_field")
            for t in op.temporal:
                if t.kind == "server_timestamp" and t.observed_value and \
                        t.observed_value == "0001-01-01T00:00:00Z":
                    errors.append(f"{op.name}.{t.field}: zero-time is not a server timestamp")
        for rel in self.relationships:
            for side in (rel.source, rel.target):
                if known_resources and side not in known_resources:
                    errors.append(f"relationship {rel.name}: unknown resource {side}")
        for path, rec in self.overrides:
            try:
                rec.validate()
            except IRValidationError as exc:
                errors.append(f"override {path}: {exc}")
        return errors

    def require_valid(self):
        errs = self.validate()
        if errs:
            raise IRValidationError("; ".join(errs))
        return self

    # -- serialisation ----------------------------------------------
    def to_dict(self):
        return {"ir_version": self.ir_version,
                "provenance": self.provenance.to_dict(),
                "users": dict(self.users), "auth": self.auth.to_dict(),
                "resources": [r.to_dict() for r in self.resources],
                "operations": [o.to_dict() for o in self.operations],
                "schemas": [s.to_dict() for s in self.schemas],
                "relationships": [r.to_dict() for r in self.relationships],
                "dependencies": [d.to_dict() for d in self.dependencies],
                "overrides": {k: v.to_dict() for k, v in self.overrides}}

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def _field_from_dict(d):
    return FieldSpec(name=d["name"], schema_type=d.get("schema_type", "string"),
                     value_kind=ValueKind(d.get("value_kind", "exact")),
                     exact_value=d.get("exact_value"),
                     input_field=d.get("input_field", ""),
                     condition=d.get("condition", ""),
                     observed=bool(d.get("observed")), 
                     claim=ClaimState(d.get("claim", "UNKNOWN")),
                     nullable=bool(d.get("nullable")))


def ir_from_dict(d: dict) -> BehavioralIR:
    """Parse a dict (e.g. legacy candidate spec lifted to v2) into the IR."""
    prov_d = d.get("provenance") or {}
    prov = Provenance(kind=prov_d.get("kind", "EVIDENCE_COMPILED"),
                      label=ProvenanceLabel(prov_d.get("label", "NON_AI")),
                      source_observations_sha256=prov_d.get(
                          "source_observations_sha256", ""),
                      per_field=tuple((prov_d.get("per_field") or {}).items()))
    ops = []
    for o in d.get("operations", d.get("routes", [])):
        ops.append(OperationSpec(
            name=o.get("name", f"{o.get('method','GET')} {o.get('path','/')}"),
            method=o["method"], path=o["path"], kind=o.get("kind", "custom"),
            resource=o.get("resource", o.get("collection", "")),
            auth=bool(o.get("auth", True)),
            permission=o.get("permission", o.get("access", "any_auth")),
            permission_observed=bool(o.get("permission_observed")),
            status=int(o.get("status", 200)),
            response_schema=o.get("response_schema", ""),
            fields=tuple(_field_from_dict(f) for f in o.get("fields", [])),
            validate=tuple(ValidationRule(**{k: v for k, v in v_.items()
                                             if k in ValidationRule.__dataclass_fields__})
                           for v_ in o.get("validate", [])),
            claim=ClaimState(o.get("claim", "UNKNOWN"))))
    resources = tuple(ResourceSpec(name=r["name"]) if isinstance(r, dict)
                      else ResourceSpec(name=str(r))
                      for r in d.get("resources", []))
    if not resources:
        resources = tuple(ResourceSpec(name=n) for n in
                          sorted({o.resource for o in ops if o.resource}))
    return BehavioralIR(provenance=prov,
                        users=tuple((d.get("users") or {}).items()),
                        resources=resources, operations=tuple(ops))
