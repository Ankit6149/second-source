"""Test-only loopback server using synthetic identities and fake Storage.

Runs the actual API and NON_AI worker; it never accesses cloud credentials.
"""
import socket
import sys
import tempfile
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

from test_backend_cloud_app import FakeStorage, LocalAcceptanceStore, config, identity
from second_source.backend.asgi import build_cloud_app
from second_source.model_gateway import MetaProvider


def forbidden(*args, **kwargs):
    raise AssertionError("Model provider transport is forbidden in this test")


MetaProvider.complete = forbidden
with tempfile.TemporaryDirectory(prefix="ss-client-integration-") as directory:
    app = build_cloud_app(config(), store=LocalAcceptanceStore(Path(directory) / "state.sqlite"),
                          transport=FakeStorage(), identity=identity)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    print(f"PORT={listener.getsockname()[1]}", flush=True)
    uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off")).run(sockets=[listener])
