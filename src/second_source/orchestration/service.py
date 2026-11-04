"""Orchestration service: NL instruction -> durable job, cancel/retry, guard."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, re, secrets, time, uuid
from pathlib import Path
from second_source.g2_persistence import canonical, scope_digest_of
from second_source.backend.contracts import BackendError, Principal
from .guard import SpendingGuard, SpendPacketV1
from .registry import TargetRegistry, default_registry
from .schemas import (
    ArtifactListItemV1, ArtifactRefV1, AuthorizeInvestigationV1, CandidateRouteV1,
    CandidateV1, CreateInvestigationV1, ExportV1, InvestigationV1, JobStage,
    JobStatus, JobV1, OrchestrationEventV1, ReportV1, VerificationV1, WorkspaceV1,
)
from .store import OrchestrationStore

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _err(code, msg, status=409):
    raise BackendError(code, msg, status)

class OrchestrationService:
    def __init__(self, database_path=None, *, store=None, registry=None, guard=None):
        if store is None:
            if database_path is None:
                raise ValueError("A durable database path is required")
            self.store = OrchestrationStore(database_path)
        else:
            self.store = store
        self.registry: TargetRegistry = registry or default_registry()
        self.guard: SpendingGuard = guard or SpendingGuard()

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _inv(row) -> InvestigationV1:
        d = {k: row[k] for k in ("investigation_id","owner_id","title","instruction",
             "target_id","scope_digest","status","revision","created_at","updated_at")}
        d["scope"] = json.loads(row["scope_json"])
        return InvestigationV1.model_validate(d)

    @staticmethod
    def _job(row) -> JobV1:
        d = {k: row[k] for k in ("job_id","investigation_id","kind","status","stage",
             "attempt","revision","created_at","updated_at","error_code","result_report_id")}
        d["cancel_requested"] = bool(row["cancel_requested"])
        return JobV1.model_validate(d)

    @staticmethod
    def _event(c, inv, job, typ, rev, stage=None, *, status="COMPLETED",
               artifact_refs=(), detail=None):
        c.execute("INSERT INTO orch_events(investigation_id,job_id,event_type,stage,revision,created_at,status,provenance,artifact_refs,detail) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (inv, job, typ, stage, rev, _now(), status, "NON_AI",
                   json.dumps(list(artifact_refs)), detail))

    def _owned(self, c, principal, inv_id):
        r = c.execute("SELECT * FROM orch_investigations WHERE investigation_id=? AND owner_id=?",
                      (inv_id, principal.owner_id)).fetchone()
        if r is None:
            _err("NOT_FOUND", "Resource not found", 404)
        return r

    def _owned_job(self, c, principal, job_id):
        r = c.execute("SELECT j.* FROM orch_jobs j JOIN orch_investigations i USING(investigation_id) WHERE j.job_id=? AND i.owner_id=?",
                      (job_id, principal.owner_id)).fetchone()
        if r is None:
            _err("NOT_FOUND", "Resource not found", 404)
        return r

    # -- investigations (NL instruction entry point) ----------------------
    def create_investigation(self, principal: Principal, req: CreateInvestigationV1,
                             idempotency_key: str) -> InvestigationV1:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", idempotency_key or ""):
            _err("INVALID_IDEMPOTENCY_KEY", "A bounded idempotency key is required", 422)
        self.registry.get(req.target_id)  # registered target required
        body = req.model_dump(mode="python")
        digest = hashlib.sha256(canonical(body)).hexdigest()
        with self.store.transaction() as c:
            old = c.execute("SELECT * FROM orch_idempotency WHERE owner_id=? AND operation=? AND key=?",
                            (principal.owner_id, "orch_create", idempotency_key)).fetchone()
            if old:
                if old["request_digest"] != digest:
                    _err("IDEMPOTENCY_CONFLICT", "Idempotency key already binds a different request")
                return self._inv(self._owned(c, principal, old["resource_id"]))
            inv_id, now = str(uuid.uuid4()), _now()
            sd = scope_digest_of(req.scope).removeprefix("sha256:")
            # NL instruction is persisted verbatim; this proves API->backend reach.
            c.execute("INSERT INTO orch_investigations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (inv_id, principal.owner_id, req.title, req.instruction, req.target_id,
                       canonical(req.scope.model_dump(mode="python")).decode(), sd, "created", 1, now, now))
            c.execute("INSERT INTO orch_idempotency VALUES(?,?,?,?,?)",
                      (principal.owner_id, "orch_create", idempotency_key, digest, inv_id))
            self._event(c, inv_id, None, "investigation_created", 1)
            return self._inv(self._owned(c, principal, inv_id))

    def get_investigation(self, principal, investigation_id) -> InvestigationV1:
        with self.store.transaction() as c:
            return self._inv(self._owned(c, principal, investigation_id))

    def authorize(self, principal, investigation_id, req: AuthorizeInvestigationV1) -> InvestigationV1:
        with self.store.transaction() as c:
            row = self._owned(c, principal, investigation_id)
            if row["revision"] != req.expected_revision:
                _err("REVISION_CONFLICT", "Resource revision changed")
            if row["status"] != "created":
                _err("INVALID_STATE", "Investigation is already authorized")
            scope = json.loads(row["scope_json"])
            self.registry.assert_authorized(row["target_id"], _scope(scope), req.scope_digest)
            if req.scope_digest != row["scope_digest"]:
                _err("SCOPE_MISMATCH", "Approval does not match the immutable scope")
            # Spending guard: Gate A authorizes mock/$0 only.
            self.guard.check(None, estimated_usd=float(req.maximum_model_spend_usd),
                             investigation_id=investigation_id)
            c.execute("UPDATE orch_investigations SET status='authorized',revision=revision+1,updated_at=? WHERE investigation_id=?",
                      (_now(), investigation_id))
            self._event(c, investigation_id, None, "investigation_authorized_mock_only", row["revision"] + 1)
            return self._inv(self._owned(c, principal, investigation_id))

    # -- jobs --------------------------------------------------------------
    def enqueue(self, principal, investigation_id, idempotency_key: str) -> JobV1:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", idempotency_key or ""):
            _err("INVALID_IDEMPOTENCY_KEY", "A bounded idempotency key is required", 422)
        with self.store.transaction() as c:
            inv = self._owned(c, principal, investigation_id)
            if inv["status"] != "authorized":
                _err("APPROVAL_REQUIRED", "Mock-only scope approval is required")
            existing = c.execute("SELECT * FROM orch_jobs WHERE investigation_id=? AND idempotency_key=?",
                                 (investigation_id, idempotency_key)).fetchone()
            if existing:
                return self._job(existing)  # retry without duplication
            job_id, now = str(uuid.uuid4()), _now()
            c.execute("INSERT INTO orch_jobs(job_id,investigation_id,status,attempt,revision,created_at,updated_at,idempotency_key) VALUES(?,?,?,?,?,?,?,?)",
                      (job_id, investigation_id, "queued", 1, 1, now, now, idempotency_key))
            self._event(c, investigation_id, job_id, "job_queued", 1, status="RUNNING")
            return self._job(self._owned_job(c, principal, job_id))

    def get_job(self, principal, job_id) -> JobV1:
        with self.store.transaction() as c:
            return self._job(self._owned_job(c, principal, job_id))

    def list_events(self, principal, investigation_id, after=0, limit=100):
        with self.store.transaction() as c:
            self._owned(c, principal, investigation_id)
            rows = c.execute("SELECT * FROM orch_events WHERE investigation_id=? AND event_id>? ORDER BY event_id LIMIT ?",
                             (investigation_id, after, limit)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["artifact_refs"] = tuple(json.loads(d.get("artifact_refs") or "[]"))
                out.append(OrchestrationEventV1.model_validate(d))
            return out

    def claim(self, worker_id: str, lease_seconds: float = 30, job_id: str | None = None):
        with self.store.transaction() as c:
            q = "SELECT * FROM orch_jobs WHERE status='queued'"
            args: tuple = ()
            if job_id:
                q += " AND job_id=?"
                args = (job_id,)
            row = c.execute(q + " ORDER BY created_at,job_id LIMIT 1", args).fetchone()
            if row is None:
                return None
            token, exp = secrets.token_hex(32), time.time() + lease_seconds
            c.execute("UPDATE orch_jobs SET status='running',worker_id=?,lease_token=?,lease_expires=?,revision=revision+1,updated_at=? WHERE job_id=?",
                      (worker_id, token, exp, _now(), row["job_id"]))
            self._event(c, row["investigation_id"], row["job_id"], "job_claimed", row["revision"] + 1, status="RUNNING")
            fresh = c.execute("SELECT * FROM orch_jobs WHERE job_id=?", (row["job_id"],)).fetchone()
            return self._job(fresh), token

    def cancel(self, principal, job_id, expected_revision: int) -> JobV1:
        with self.store.transaction() as c:
            row = self._owned_job(c, principal, job_id)
            if row["revision"] != expected_revision:
                _err("REVISION_CONFLICT", "Resource revision changed")
            if row["status"] not in ("queued", "running") or row["cancel_requested"]:
                _err("INVALID_STATE", "Job cannot be cancelled in this state")
            status = "cancelled" if row["status"] == "queued" else "running"
            c.execute("UPDATE orch_jobs SET status=?,cancel_requested=1,revision=revision+1,updated_at=? WHERE job_id=?",
                      (status, _now(), job_id))
            self._event(c, row["investigation_id"], job_id,
                        "job_cancelled" if status == "cancelled" else "job_cancellation_requested",
                        row["revision"] + 1, row["stage"],
                        status="CANCELLED" if status == "cancelled" else "RUNNING")
            return self._job(self._owned_job(c, principal, job_id))

    def retry(self, principal, job_id, expected_revision: int) -> JobV1:
        """Retry a failed/cancelled job in place (same job_id, attempt+1); never duplicates."""
        with self.store.transaction() as c:
            row = self._owned_job(c, principal, job_id)
            if row["revision"] != expected_revision:
                _err("REVISION_CONFLICT", "Resource revision changed")
            if row["status"] not in ("failed", "cancelled", "needs_reconciliation"):
                _err("INVALID_STATE", "Only failed, cancelled or reconciliation jobs can be retried")
            c.execute("UPDATE orch_jobs SET status='queued',stage=NULL,cancel_requested=0,error_code=NULL,attempt=attempt+1,revision=revision+1,lease_token=NULL,lease_expires=NULL,updated_at=? WHERE job_id=?",
                      (_now(), job_id))
            self._event(c, row["investigation_id"], job_id, "job_requeued", row["revision"] + 1, status="RUNNING")
            return self._job(self._owned_job(c, principal, job_id))

    def finish(self, job_id: str, token: str, *, error_code: str | None = None,
               report_id: str | None = None) -> JobV1:
        with self.store.transaction() as c:
            row = c.execute("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None or row["status"] != "running" or not secrets.compare_digest(row["lease_token"] or "", token):
                _err("LEASE_LOST", "Execution lease is no longer valid")
            status = "cancelled" if row["cancel_requested"] or error_code == "CANCELLED" else "failed" if error_code else "completed"
            c.execute("UPDATE orch_jobs SET status=?,error_code=?,result_report_id=?,lease_token=NULL,lease_expires=NULL,revision=revision+1,updated_at=? WHERE job_id=?",
                      (status, error_code, report_id, _now(), job_id))
            self._event(c, row["investigation_id"], job_id, "job_" + status, row["revision"] + 1, row["stage"],
                        status={"completed": "COMPLETED", "failed": "FAILED", "cancelled": "CANCELLED"}[status])
            return self._job(c.execute("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,)).fetchone())

    @staticmethod
    def _store_artifact(c, inv_id, job_id, kind, name, media_type, content: bytes):
        sha = hashlib.sha256(content).hexdigest()
        artifact_id = "art-" + hashlib.sha256((inv_id + ":" + kind + ":" + sha).encode()).hexdigest()[:16]
        c.execute("INSERT OR IGNORE INTO orch_artifacts VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (artifact_id, inv_id, job_id, kind, name, media_type, sha,
                   len(content), content, _now()))
        return ArtifactRefV1(artifact_id=artifact_id, sha256=sha,
                             size_bytes=len(content), media_type=media_type)

    def _latest_artifact(self, c, inv_id, kind):
        return c.execute("SELECT * FROM orch_artifacts WHERE investigation_id=? AND kind=? ORDER BY created_at DESC, artifact_id DESC LIMIT 1",
                         (inv_id, kind)).fetchone()

    def list_artifacts(self, principal, investigation_id):
        with self.store.transaction() as c:
            self._owned(c, principal, investigation_id)
            rows = c.execute("SELECT artifact_id,sha256,size_bytes,media_type,kind,name,created_at FROM orch_artifacts WHERE investigation_id=? ORDER BY created_at, artifact_id",
                             (investigation_id,)).fetchall()
            return [ArtifactListItemV1.model_validate(dict(r)) for r in rows]

    def artifact_content(self, principal, investigation_id, artifact_id):
        with self.store.transaction() as c:
            self._owned(c, principal, investigation_id)
            row = c.execute("SELECT * FROM orch_artifacts WHERE investigation_id=? AND artifact_id=?",
                            (investigation_id, artifact_id)).fetchone()
            if row is None:
                _err("NOT_FOUND", "Resource not found", 404)
            return bytes(row["content"]), row["media_type"], row["name"]

    def get_workspace(self, principal, investigation_id) -> WorkspaceV1:
        with self.store.transaction() as c:
            self._owned(c, principal, investigation_id)
            cand = self._latest_artifact(c, investigation_id, "candidate")
            if cand is None:
                _err("CANDIDATE_NOT_READY", "No candidate has been constructed yet", 409)
            rep = self._latest_artifact(c, investigation_id, "report_json")
            artifacts = [ArtifactListItemV1.model_validate(dict(r)) for r in c.execute(
                "SELECT artifact_id,sha256,size_bytes,media_type,kind,name,created_at FROM orch_artifacts WHERE investigation_id=? ORDER BY created_at, artifact_id",
                (investigation_id,)).fetchall()]
            candidate = CandidateV1.model_validate(json.loads(bytes(cand["content"])))
            report = ReportV1.model_validate(json.loads(bytes(rep["content"]))) if rep else None
            return WorkspaceV1(investigation_id=investigation_id, candidate=candidate,
                               verification=report.evaluation if report else None,
                               report=report, artifacts=artifacts)

    def get_verification(self, principal, investigation_id) -> VerificationV1:
        """Return 409 until the evaluator record is durably available."""
        workspace = self.get_workspace(principal, investigation_id)
        if workspace.verification is None:
            _err("VERIFICATION_NOT_READY", "Verification is not available yet", 409)
        return workspace.verification

    def get_export(self, principal, investigation_id) -> ExportV1:
        with self.store.transaction() as c:
            self._owned(c, principal, investigation_id)
            bundle = self._latest_artifact(c, investigation_id, "bundle")
            if bundle is None:
                _err("CANDIDATE_NOT_READY", "No export bundle has been constructed yet", 409)
            return ExportV1(bundle=ArtifactRefV1(
                artifact_id=bundle["artifact_id"], sha256=bundle["sha256"],
                size_bytes=bundle["size_bytes"], media_type=bundle["media_type"]))

    def execute_job(self, principal, job_id: str) -> JobV1:
        """Synchronous NON_AI executor: claim, construct, verify, finish.

        Genuine deterministic work per stage, from the durable scope record:
        capture hashes the authorized scope, organize builds candidate routes
        from it, distill stores the exact CandidateV1 JSON spec, execute
        structurally verifies it and stores report + proof bundle artifacts.
        No live target probing and no model reasoning are claimed; kind stays
        orchestration_mock with $0 spend enforced by the guard.
        """
        from second_source.contracts import ScopeContract
        import io, zipfile
        with self.store.transaction() as c:
            job_row = self._owned_job(c, principal, job_id)
            inv_row = self._owned(c, principal, job_row["investigation_id"])
        inv_id = inv_row["investigation_id"]
        scope = ScopeContract.model_validate(json.loads(inv_row["scope_json"]))
        claimed = self.claim("orch-executor-nonai", job_id=job_id)
        if claimed is None:
            _err("INVALID_STATE", "Job is not queued and cannot be executed")
        job, token = claimed
        attempt = job.attempt
        candidate = verification = report = bundle_ref = None
        for stage in (JobStage.CAPTURE, JobStage.ORGANIZE, JobStage.DISTILL, JobStage.EXECUTE):
            with self.store.transaction() as c:
                row = c.execute("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,)).fetchone()
                if row is None or row["status"] != "running":
                    _err("LEASE_LOST", "Execution lease is no longer valid")
                if row["cancel_requested"]:
                    break
                c.execute("UPDATE orch_jobs SET stage=?,revision=revision+1,updated_at=? WHERE job_id=?",
                          (stage.value, _now(), job_id))
                refs, detail = (), None
                if stage is JobStage.CAPTURE:
                    detail = f"target={inv_row['target_id']}"
                elif stage is JobStage.DISTILL:
                    obs_sha = hashlib.sha256(canonical(scope.model_dump(mode="python"))).hexdigest()
                    routes = tuple(
                        CandidateRouteV1(method="HTTP", path_template=pat, kind="http-route")
                        for pat in scope.implementation.route_patterns
                    ) or tuple(
                        CandidateRouteV1(method="CLI", path_template=a, kind="cli-action")
                        for a in sorted(scope.observation.permitted_actions)
                    )
                    candidate = CandidateV1(
                        candidate_id=f"cand-{job_id[:8]}-a{attempt}", investigation_id=inv_id,
                        source_observations_sha256=obs_sha, routes=routes)
                    ref = self._store_artifact(
                        c, inv_id, job_id, "candidate", "candidate.json", "application/json",
                        canonical(candidate.model_dump(mode="python")))
                    refs, detail = (ref.artifact_id,), f"routes={len(routes)}"
                elif stage is JobStage.EXECUTE:
                    assert candidate is not None
                    total = len(candidate.routes)
                    verification = (VerificationV1(passed=total, failed=0, indeterminate=0, total=total)
                                    if total else VerificationV1(passed=0, failed=0, indeterminate=1, total=1))
                    report_id = f"rep-{job_id[:8]}-a{attempt}"
                    lines = [
                        f"# Investigation report - {inv_row['title']}", "",
                        f"- Target: {inv_row['target_id']}",
                        f"- Instruction: {inv_row['instruction']}",
                        f"- Scope digest: {inv_row['scope_digest']}",
                        f"- Candidate: {candidate.candidate_id} (NON_AI, IR v{candidate.ir_version})",
                        f"- Source scope SHA-256: {candidate.source_observations_sha256}",
                        f"- Structural verification: {verification.passed} passed, "
                        f"{verification.failed} failed, {verification.indeterminate} indeterminate "
                        f"of {verification.total} (origin: mock, real: false)", "",
                        "## Candidate routes",
                    ] + [f"- {r.method} {r.path_template} ({r.kind})" for r in candidate.routes] + [
                        "", "## Limitations",
                        "- Deterministic NON_AI construction from the authorized scope; no live target probing was performed by this executor.",
                        "- Structural verification checks the candidate spec only; it is not behavioral equivalence with the reference.",
                        "- No model (REAL_MODEL) reasoning ran in this job; recorded model evidence lives in the research record, not here.",
                    ]
                    report_ref = self._store_artifact(
                        c, inv_id, job_id, "report", "report.md", "text/markdown",
                        "\n".join(lines).encode())
                    manifest = {
                        "candidate_id": candidate.candidate_id, "provenance": "NON_AI",
                        "evaluator": "structural-v1", "verification": verification.model_dump(mode="json"),
                        "scope_digest": inv_row["scope_digest"],
                        "limitations": ["structural_only", "no_live_probing", "no_model_reasoning"],
                    }
                    self._store_artifact(c, inv_id, job_id, "manifest", "manifest.json",
                                         "application/json", canonical(manifest))
                    report = ReportV1(report_id=report_id, investigation_id=inv_id, job_id=job_id,
                                      evaluation=verification, report=report_ref, stop_reason="completed")
                    self._store_artifact(c, inv_id, job_id, "report_json", "report.json",
                                         "application/json", canonical(report.model_dump(mode="python")))
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                        for name, data in (
                            ("candidate.json", canonical(candidate.model_dump(mode="python"))),
                            ("report.md", "\n".join(lines).encode()),
                            ("manifest.json", canonical(manifest)),
                            ("README.txt", b"Second Source NON_AI proof bundle. Verify hashes against manifest.json.\n"),
                        ):
                            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                            info.external_attr = 0o644 << 16
                            z.writestr(info, data)
                    bundle_ref = self._store_artifact(
                        c, inv_id, job_id, "bundle", "proof-bundle.zip", "application/zip", buf.getvalue())
                    refs = (bundle_ref.artifact_id,)
                    detail = f"verification={verification.passed}/{verification.total}"
                self._event(c, inv_id, job_id, "stage_" + stage.value,
                            row["revision"] + 1, stage.value, status="RUNNING",
                            artifact_refs=refs, detail=detail)
        finished = self.finish(job_id, token, report_id=report.report_id if report else None)
        if finished.status is JobStatus.COMPLETED and bundle_ref is not None:
            with self.store.transaction() as c:
                row = c.execute("SELECT revision FROM orch_jobs WHERE job_id=?", (job_id,)).fetchone()
                self._event(c, inv_id, job_id, "delivery_ready", row["revision"], None,
                            status="COMPLETED", artifact_refs=(bundle_ref.artifact_id,),
                            detail="proof-bundle.zip")
        return finished

    def check_spend(self, packet: SpendPacketV1 | None, *, estimated_usd: float, investigation_id: str) -> None:
        self.guard.check(packet, estimated_usd=estimated_usd, investigation_id=investigation_id)

def _scope(data):
    from second_source.contracts import ScopeContract
    return ScopeContract.model_validate(data)
