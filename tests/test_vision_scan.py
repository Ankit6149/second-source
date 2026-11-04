"""Vision scan: honest availability, strict region validation, real motion physics."""
import base64
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vision_scan as vs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def test_capabilities_never_leak_credentials(monkeypatch):
    monkeypatch.setenv("SECOND_SOURCE_VISION_ENDPOINT", "https://sam.internal.example/scan")
    monkeypatch.setenv("SECOND_SOURCE_VISION_API_KEY", "secret-key")
    caps = vs.capabilities()
    assert caps["regions"] == "sam-or-compatible-service"
    assert caps["regions_endpoint_host"] == "sam.internal.example"
    assert "secret-key" not in json.dumps(caps)
    monkeypatch.delenv("SECOND_SOURCE_VISION_ENDPOINT")
    assert vs.capabilities()["regions"] == "unconfigured"


def test_motion_physics_from_real_capture():
    res = vs.scan_motion(ROOT / "browser-slice-v2")
    assert res["available"] is True
    assert res["provenance"] == "NON_AI"
    assert res["spring_physics"] == {"stiffness": 164.0, "damping": 14.0,
                                     "fit_rmse_px": 4.367, "release_x_px": 260.0}
    assert res["held_out_trajectory"]["rmse_px"] == 2.505
    assert res["verdict_pass"] is True


def test_motion_missing_capture_is_explicit(tmp_path):
    empty = tmp_path / "capture"
    empty.mkdir()
    res = vs.scan_motion(empty)
    assert res["spring_physics"] is None
    assert res["held_out_trajectory"] is None
    with pytest.raises(FileNotFoundError):
        vs.scan_motion(tmp_path / "nope")


def test_image_input_validation(tmp_path, monkeypatch):
    monkeypatch.delenv("SECOND_SOURCE_VISION_ENDPOINT", raising=False)
    with pytest.raises(FileNotFoundError):
        vs.scan_image(tmp_path / "missing.png")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a png")
    with pytest.raises(ValueError):
        vs.scan_image(bad)
    with pytest.raises(ValueError):
        vs.scan_image(bad, backend="yolo")


def test_image_unconfigured_is_unmeasured(tmp_path, monkeypatch):
    monkeypatch.delenv("SECOND_SOURCE_VISION_ENDPOINT", raising=False)
    img = tmp_path / "shot.png"
    img.write_bytes(TINY_PNG)
    res = vs.scan_image(img)
    assert res["available"] is False
    assert res["regions"] is None
    assert "not configured" in res["reason"]


def test_image_rejects_bad_endpoints(tmp_path, monkeypatch):
    img = tmp_path / "shot.png"
    img.write_bytes(TINY_PNG)
    monkeypatch.setenv("SECOND_SOURCE_VISION_ENDPOINT", "ftp://x/y")
    assert vs.scan_image(img)["available"] is False
    monkeypatch.setenv("SECOND_SOURCE_VISION_ENDPOINT", "http://remote.example/scan")
    assert "non-TLS" in vs.scan_image(img)["reason"]


class _Stub:
    payload: bytes = b"{}"
    status: int = 200
    seen_auth: str | None = None


def _serve(stub):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            _Stub.seen_auth = self.headers.get("Authorization")
            body = stub.payload
            self.send_response(stub.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_image_round_trip_and_strict_shapes(tmp_path, monkeypatch):
    img = tmp_path / "shot.png"
    img.write_bytes(TINY_PNG)
    stub = _Stub()
    server = _serve(stub)
    try:
        monkeypatch.setenv("SECOND_SOURCE_VISION_ENDPOINT",
                           f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("SECOND_SOURCE_VISION_API_KEY", "k")
        stub.payload = json.dumps({"regions": [
            {"label": "button", "x": 1, "y": 2, "w": 30, "h": 10, "score": 0.9}]}).encode()
        ok = vs.scan_image(img, backend="sam")
        assert ok["available"] is True
        assert ok["regions"] == [{"label": "button", "x": 1, "y": 2, "w": 30,
                                  "h": 10, "score": 0.9}]
        assert _Stub.seen_auth == "Bearer k"
        stub.payload = json.dumps({"regions": [{"label": "x"}]}).encode()
        assert vs.scan_image(img)["available"] is False
        stub.payload = json.dumps({"regions": "nope"}).encode()
        assert vs.scan_image(img)["available"] is False
        stub.status = 500
        stub.payload = b"{}"
        assert "HTTP 500" in vs.scan_image(img)["reason"]
    finally:
        server.shutdown()
