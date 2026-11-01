"""Owned stateful HTTP fixture for G4 cross-protocol reconstruction (scaffolding).

A minimal JSON resource API over stdlib ``http.server`` (no dependencies):

- POST   /items        {label, amount} -> 201 {id} | 400 | 409
- GET    /items                        -> 200 {items}
- GET    /items/{id}                   -> 200 item | 404
- DELETE /items/{id}                   -> 200 {removed} | 404
- unknown route                         -> 404 {unknown_route}
- wrong method on a known route          -> 405 {method_not_allowed}

Hidden rules (deliberately different from both ledger fixtures):

- label: trimmed, 1..32 chars, case-SENSITIVE uniqueness
- amount: integer 1..250
- error codes: invalid_title / invalid_qty / duplicate_title / missing_id

Usage: ``python server.py --port-file <path>`` binds 127.0.0.1 on an
ephemeral port, writes the port number to the file, then serves until
killed. Fresh process resets all state. Never pass source to the model.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class _Store:
    def __init__(self):
        self.items = {}
        self.next_id = 1


STORE = _Store()


def _send(handler, status, payload):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler):
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        return None
    if length <= 0 or length > 65536:
        return None
    try:
        parsed = json.loads(handler.rfile.read(length).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


class _Handler(BaseHTTPRequestHandler):
    server_version = "OwnedFixture/1"

    def log_message(self, *args):
        pass

    def _route(self, method):
        path = urlparse(self.path).path.rstrip("/") or "/"
        parts = [p for p in path.split("/") if p]
        if parts[:1] != ["items"]:
            _send(self, 404, {"error": "unknown_route"})
            return
        if len(parts) == 1:
            if method == "POST":
                self._create()
            elif method == "GET":
                _send(self, 200, {"items": list(STORE.items.values())})
            else:
                _send(self, 405, {"error": "method_not_allowed"})
        elif len(parts) == 2:
            item_id = parts[1]
            if method == "GET":
                item = STORE.items.get(item_id)
                if item is None:
                    _send(self, 404, {"error": "missing_id"})
                else:
                    _send(self, 200, dict(item))
            elif method == "DELETE":
                if item_id not in STORE.items:
                    _send(self, 404, {"error": "missing_id"})
                else:
                    del STORE.items[item_id]
                    _send(self, 200, {"removed": item_id})
            else:
                _send(self, 405, {"error": "method_not_allowed"})
        else:
            _send(self, 404, {"error": "unknown_route"})

    def _create(self):
        req = _read_json(self)
        if req is None:
            _send(self, 400, {"error": "invalid_title"})
            return
        label, amount = req.get("label"), req.get("amount")
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 32:
            _send(self, 400, {"error": "invalid_title"})
        elif type(amount) is not int or not 1 <= amount <= 250:
            _send(self, 400, {"error": "invalid_qty"})
        elif label.strip() in (v["label"] for v in STORE.items.values()):
            _send(self, 409, {"error": "duplicate_title"})
        else:
            key = str(STORE.next_id)
            STORE.next_id += 1
            STORE.items[key] = {"id": key, "label": label.strip(), "amount": amount}
            _send(self, 201, {"id": key})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_DELETE(self):
        self._route("DELETE")

    def do_PUT(self):
        self._route("PUT")

    def do_PATCH(self):
        self._route("PATCH")


def main(argv):
    port_file = None
    for index, token in enumerate(argv):
        if token == "--port-file" and index + 1 < len(argv):
            port_file = argv[index + 1]
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    if port_file is not None:
        with open(port_file, "w", encoding="utf-8") as stream:
            stream.write(str(server.server_address[1]))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
