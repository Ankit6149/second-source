"""Cloud-identity ingress acceptance, with no live network or credentials."""
import hashlib
import json
import uuid
from urllib.error import HTTPError, URLError

from fastapi.testclient import TestClient
import pytest

from second_source.backend.api import create_app
from second_source.backend.auth import SupabaseIdentity
from second_source.backend.contracts import Principal
from second_source.backend.service import BackendService
from second_source.live_experiment import create_scope

PROJECT = "jpqcqqbzriizxhigvjki"
PUBLIC_KEY = "sb_publishable_" + "x" * 32
OWNER = str(uuid.uuid4())
OTHER = str(uuid.uuid4())
GOOD = "a" * 28 + "." + "b" * 28 + "." + "c" * 48


def identity(owner=OWNER, *, token=GOOD):
    def transport(url, headers, timeout):
        assert url == f"https://{PROJECT}.supabase.co/auth/v1/user"
        assert headers["apikey"] == PUBLIC_KEY
        assert headers["Authorization"] == "Bearer " + token
        assert 0 < timeout <= 8
        return {"id": owner, "role": "authenticated", "is_anonymous": False}
    return SupabaseIdentity(PROJECT, PUBLIC_KEY, fetch_user=transport)


def test_validation_and_remote_verification():
    verify = identity()
    assert verify(GOOD) == Principal(owner_id=OWNER)
    assert verify("legacy-opaque-token") is None
    with pytest.raises(ValueError):
        SupabaseIdentity("https://evil.example", PUBLIC_KEY)
    with pytest.raises(ValueError):
        SupabaseIdentity(PROJECT, "too-short")


@pytest.mark.parametrize("body", [
    {"id": OWNER, "role": "service_role"},
    {"id": OWNER, "role": "anon"},
    {"id": OWNER, "role": "authenticated", "is_anonymous": True},
    {"id": OWNER, "role": "authenticated"},
    {"id": OWNER, "role": "authenticated", "is_anonymous": None},
    {"id": OWNER, "role": "authenticated", "is_anonymous": "false"},
    {"id": OWNER, "role": "authenticated", "is_anonymous": 0},
    {"id": "not-a-uuid", "role": "authenticated"},
    {"id": OWNER.upper() + "-extra", "role": "authenticated"},
    {"role": "authenticated"},
    {"id": OWNER, "role": "authenticated", "is_anonymous": False, "unused": 1},
    [], None,
])
def test_fail_closed_non_user_and_incorrect_identity(body):
    user = SupabaseIdentity(PROJECT, PUBLIC_KEY, fetch_user=lambda *args: body)
    if isinstance(body, dict) and body.get("id") == OWNER and body.get("role") == "authenticated" and body.get("is_anonymous") is False:
        assert user(GOOD).owner_id == OWNER  # ignore unrelated user fields, never authorize by metadata
    else:
        assert user(GOOD) is None


def test_remote_outages_are_unauthenticated_and_never_echoed():
    secret = "SECRET_INVALID_TOKEN_FROM_REMOTE"
    for problem in (URLError("network failure " + secret), TimeoutError(secret),
                    ValueError(secret), HTTPError("https://a", 401, secret, {}, None)):
        def broken(*args):
            raise problem
        resolver = SupabaseIdentity(PROJECT, PUBLIC_KEY, fetch_user=broken)
        assert resolver(GOOD) is None


def test_api_accepts_verified_project_identity_and_isolates_owners(tmp_path):
    store = BackendService(tmp_path / "auth.sqlite")
    def lookup(token):
        return identity(OWNER if token == GOOD else OTHER, token=token)(token)
    with TestClient(create_app(store, identity_resolver=lookup), raise_server_exceptions=False) as client:
        response = client.post("/v1/investigations", headers={
            "Authorization": "Bearer " + GOOD, "Idempotency-Key": "auth1"
        }, json={"title": "Cloud auth NON_AI", "scope": create_scope(0, 1).model_dump(mode="json")})
        assert response.status_code == 201, response.text
        inv = response.json()
        assert inv["owner_id"] == OWNER
        alternate = "x" * 28 + "." + "y" * 28 + "." + "z" * 48
        assert client.get("/v1/investigations/" + inv["investigation_id"],
                          headers={"Authorization": "Bearer " + alternate}).status_code == 404
        assert client.get("/v1/investigations/" + inv["investigation_id"],
                          headers={"Authorization": "Bearer opaque"}).status_code == 401
        assert client.get("/v1/capabilities", headers={"Authorization": "Bearer " + GOOD}).json()["real"] is False


def test_mixed_auth_authorities_are_denied(tmp_path):
    service = BackendService(tmp_path / "authmode.sqlite")
    token_digest = hashlib.sha256(b"mock").hexdigest()
    with pytest.raises(ValueError):
        create_app(service, {token_digest: "local"}, identity_resolver=identity())
    with pytest.raises(ValueError):
        create_app(service)


def test_preauth_rate_limit_prevents_remote_verification_flood(tmp_path):
    store = BackendService(tmp_path / "authburst.sqlite")
    calls = []
    def remote(token):
        calls.append(token)
        return Principal(owner_id=OWNER)
    with TestClient(create_app(store, identity_resolver=remote, requests_per_minute=1)) as client:
        assert client.get("/v1/capabilities", headers={"Authorization": "Bearer " + GOOD}).status_code == 200
        second = client.get("/v1/capabilities", headers={"Authorization": "Bearer " + GOOD})
        assert second.status_code == 429
        assert calls == [GOOD]
