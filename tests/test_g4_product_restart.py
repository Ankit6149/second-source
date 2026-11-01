"""G4 product evidence survives a control-plane restart without redispatch."""
import hashlib

from fastapi.testclient import TestClient

from second_source.backend.api import create_app
from second_source.backend.artifacts import ArtifactStore, verify_bundle
from second_source.backend.contracts import AuthorizeInvestigation, CreateInvestigation, CreateRun, Principal
from second_source.backend.service import BackendService
from second_source.backend.worker import G3MockEngine, Worker
from second_source.g4_http_reconstruct import create_g4_http_scope


def test_http_report_export_and_owner_isolation_after_restart(tmp_path):
    owner, other = Principal(owner_id="owner_alpha"), Principal(owner_id="owner_beta")
    first_token, second_token = "NON_AI_" + "1" * 40, "NON_AI_" + "2" * 40
    tokens = {hashlib.sha256(first_token.encode()).hexdigest(): owner.owner_id,
              hashlib.sha256(second_token.encode()).hexdigest(): other.owner_id}
    service = BackendService(tmp_path / "state.sqlite")
    artifacts = ArtifactStore(tmp_path / "reports")
    investigation = service.create_investigation(owner, CreateInvestigation(
        title="HTTP restart acceptance", scope=create_g4_http_scope(0)), "investigation")
    investigation = service.authorize_investigation(owner, investigation.investigation_id,
        AuthorizeInvestigation(expected_revision=investigation.revision, scope_digest=investigation.scope_digest))
    queued = service.create_run(owner, investigation.investigation_id, CreateRun(), "run")
    assert Worker(service, G3MockEngine(tmp_path / "private", artifacts), "before_restart").once()
    completed = service.get_run(owner, queued.run_id)
    assert completed.status == "completed" and completed.result.evaluation.total == 30

    restarted = BackendService(tmp_path / "state.sqlite")
    assert restarted.get_run(owner, queued.run_id) == completed
    assert restarted.claim("after_restart") is None
    with TestClient(create_app(restarted, tokens, ArtifactStore(tmp_path / "reports"))) as client:
        owner_headers = {"Authorization": f"Bearer {first_token}"}
        other_headers = {"Authorization": f"Bearer {second_token}"}
        for suffix in ("/verification", "/report", "/export.zip"):
            url = f"/v1/runs/{queued.run_id}{suffix}"
            response = client.get(url, headers=owner_headers)
            assert response.status_code == 200
            if suffix == "/export.zip":
                assert verify_bundle(response.content)["valid"]
            assert client.get(url, headers=other_headers).status_code == 404
