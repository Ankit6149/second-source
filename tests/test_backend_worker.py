"""Integrated NON_AI service -> leased worker -> existing sealed G3 -> proof bundle."""
import io
import json
import hashlib
import subprocess
import uuid
import zipfile

import pytest

from second_source.backend.artifacts import ArtifactStore, sanitized_report, verify_bundle
from second_source.backend.contracts import (
    AuthorizeInvestigation, BackendError, CodeStage, CreateInvestigation, CreateRun,
    EngineResult, EvaluationSummary, Principal,
)
from second_source.backend.service import BackendService
from second_source.backend.worker import G3MockEngine, Worker
from second_source.reconstruct import create_scope

OWNER = Principal(owner_id="test_owner")


def prepared(tmp_path, scope=None):
    service = BackendService(tmp_path / "state.sqlite")
    item = service.create_investigation(OWNER, CreateInvestigation(title="NON_AI acceptance",
        scope=scope or create_scope(0)), "investigation")
    item = service.authorize_investigation(OWNER, item.investigation_id,
        AuthorizeInvestigation(expected_revision=item.revision, scope_digest=item.scope_digest))
    run = service.create_run(OWNER, item.investigation_id, CreateRun(), "run")
    return service, item, run


def report():
    return {"origin": "mock", "real": False, "stop_reason": "completed_mock_run",
        "usage": {"attempts": 1}, "evaluation": {"passed": 22, "failed": 3, "indeterminate": 0, "total": 25},
        "scope_digest": "a" * 64, "suite_digest": "sha256:" + "b" * 64,
        "private_path": "C:/PRIVATE_SENTINEL", "response_text": "MODEL_SECRET_SENTINEL",
        "evaluation_receipt": {"cases": ["SEALED_SENTINEL"]}}


def test_service_worker_existing_g3_and_independently_verified_export(tmp_path, monkeypatch):
    service, item, queued = prepared(tmp_path)
    artifacts = ArtifactStore(tmp_path / "reports")
    # A fixture value tests environment isolation, not a real credential operation.
    monkeypatch.setenv("MODEL_API_KEY", "NONCREDENTIAL_SENTINEL_MUST_NOT_REACH_CHILD")
    real_popen = subprocess.Popen
    def checked_popen(*args, **kwargs):
        assert "MODEL_API_KEY" not in kwargs["env"] and "META_API_KEY" not in kwargs["env"]
        assert kwargs["env"]["SECOND_SOURCE_MAX_RUN_USD"] == "0"
        assert "--mode" in args[0] and "real" not in args[0]
        return real_popen(*args, **kwargs)
    monkeypatch.setattr("second_source.backend.worker.subprocess.Popen", checked_popen)
    engine = G3MockEngine(tmp_path / "private", artifacts)
    worker = Worker(service, engine, "acceptance_worker")
    assert worker.once() is True and worker.once() is False
    completed = service.get_run(OWNER, queued.run_id)
    assert completed.status == "completed" and completed.stage == "execute"
    assert completed.result.origin == "mock" and completed.result.real is False
    assert completed.result.evaluation == EvaluationSummary(passed=22, failed=3, indeterminate=0, total=25)
    assert completed.result.usage.estimated_cost_usd == completed.result.usage.uncertain_cost_usd == 0
    events = service.events(OWNER, item.investigation_id)
    assert [e.stage for e in events if e.event_type == "stage_started"] == list(CodeStage)
    archive = artifacts.export_bundle(item, completed, events)
    assert verify_bundle(archive)["valid"] is True
    assert verify_bundle(archive)["origin"] == "mock" and verify_bundle(archive)["attests_provider"] is False
    assert archive == artifacts.export_bundle(item, completed, events)
    assert b"NONCREDENTIAL_SENTINEL" not in archive and str(tmp_path).encode() not in archive
    # Original candidate and sealed bytes remain private for controlled offline use.
    assert (tmp_path / "private" / queued.run_id / "engine" / "candidate.v1.json").is_file()
    assert (tmp_path / "private" / queued.run_id / "sealed" / "suite.json").is_file()
    restarted = BackendService(tmp_path / "state.sqlite")
    assert restarted.get_run(OWNER, queued.run_id) == completed
    assert restarted.claim("restart") is None


def test_unsupported_scope_never_executes_or_widens_permissions(tmp_path, monkeypatch):
    scope = create_scope(0).model_copy(update={"goal": "A different, unauthorized engine scope"})
    service, _, queued = prepared(tmp_path, scope)
    monkeypatch.setattr("second_source.backend.worker.subprocess.Popen", lambda *a, **kw: pytest.fail("scope bypass"))
    assert Worker(service, G3MockEngine(tmp_path / "private", ArtifactStore(tmp_path / "reports")), "w").once()
    result = service.get_run(OWNER, queued.run_id)
    assert result.status == "failed" and result.error_code == "UNSUPPORTED_SCOPE"


def test_running_cancel_prevents_success_and_does_not_requeue(tmp_path):
    service, _, queued = prepared(tmp_path)
    class CancelEngine:
        def execute(self, lease, stage, cancelled):
            stage(CodeStage.CAPTURE)
            current = service.get_run(OWNER, queued.run_id)
            service.cancel_run(OWNER, queued.run_id, current.revision)
            assert cancelled()
            raise BackendError("CANCELLED", "Run cancellation requested")
    assert Worker(service, CancelEngine(), "w").once()
    assert service.get_run(OWNER, queued.run_id).status == "cancelled"
    assert service.claim("later") is None


def test_worker_failure_sanitizes_untrusted_exception(tmp_path, caplog):
    service, _, queued = prepared(tmp_path)
    class BrokenEngine:
        def execute(self, *args):
            raise RuntimeError("PRIVATE_PATH_AND_TOKEN_SENTINEL")
    assert Worker(service, BrokenEngine(), "w").once()
    failed = service.get_run(OWNER, queued.run_id)
    assert failed.error_code == "ENGINE_INTERNAL_ERROR" and failed.result is None
    assert "PRIVATE_PATH_AND_TOKEN_SENTINEL" not in caplog.text


def test_sanitized_report_and_bundle_reject_corruption_and_path_members(tmp_path):
    service, item, queued = prepared(tmp_path)
    artifacts = ArtifactStore(tmp_path / "reports")
    reference = artifacts.publish_report(queued.run_id, report())
    public = artifacts.read(queued.run_id, reference)
    assert b"SENTINEL" not in public and b"PRIVATE" not in public
    with pytest.raises(FileExistsError):
        artifacts.publish_report(queued.run_id, report())
    lease = service.claim("worker")
    for stage in CodeStage:
        service.stage(queued.run_id, lease.token, stage)
    finished = service.finish(queued.run_id, lease.token,
        EngineResult(stop_reason="completed_mock_run", report=reference,
            usage=report()["usage"], evaluation=report()["evaluation"]))
    bundle = artifacts.export_bundle(item, finished, service.events(OWNER, item.investigation_id))
    assert verify_bundle(bundle)["valid"]
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle)) as source, zipfile.ZipFile(output, "w") as changed:
        for name in source.namelist():
            changed.writestr(name, b"{}" if name == "report.json" else source.read(name))
    with pytest.raises(BackendError, match="integrity"):
        verify_bundle(output.getvalue())
    # Even internally consistent hashes cannot turn malformed report shape into
    # a valid sanitized proof or expose a traceback from independent verification.
    with zipfile.ZipFile(io.BytesIO(bundle)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    files["report.json"] = b"[]"
    proof_run = json.loads(files["run.json"])
    proof_run["result"]["report"].update(sha256=hashlib.sha256(b"[]").hexdigest(), size_bytes=2)
    files["run.json"] = json.dumps(proof_run).encode()
    manifest = json.loads(files["manifest.json"])
    for name in manifest["files"]:
        manifest["files"][name] = {"sha256": hashlib.sha256(files[name]).hexdigest(), "size_bytes": len(files[name])}
    files["manifest.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as changed:
        for name, content in files.items():
            changed.writestr(name, content)
    with pytest.raises(BackendError, match="integrity"):
        verify_bundle(output.getvalue())
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as changed:
        changed.writestr("../report.json", b"{}")
    with pytest.raises(BackendError):
        verify_bundle(output.getvalue())
    (tmp_path / "reports" / queued.run_id / "report.json").write_bytes(b"{}")
    with pytest.raises(BackendError, match="integrity"):
        artifacts.read(queued.run_id, reference)


def test_real_or_paid_report_cannot_be_relabelled_mock():
    with pytest.raises(BackendError):
        sanitized_report({**report(), "origin": "real", "real": True})
    with pytest.raises(BackendError):
        sanitized_report({**report(), "usage": {"estimated_cost_usd": .01}})
    with pytest.raises(ValueError):
        EvaluationSummary(passed=25, failed=3, indeterminate=0, total=25)


def test_artifact_paths_reject_traversal_and_linked_storage(tmp_path):
    store = ArtifactStore(tmp_path / "safe")
    with pytest.raises(BackendError):
        store.publish_report("../outside", report())
    run_id = str(uuid.uuid4())
    target = tmp_path / "elsewhere"
    target.mkdir()
    try:
        (store.root / run_id).symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Local account lacks directory symlink privilege")
    with pytest.raises(BackendError):
        store.publish_report(run_id, report())
