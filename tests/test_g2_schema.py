"""Server-side JSON-schema-subset validator tests."""

from second_source.schema_validate import validate_json_schema

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["a", "b"],
    "properties": {
        "a": {"type": "string", "minLength": 1},
        "b": {"type": "array", "minItems": 1, "items": {"type": "integer"}},
    },
}


def test_valid():
    assert validate_json_schema({"a": "x", "b": [1]}, SCHEMA) == []


def test_missing_required():
    assert validate_json_schema({"a": "x"}, SCHEMA)


def test_additional_forbidden():
    errors = validate_json_schema({"a": "x", "b": [1], "approval_granted": True}, SCHEMA)
    assert any("additional property" in e for e in errors)


def test_wrong_types():
    assert validate_json_schema({"a": 5, "b": [1]}, SCHEMA)
    assert validate_json_schema({"a": "x", "b": [True]}, SCHEMA)  # bool is not integer


def test_bounds():
    assert validate_json_schema({"a": "", "b": [1]}, SCHEMA)
    assert validate_json_schema({"a": "x", "b": []}, SCHEMA)


def test_const_enum():
    schema = {"type": "string", "const": "fresh_process_per_sequence"}
    assert validate_json_schema("fresh_process_per_sequence", schema) == []
    assert validate_json_schema("persistent_session", schema)
    schema = {"type": "string", "enum": ["read_only", "external"]}
    assert validate_json_schema("read_only", schema) == []
    assert validate_json_schema("other", schema)
