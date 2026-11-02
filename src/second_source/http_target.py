"""Owned HTTP observation adapter (G4 cross-protocol scaffolding).

Typed HTTP request/response records plus a managed fixture-server lifecycle
(spawn ``fixtures/owned_http_items/server.py``, reset by respawning for a
fresh deterministic state). Transport failures surface as explicit errors,
never as successful observations. stdlib only.
"""
from __future__ import annotations

import http.client
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "fixtures" / "owned_http_items" / "server.py"


@dataclass(frozen=True)
class HttpRequest:
    method: str
    path: str
    body: dict | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: dict


@dataclass(frozen=True)
class HttpExchange:
    request: HttpRequest
    response: HttpResponse
    duration_ms: int


class HttpTransportError(RuntimeError):
    """The fixture server could not be reached or answered unparseably."""


class HttpObservationAdapter:
    """Managed lifecycle for the owned HTTP fixture plus typed exchanges."""

    def __init__(self, *, timeout_s: float = 10.0) -> None:
        self._timeout_s = timeout_s
        self._process: subprocess.Popen | None = None
        self._port: int | None = None

    @property
    def port(self) -> int | None:
        return self._port

    def start(self) -> int:
        self.stop()
        port_file = ROOT / ".runs" / ".http-fixture-port"
        port_file.parent.mkdir(parents=True, exist_ok=True)
        if port_file.exists():
            port_file.unlink()
        self._process = subprocess.Popen(
            [sys.executable, "-B", str(SERVER), "--port-file", str(port_file)],
            cwd=str(ROOT), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise HttpTransportError("fixture server exited during start")
            try:
                self._port = int(port_file.read_text(
                    encoding="utf-8").strip())
                port_file.unlink(missing_ok=True)
                return self._port
            except (OSError, ValueError):
                time.sleep(0.05)
        self.stop()
        raise HttpTransportError("fixture server did not publish a port")

    def stop(self) -> None:
        process, self._process = self._process, None
        self._port = None
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=10)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    def reset(self) -> int:
        """Restart the fixture for fresh deterministic state."""
        return self.start()

    def exchange(self, request: HttpRequest) -> HttpExchange:
        if self._port is None:
            raise HttpTransportError("fixture server is not running")
        payload = None
        headers = {}
        if request.body is not None:
            payload = json.dumps(request.body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        started = time.monotonic()
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1", self._port, timeout=self._timeout_s)
            try:
                connection.request(request.method, request.path,
                                   body=payload, headers=headers)
                raw = connection.getresponse()
                text = raw.read(65536)
            finally:
                connection.close()
        except (OSError, http.client.HTTPException) as exc:
            raise HttpTransportError(
                "fixture transport failed: %s" % type(exc).__name__) from exc
        try:
            body = json.loads(text.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HttpTransportError("fixture answered unparseably") from exc
        if not isinstance(body, dict):
            raise HttpTransportError("fixture answered a non-object")
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        return HttpExchange(request=request,
                            response=HttpResponse(status=raw.status,
                                                  body=body),
                            duration_ms=duration_ms)

    def observe(self, actions: list[HttpRequest]) -> list[HttpExchange]:
        return [self.exchange(action) for action in actions]
