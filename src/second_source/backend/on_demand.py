"""Request-driven, exact-run invocation of the existing bounded NON_AI worker."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import threading
import time

from .cloud_artifacts import PRIVATE_ARTIFACT_NAMES
from .contracts import BackendError, Principal
from .worker import G3MockEngine, Worker


class OnDemandMockExecutor:
    def __init__(self, service, artifacts, *, record_artifact, engine_factory=G3MockEngine):
        self.service, self.artifacts = service, artifacts
        self.record_artifact, self.engine_factory = record_artifact, engine_factory
        self._slot = threading.BoundedSemaphore(1)

    def __call__(self, principal: Principal, run_id: str, expected_revision: int):
        run = self.service.get_run(principal, run_id)
        if run.status != "queued":
            return run  # Active/terminal/uncertain operations never replay.
        if run.revision != expected_revision:
            raise BackendError("REVISION_CONFLICT", "Resource revision changed")
        if not self._slot.acquire(blocking=False):
            raise BackendError("BUSY", "Execution capacity is occupied", 503)
        try:
            private = self.artifacts.for_worker(principal)
            deadline = time.monotonic() + 100
            with tempfile.TemporaryDirectory(prefix="second-source-worker-") as temporary:
                root = Path(temporary)
                publisher = self

                class DurableEngine:
                    def execute(self, lease, stage, cancelled):
                        def check_publication():
                            if time.monotonic() >= deadline:
                                raise BackendError("ARTIFACT_PUBLICATION_UNCERTAIN", "Publication deadline exceeded")
                            state = publisher.service.heartbeat(lease.run.run_id, lease.token)
                            if state.cancel_requested or cancelled():
                                raise BackendError("CANCELLED", "Run cancellation requested")

                        class FencedReports:
                            def publish_report(self, run_id, report):
                                check_publication()
                                return private.publish_report(run_id, report)

                        engine = publisher.engine_factory(root / "private", FencedReports(), timeout_seconds=90)
                        try:
                            result = engine.execute(lease, stage, cancelled)
                        except BackendError as error:
                            if error.code.startswith("CLOUD_STORAGE") or error.code == "ARTIFACT_INTEGRITY":
                                raise BackendError("ARTIFACT_PUBLICATION_UNCERTAIN",
                                                   "Artifact publication needs reconciliation") from None
                            raise
                        try:
                            directory = root / "private" / lease.run.run_id / "engine"
                            mandatory = PRIVATE_ARTIFACT_NAMES - {"G3_input_provenance.json"}
                            if result.stop_reason == "completed_mock_run" and any(
                                    not (directory / name).is_file() for name in mandatory):
                                raise ValueError("Required private archive is missing")
                            for name in sorted(PRIVATE_ARTIFACT_NAMES):
                                path = directory / name
                                if not path.exists():
                                    continue
                                if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
                                    raise ValueError
                                raw = path.read_bytes()
                                check_publication()
                                reference = private.retain_private(lease.run.run_id, name, raw,
                                    expected_sha256=hashlib.sha256(raw).hexdigest())
                                publisher.record_artifact(principal, lease.run.run_id, reference, lease_token=lease.token)
                            if result.report is not None:
                                publisher.record_artifact(principal, lease.run.run_id, result.report, lease_token=lease.token)
                        except Exception:
                            # Execution happened; an upload/metadata acknowledgement
                            # may be ambiguous. Quarantine, never regenerate/retry.
                            raise BackendError("ARTIFACT_PUBLICATION_UNCERTAIN",
                                               "Artifact publication needs reconciliation") from None
                        return result

                Worker(self.service, DurableEngine(), "on_demand_mock").once(run_id=run_id)
            return self.service.get_run(principal, run_id)
        finally:
            self._slot.release()
