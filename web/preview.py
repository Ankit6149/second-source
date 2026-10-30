"""Serve only public frontend assets and the canonical read-only console locally."""
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
CONSOLE = ROOT.parent / "demo" / "index.html"
PUBLIC = {"index.html", "styles.css", "release.css", "script.js"}
ASSETS = {"dm-sans.ttf", "manrope.ttf", "DM-Sans-OFL.txt", "Manrope-OFL.txt"}


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path in {"/console", "/console/", "/console/index.html"}:
            self.public_file = CONSOLE
        elif path == "/":
            self.public_file = ROOT / "index.html"
        elif path.removeprefix("/") in PUBLIC:
            self.public_file = ROOT / path.removeprefix("/")
        elif path.removeprefix("/assets/") in ASSETS and path.startswith("/assets/"):
            candidate = (ROOT / path.removeprefix("/")).resolve()
            if not candidate.is_relative_to(ROOT / "assets") or not candidate.is_file():
                self.send_error(404)
                return
            self.public_file = candidate
        else:
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        self.send_error(405, "Preview supports GET only")

    def translate_path(self, path):
        return str(self.public_file)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    print(f"Second Source static preview: http://127.0.0.1:{args.port}", flush=True)
    with ThreadingHTTPServer(("127.0.0.1", args.port), PreviewHandler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
