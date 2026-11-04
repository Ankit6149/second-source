"""Serve only public frontend assets and the canonical read-only console locally."""
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from build import app_asset

ROOT = Path(__file__).resolve().parent
PUBLIC = {"index.html", "styles.css", "release.css", "script.js"}
ASSETS = {"dm-sans.ttf", "manrope.ttf", "DM-Sans-OFL.txt", "Manrope-OFL.txt"}


STUB = ('<!doctype html><meta charset="utf-8"><title>Second Source</title>'
        '<meta http-equiv="refresh" content="0; url=/app/">'
        '<link rel="canonical" href="/app/">'
        '<p>This page has moved into the app. <a href="/app/">Open Second Source</a>.</p>'
        "<script>location.replace('/app/')</script>")
REMOVED = ("console", "evidence", "lab", "challenge", "handoff")

class PreviewHandler(SimpleHTTPRequestHandler):
    def _stub(self):
        body = STUB.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if any(path in {f"/{r}", f"/{r}/", f"/{r}/index.html"} for r in REMOVED):
            self._stub()
            return
        elif path in {"/app", "/app/"} or app_asset(path.lstrip("/")):
            name = "app/index.html" if path in {"/app", "/app/"} else path.lstrip("/")
            candidate = (ROOT / "dist" / name).resolve()
            if not candidate.is_relative_to((ROOT / "dist" / "app").resolve()) or not candidate.is_file():
                self.send_error(503, "Build the workspace with python web/build.py --with-app first")
                return
            self.public_file = candidate
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
