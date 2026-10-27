"""Original, owned synthetic black-box fixture. Never pass source to the model.

Protocol: stdin JSONL actions, stdout JSONL results; fresh process resets all state.
The test harness deliberately exercises hidden validation and session rules.
"""
import json
import sys


def run():
    items = {}
    next_id = 1
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("request must be an object")
            cmd = req.get("command")
            if cmd == "add":
                label = req.get("label")
                amount = req.get("amount")
                if not isinstance(label, str) or not label.strip() or len(label.strip()) > 24:
                    out = {"ok": False, "error": "invalid_label"}
                elif type(amount) is not int or not 1 <= amount <= 100:
                    out = {"ok": False, "error": "invalid_amount"}
                elif label.strip().casefold() in (v["label"].casefold() for v in items.values()):
                    out = {"ok": False, "error": "duplicate_label"}
                else:
                    key = str(next_id)
                    next_id += 1
                    items[key] = {"id": key, "label": label.strip(), "amount": amount}
                    out = {"ok": True, "id": key}
            elif cmd == "list":
                out = {"ok": True, "items": list(items.values())}
            elif cmd == "total":
                out = {"ok": True, "count": len(items), "amount": sum(x["amount"] for x in items.values())}
            elif cmd == "remove":
                item_id = req.get("id")
                if not isinstance(item_id, str) or item_id not in items:
                    out = {"ok": False, "error": "not_found"}
                else:
                    del items[item_id]
                    out = {"ok": True, "removed": item_id}
            else:
                out = {"ok": False, "error": "unknown_command"}
        except (ValueError, TypeError, json.JSONDecodeError):
            out = {"ok": False, "error": "invalid_json"}
        print(json.dumps(out, separators=(",", ":"), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    run()
