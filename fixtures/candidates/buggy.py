"""Intentionally incorrect harness candidate (NOT a Muse reconstruction)."""
import json
import sys


def main():
    items = []
    for line in sys.stdin:
        req = json.loads(line)
        cmd = req.get("command")
        if cmd == "add":
            # Deliberately broken: rejects duplicates never, ignores amount validation.
            items.append({"id": str(len(items) + 1), "label": req.get("label"), "amount": req.get("amount")})
            out = {"ok": True, "id": str(len(items))}
        elif cmd == "list":
            out = {"ok": True, "items": list(items)}
        elif cmd == "total":
            out = {"ok": True, "count": len(items), "amount": sum(int(x.get("amount") or 0) for x in items)}
        elif cmd == "remove":
            out = {"ok": False, "error": "not_found"}
        else:
            out = {"ok": False, "error": "unknown_command"}
        print(json.dumps(out, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
