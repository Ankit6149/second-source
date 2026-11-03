"""Generic field-inventory tests: no target-specific field names."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "field_inventory",
    Path(__file__).resolve().parents[1] / "scripts" / "field_inventory.py")
fi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fi)


def test_value_classes():
    assert fi.value_class(None) == "null"
    assert fi.value_class("0001-01-01T00:00:00Z") == "zero_time"
    assert fi.value_class("2026-01-01T00:00:00Z") == "timestamp"
    assert fi.value_class([]) == "empty_list"
    assert fi.value_class([1]) == "nonempty_list"
    assert fi.value_class(True) == "bool"


def test_inventory_is_target_agnostic():
    # A completely different app's observations (invented CRM API):
    obs = [
        {"action": "POST /v9/widgets", "status": 201,
         "body": {"wid": 3, "gadget_state": "idle", "charged_at": None}},
        {"action": "GET /v9/widgets", "status": 200,
         "body": [{"wid": 3, "gadget_state": "idle", "charged_at": "0001-01-01T00:00:00Z"}]},
        {"action": "POST /v9/widgets", "status": 422,
         "body": {"problem": "bad gadget"}},
    ]
    inv = fi.build_inventory(obs)
    route = inv["routes"]["POST /v9/widgets"]
    assert route["statuses"] == [201, 422]
    assert route["fields"]["success"]["charged_at"]["classes"] == ["null"]
    listing = inv["routes"]["GET /v9/widgets"]
    assert listing["fields"]["success"]["charged_at"]["classes"] == ["zero_time"]


def test_prompt_block_mentions_no_vikunja_fields():
    obs = [{"action": "PUT /things", "status": 201, "body": {"thing_id": 1}}]
    block = fi.inventory_prompt_block(obs)
    assert "PUT /things" in block
    assert "thing_id" in block
