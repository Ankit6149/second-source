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
    AuthorizeInvestigationV1, CreateInvestigationV1, InvestigationV1, JobStage,
    JobStatus, JobV1, OrchestrationEventV1,
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
    def _event(c, inv, job, typ, rev, stage=None):
        c.execute("INSERT INTO orch_events(investigation_id,job_id,event_type,stage,revision,created_at) VALUES(?,?,?,?,?,?)",
                  (inv, job, typ, stage, rev, _now()))

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
            self._event(c, investigation_id, job_id, "job_queued", 1)
            return self._job(self._owned_job(c, principal, job_id))

    def get_job(self, principal, job_id) -> JobV1:
        with self.store.transaction() as c:
            return self._job(self._owned_job(c, principal, job_id))

    def list_events(self, principal, investigation_id, after=0, limit=100):
        with self.store.transaction() as c:
            self._owned(c, principal, investigation_id)
            rows = c.execute("SELECT * FROM orch_events WHERE investigation_id=? AND event_id>? ORDER BY event_id LIMIT ?",
                             (investigation_id, after, limit)).fetchall()
            return [OrchestrationEventV1.model_validate(dict(r)) for r in rows]

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
            self._event(c, row["investigation_id"], row["job_id"], "job_claimed", row["revision"] + 1)
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
                        row["revision"] + 1, row["stage"])
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
            self._event(c, row["investigation_id"], job_id, "job_requeued", row["revision"] + 1)
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
            self._event(c, row["investigation_id"], job_id, "job_" + status, row["revision"] + 1, row["stage"])
            return self._job(c.execute("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,)).fetchone())

    def execute_job(self, principal, job_id: str) -> JobV1:
        """Synchronous NON_AI executor: claim, advance genuine stages, finish.

        Records real stage events (capture/organize/distill/execute) from the
        durable job record. No model reasoning is fabricated; kind stays
        orchestration_mock with $0 spend enforced by the guard.
        """
        with self.store.transaction() as c:
            self._owned_job(c, principal, job_id)
        claimed = self.claim("orch-executor-nonai", job_id=job_id)
        if claimed is None:
            _err("INVALID_STATE", "Job is not queued and cannot be executed")
        job, token = claimed
        for stage in (JobStage.CAPTURE, JobStage.ORGANIZE, JobStage.DISTILL, JobStage.EXECUTE):
            with self.store.transaction() as c:
                row = c.execute("SELECT * FROM orch_jobs WHERE job_id=?", (job_id,)).fetchone()
                if row is None or row["status"] != "running":
                    _err("LEASE_LOST", "Execution lease is no longer valid")
                if row["cancel_requested"]:
                    break
                c.execute("UPDATE orch_jobs SET stage=?,revision=revision+1,updated_at=? WHERE job_id=?",
                          (stage.value, _now(), job_id))
                self._event(c, row["investigation_id"], job_id, "stage_" + stage.value,
                            row["revision"] + 1, stage.value)
        return self.finish(job_id, token)

    def check_spend(self, packet: SpendPacketV1 | None, *, estimated_usd: float, investigation_id: str) -> None:
        self.guard.check(packet, estimated_usd=estimated_usd, investigation_id=investigation_id)

def _scope(data):
    from second_source.contracts import ScopeContract
    return ScopeContract.model_validate(data)
