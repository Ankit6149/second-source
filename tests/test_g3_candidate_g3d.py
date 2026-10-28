"""G3-D provenance binding: pinned contract/manifest/registry + exact request."""

import copy
import json
from pathlib import Path

import pytest

from second_source.budgets import RunBudget
from second_source.candidate_generation import (
    build_generation_context,
    build_generation_report,
    build_synthesize_request,
    expected_scope_projection,
    pin_public_manifest,
    request_candidate_spec,
    validate_context_against_pins,
    validate_generated_spec,
)
from second_source.contracts import Budgets
from second_source.model_gateway import (
    DEFAULT_FORBIDDEN_MARKERS,
    GatewayError,
    MockProvider,
    ModelGateway,
)

FIXTURE = Path(__file__).resolve().parent / "g3_fixtures" / "valid_candidate.json"
PUBLIC = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "owned_ledger"
    / "public_contract.json"
)


def _observation():
    return {
        "observation_id": "obs-1",
        "sequence_id": "seq-1",
        "action_index": 0,
        "input_action": {"command": "list"},
        "output": {"ok": True},
        "exit_code": 0,
        "duration_ms": 1,
        "status": "ok",
    }


def bound_inputs(cli_scope):
    digest = "c" * 64
    ctx = build_generation_context(
        scope_goal=cli_scope.goal,
        requirement_ids=sorted(cli_scope.implementation.requirements),
        allowed_commands=sorted(cli_scope.observation.allowed_commands),
        excluded_subsystems=sorted(cli_scope.exclusions.subsystems),
        public_command_manifest=json.loads(PUBLIC.read_text(encoding="utf-8")),
        redacted_views=[{"digest": digest, "observation": _observation()}],
        hypotheses=[
            {
                "id": "hyp-1",
                "statement": "duplicates rejected",
                "evidence_ids": [digest],
                "status": "hypothesized",
            }
        ],
    )
    manifest_digest = pin_public_manifest(ctx["public_commands"])
    registry = {digest: copy.deepcopy(ctx["evidence"][0]["observation"])}
    return ctx, manifest_digest, registry


def test_scope_projection_matches_contract(cli_scope):
    proj = expected_scope_projection(cli_scope)
    assert proj["goal"] == cli_scope.goal
    assert proj["allowed_commands"] == ["add", "list", "remove", "total"]


def test_pins_admit_bound_context(cli_scope):
    ctx, manifest_digest, registry = bound_inputs(cli_scope)
    safe = validate_context_against_pins(
        ctx,
        contract=cli_scope,
        public_manifest_digest=manifest_digest,
        approved_evidence=registry,
    )
    assert safe["scope"]["goal"] == cli_scope.goal


def test_bound_request_is_exactly_what_broker_sends(cli_scope):
    ctx, manifest_digest, registry = bound_inputs(cli_scope)
    spec_dict = json.loads(FIXTURE.read_text(encoding="utf-8"))
    captured = {}

    def responder(request):
        captured["request"] = request.model_dump(mode="json")
        return {"content": spec_dict}

    gateway = ModelGateway(
        MockProvider(responder=responder), RunBudget(Budgets())
    )
    parsed, receipt = request_candidate_spec(
        ctx,
        gateway,
        contract=cli_scope,
        public_manifest_digest=manifest_digest,
        approved_evidence=registry,
    )
    assert receipt.origin == "mock" and receipt.real is False
    logical = build_synthesize_request(
        validate_context_against_pins(
            ctx,
            contract=cli_scope,
            public_manifest_digest=manifest_digest,
            approved_evidence=registry,
        )
    ).model_dump(mode="json")
    wire = captured["request"]
    # The credential-owning broker prepends exactly one deterministic schema
    # preamble and must deliver our inspected messages/schema unmodified.
    assert wire["messages"][1:] == logical["messages"]
    assert wire["stage"] == logical["stage"]
    assert wire["json_schema"] == logical["json_schema"]
    assert wire["max_output_tokens"] == logical["max_output_tokens"]
    preamble = wire["messages"][0]
    assert preamble["role"] == "system"
    sent_schema = json.loads(
        preamble["content"].split("JSON Schema:\n", 1)[1]
    )
    assert sent_schema == logical["json_schema"]
    loaded, stamped = validate_generated_spec(parsed, cli_scope, receipt)
    assert stamped.spec_digest == loaded.digest


def test_bound_rejects_unapproved_evidence(cli_scope):
    ctx, manifest_digest, registry = bound_inputs(cli_scope)
    tampered = copy.deepcopy(ctx)
    tampered["evidence"][0]["observation"]["output"] = {"ok": False}
    tampered["hypotheses"][0]["evidence_ids"] = [
        tampered["evidence"][0]["digest"]
    ]
    gateway = ModelGateway(
        MockProvider([{"content": json.loads(FIXTURE.read_text(encoding="utf-8"))}]),
        RunBudget(Budgets()),
    )
    with pytest.raises(GatewayError):
        request_candidate_spec(
            tampered,
            gateway,
            contract=cli_scope,
            public_manifest_digest=manifest_digest,
            approved_evidence=registry,
        )


def test_bound_rejects_manifest_swap(cli_scope):
    ctx, manifest_digest, registry = bound_inputs(cli_scope)
    swapped = copy.deepcopy(ctx)
    swapped["public_commands"] = copy.deepcopy(ctx["public_commands"])
    swapped["public_commands"]["description"] = "forged manifest"
    gateway = ModelGateway(
        MockProvider([{"content": json.loads(FIXTURE.read_text(encoding="utf-8"))}]),
        RunBudget(Budgets()),
    )
    with pytest.raises(GatewayError):
        request_candidate_spec(
            swapped,
            gateway,
            contract=cli_scope,
            public_manifest_digest=manifest_digest,
            approved_evidence=registry,
        )


def test_bound_rejects_scope_mismatch(cli_scope):
    ctx, manifest_digest, registry = bound_inputs(cli_scope)
    drifted = copy.deepcopy(ctx)
    drifted["scope"]["goal"] = "a different goal"
    gateway = ModelGateway(
        MockProvider([{"content": json.loads(FIXTURE.read_text(encoding="utf-8"))}]),
        RunBudget(Budgets()),
    )
    with pytest.raises(GatewayError):
        request_candidate_spec(
            drifted,
            gateway,
            contract=cli_scope,
            public_manifest_digest=manifest_digest,
            approved_evidence=registry,
        )


def test_bound_rejects_partial_pins(cli_scope):
    ctx, manifest_digest, registry = bound_inputs(cli_scope)
    gateway = ModelGateway(
        MockProvider([{"content": json.loads(FIXTURE.read_text(encoding="utf-8"))}]),
        RunBudget(Budgets()),
    )
    with pytest.raises(GatewayError):
        request_candidate_spec(ctx, gateway, contract=cli_scope)


def test_generation_report_sanitized(cli_scope):
    ctx, manifest_digest, registry = bound_inputs(cli_scope)
    gateway = ModelGateway(
        MockProvider([{"content": json.loads(FIXTURE.read_text(encoding="utf-8"))}]),
        RunBudget(Budgets()),
    )
    parsed, receipt = request_candidate_spec(
        ctx,
        gateway,
        contract=cli_scope,
        public_manifest_digest=manifest_digest,
        approved_evidence=registry,
    )
    loaded, stamped = validate_generated_spec(parsed, cli_scope, receipt)
    report = build_generation_report(
        receipt=stamped,
        scope_digest="sha256:" + "d" * 64,
        public_manifest_digest=manifest_digest,
        evidence_digests=list(registry),
    )
    assert report["kind"] == "GENERATION_REPORT_NOT_EVALUATION"
    assert report["spec_digest"] == loaded.digest
    blob = json.dumps(report)
    assert "observation" not in blob and "input_action" not in blob
    for marker in DEFAULT_FORBIDDEN_MARKERS:
        assert marker not in blob
