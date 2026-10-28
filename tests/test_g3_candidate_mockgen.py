"""G3-A generation-boundary tests: mock path, origins, context isolation."""

import json
from pathlib import Path

import pytest

from second_source.budgets import RunBudget
from second_source.candidate_generation import (
    build_generation_context,
    mock_propose_candidate,
    origin_of,
    request_candidate_spec,
    validate_generated_spec,
)
from second_source.contracts import Budgets
from second_source.model_gateway import (
    GatewayError,
    MockProvider,
    ModelGateway,
    ModelResponse,
)

FIXTURE = Path(__file__).resolve().parent / "g3_fixtures" / "valid_candidate.json"
PUBLIC = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "owned_ledger"
    / "public_contract.json"
)


def _observation(output=None):
    return {
        "observation_id": "obs-1",
        "sequence_id": "seq-1",
        "action_index": 0,
        "input_action": {"command": "list"},
        "output": {"ok": True} if output is None else output,
        "exit_code": 0,
        "duration_ms": 1,
        "status": "ok",
    }


def context():
    digest = "a" * 64
    return build_generation_context(
        scope_goal="reconstruct ledger behavior",
        requirement_ids=["REQ-LEDGER"],
        allowed_commands=["add", "list", "total", "remove"],
        excluded_subsystems=["payments"],
        public_command_manifest=json.loads(PUBLIC.read_text(encoding="utf-8")),
        redacted_views=[
            {"digest": digest, "observation": _observation()}
        ],
        hypotheses=[
            {
                "id": "hyp-1",
                "statement": "duplicates rejected",
                "evidence_ids": [digest],
                "status": "hypothesized",
                "alternatives": [],
                "unresolved_questions": [],
            }
        ],
    )


def test_context_has_closed_top_level_keys():
    ctx = context()
    assert set(ctx) == {
        "scope",
        "public_commands",
        "evidence",
        "hypotheses",
    }
    assert ctx["scope"]["requirement_ids"] == ["REQ-LEDGER"]
    assert "payments" in ctx["scope"]["excluded_subsystems"]


def test_context_redacts_secrets():
    ctx = build_generation_context(
        scope_goal="reconstruct ledger behavior",
        requirement_ids=["REQ-LEDGER"],
        allowed_commands=["add", "list", "total", "remove"],
        excluded_subsystems=[],
        public_command_manifest=json.loads(PUBLIC.read_text(encoding="utf-8")),
        redacted_views=[
            {
                "digest": "b" * 64,
                "observation": _observation(
                    {"ok": True, "authorization": "Bearer abc123"}
                ),
            }
        ],
        hypotheses=[
            {
                "id": "hyp-secret",
                "statement": "redaction boundary",
                "evidence_ids": ["b" * 64],
            }
        ],
    )
    assert "abc123" not in json.dumps(ctx)


def test_context_build_reads_no_restricted_paths(monkeypatch):
    """The builder takes explicit inputs; it must never open reference/gold paths."""
    import pathlib

    real_read_text = pathlib.Path.read_text

    def guarded(self, *args, **kwargs):
        if "reference.py" in str(self) or "gold" in str(self):
            raise AssertionError(f"boundary crossed: {self}")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", guarded)
    ctx = context()
    assert ctx["public_commands"]["version"] == "1"


def test_mock_path_validates_and_labels_mock(cli_scope):
    spec_dict = json.loads(FIXTURE.read_text(encoding="utf-8"))
    loaded, receipt = mock_propose_candidate(spec_dict, cli_scope)
    assert receipt.origin == "mock"
    assert receipt.real is False
    assert receipt.spec_digest == loaded.digest
    assert loaded.manifest.files[0].subsystem == "cli_ledger"


def test_mock_path_rejects_invalid(cli_scope):
    with pytest.raises(Exception):
        mock_propose_candidate({"spec_version": "9"}, cli_scope)


def test_request_labels_mock_origin(cli_scope):
    spec_dict = json.loads(FIXTURE.read_text(encoding="utf-8"))
    gateway = ModelGateway(
        MockProvider([{"content": spec_dict}]),
        RunBudget(Budgets()),
    )
    parsed, receipt = request_candidate_spec(context(), gateway)
    assert receipt.origin == "mock"
    assert receipt.real is False

    loaded, stamped = validate_generated_spec(
        parsed, cli_scope, receipt
    )
    assert stamped.spec_digest == loaded.digest
    assert stamped.origin == "mock"  # validation never upgrades origin


def test_context_rejects_hypothesis_with_unknown_evidence():
    ctx = context()
    ctx["hypotheses"][0]["evidence_ids"] = ["f" * 64]
    gateway = ModelGateway(
        MockProvider([{"content": json.loads(FIXTURE.read_text(encoding="utf-8"))}]),
        RunBudget(Budgets()),
    )
    with pytest.raises(GatewayError, match="unavailable evidence"):
        request_candidate_spec(ctx, gateway)


def test_context_rejects_nested_evidence_injection():
    ctx = context()
    ctx["evidence"][0]["gold_case"] = {"secret": 1}
    gateway = ModelGateway(
        MockProvider([{"content": json.loads(FIXTURE.read_text(encoding="utf-8"))}]),
        RunBudget(Budgets()),
    )
    with pytest.raises(GatewayError, match="malformed evidence"):
        request_candidate_spec(ctx, gateway)


def test_request_rejects_extra_generation_context_key():
    spec_dict = json.loads(FIXTURE.read_text(encoding="utf-8"))
    gateway = ModelGateway(
        MockProvider([{"content": spec_dict}]),
        RunBudget(Budgets()),
    )
    unsafe = context()
    unsafe["gold_cases"] = [{"case_id": "do-not-send"}]
    with pytest.raises(GatewayError, match="generation context"):
        request_candidate_spec(unsafe, gateway)


def test_request_redacts_again_at_final_boundary():
    captured = {}

    def responder(request):
        captured["rendered"] = "\n".join(
            message["content"] for message in request.messages
        )
        return {
            "content": json.loads(
                FIXTURE.read_text(encoding="utf-8")
            )
        }

    gateway = ModelGateway(
        MockProvider(responder=responder),
        RunBudget(Budgets()),
    )
    ctx = context()
    ctx["evidence"].append(
        {
            "digest": "c" * 64,
            "observation": _observation(
                {"ok": True, "authorization": "Bearer late-secret-token"}
            ),
        }
    )
    ctx["hypotheses"].append(
        {
            "id": "hyp-late",
            "statement": "late evidence",
            "evidence_ids": ["c" * 64],
        }
    )
    request_candidate_spec(ctx, gateway)
    assert "late-secret-token" not in captured["rendered"]


def test_origin_mapping():
    assert (
        origin_of(
            ModelResponse(
                provider="meta-direct",
                real=True,
                model="m",
                response_id="r",
                content_text="{}",
                prompt_version="v",
            )
        )
        == "real"
    )
    assert (
        origin_of(
            ModelResponse(
                provider="mock",
                real=False,
                model="m",
                response_id="r",
                content_text="{}",
                prompt_version="v",
            )
        )
        == "mock"
    )


def test_mock_demo_runs_labeled_and_matches_public_controls(cli_scope):
    from second_source.g3_mock_demo import run_demo

    report = run_demo()
    assert report["origin"] == "mock"
    assert report["content_provenance"] == "trusted-test-fixture"
    assert report["evaluation_kind"] == "NON_SEALED_TRUSTED_CONTROL"
    assert "not_AI" in report["demo_kind"]
    assert report["evaluation"]["total"] == 3
    assert report["evaluation"]["passed"] == 3
    assert report["evaluation"]["failed"] == 0
    assert report["evaluation"]["indeterminate"] == 0
