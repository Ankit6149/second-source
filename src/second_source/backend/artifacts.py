"""Private immutable report storage and checksum-verifiable sanitized proof exports.

Exports are integrity packages, not provider signatures or sealed-suite exports.
Raw reports, hypotheses, private paths and model content are never copied to them.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import re
import stat
import zipfile

from second_source.evidence import publish_once
from second_source.g2_persistence import canonical
from .contracts import (
    ArtifactReference, BackendError, CodeStage, EngineResult, EvaluationSummary,
    Investigation, LifecycleEvent, Run, RunStatus, UsageSummary,
)
from .paths import safe_directory as _safe_directory

_ID = re.compile(r"^[a-f0-9-]{36}$")
_DIGEST = re.compile(r"^(sha256:)?[a-f0-9]{64}$")
_MAX_BYTES = 2_000_000


def sanitized_report(report: dict) -> dict:
    """Build a typed allowlist; never recursively copy untrusted report fields."""
    if report.get("origin") != "mock" or report.get("real") is not False:
        raise BackendError("UNSUPPORTED_ORIGIN", "Only nonbillable mock reports are supported", 422)
    reason = report.get("stop_reason")
    if reason not in {"completed_mock_run", "broker_failed", "evaluation_failed", "interrupted_stopped"}:
        raise BackendError("INVALID_REPORT", "Engine report is invalid", 422)
    usage = UsageSummary.model_validate(report.get("usage", {}))
    if usage.estimated_cost_usd or usage.uncertain_cost_usd:
        raise BackendError("UNSUPPORTED_ORIGIN", "Mock engine reported nonzero spend", 422)
    evaluation = None
    if report.get("evaluation") is not None:
        raw = report["evaluation"]
        evaluation = EvaluationSummary.model_validate({k: raw[k] for k in ("passed", "failed", "indeterminate", "total")})
    value = {"schema_version": "1", "kind": "SANITIZED_G3_REPORT", "origin": "mock", "real": False,
        "stop_reason": reason, "usage": usage.model_dump(mode="json"),
        "evaluation": evaluation.model_dump(mode="json") if evaluation else None,
        "claim": "NON_AI plumbing evidence; not model reconstruction quality"}
    for key in ("suite_digest", "scope_digest", "approved_context_digest", "spec_digest", "plan_digest"):
        val = report.get(key)
        if isinstance(val, str) and _DIGEST.fullmatch(val):
            value[key] = val
    return value


class ArtifactStore:
    def __init__(self, root: str | Path):
        self.root = _safe_directory(Path(root).absolute())

    def _path(self, run_id: str) -> Path:
        if not _ID.fullmatch(run_id):
            raise BackendError("INVALID_ID", "Run identity is invalid", 422)
        directory = _safe_directory(self.root / run_id)
        path = directory / "report.json"
        if path.exists():
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise BackendError("UNSAFE_ARTIFACT", "Artifact path is unsafe", 409)
        return path

    def publish_report(self, run_id: str, report: dict) -> ArtifactReference:
        raw = canonical(sanitized_report(report))
        if len(raw) > _MAX_BYTES:
            raise BackendError("ARTIFACT_TOO_LARGE", "Artifact exceeds supported size", 422)
        publish_once(self._path(run_id), raw)
        return ArtifactReference(artifact_id="report", sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw), media_type="application/json")

    def read(self, run_id: str, reference: ArtifactReference) -> bytes:
        if reference.artifact_id != "report":
            raise BackendError("NOT_FOUND", "Artifact not found", 404)
        path = self._path(run_id)
        if not path.exists():
            raise BackendError("NOT_FOUND", "Artifact not found", 404)
        if path.stat().st_size > _MAX_BYTES:
            raise BackendError("ARTIFACT_INTEGRITY", "Artifact integrity check failed", 409)
        raw = path.read_bytes()
        if len(raw) != reference.size_bytes or hashlib.sha256(raw).hexdigest() != reference.sha256:
            raise BackendError("ARTIFACT_INTEGRITY", "Artifact integrity check failed", 409)
        return raw

    def export_bundle(self, investigation: Investigation, run: Run, events: list[LifecycleEvent]) -> bytes:
        if run.investigation_id != investigation.investigation_id or not run.result or not run.result.report:
            raise BackendError("REPORT_UNAVAILABLE", "Verified report is not available", 409)
        if len(events) > 1000 or any(e.investigation_id != investigation.investigation_id for e in events):
            raise BackendError("EXPORT_LIMIT", "Export event scope or size is invalid", 409)
        # Do not export owner identifiers, arbitrary titles/goals, scope permissions,
        # exception text, input/model bodies, private artifact paths or gold cases.
        files = {
            "report.json": self.read(run.run_id, run.result.report),
            "run.json": canonical({"schema_version": "1", "run_id": run.run_id,
                "investigation_id": run.investigation_id, "scope_digest": investigation.scope_digest,
                "status": run.status.value, "stage": run.stage.value if run.stage else None,
                "revision": run.revision, "created_at": run.created_at, "updated_at": run.updated_at,
                "result": run.result.model_dump(mode="json")}),
            "events.json": canonical([e.model_dump(mode="json") for e in events if e.run_id in (None, run.run_id)]),
        }
        manifest = {"schema_version": "1", "kind": "SECOND_SOURCE_SANITIZED_PROOF",
            "claim": "Checksum integrity only; not provider attestation or real reconstruction",
            "files": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)} for name, raw in files.items()}}
        files["manifest.json"] = canonical(manifest)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, raw in sorted(files.items()):
                archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), raw)
        return stream.getvalue()


def verify_bundle(raw: bytes, expected_sha256: str | None = None) -> dict:
    """Bounded in-memory verification, no extraction or execution of bundle bytes."""
    if len(raw) > 4 * _MAX_BYTES:
        raise BackendError("INVALID_BUNDLE", "Proof bundle is invalid", 422)
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise BackendError("INVALID_BUNDLE", "Proof bundle does not match the external witness", 422)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if sorted(names) != ["events.json", "manifest.json", "report.json", "run.json"]:
                raise ValueError
            if any(i.file_size > _MAX_BYTES or i.compress_type != zipfile.ZIP_STORED for i in archive.infolist()):
                raise ValueError
            manifest = json.loads(archive.read("manifest.json"))
            if manifest["schema_version"] != "1" or manifest["kind"] != "SECOND_SOURCE_SANITIZED_PROOF" or set(manifest["files"]) != set(names) - {"manifest.json"}:
                raise ValueError
            for name, witness in manifest["files"].items():
                content = archive.read(name)
                if len(content) != witness["size_bytes"] or hashlib.sha256(content).hexdigest() != witness["sha256"]:
                    raise ValueError
            result = json.loads(archive.read("run.json"))
            if not isinstance(result, dict) or set(result) != {"schema_version", "run_id", "investigation_id", "scope_digest", "status", "stage", "revision", "created_at", "updated_at", "result"}:
                raise ValueError
            if result["schema_version"] != "1" or not _ID.fullmatch(result["run_id"]) or not _ID.fullmatch(result["investigation_id"]) or not _DIGEST.fullmatch(result["scope_digest"]):
                raise ValueError
            RunStatus(result["status"])
            if result["stage"] is not None:
                CodeStage(result["stage"])
            typed = EngineResult.model_validate(result["result"])
            report = archive.read("report.json")
            if typed.report is None or typed.report.artifact_id != "report" or typed.report.media_type != "application/json" or typed.report.sha256 != hashlib.sha256(report).hexdigest() or typed.report.size_bytes != len(report):
                raise ValueError
            sanitized = json.loads(report)
            if not isinstance(sanitized, dict) or canonical(sanitized_report(sanitized)) != canonical(sanitized):
                raise ValueError
            if sanitized.get("usage") != typed.usage.model_dump(mode="json") or sanitized.get("stop_reason") != typed.stop_reason or sanitized.get("evaluation") != (typed.evaluation.model_dump(mode="json") if typed.evaluation else None):
                raise ValueError
            events = json.loads(archive.read("events.json"))
            if not isinstance(events, list) or len(events) > 1000:
                raise ValueError
            previous_id = -1
            for raw_event in events:
                event = LifecycleEvent.model_validate(raw_event)
                if event.investigation_id != result["investigation_id"] or event.run_id not in (None, result["run_id"]) or event.event_id <= previous_id:
                    raise ValueError
                previous_id = event.event_id
            return {"valid": True, "schema_version": "1", "file_count": 3,
                "bundle_sha256": hashlib.sha256(raw).hexdigest(), "origin": "mock",
                "attests_provider": False}
    except (ValueError, KeyError, TypeError, AttributeError, BackendError, zipfile.BadZipFile, RuntimeError):
        raise BackendError("INVALID_BUNDLE", "Proof bundle integrity check failed", 422) from None
