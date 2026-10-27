"""G3-A spec schema, manifest, and loader tests."""

import copy
import json
from pathlib import Path

import pytest

from second_source.candidate_spec import (
    CandidateError,
    load_candidate,
    parse_spec,
)

FIXTURE = Path(__file__).resolve().parent / "g3_fixtures" / "valid_candidate.json"


def valid_doc():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_valid_spec_loads_with_stable_digest(cli_scope):
    spec, digest = parse_spec(valid_doc())
    assert digest.startswith("sha256:")
    loaded = load_candidate(valid_doc(), cli_scope)
    assert loaded.digest == digest
    assert loaded.manifest.files[0].path == "candidate.json"
    assert loaded.manifest.spec_digest == digest


def test_unknown_command_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["drop_table"] = {"respond": {}}
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_missing_command_rejected(cli_scope):
    doc = valid_doc()
    del doc["commands"]["remove"]
    with pytest.raises(CandidateError, match="omits"):
        load_candidate(doc, cli_scope)


def test_unknown_subsystem_rejected(cli_scope):
    doc = valid_doc()
    doc["subsystem"] = "payments"
    with pytest.raises(CandidateError, match="authorized"):
        load_candidate(doc, cli_scope)


def test_extra_requirement_rejected(cli_scope):
    doc = valid_doc()
    doc["requirement_ids"] = ["REQ-LEDGER", "REQ-PAYMENTS"]
    with pytest.raises(CandidateError, match="not in scope"):
        load_candidate(doc, cli_scope)


def test_bad_spec_version_rejected(cli_scope):
    doc = valid_doc()
    doc["spec_version"] = "2"
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_non_json_rejected(cli_scope):
    with pytest.raises(CandidateError):
        parse_spec("{not json")


def test_oversize_spec_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["add"]["params"]["label"]["error"] = "x" * 70_000
    with pytest.raises(CandidateError, match="exceeds"):
        parse_spec(doc)


def test_unknown_param_type_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["add"]["params"]["label"]["type"] = "float"
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_bad_error_code_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["add"]["params"]["label"]["error"] = "Invalid Label!"
    with pytest.raises(CandidateError, match="error code"):
        load_candidate(doc, cli_scope)


def test_unresolvable_respond_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["add"]["respond"] = {"id": "credit_card"}
    with pytest.raises(CandidateError, match="unresolvable"):
        load_candidate(doc, cli_scope)


def test_add_without_uniqueness_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["add"]["unique_field"] = None
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_malformed_manifest_path_rejected(cli_scope):
    from second_source.contracts import ProposedFile
    from second_source.scope_guard import ScopeGuard

    decision = ScopeGuard(cli_scope).validate_candidate_files([
        ProposedFile(path="../escape.json", subsystem="cli_ledger", requirement_ids={"REQ-LEDGER"}),
    ])
    assert not decision.allowed


def test_overbuild_subsystem_rejected(cli_scope):
    from second_source.contracts import ProposedFile
    from second_source.scope_guard import ScopeGuard

    decision = ScopeGuard(cli_scope).validate_candidate_files([
        ProposedFile(path="payments.py", subsystem="payments", requirement_ids={"REQ-LEDGER"}),
    ])
    assert not decision.allowed


def test_fixture_origin_is_not_model_output():
    readme = Path(__file__).resolve().parent / "g3_fixtures" / "README.md"
    assert "NOT Muse output" in readme.read_text(encoding="utf-8")
