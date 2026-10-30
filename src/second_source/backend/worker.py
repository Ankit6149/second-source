"""Bounded durable worker adapter for the EXISTING nonbillable G3 engine.

No paid adapter exists in this slice. Expired dispatches require reconciliation;
neither this worker nor the control plane automatically retries a job.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Callable, Protocol

from second_source.g2_persistence import scope_digest_of
from second_source.reconstruct import create_scope
from .artifacts import ArtifactStore, _safe_directory
from .contracts import BackendError, CodeStage, EngineResult, EvaluationSummary, Lease, UsageSummary
from .service import BackendService

LOG = logging.getLogger("second_source.backend.worker")
ROOT = Path(__file__).resolve().parents[3]


class Engine(Protocol):
    def execute(self, lease: Lease, stage: Callable[[CodeStage], None],
                cancelled: Callable[[], bool]) -> EngineResult: ...


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    # Kill the POSIX wrapper group, but independently sessioned staged workers
    # may outlive it until their existing resource/time bounds stop them.
    # Complete descendant cancellation is best effort on both platforms; this
    # is not an OS sandbox or a certified Job Object/process-tree boundary.
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.wait(timeout=10)


class G3MockEngine:
    """Only explicitly approved fixed owned-ledger scope; keys never inherited."""
    def __init__(self, data_root: str | Path, artifacts: ArtifactStore, *, timeout_seconds: float = 90):
        self.root = _safe_directory(Path(data_root).absolute())
        if self.root == ROOT or ROOT in self.root.parents:
            raise BackendError("UNSAFE_STORAGE", "Private engine storage must be outside the checkout", 422)
        if not 1 <= timeout_seconds <= 600:
            raise ValueError("Worker timeout must be between 1 and 600 seconds")
        self.artifacts = artifacts
        self.timeout_seconds = timeout_seconds

    def execute(self, lease: Lease, stage: Callable[[CodeStage], None],
                cancelled: Callable[[], bool]) -> EngineResult:
        if lease.run.kind != "g3_mock" or scope_digest_of(lease.scope) != scope_digest_of(create_scope(0)):
            raise BackendError("UNSUPPORTED_SCOPE", "Mock engine requires its exact published zero-cost scope", 422)
        # The control plane owns IDs, never a submitted command/path or shell.
        run_id = lease.run.run_id
        if len(run_id) != 36 or any(ch not in "0123456789abcdef-" for ch in run_id):
            raise BackendError("INVALID_ID", "Run identity is invalid", 422)
        work = self.root / run_id
        work.mkdir(mode=0o700, exist_ok=False)
        run_dir, seal_dir = work / "engine", work / "sealed"
        stdout_path, progress_path = work / "stdout.private.log", work / "progress.private.log"
        env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH") if k in os.environ}
        env.update(PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1", SECOND_SOURCE_MAX_RUN_USD="0")
        argv = [sys.executable, "-B", "-m", "second_source.reconstruct", "--mode", "mock",
            "--max-usd", "0", "--run-dir", str(run_dir), "--seal-dir", str(seal_dir)]
        stage(CodeStage.CAPTURE)
        if cancelled():
            raise BackendError("CANCELLED", "Run cancellation requested")
        started, offset = time.monotonic(), 0
        remaining = b""
        stage_map = {"evidence_ready": CodeStage.ORGANIZE, "inspected": CodeStage.DISTILL,
                     "admitted": CodeStage.EXECUTE}
        with stdout_path.open("xb") as stdout, progress_path.open("xb") as stderr:
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                start_new_session=os.name == "posix", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                while True:
                    if cancelled():
                        raise BackendError("CANCELLED", "Run cancellation requested")
                    if time.monotonic() - started > min(self.timeout_seconds, lease.scope.budgets.max_wall_seconds):
                        raise BackendError("ENGINE_TIMEOUT", "Engine execution exceeded its time limit")
                    if stdout_path.stat().st_size > 1_000_000 or progress_path.stat().st_size > 1_000_000:
                        raise BackendError("ENGINE_OUTPUT_LIMIT", "Engine output exceeded its size limit")
                    with progress_path.open("rb") as stream:
                        stream.seek(offset)
                        chunk = stream.read(1_000_001)
                        offset += len(chunk)
                    lines = (remaining + chunk).split(b"\n")
                    remaining = lines.pop()
                    for line in lines:
                        try:
                            event = json.loads(line)
                        except (ValueError, UnicodeError):
                            continue  # Private unexpected stderr is not an API event.
                        if event.get("run_id") == run_id or event.get("run_id") == "engine":
                            if event.get("progress") in stage_map:
                                stage(stage_map[event["progress"]])
                    if process.poll() is not None:
                        break
                    time.sleep(.05)
                report_path = run_dir / "G3_report.json"
                if not report_path.is_file() or report_path.stat().st_size > 2_000_000:
                    raise BackendError("ENGINE_REPORT_MISSING", "Engine did not publish a supported report")
                report = json.loads(report_path.read_bytes())
                reference = self.artifacts.publish_report(run_id, report)
                evaluation = report.get("evaluation")
                summary = EvaluationSummary.model_validate({k: evaluation[k] for k in ("passed", "failed", "indeterminate", "total")}) if evaluation else None
                if process.returncode != 0 and report.get("stop_reason") == "completed_mock_run":
                    raise BackendError("ENGINE_FAILED", "Engine exit and report disagree")
                return EngineResult(stop_reason=report["stop_reason"], usage=UsageSummary.model_validate(report["usage"]),
                    evaluation=summary, report=reference)
            finally:
                _terminate(process)


class Worker:
    def __init__(self, service: BackendService, engine: Engine, worker_id: str, *, lease_seconds: float = 30):
        self.service, self.engine, self.worker_id = service, engine, worker_id
        self.lease_seconds = lease_seconds
        self.stopping = False

    def stop(self) -> None:
        self.stopping = True

    def once(self, *, run_id: str | None = None) -> bool:
        if self.stopping:
            return False
        if run_id is None:
            lease = self.service.claim(self.worker_id, lease_seconds=self.lease_seconds)
        else:
            lease = self.service.claim(self.worker_id, lease_seconds=self.lease_seconds, run_id=run_id)
        if lease is None:
            return False
        last_heartbeat = 0.0
        def cancelled() -> bool:
            nonlocal last_heartbeat
            if self.stopping:
                return True
            if time.monotonic() - last_heartbeat >= min(1.0, self.lease_seconds / 3):
                run = self.service.heartbeat(lease.run.run_id, lease.token, lease_seconds=self.lease_seconds)
                last_heartbeat = time.monotonic()
                return run.cancel_requested
            # Poll cancellation at every callback; ownership comes from current lease.
            run = self.service.get_run_by_lease(lease.run.run_id, lease.token) if hasattr(self.service, "get_run_by_lease") else None
            return bool(run and run.cancel_requested)
        try:
            result = self.engine.execute(lease, lambda stage: self.service.stage(lease.run.run_id, lease.token, stage), cancelled)
            code = {"completed_mock_run": "RUN_COMPLETED", "broker_failed": "BROKER_FAILED",
                "evaluation_failed": "EVALUATION_FAILED", "interrupted_stopped": "CANCELLED"}.get(result.stop_reason, "ENGINE_FAILED")
            self.service.finish(lease.run.run_id, lease.token, result,
                error_code=None if code == "RUN_COMPLETED" else code)
        except BackendError as exc:
            code = exc.code
            # A stale worker must not overwrite recovery/new state.
            try:
                self.service.finish(lease.run.run_id, lease.token, None, error_code=code)
            except BackendError:
                pass
        except Exception:
            code = "ENGINE_INTERNAL_ERROR"
            try:
                self.service.finish(lease.run.run_id, lease.token, None, error_code=code)
            except BackendError:
                pass
        LOG.info(json.dumps({"event": code, "run_id": lease.run.run_id, "worker_id": self.worker_id}))
        return True
