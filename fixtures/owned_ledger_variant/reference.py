"""Second owned synthetic black-box fixture (G4 scaffolding).

Same ledger-DSL command surface as fixtures/owned_ledger (add/list/total/
remove over labeled amounts), deliberately DIFFERENT hidden rules:

- label: trimmed, 1..48 chars (vs 1..24)
- uniqueness: case-SENSITIVE on the trimmed label (vs casefold)
- amount: integer 1..500 (vs 1..100)
- error codes: invalid_title / invalid_qty / duplicate_title / missing_id
  (vs invalid_label / invalid_amount / duplicate_label / not_found)

The public command signatures are identical, so guided synthesis must
distinguish the two targets purely from observed evidence. Never pass
source to the model.

Protocol: stdin JSONL actions, stdout JSONL results; fresh process resets
all state.
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
                if not isinstance(label, str) or not label.strip() or len(label.strip()) > 48:
                    out = {"ok": False, "error": "invalid_title"}
                elif type(amount) is not int or not 1 <= amount <= 500:
                    out = {"ok": False, "error": "invalid_qty"}
                elif label.strip() in (v["label"] for v in items.values()):
                    out = {"ok": False, "error": "duplicate_title"}
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
                    out = {"ok": False, "error": "missing_id"}
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
