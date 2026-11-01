"""End-to-end G4 HTTP Backend + Worker + Storage + Proof-Bundle Acceptance Suite.

Proves the complete 12-step executable acceptance journey for the primary G4 HTTP
target (`owned-http-task-workflow-v1`) through the real FastAPI control plane
(`create_app` and `build_cloud_app`), `BackendService`, `OnDemandMockExecutor`,
`Worker`, `G3MockEngine`, `ArtifactStore` / `SupabaseArtifactStore`, and offline
proof-bundle verifier (`verify_bundle`):

1. Start local application and owned HTTP reference.
2. Discover the G4 target via `/v1/targets` with truthful capabilities.
3. Create and authorize an HTTP investigation.
4. Collect actual bounded HTTP observations via worker execution.
5. Persist evidence and hypotheses.
6. Execute active experiments and record lifecycle stage events.
7. Admit a deterministic candidate through the real candidate validation boundary.
8. Verify behavior against the 30 held-out cases (`25/30 -> 30/30`).
9. Produce categorized mismatch & repair results (`/v1/runs/{id}/verification`).
10. Generate a durable report (`/v1/runs/{id}/report`) and sanitized proof bundle (`/v1/runs/{id}/export.zip`).
11. Validate the exported bundle using the existing offline verifier (`verify_bundle`).
12. Demonstrate cancellation, lease-expiry recovery, invalid input / unauthorized scope refusal,
    duplicate worker dispatch / idempotency, and two-user owner isolation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from fixtures.owned_http_task_workflow import (
    TARGET_ID,
    create_http_scope,
    load_http_candidate,
)
from second_source.backend.api import create_app
from second_source.backend.artifacts import ArtifactStore, verify_bundle
from second_source.backend.asgi import build_cloud_app
from second_source.backend.contracts import (
    AuthorizeInvestigation,
    CodeStage,
    CreateInvestigation,
    CreateRun,
    EvaluationSummary,
    Principal,
)
from second_source.backend.service import BackendService
from second_source.backend.settings import CloudSettings
from second_source.backend.store import SQLiteStore
from second_source.backend.worker import G3MockEngine, Worker
from second_source.contracts import ScopeContract, TargetKind
from second_source.g2_persistence import scope_digest_of
from second_source.g4_http_reconstruct import create_g4_http_scope
from second_source.model_gateway import MetaProvider
from test_backend_cloud_artifacts import FakeStorage

TOKEN_OWNER = "a" * 32 + "." + "b" * 32 + "." + "c" * 48
TOKEN_OTHER = "x" * 32 + "." + "y" * 32 + "." + "z" * 48
OWNER_ID = "a186fb18-72b4-4071-9794-e8746c3e4231"
OTHER_ID = "194d8e1f-b8d2-4b59-a387-92698d47678c"
HEADERS_OWNER = {"Authorization": f"Bearer {TOKEN_OWNER}"}
HEADERS_OTHER = {"Authorization": f"Bearer {TOKEN_OTHER}"}


class LocalAcceptanceStore(SQLiteStore):
    """Local SQLite store with private artifact reference indexing for cloud-app testing."""

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        self.refs: dict[tuple[str, str, str], Any] = {}

    def record_artifact_ref(
        self, principal: Principal, run_id: str, reference: Any, *, lease_token: str
    ) -> None:
        assert isinstance(lease_token, str) and lease_token
        key = (principal.owner_id, run_id, reference.artifact_id)
        assert key not in self.refs or self.refs[key] == reference
        self.refs[key] = reference


def _cloud_config(enabled: bool = True) -> CloudSettings:
    return CloudSettings(
        database_url="NOT_A_CREDENTIAL_" + "d" * 24,
        publishable_key="sb_publishable_" + "x" * 30,
        storage_key="NOT_A_CREDENTIAL_" + "s" * 24,
        cors_origins=("https://ui.example",),
        enable_mock_execution=enabled,
    )


def _identity_resolver(token: str) -> Principal | None:
    if token == TOKEN_OWNER:
        return Principal(owner_id=OWNER_ID)
    if token == TOKEN_OTHER:
        return Principal(owner_id=OTHER_ID)
    return None


def test_g4_http_complete_12_step_cloud_app_worker_acceptance_journey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Execute the full 12-step G4 HTTP acceptance journey through build_cloud_app + OnDemandMockExecutor."""
    monkeypatch.setattr(
        MetaProvider,
        "complete",
        lambda *a, **k: pytest.fail("Paid provider transport is strictly forbidden"),
    )

    # Step 1: Start local application and owned HTTP reference wiring
    db = LocalAcceptanceStore(tmp_path / "g4_cloud_acceptance.sqlite")
    transport = FakeStorage()
    app = build_cloud_app(
        _cloud_config(True),
        store=db,
        transport=transport,
        identity=_identity_resolver,
    )

    with TestClient(app) as client:
        # Step 2: Discover the G4 target via /v1/targets with truthful capabilities
        assert client.get("/v1/session").status_code == 401
        sess = client.get("/v1/session", headers=HEADERS_OWNER).json()
        assert sess == {"owner_id": OWNER_ID, "authenticated": True}

        caps = client.get("/v1/capabilities", headers=HEADERS_OWNER).json()
        assert caps["real"] is False
        assert caps["real_inference_enabled"] is False
        assert caps["paid_authorization_enabled"] is False
        assert caps["execution_mode"] == "on_demand_mock"

        # Default /v1/targets preserves backward compatibility; ?include_g4=true and ?target_id=... expose G4 HTTP
        all_targets = client.get("/v1/targets?include_g4=true", headers=HEADERS_OWNER)
        assert all_targets.status_code == 200
        target_ids = [t["target_id"] for t in all_targets.json()]
        assert target_ids == ["owned-ledger-v1", TARGET_ID]

        g4_targets = client.get(
            f"/v1/targets?target_id={TARGET_ID}", headers=HEADERS_OWNER
        )
        assert g4_targets.status_code == 200
        (g4_target,) = g4_targets.json()
        assert g4_target["target_id"] == TARGET_ID
        assert g4_target["label"] == "Owned HTTP task-workflow fixture"
        assert g4_target["run_kind"] == "g3_mock"
        assert g4_target["origin"] == "mock"
        assert g4_target["real"] is False
        assert g4_target["execution_enabled"] is True

        parsed_scope = ScopeContract.model_validate(g4_target["scope"])
        assert parsed_scope.target.kind == TargetKind.HTTP
        assert parsed_scope.target.permission_ref == TARGET_ID
        expected_digest = scope_digest_of(create_g4_http_scope(0)).removeprefix("sha256:")
        assert g4_target["scope_digest"] == expected_digest

        # Step 3: Create and authorize an HTTP investigation
        inv_resp = client.post(
            "/v1/investigations",
            headers={**HEADERS_OWNER, "Idempotency-Key": "g4-inv-1"},
            json={
                "title": "PRIVATE_G4_HTTP_INVESTIGATION_TITLE_SENTINEL",
                "scope": g4_target["scope"],
            },
        )
        assert inv_resp.status_code == 201, inv_resp.text
        inv = inv_resp.json()
        assert inv["scope_digest"] == expected_digest
        assert inv["status"] == "created"
        assert inv["revision"] == 1

        # Idempotent replay returns identical investigation; modified body returns 409
        assert (
            client.post(
                "/v1/investigations",
                headers={**HEADERS_OWNER, "Idempotency-Key": "g4-inv-1"},
                json={
                    "title": "PRIVATE_G4_HTTP_INVESTIGATION_TITLE_SENTINEL",
                    "scope": g4_target["scope"],
                },
            ).json()
            == inv
        )
        assert (
            client.post(
                "/v1/investigations",
                headers={**HEADERS_OWNER, "Idempotency-Key": "g4-inv-1"},
                json={"title": "DIFFERENT_TITLE", "scope": g4_target["scope"]},
            ).status_code
            == 409
        )

        # Paid authorization is refused fail-closed (422)
        assert (
            client.post(
                f"/v1/investigations/{inv['investigation_id']}/authorize",
                headers=HEADERS_OWNER,
                json={
                    "expected_revision": 1,
                    "scope_digest": inv["scope_digest"],
                    "mode": "real",
                },
            ).status_code
            == 422
        )

        auth_resp = client.post(
            f"/v1/investigations/{inv['investigation_id']}/authorize",
            headers=HEADERS_OWNER,
            json={
                "expected_revision": inv["revision"],
                "scope_digest": inv["scope_digest"],
                "mode": "mock",
                "maximum_model_spend_usd": 0,
            },
        )
        assert auth_resp.status_code == 200, auth_resp.text
        authorized_inv = auth_resp.json()
        assert authorized_inv["status"] == "authorized"
        assert authorized_inv["revision"] == 2

        # Step 4: Queue and execute the G4 HTTP run via the worker
        run_resp = client.post(
            f"/v1/investigations/{inv['investigation_id']}/runs",
            headers={**HEADERS_OWNER, "Idempotency-Key": "g4-run-1"},
            json={"kind": "g3_mock"},
        )
        assert run_resp.status_code == 201, run_resp.text
        queued_run = run_resp.json()
        run_id = queued_run["run_id"]
        assert queued_run["status"] == "queued"
        assert queued_run["result"] is None

        # Outsider cannot execute or view the run (Step 12 owner isolation)
        assert (
            client.post(
                f"/v1/runs/{run_id}/execute",
                headers=HEADERS_OTHER,
                json={"expected_revision": 1},
            ).status_code
            == 404
        )

        exec_resp = client.post(
            f"/v1/runs/{run_id}/execute",
            headers=HEADERS_OWNER,
            json={"expected_revision": 1},
        )
        assert exec_resp.status_code == 200, exec_resp.text
        completed_run = exec_resp.json()
        assert completed_run["status"] == "completed", completed_run
        assert completed_run["stage"] == "execute"

        # Step 5, 6, 7, 8: Verify persisted private artifacts, candidate admission, and 30-case evaluation
        result = completed_run["result"]
        assert result["origin"] == "mock"
        assert result["real"] is False
        assert result["stop_reason"] == "completed_mock_run"
        assert result["evaluation"] == {
            "passed": 30,
            "failed": 0,
            "indeterminate": 0,
            "total": 30,
        }
        assert (
            result["usage"]["estimated_cost_usd"]
            == result["usage"]["uncertain_cost_usd"]
            == 0
        )

        # Verify stage events and repair events on the run timeline
        events_resp = client.get(f"/v1/runs/{run_id}/events", headers=HEADERS_OWNER)
        assert events_resp.status_code == 200
        run_events = events_resp.json()["items"]
        event_types = [e["event_type"] for e in run_events]
        assert event_types == [
            "investigation_created",
            "investigation_authorized_mock_only",
            "run_queued",
            "run_claimed",
            "stage_started",
            "stage_started",
            "stage_started",
            "stage_started",
            "repair_started",
            "repair_completed",
            "run_completed",
        ]
        stages = [e["stage"] for e in run_events if e["event_type"] == "stage_started"]
        assert stages == ["capture", "organize", "distill", "execute"]

        # Step 9: Verify categorized mismatch & repair lineage via /v1/runs/{id}/verification
        ver_resp = client.get(f"/v1/runs/{run_id}/verification", headers=HEADERS_OWNER)
        assert ver_resp.status_code == 200
        verification = ver_resp.json()
        assert verification["origin"] == "mock"
        assert verification["real"] is False
        assert verification["evaluation"] == {
            "passed": 30,
            "failed": 0,
            "indeterminate": 0,
            "total": 30,
        }
        assert verification["repair_history_availability"] == "available"
        repair_view = verification["repair"]
        assert repair_view is not None
        assert repair_view["verdict"] == "improved"
        assert repair_view["stop_reason"] == "repaired_to_perfect"
        assert repair_view["selected_version"] == "repair-1"
        assert len(repair_view["versions"]) == 2
        assert repair_view["versions"][0]["round"] == 0
        assert repair_view["versions"][0]["evaluation"] == {
            "passed": 25,
            "failed": 5,
            "indeterminate": 0,
            "total": 30,
        }
        assert repair_view["versions"][1]["round"] == 1
        assert repair_view["versions"][1]["evaluation"] == {
            "passed": 30,
            "failed": 0,
            "indeterminate": 0,
            "total": 30,
        }

        # Verify retained private artifacts in simulated private storage
        for expected_private in (
            "private:candidate.v1.json",
            "private:broker-artifact.v1.json",
            "private:evaluation-receipt.v1.json",
            "private:evaluation-manifest.v1.json",
            "private:candidate.r1.json",
            "private:broker-artifact.r1.json",
            "private:evaluation-receipt.r1.json",
            "private:evaluation-manifest.r1.json",
            "private:G3_report.json",
            "private:G3_repair_history.json",
        ):
            assert (OWNER_ID, run_id, expected_private) in db.refs, (
                f"Missing private artifact {expected_private}"
            )

        # Verify admitted candidates pass real load_http_candidate validation
        for cand_name in ("private:candidate.v1.json", "private:candidate.r1.json"):
            cand_ref = db.refs[(OWNER_ID, run_id, cand_name)]
            cand_bytes = next(
                body
                for key, body in transport.objects.items()
                if key.endswith("/" + cand_name.removeprefix("private:"))
            )
            assert hashlib.sha256(cand_bytes).hexdigest() == cand_ref.sha256
            admitted_spec = load_http_candidate(cand_bytes, parsed_scope)
            assert admitted_spec.spec.subsystem == "http_task_workflow"

        # Step 10 & 11: Generate durable report and downloadable sanitized proof bundle, then verify offline
        report_resp = client.get(f"/v1/runs/{run_id}/report", headers=HEADERS_OWNER)
        assert report_resp.status_code == 200
        pub_report = report_resp.json()
        assert pub_report["origin"] == "mock"
        assert pub_report["real"] is False
        assert pub_report["scope_digest"] == expected_digest
        assert pub_report["evaluation"] == {
            "passed": 30,
            "failed": 0,
            "indeterminate": 0,
            "total": 30,
        }
        assert pub_report["repair"]["verdict"] == "improved"
        assert pub_report["repair"]["selected_version"] == "repair-1"

        bundle_resp = client.get(f"/v1/runs/{run_id}/export.zip", headers=HEADERS_OWNER)
        assert bundle_resp.status_code == 200
        assert bundle_resp.headers["content-type"] == "application/zip"
        bundle_verification = verify_bundle(bundle_resp.content)
        assert bundle_verification["valid"] is True
        assert bundle_verification["origin"] == "mock"
        assert bundle_verification["attests_provider"] is False

        # Ensure zero leakage of private titles, owner IDs, filesystem paths, or sealed test IDs
        for sentinel in (
            b"PRIVATE_G4_HTTP_INVESTIGATION_TITLE_SENTINEL",
            OWNER_ID.encode("utf-8"),
            str(tmp_path).encode("utf-8"),
            b"TaskWorkflowReferenceState",
            b"G4-HTTP-",
        ):
            assert sentinel not in report_resp.content
            assert sentinel not in bundle_resp.content

        # Duplicate execute call on completed run is a safe idempotent no-op
        storage_call_count = len(transport.calls)
        repeat_exec = client.post(
            f"/v1/runs/{run_id}/execute",
            headers=HEADERS_OWNER,
            json={"expected_revision": 1},
        )
        assert repeat_exec.status_code == 200
        assert repeat_exec.json() == completed_run
        assert len(transport.calls) == storage_call_count

        # Step 12a: Owner isolation across all endpoints
        for protected_get in (
            f"/v1/investigations/{inv['investigation_id']}",
            f"/v1/investigations/{inv['investigation_id']}/runs",
            f"/v1/investigations/{inv['investigation_id']}/events",
            f"/v1/runs/{run_id}",
            f"/v1/runs/{run_id}/events",
            f"/v1/runs/{run_id}/verification",
            f"/v1/runs/{run_id}/report",
            f"/v1/runs/{run_id}/export.zip",
        ):
            assert client.get(protected_get, headers=HEADERS_OTHER).status_code == 404


def test_g4_http_worker_evidence_persistence_and_failure_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify Step 5 (persisted EvidenceLedger & discovery summary) and Step 12 failure/safety controls:
    cancellation, lease-expiry reconciliation, duplicate worker dispatch prevention, and unauthorized HTTP scope refusal.
    """
    owner = Principal(owner_id="owner_alpha")
    other = Principal(owner_id="owner_beta")
    token_alpha = "NON_AI_" + "1" * 40
    token_beta = "NON_AI_" + "2" * 40
    tokens = {
        hashlib.sha256(token_alpha.encode()).hexdigest(): owner.owner_id,
        hashlib.sha256(token_beta.encode()).hexdigest(): other.owner_id,
    }
    headers_alpha = {"Authorization": f"Bearer {token_alpha}"}
    headers_beta = {"Authorization": f"Bearer {token_beta}"}

    service = BackendService(tmp_path / "g4_worker_state.sqlite")
    artifacts = ArtifactStore(tmp_path / "g4_reports")
    private_dir = tmp_path / "g4_private"
    engine = G3MockEngine(private_dir, artifacts)
    worker = Worker(service, engine, "g4_worker_1")

    with TestClient(create_app(service, tokens, artifacts)) as client:
        # 1. Invalid target query parameter is rejected (422)
        assert (
            client.get(
                "/v1/targets?target_id=unauthorized-http-target", headers=headers_alpha
            ).status_code
            == 422
        )

        # 2. Discover G4 HTTP target and run through Worker.once()
        (target,) = client.get(
            f"/v1/targets?target_id={TARGET_ID}", headers=headers_alpha
        ).json()
        inv = service.create_investigation(
            owner,
            CreateInvestigation(
                title="G4 HTTP Worker Run",
                scope=ScopeContract.model_validate(target["scope"]),
            ),
            "inv-g4-worker",
        )
        inv = service.authorize_investigation(
            owner,
            inv.investigation_id,
            AuthorizeInvestigation(
                expected_revision=inv.revision, scope_digest=inv.scope_digest
            ),
        )
        queued = service.create_run(
            owner, inv.investigation_id, CreateRun(kind="g3_mock"), "run-g4-worker"
        )

        assert worker.once() is True
        # Duplicate worker dispatch returns False when queue is empty
        assert worker.once() is False

        completed = service.get_run(owner, queued.run_id)
        assert completed.status == "completed"
        assert completed.stage == CodeStage.EXECUTE
        assert completed.result is not None
        assert completed.result.evaluation == EvaluationSummary(
            passed=30, failed=0, indeterminate=0, total=30
        )

        # Verify persisted EvidenceLedger observations and G4_discovery_summary.json on disk
        engine_dir = private_dir / queued.run_id / "engine"
        discovery_summary_path = engine_dir / "G4_discovery_summary.json"
        assert discovery_summary_path.is_file()
        discovery_summary = json.loads(discovery_summary_path.read_text(encoding="utf-8"))
        assert discovery_summary["target_id"] == TARGET_ID
        assert discovery_summary["seed_experiments"] == 5
        assert discovery_summary["seed_actions"] == 15
        assert discovery_summary["active_rounds_executed"] == 4
        assert discovery_summary["total_observations_recorded"] == 26
        assert (
            discovery_summary["initial_passive_attribution"]["rules_revealed_count"] == 4
        )
        assert (
            discovery_summary["post_discovery_active_attribution"]["rules_revealed_count"]
            == 8
        )

        # Verify initial receipt (25/30 with categorized mismatches) vs repaired receipt (30/30)
        initial_receipt = json.loads(
            (engine_dir / "evaluation-manifest.v1.json").read_text(encoding="utf-8")
        )
        assert initial_receipt["evaluation"]["passed"] == 25
        assert initial_receipt["evaluation"]["failed"] == 5
        assert initial_receipt["evaluation"]["failure_categories"] == {
            "error": 5,
        }
        repaired_receipt = json.loads(
            (engine_dir / "evaluation-manifest.r1.json").read_text(encoding="utf-8")
        )
        assert repaired_receipt["evaluation"]["passed"] == 30
        assert repaired_receipt["evaluation"]["failed"] == 0

        # 3. Cancellation of a queued G4 HTTP run
        queued_cancel = service.create_run(
            owner, inv.investigation_id, CreateRun(kind="g3_mock"), "run-g4-cancel"
        )
        cancel_resp = client.post(
            f"/v1/runs/{queued_cancel.run_id}/cancel",
            headers=headers_alpha,
            json={"expected_revision": queued_cancel.revision},
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"
        assert service.claim("any_worker", run_id=queued_cancel.run_id) is None

        # 4. Duplicate worker claim prevention & Lease-expiry recovery (reconcile)
        queued_lease = service.create_run(
            owner, inv.investigation_id, CreateRun(kind="g3_mock"), "run-g4-lease"
        )
        lease = service.claim("worker_a", run_id=queued_lease.run_id)
        assert lease is not None
        # Concurrent worker cannot claim an already-leased G4 HTTP run
        assert service.claim("worker_b", run_id=queued_lease.run_id) is None

        # Simulate lease expiry
        with service.store.transaction() as conn:
            conn.execute(
                "UPDATE runs SET lease_expires=0 WHERE run_id=?",
                (queued_lease.run_id,),
            )

        # Other owner cannot reconcile
        assert (
            client.post(
                f"/v1/runs/{queued_lease.run_id}/reconcile",
                headers=headers_beta,
                json={"expected_revision": lease.run.revision},
            ).status_code
            == 404
        )
        reconcile_resp = client.post(
            f"/v1/runs/{queued_lease.run_id}/reconcile",
            headers=headers_alpha,
            json={"expected_revision": lease.run.revision},
        )
        assert reconcile_resp.status_code == 200
        reconciled = reconcile_resp.json()
        assert reconciled["status"] == "needs_reconciliation"
        assert reconciled["error_code"] == "LEASE_EXPIRED"
        # Expired run is quarantined and never automatically re-claimed
        assert service.claim("worker_c", run_id=queued_lease.run_id) is None

        # 5. Unauthorized HTTP URL scope fails closed with UNSUPPORTED_SCOPE without spawning subprocess
        unauthorized_http_scope = create_http_scope(
            "https://evil.example", max_usd=0.0
        )
        unauth_inv = service.create_investigation(
            owner,
            CreateInvestigation(
                title="Unauthorized external HTTP target",
                scope=unauthorized_http_scope,
            ),
            "inv-unauth-http",
        )
        unauth_inv = service.authorize_investigation(
            owner,
            unauth_inv.investigation_id,
            AuthorizeInvestigation(
                expected_revision=unauth_inv.revision,
                scope_digest=unauth_inv.scope_digest,
            ),
        )
        unauth_run = service.create_run(
            owner,
            unauth_inv.investigation_id,
            CreateRun(kind="g3_mock"),
            "run-unauth-http",
        )
        monkeypatch.setattr(
            "second_source.backend.worker.subprocess.Popen",
            lambda *a, **kw: pytest.fail("Unauthorized HTTP scope must never spawn subprocess"),
        )
        assert worker.once(run_id=unauth_run.run_id) is True
        failed_unauth = service.get_run(owner, unauth_run.run_id)
        assert failed_unauth.status == "failed"
        assert failed_unauth.error_code == "UNSUPPORTED_SCOPE"
