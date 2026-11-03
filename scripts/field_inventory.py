"""Generic field inventory from black-box observations (any HTTP target).

Diagnosis generalized: candidates fail held-out cases less often on
route discovery than on field-VALUE fidelity — literals, zero-times,
null-vs-empty collections, per-route field presence. This module turns
whatever public observations exist for ANY target into a compact,
model-usable inventory: per (method, route, status class), the fields
seen and the class of value each field carried.

Nothing here knows any application's field names. Swap the
observations file and the inventory follows.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_ZERO_TIME = "0001-01-01T00:00:00Z"


def value_class(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        if value == _ZERO_TIME:
            return "zero_time"
        if _TS.match(value):
            return "timestamp"
        return "string"
    if isinstance(value, list):
        return "empty_list" if not value else "nonempty_list"
    if isinstance(value, dict):
        return "object"
    return "other"


def _route_of(action: str) -> str:
    parts = action.split(" ", 1)
    return parts[1].split("?")[0] if len(parts) == 2 else action


def build_inventory(observations: list[dict]) -> dict:
    """observations: [{action: 'METHOD /route', status, body}]"""
    routes: dict[tuple, dict] = {}
    for obs in observations:
        action = str(obs.get("action", ""))
        method = action.split(" ", 1)[0] if " " in action else "?"
        route = _route_of(action)
        status = obs.get("status")
        klass = "success" if isinstance(status, int) and status < 300 else \
            "error" if isinstance(status, int) else "unknown"
        entry = routes.setdefault((method, route), {"statuses": set(), "classes": {}})
        if isinstance(status, int):
            entry["statuses"].add(status)
        body = obs.get("body")
        fields = entry["classes"].setdefault(klass, {})
        if isinstance(body, dict):
            for name, value in body.items():
                slot = fields.setdefault(name, {"classes": set(), "exemplar": value})
                slot["classes"].add(value_class(value))
        elif isinstance(body, list) and body and isinstance(body[0], dict):
            for name, value in body[0].items():
                slot = fields.setdefault(name, {"classes": set(), "exemplar": value})
                slot["classes"].add(value_class(value))
    out = {}
    for (method, route), entry in sorted(routes.items()):
        out[f"{method} {route}"] = {
            "statuses": sorted(entry["statuses"]),
            "fields": {
                klass: {name: {"classes": sorted(slot["classes"]),
                               "exemplar": slot["exemplar"]}
                        for name, slot in sorted(fields.items())}
                for klass, fields in sorted(entry["classes"].items())
            },
        }
    return {"kind": "FIELD_INVENTORY_V1", "routes": out}


def inventory_prompt_block(observations: list[dict], max_chars: int = 6000) -> str:
    """Compact per-route field/value-class summary for synthesis prompts."""
    inv = build_inventory(observations)
    lines = ["FIELD INVENTORY (observed values only; per route and status class):"]
    for route, data in inv["routes"].items():
        lines.append(f"{route} -> statuses {data['statuses']}")
        for klass, fields in data["fields"].items():
            for name, info in fields.items():
                ex = info["exemplar"]
                ex_s = json.dumps(ex)[:40] if not isinstance(ex, (dict, list)) else info["classes"][0]
                lines.append(f"  [{klass}] {name}: {'|'.join(info['classes'])} e.g. {ex_s}")
    text = "\n".join(lines)
    return text[:max_chars]


def main() -> int:
    import sys
    root = Path(__file__).resolve().parents[1]
    obs = json.loads((root / ".runs/vikunja-benchmark/public_observations.json")
                     .read_text(encoding="utf-8"))
    print(inventory_prompt_block(obs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
