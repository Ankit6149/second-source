"""Gate A orchestration: NL instruction reaches backend, durable jobs, guard."""
import hashlib
import pytest
from fastapi.testclient import TestClient
from second_source.backend.api import create_app
from second_source.backend.contracts import BackendError, Principal
from second_source.backend.service import BackendService
from second_source.orchestration.guard import SpendingGuard, SpendPacketV1
from second_source.orchestration.registry import default_registry
from second_source.orchestration.schemas import CreateInvestigationV1, VerificationV1
from second_source.orchestration.service import OrchestrationService
from second_source.reconstruct import create_scope

TOKEN = "NON_AI_" + "a" * 40
TOKENS = {hashlib.sha256(TOKEN.encode()).hexdigest(): "owner"}
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
NL = "Reconstruct the owned ledger create/list/get workflow exactly as observed."

@pytest.fixture
def orch(tmp_path):
    return OrchestrationService(tmp_path / "orch.sqlite")

@pytest.fixture
def client(tmp_path):
    backend = BackendService(tmp_path / "api.sqlite")
    orch = OrchestrationService(tmp_path / "orch.sqlite")
    with TestClient(create_app(backend, TOKENS, orchestration_service=orch),
                    raise_server_exceptions=False) as c:
        yield c

def _payload():
    reg = default_registry()
    t = reg.get("owned-ledger-v1")
    return {"title": "Ledger check", "instruction": NL, "target_id": "owned-ledger-v1",
            "scope": t.scope.model_dump(mode="json")}

def _create(client, key="k1"):
    r = client.post("/v1/orchestration/investigations",
                    headers={**HEADERS, "Idempotency-Key": key}, json=_payload())
    assert r.status_code == 201, r.text
    return r.json()

def test_nl_instruction_reaches_backend_and_persists(client):
    inv = _create(client)
    assert inv["instruction"] == NL
    got = client.get(f"/v1/orchestration/investigations/{inv['investigation_id']}", headers=HEADERS)
    assert got.status_code == 200 and got.json()["instruction"] == NL

def test_nl_instruction_service_level(orch):
    reg = default_registry(); t = reg.get("owned-ledger-v1")
    inv = orch.create_investigation(Principal(owner_id="owner"),
        CreateInvestigationV1(title="t", instruction=NL, target_id="owned-ledger-v1", scope=t.scope), "k1")
    assert orch.get_investigation(Principal(owner_id="owner"), inv.investigation_id).instruction == NL
    with pytest.raises(BackendError):
        orch.get_investigation(Principal(owner_id="other"), inv.investigation_id)

def test_targets_registered(client):
    r = client.get("/v1/orchestration/targets", headers=HEADERS)
    assert r.status_code == 200
    ids = {t["target_id"] for t in r.json()}
    assert {"owned-ledger-v1", "owned-http-task-workflow-v1"} <= ids

def test_unknown_target_rejected(client):
    p = _payload(); p["target_id"] = "nope-v1"
    r = client.post("/v1/orchestration/investigations", headers={**HEADERS, "Idempotency-Key": "k9"}, json=p)
    assert r.status_code == 422

def test_authorize_then_enqueue_idempotent(client):
    inv = _create(client)
    r = client.post(f"/v1/orchestration/investigations/{inv['investigation_id']}/authorize",
                    headers=HEADERS, json={"expected_revision": inv["revision"], "scope_digest": inv["scope_digest"]})
    assert r.status_code == 200, r.text
    j1 = client.post(f"/v1/orchestration/investigations/{inv['investigation_id']}/jobs",
                     headers={**HEADERS, "Idempotency-Key": "job1"}, json={})
    assert j1.status_code == 201, j1.text
    j2 = client.post(f"/v1/orchestration/investigations/{inv['investigation_id']}/jobs",
                     headers={**HEADERS, "Idempotency-Key": "job1"}, json={})
    assert j2.json()["job_id"] == j1.json()["job_id"]  # no duplication

def test_cancel_and_retry_without_duplication(orch):
    reg = default_registry(); t = reg.get("owned-ledger-v1")
    me = Principal(owner_id="owner")
    inv = orch.create_investigation(me, CreateInvestigationV1(
        title="t", instruction=NL, target_id="owned-ledger-v1", scope=t.scope), "k1")
    from second_source.orchestration.schemas import AuthorizeInvestigationV1
    orch.authorize(me, inv.investigation_id, AuthorizeInvestigationV1(
        expected_revision=inv.revision, scope_digest=inv.scope_digest))
    job = orch.enqueue(me, inv.investigation_id, "job1")
    cancelled = orch.cancel(me, job.job_id, job.revision)
    assert cancelled.status == "cancelled"
    retried = orch.retry(me, job.job_id, cancelled.revision)
    assert retried.job_id == job.job_id and retried.attempt == 2 and retried.status == "queued"

def test_spending_guard_blocks_paid_without_packet():
    g = SpendingGuard()
    g.check(None, estimated_usd=0, investigation_id="i1")  # mock/$0 ok
    with pytest.raises(BackendError):
        g.check(None, estimated_usd=0.5, investigation_id="i1")
    stale = SpendPacketV1(packet_id="p1", owner_id="o", investigation_id="i1",
                          max_spend_usd=5, max_model_calls=3, fresh=False, mode="paid")
    with pytest.raises(BackendError):
        g.check(stale, estimated_usd=0.5, investigation_id="i1")
    fresh = stale.model_copy(update={"fresh": True})
    g.check(fresh, estimated_usd=0.5, investigation_id="i1")
    g.commit(fresh, estimated_usd=0.5, investigation_id="i1")
    with pytest.raises(BackendError):
        g.check(fresh, estimated_usd=5.0, investigation_id="i1")

def test_verification_counts_must_agree():
    with pytest.raises(Exception):
        VerificationV1(passed=1, failed=1, indeterminate=0, total=5)
    assert VerificationV1(passed=1, failed=1, indeterminate=0, total=2).total == 2

def test_durable_across_reopen(tmp_path):
    path = tmp_path / "orch.sqlite"
    reg = default_registry(); t = reg.get("owned-ledger-v1")
    me = Principal(owner_id="owner")
    s1 = OrchestrationService(path)
    inv = s1.create_investigation(me, CreateInvestigationV1(
        title="t", instruction=NL, target_id="owned-ledger-v1", scope=t.scope), "k1")
    s2 = OrchestrationService(path)  # reopen same DB
    assert s2.get_investigation(me, inv.investigation_id).instruction == NL
    events = s2.list_events(me, inv.investigation_id)
    assert events and events[0].event_type == "investigation_created"


def test_execute_job_completes_with_genuine_stage_events(client):
    inv = _create(client)
    r = client.post(f"/v1/orchestration/investigations/{inv['investigation_id']}/authorize", headers=HEADERS, json={"expected_revision": inv["revision"], "scope_digest": inv["scope_digest"]})
    assert r.status_code == 200, r.text
    j = client.post(f"/v1/orchestration/investigations/{inv['investigation_id']}/jobs", headers={**HEADERS, "Idempotency-Key": "job-exec"}, json={})
    assert j.status_code == 201, j.text
    done = client.post(f"/v1/orchestration/jobs/{j.json()['job_id']}/execute", headers=HEADERS, json={})
    assert done.status_code == 200 and done.json()["status"] == "completed", done.text
    ev = client.get(f"/v1/orchestration/investigations/{inv['investigation_id']}/events", headers=HEADERS)
    kinds = [e["event_type"] for e in ev.json()["items"]]
    assert "stage_capture" in kinds and "stage_execute" in kinds and kinds[-1] == "job_completed"

