"""Minimal JSON-schema-subset validator (G2).

The gateway requests non-strict `json_object` output (discriminating-experiment
params are inherently open shapes that Meta's strict subset cannot express),
so the server side enforces the closed contract instead. This checker covers
exactly the subset our schemas emit; anything else fails closed.
"""
from __future__ import annotations

from typing import Any


def validate_json_schema(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Return a list of violations; empty means valid."""
    errors: list[str] = []
    if not isinstance(schema, dict):
        return [f"{path}: schema must be an object"]
    schema_type = schema.get("type")
    if schema_type is not None and not _check_type(instance, schema_type):
        return [f"{path}: expected {schema_type}, got {_typename(instance)}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for required_key in schema.get("required", []):
            if required_key not in instance:
                errors.append(f"{path}: missing required {required_key!r}")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: additional property {key!r} forbidden")
        for key, subschema in properties.items():
            if key in instance and isinstance(subschema, dict):
                errors.extend(validate_json_schema(instance[key], subschema, f"{path}.{key}"))
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            errors.append(f"{path}: fewer than minProperties {schema['minProperties']}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than maxItems {schema['maxItems']}")
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(instance):
                errors.extend(validate_json_schema(item, items, f"{path}[{index}]"))
    return errors


def _check_type(instance: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(instance, dict)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected == "null":
        return instance is None
    return False


def _typename(instance: Any) -> str:
    if isinstance(instance, bool):
        return "boolean"
    if isinstance(instance, int):
        return "integer"
    if isinstance(instance, float):
        return "number"
    if isinstance(instance, str):
        return "string"
    if isinstance(instance, list):
        return "array"
    if isinstance(instance, dict):
        return "object"
    if instance is None:
        return "null"
    return type(instance).__name__
