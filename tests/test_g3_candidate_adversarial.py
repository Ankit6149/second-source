"""G3-A adversarial tests: the DSL cannot express code, egress, or escape.

Every case asserts fail-closed rejection at LOAD time (before any execution)
or a safe error at RUN time. Nothing here executes model-supplied strings as
code — the interpreter has no eval/exec/compile/import/subprocess path, and
these tests pin that property by attempting to smuggle each one through.
"""

import json
from pathlib import Path

import pytest

from second_source.candidate_runtime import CandidateInterpreter
from second_source.candidate_spec import CandidateError, load_candidate

FIXTURE = Path(__file__).resolve().parent / "g3_fixtures" / "valid_candidate.json"


def valid_doc():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_shell_op_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["add"]["exec_shell"] = "rm -rf /"
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_egress_op_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["list"]["http_get"] = "https://evil.example/exfil"
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_credential_read_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["total"]["env_read"] = "MODEL_API_KEY"
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_eval_import_rejected(cli_scope):
    for key in ("eval", "exec", "compile", "import", "subprocess", "open", "write_file"):
        doc = valid_doc()
        doc["commands"]["add"][key] = "payload"
        with pytest.raises(CandidateError):
            load_candidate(doc, cli_scope)


def test_extra_command_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["admin_reset"] = {"respond": {}}
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_admin_subsystem_rejected(cli_scope):
    doc = valid_doc()
    doc["subsystem"] = "admin"
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_lookup_without_error_code_rejected(cli_scope):
    doc = valid_doc()
    del doc["commands"]["remove"]["not_found_error"]
    with pytest.raises(CandidateError):
        load_candidate(doc, cli_scope)


def test_giant_spec_rejected(cli_scope):
    doc = valid_doc()
    doc["commands"]["add"]["params"]["label"]["error"] = "e" * 70_000
    with pytest.raises(CandidateError, match="exceeds"):
        load_candidate(doc, cli_scope)


def test_non_object_spec_rejected(cli_scope):
    with pytest.raises(CandidateError):
        load_candidate([1, 2, 3], cli_scope)


def test_injection_label_is_data_not_code(cli_scope):
    """A hostile label is stored/compared as text; duplicates still detected."""
    loaded = load_candidate(valid_doc(), cli_scope)
    interp = CandidateInterpreter(loaded.spec)
    evil = "<script>x</script>"
    result = interp.execute_sequence(
        [
            {"command": "add", "label": evil, "amount": 1},
            {"command": "add", "label": evil.upper(), "amount": 1},
            {"command": "list"},
        ],
        sequence_id="a",
    )
    assert result.status == "ok"
    assert result.observations[0].output == {"ok": True, "id": "1"}
    assert result.observations[1].output == {"ok": False, "error": "duplicate_label"}
    items = result.observations[2].output["items"]
    assert items == [{"id": "1", "label": evil, "amount": 1}]


def test_no_dynamic_execution_primitives_in_runtime():
    text = (Path(__file__).resolve().parents[1] / "src" / "second_source" / "candidate_runtime.py").read_text(encoding="utf-8")
    for primitive in ("eval(", "exec(", "compile(", "__import__(", "import subprocess",
                        "import os", "os.system(", "open("):
        assert primitive not in text
