"""No-cost MCP read/probe integration tests; no Meta calls, secrets or network."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from second_source import mcp_evidence as mcp


def test_mcp_capabilities_are_strictly_local_and_nonbillable():
    result = mcp.capabilities()
    assert result["targets"][0]["id"] == "owned-ledger-v1"
    assert result["model_calls"] is False
    assert result["remote_targets"] is False
    assert result["private_sealed_tests_exposed"] is False
    assert result["paid_operations"] is False


def test_public_historical_report_is_digest_verified_and_truthful():
    report = mcp.reconstruction_report()
    assert report["model"] == "muse-spark-1.3"
    assert report["evaluation"]["passed"] == 14
    assert report["evaluation"]["failed"] == 11
    assert report["evaluation"]["total"] == 25
    assert report["accepted"] is False
    assert "not independently attested" in report["provenance"]
    assert "sealed" not in json.dumps(report).lower() or "sealed inputs" in json.dumps(report).lower()


def test_candidate_rules_are_real_public_meta_spec_not_oracle_source():
    candidate = mcp.candidate_rules()
    assert candidate["classification"] == "historical_Meta_generated_declarative_candidate"
    assert candidate["candidate_digest"].startswith("sha256:")
    assert candidate["specification"]["commands"]["add"]["params"]["amount"]["maximum"] == 1_000_000
    assert "reference.py" not in candidate["source"]


@pytest.mark.parametrize("actions", [
    [],
    [{"command": "list"}] * 7,
    [{"command": "shutdown"}],
    [{"command": "add", "label": "A", "amount": 2, "path": "/tmp/unwanted"}],
    [{"command": "list", "role": "admin"}],
    [{"command": "add", "label": {"$eval": "1+1"}, "amount": 3}],
    [{"command": "add", "label": "A", "amount": math.inf}],
    [{"command": "add", "label": "A", "amount": 1_000_001}],
    [{"command": "add", "label": "a" * 129, "amount": 2}],
    [{"command": "add", "label": "A", "amount": 2.5}],
    [{"command": "remove", "id": ["1"]}],
    ["list"],
])
def test_mcp_rejects_out_of_scope_and_unsafe_probes(actions):
    with pytest.raises(ValueError):
        mcp._validated_actions(actions)


def test_mcp_rejects_unlisted_artifacts():
    with pytest.raises(ValueError):
        mcp._load_artifact("generation-result.v1.private.json")
    with pytest.raises(ValueError):
        mcp._load_artifact("../G3_report.json")


def test_mcp_detects_tampering_in_public_candidate(tmp_path, monkeypatch):
    original = mcp._ARCHIVE
    manifest = json.loads((original / "export-manifest.json").read_text(encoding="utf-8"))
    (tmp_path / "export-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "candidate.v1.json").write_text('{"spec_version":"1","commands":{}}', encoding="utf-8")
    monkeypatch.setattr(mcp, "_ARCHIVE", tmp_path)
    monkeypatch.setattr(mcp, "_MANIFEST", tmp_path / "export-manifest.json")
    with pytest.raises(RuntimeError, match="integrity"):
        mcp.candidate_rules()


@pytest.mark.parametrize("actions,divergent_step", [
    ([{"command": "add", "label": "Milk", "amount": 2},
      {"command": "add", "label": "MILK", "amount": 3}], 1),
    ([{"command": "add", "label": "Valid", "amount": 500}], 0),
    ([{"command": "add", "label": "Valid", "amount": 2},
      {"command": "remove", "id": "1"}], 1),
])
def test_public_mcp_probe_compares_actual_local_workers(actions, divergent_step):
    result = mcp.compare_ledger(actions)
    assert result["status"] == "completed_public_probe", result
    assert result["model_called"] is False
    assert result["sealed_cases_used"] is False
    assert result["not_a_score"] is True
    assert result["steps"][divergent_step]["equal"] is False


def test_mcp_probes_reset_state_between_invocations():
    actions = [{"command": "add", "label": "Reset", "amount": 2}]
    first = mcp.compare_ledger(actions)
    second = mcp.compare_ledger(actions)
    assert first["status"] == second["status"] == "completed_public_probe"
    assert first["steps"][0]["reference_output"] == second["steps"][0]["reference_output"]


def _report(evaluation, origin):
    return {"evaluation": evaluation,
            "evaluation_receipt": {"origin": origin, "suite_digest": "sha256:" + "a" * 64,
                                   "g3_accepted": False}}


_BASE_EVAL = {"passed": 14, "failed": 11, "indeterminate": 0, "total": 25,
              "failure_categories": {"schema": 9, "error": 2}}
_BASE_ORIGIN = {"model": "muse-spark-1.3", "provider": "meta-direct",
                "response_id": "resp-1", "candidate_digest": "sha256:" + "b" * 64}


@pytest.mark.parametrize("evaluation,origin", [
    ({k: v for k, v in _BASE_EVAL.items() if k != "failed"}, _BASE_ORIGIN),
    ({**_BASE_EVAL, "passed": 30, "failed": -5}, _BASE_ORIGIN),
    ({**_BASE_EVAL, "failure_categories": "schema"}, _BASE_ORIGIN),
    (_BASE_EVAL, {**_BASE_ORIGIN, "model": 123}),
    (_BASE_EVAL, {**_BASE_ORIGIN, "candidate_digest": "ee1f"}),
])
def test_mcp_report_rejects_malformed_public_evaluation(monkeypatch, evaluation, origin):
    monkeypatch.setattr(mcp, "_load_artifact", lambda name: _report(evaluation, origin))
    with pytest.raises(RuntimeError):
        mcp.reconstruction_report()


def test_mcp_candidate_rules_rejects_spec_without_validated_commands(monkeypatch):
    monkeypatch.setattr(mcp, "_load_artifact_bytes",
                        lambda name: b'{"spec_version":"1","subsystem":"cli_ledger"}')
    with pytest.raises(RuntimeError, match="Unsupported public candidate"):
        mcp.candidate_rules()


def _mcp_v2_available():
    try:
        from mcp import Client  # noqa: F401
        from mcp.server import MCPServer  # noqa: F401
    except Exception:
        return False
    return True


@pytest.mark.skipif(not _mcp_v2_available(),
                    reason="Optional MCP SDK not installed; pure and worker tests still run")
def test_mcp_v2_protocol_roundtrip():
    import asyncio
    from mcp import Client
    from second_source.mcp_server import create_server

    async def verify():
        async with Client(create_server()) as client:
            result = await client.call_tool("second_source_compare_ledger", {
                "actions": [
                    {"command": "add", "label": "Milk", "amount": 2},
                    {"command": "add", "label": "MILK", "amount": 3},
                ],
            })
            body = result.structured_content
            assert body["status"] == "completed_public_probe"
            assert body["model_called"] is False
            assert body["steps"][1]["equal"] is False

    asyncio.run(verify())
