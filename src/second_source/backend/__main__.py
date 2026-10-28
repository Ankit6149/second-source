"""Local modular backend entry point. Real inference and deployment stay disabled."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import signal
import sys
import time

from second_source.reconstruct import create_scope
from .artifacts import ArtifactStore, verify_bundle
from .contracts import AuthorizeInvestigation, BackendError, CreateInvestigation, CreateRun, Principal
from .service import BackendService
from .worker import G3MockEngine, ROOT, Worker
from .paths import checked_regular_file, reject_links


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="Private durable local directory outside the checkout")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    smoke = commands.add_parser("mock", help="One authorized NON_AI owned-ledger workflow; no credentials")
    smoke.add_argument("--owner", default="local_operator")
    smoke.add_argument("--idempotency-key", default="local-mock-smoke")
    status = commands.add_parser("status")
    status.add_argument("--owner", default="local_operator")
    status.add_argument("--run-id", required=True)
    worker_parser = commands.add_parser("worker")
    worker_parser.add_argument("--once", action="store_true")
    worker_parser.add_argument("--worker-id", default="local_worker")
    server = commands.add_parser("serve", help="Local loopback API; no inference in HTTP process")
    server.add_argument("--token-hashes", type=Path, required=True, help="JSON mapping SHA256 bearer digests to owner IDs; never plaintext keys")
    server.add_argument("--port", type=int, default=8000, choices=range(1024, 65536), metavar="1024..65535")
    verify = commands.add_parser("verify-bundle")
    verify.add_argument("bundle", type=Path)
    verify.add_argument("--expected-sha256", help="Externally retained bundle SHA256 witness")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        reject_links(args.data_dir.absolute())
        data = args.data_dir.absolute().resolve()
        if data == ROOT or ROOT in data.parents:
            raise BackendError("UNSAFE_STORAGE", "Private durable storage must be outside the checkout", 422)
        if args.command == "verify-bundle":
            if args.bundle.stat().st_size > 8_000_000:
                raise BackendError("INVALID_BUNDLE", "Proof bundle exceeds supported size", 422)
            print(json.dumps(verify_bundle(args.bundle.read_bytes(), expected_sha256=args.expected_sha256)))
            return 0
        service = BackendService(data / "state.sqlite")
        artifacts = ArtifactStore(data / "public_reports")
        if args.command == "init":
            print(json.dumps({"schema_version": service.store.SCHEMA_VERSION, "ready": service.readiness(),
                "real_inference_enabled": False, "paid_authorization_enabled": False}))
            return 0
        if args.command == "status":
            print(service.get_run(Principal(owner_id=args.owner), args.run_id).model_dump_json())
            return 0
        if args.command == "serve":
            checked_regular_file(args.token_hashes.absolute())
            if args.token_hashes.stat().st_size > 65_536:
                raise BackendError("INVALID_CONFIG", "Token hash configuration is invalid", 422)
            token_hashes = json.loads(args.token_hashes.read_bytes())
            from .api import create_app
            import uvicorn
            app = create_app(service, token_hashes=token_hashes, artifact_store=artifacts)
            uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1,
                access_log=False, timeout_keep_alive=5, limit_concurrency=32, limit_max_requests=100_000)
            return 0
        engine = G3MockEngine(data / "private_engine", artifacts)
        worker = Worker(service, engine, getattr(args, "worker_id", "local_smoke"))
        # Signal handlers request cancellation; no new task is claimed afterward.
        old_handlers = {}
        def stopping(signum, frame):
            worker.stop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, stopping)
        try:
            if args.command == "mock":
                principal = Principal(owner_id=args.owner)
                inv = service.create_investigation(principal, CreateInvestigation(title="NON_AI local backend acceptance", scope=create_scope(0)), args.idempotency_key + ":investigation")
                if inv.status == "created":
                    inv = service.authorize_investigation(principal, inv.investigation_id,
                        AuthorizeInvestigation(expected_revision=inv.revision, scope_digest=inv.scope_digest))
                queued = service.create_run(principal, inv.investigation_id, CreateRun(), args.idempotency_key + ":run")
                if queued.status == "queued":
                    worker.once()
                run = service.get_run(principal, queued.run_id)
                print(run.model_dump_json())
                return 0 if run.status == "completed" else 1
            recovered = service.recover_expired()
            print(json.dumps({"event": "WORKER_READY", "reconciliation_required": recovered, "real": False}), flush=True)
            while not worker.stopping:
                did_work = worker.once()
                if args.once:
                    break
                if not did_work:
                    time.sleep(.5)
            return 0
        finally:
            for signum, handler in old_handlers.items():
                signal.signal(signum, handler)
    except BackendError as exc:
        print(json.dumps({"code": exc.code, "message": exc.message}), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError):
        print(json.dumps({"code": "INVALID_CONFIG_OR_STORAGE", "message": "Backend configuration or storage is unavailable"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
