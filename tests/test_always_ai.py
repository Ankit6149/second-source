"""Always-AI endpoints: /assist answers text, /capture observes public links.

No model calls, no network beyond a loopback stub: the model stage is
monkeypatched and link capture is fenced to public hosts.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import investigation_engine as engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client():
    return TestClient(engine.app, raise_server_exceptions=False)


def _enable(monkeypatch, tmp_path, spend=0.0):
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    monkeypatch.setenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", "true")
    monkeypatch.setenv("MODEL_API_KEY", "test-only-fake-key")
    monkeypatch.delenv("SECOND_SOURCE_MAX_SPEND_USD", raising=False)
    (tmp_path / "spend.json").write_text(json.dumps({"total_estimated_usd": spend}))
    engine._ASSIST_LAST[0] = 0.0


def test_assist_gates(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    client = _client()
    assert client.post("/engine/v1/assist", json={"text": ""}).status_code == 422
    assert client.post("/engine/v1/assist", json={"text": "x" * 2001}).status_code == 422
    monkeypatch.delenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", raising=False)
    assert client.post("/engine/v1/assist", json={"text": "hi"}).status_code == 409
    monkeypatch.setenv("SECOND_SOURCE_ALLOW_MUSE_REPAIR", "true")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert client.post("/engine/v1/assist", json={"text": "hi"}).status_code == 503


def test_assist_success_records_spend(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(engine, "_muse_assist",
                        lambda text, ctx, key, sink: ("Do this.", {"response_id": "r",
                                                                  "input_tokens": 10, "output_tokens": 5,
                                                                  "estimated_cost_usd": 0.02}))
    resp = _client().post("/engine/v1/assist", json={"text": "rebuild notes?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Do this."
    assert body["model"] == "muse-spark-1.3"
    assert engine._spend_total_usd() == 0.02
    assert (tmp_path / "assist-receipts.jsonl").is_file() is False


def test_assist_cap_and_cooldown(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path, spend=14.8)
    monkeypatch.setattr(engine, "_muse_assist", lambda *a: ("x", {}))
    assert _client().post("/engine/v1/assist", json={"text": "hi"}).status_code == 402
    _enable(monkeypatch, tmp_path, spend=1.0)
    client = _client()
    assert client.post("/engine/v1/assist", json={"text": "hi"}).status_code == 200
    assert client.post("/engine/v1/assist", json={"text": "again"}).status_code == 429


def test_assist_failure_is_honest(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    def boom(*a):
        raise ValueError("PROVIDER_NOT_REAL_META")
    monkeypatch.setattr(engine, "_muse_assist", boom)
    resp = _client().post("/engine/v1/assist", json={"text": "hi"})
    assert resp.status_code == 502
    assert "ValueError" in resp.json()["detail"]


def test_capture_refuses_without_permission_and_private_hosts(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    client = _client()
    assert client.post("/engine/v1/capture",
                       json={"url": "https://example.com", "permission": False}).status_code == 422
    for bad in ("ftp://example.com/x", "http://localhost:8000/", "http://127.0.0.1:8000/",
                "http://10.0.0.5/", "http://192.168.1.1/", "http://169.254.1.1/",
                "https://user:pass@example.com/", "http://app.local/"):
        resp = client.post("/engine/v1/capture", json={"url": bad, "permission": True})
        assert resp.status_code == 422, bad


def test_capture_round_trip_with_summary(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv("SECOND_SOURCE_CAPTURE_ALLOW_LOOPBACK", "true")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<html><head><title>Demo</title></head><body><form></form><a href=/x></a></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(engine, "_muse_assist",
                            lambda text, ctx, key, sink: ("A demo page.", {"response_id": "r",
                                                                          "input_tokens": 40, "output_tokens": 5,
                                                                          "estimated_cost_usd": 0.01}))
        resp = _client().post("/engine/v1/capture", json={
            "url": f"http://127.0.0.1:{server.server_port}/", "permission": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["surface"]["kind"] == "html"
        assert body["surface"]["title"] == "Demo"
        assert body["surface"]["forms"] == 1
        assert body["summary"] == "A demo page."
        assert body["model"]["model"] == "muse-spark-1.3"
        assert "not rebuilt" in body["note"]
        assert engine._spend_total_usd() == 0.01
    finally:
        server.shutdown()


def test_public_origin_guard(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "RUNS", tmp_path)
    monkeypatch.setenv("SECOND_SOURCE_ENGINE_PUBLIC", "true")
    monkeypatch.setenv("SECOND_SOURCE_PUBLIC_ORIGINS", "https://app.example")
    client = _client()
    evil = client.post("/engine/v1/assist", json={"text": "hi"},
                       headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    ok = client.post("/engine/v1/assist", json={"text": "hi"},
                     headers={"Origin": "https://app.example"})
    assert ok.status_code in (409, 503)  # past origin, into Muse gates
    local = client.post("/engine/v1/assist", json={"text": "hi"},
                        headers={"Origin": "http://127.0.0.1:5173"})
    assert local.status_code in (409, 503)
    assert client.get("/engine/v1/health").json()["public"] is True


def test_per_visitor_daily_limits(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv("SECOND_SOURCE_ENGINE_PUBLIC", "true")
    monkeypatch.setattr(engine, "_muse_assist", lambda *a: ("x", {}))
    engine._IP_HITS.clear()
    client = _client()
    head = {"X-Forwarded-For": "203.0.113.9"}
    for _ in range(25):
        engine._ASSIST_LAST[0] = 0.0
        assert client.post("/engine/v1/assist", json={"text": "hi"}, headers=head).status_code == 200
    engine._ASSIST_LAST[0] = 0.0
    assert client.post("/engine/v1/assist", json={"text": "hi"}, headers=head).status_code == 429
    engine._ASSIST_LAST[0] = 0.0
    other = client.post("/engine/v1/assist", json={"text": "hi"},
                        headers={"X-Forwarded-For": "198.51.100.4"})
    assert other.status_code == 200


def test_local_mode_has_no_visitor_limits(monkeypatch):
    monkeypatch.delenv("SECOND_SOURCE_ENGINE_PUBLIC", raising=False)
    assert engine._ip_allowed("assist", "anyone") is True
    assert engine._allowed_origin("http://127.0.0.1:5173") is True
    assert engine._allowed_origin("https://evil.example") is False


def test_capture_without_summarize_spends_nothing(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv("SECOND_SOURCE_CAPTURE_ALLOW_LOOPBACK", "true")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"items": [1, 2]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        def boom(*a):
            raise AssertionError("model must not be called")
        monkeypatch.setattr(engine, "_muse_assist", boom)
        resp = _client().post("/engine/v1/capture", json={
            "url": f"http://127.0.0.1:{server.server_port}/api", "permission": True,
            "summarize": False})
        assert resp.status_code == 200
        assert resp.json()["surface"] == {"kind": "json", "keys": ["items"], "key_count": 1}
        assert resp.json()["summary"] is None
        assert engine._spend_total_usd() == 0.0
    finally:
        server.shutdown()
