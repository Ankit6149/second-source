"""Behavioral IR v2 + protected-fact compiler tests (public evidence only)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from behavioral_ir import (  # noqa: E402
    BehavioralIR, ClaimState, FieldSpec, OperationSpec, OverrideRecord,
    Provenance, ProvenanceLabel, ResourceSpec, SchemaSpec, TemporalSpec,
    ValidationRule, ValueKind,
)
from behavioral_interpreter import BehavioralInterpreter  # noqa: E402
from protected_compiler import (  # noqa: E402
    ProtectedFactError, SubtaskNode, apply_override, casual_overwrite_attempt,
    collect_protected_facts, compile_candidate, compile_subtask_graph,
    public_conformance, repair_with_public_conformance,
)
from behavioral_ir import IRValidationError  # noqa: E402

OBS = [
    {"action": "PUT /projects", "as": "alice", "request": {"title": "P"},
     "status": 201, "body": {"id": 1, "title": "P",
                             "created_at": "2026-01-01T10:00:00Z",
                             "updated_at": "2026-01-01T10:00:00Z"}},
    {"action": "GET /projects", "as": "alice", "request": None,
     "status": 200, "body": [{"id": 1, "title": "P"}]},
    {"action": "GET /projects", "as": "bob", "request": None,
     "status": 200, "body": []},
    {"action": "PUT /projects", "as": "alice", "request": {"title": ""},
     "status": 400, "body": {"message": "bad"}},
    {"action": "GET /projects", "as": "None", "request": None,
     "status": 401, "body": {"message": "unauth"}},
]


def _ir():
    return compile_candidate(OBS, source_hash="abc123")


def _record(**kw):
    base = dict(rule="r", why="w", evidence="probe#9 contradicts",
                uncertainty="low", affected_behavior="status only",
                distinguishing_experiment="replay probe#9",
                regression_risk="low")
    base.update(kw)
    return OverrideRecord(**base)


def test_compile_produces_typed_ir_v2_non_ai():
    ir = _ir()
    assert ir.ir_version == 2
    assert ir.provenance.label == ProvenanceLabel.NON_AI
    assert ir.provenance.source_observations_sha256 == "abc123"
    assert ir.validate() == []
    assert any(o.kind.startswith("compiled") for o in ir.operations)


def test_observed_timestamp_cannot_be_casually_overwritten():
    ir = _ir()
    facts = collect_protected_facts(ir)
    ts_paths = [p for p in facts if "timestamp" in p or "created_at" in p]
    assert ts_paths, facts
    with pytest.raises(ProtectedFactError):
        casual_overwrite_attempt(ir, ts_paths[0], "1999-01-01T00:00:00Z")
    # Even with a record, no contradicting evidence = casual overwrite.
    with pytest.raises(ProtectedFactError):
        apply_override(ir, "operations.PUT /projects.status", 200,
                       record=_record(), contradicting_evidence="")


def test_observed_permission_cannot_be_casually_overwritten():
    ir = _ir()
    perm_paths = [p for p in collect_protected_facts(ir) if "permission" in p]
    assert perm_paths, collect_protected_facts(ir)
    with pytest.raises(ProtectedFactError):
        casual_overwrite_attempt(ir, perm_paths[0], "any_auth")
    with pytest.raises(ProtectedFactError):
        apply_override(ir, "operations.PUT /projects.permission", "any_auth",
                       record=None, contradicting_evidence="probe#1")


def test_incomplete_override_record_rejected():
    ir = _ir()
    with pytest.raises((ProtectedFactError, IRValidationError)):
        apply_override(ir, "operations.PUT /projects.status", 200,
                       record=_record(why=""), contradicting_evidence="probe#9")


def test_justified_override_with_full_record_and_evidence():
    ir = _ir()
    new = apply_override(ir, "operations.PUT /projects.status", 200,
                         record=_record(), contradicting_evidence="probe#9: status 200")
    assert new.operation("PUT /projects").status == 200
    assert new.operation("PUT /projects").claim == ClaimState.CONTRADICTED
    assert dict(new.overrides)["operations.PUT /projects.status"].why == "w"
    # original untouched (immutable by default)
    assert ir.operation("PUT /projects").status == 201


def test_ir_is_frozen_and_validation_catches_bad():
    ir = _ir()
    with pytest.raises(Exception):
        ir.ir_version = 3  # frozen dataclass
    bad = BehavioralIR(operations=(OperationSpec(name="x", method="FETCH", path="nope", kind="get"),))
    assert bad.validate()


def test_subtask_graph_compiles_to_one_candidate_observed_wins():
    obs_op = OperationSpec(name="GET /items", method="GET", path="/items",
                           kind="list", resource="items", status=200,
                           permission="owner", permission_observed=True,
                           claim=ClaimState.OBSERVED)
    guess = OperationSpec(name="GET /items", method="GET", path="/items",
                          kind="list", resource="items", status=201,
                          permission="any_auth", claim=ClaimState.ASSUMED)
    ir = compile_subtask_graph([
        SubtaskNode(id="s1", kind="compile_route", operation=obs_op, resource="items"),
        SubtaskNode(id="s2", kind="author_field", depends_on=("s1",), operation=guess),
    ])
    assert len(ir.operations) == 1
    assert ir.operations[0].status == 200
    assert ir.operations[0].permission == "owner"


def test_subtask_cycle_rejected():
    with pytest.raises(IRValidationError):
        compile_subtask_graph([
            SubtaskNode(id="a", kind="repair", depends_on=("b",)),
            SubtaskNode(id="b", kind="repair", depends_on=("a",)),
        ])


def test_public_conformance_repair_non_regression():
    ir = _ir()
    assert public_conformance(ir, OBS)["count"] == 0
    # Regressing edit: change observed create status away from observed 201.
    regressed, report = repair_with_public_conformance(
        ir, OBS, [("operations.PUT /projects.status", 200, _record(),
                   "probe#9 claims 200")])
    assert report["rejected"] is True
    assert regressed.operation("PUT /projects").status == 201
    # Non-regressing edit on an unobserved route passes the gate.
    assert report["after"]["source"] == "public_observations_only"


def test_interpreter_executes_compiled_candidate():
    ir = _ir()
    cand = BehavioralInterpreter(ir, clock=lambda: "2026-02-02T00:00:00Z")
    status, body = cand.handle("PUT", "/projects", actor="alice", body={"title": "X"})
    assert status == 201 and body["title"] == "X" and isinstance(body["id"], int)
    assert body["created_at"] == "2026-02-02T00:00:00Z"  # shape kept, server time
    status, body = cand.handle("PUT", "/projects", actor="alice", body={"title": ""})
    assert status == 400
    status, _ = cand.handle("GET", "/projects", actor=None)
    assert status == 401


def test_exact_zero_and_conditional_and_temporal_validation():
    schema = SchemaSpec(name="S", fields=(
        FieldSpec(name="done", schema_type="boolean", exact_value=False, observed=True),
        FieldSpec(name="perm_label", condition="permission>=1"),
    ))
    assert schema.field("done").exact_value is False
    assert schema.field("perm_label").conditional is True
    bad = BehavioralIR(operations=(OperationSpec(
        name="GET /x", method="GET", path="/x", kind="get",
        temporal=(TemporalSpec(field="t", observed_value="0001-01-01T00:00:00Z"),)),))
    assert any("zero-time" in e for e in bad.validate())


def test_unknown_preserved_not_upgraded():
    ir = BehavioralIR(operations=(OperationSpec(
        name="GET /never", method="GET", path="/never", kind="get"),))
    assert ir.operations[0].claim == ClaimState.UNKNOWN
    public_conformance(ir, OBS)  # scoring never upgrades a claim
    assert ir.operations[0].claim == ClaimState.UNKNOWN
