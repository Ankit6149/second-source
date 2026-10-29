"""Supabase Auth user lookup for externally issued access tokens.

No signing secrets, service-role keys, model keys or unverified JWT claims are
used for ownership. Supabase Auth's /user endpoint validates the bearer token.
Production callers configure a public project key and a pinned project ref.
"""
from __future__ import annotations

import json
import re
import ssl
import uuid
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

from .contracts import Principal

_PROJECT = re.compile(r"[a-z0-9]{20}\Z")
_PUBLIC_KEY = re.compile(r"[A-Za-z0-9_./\-]{20,3000}\Z")
_JWT = re.compile(r"[A-Za-z0-9_-]{2,4096}\.[A-Za-z0-9_-]{2,4096}\.[A-Za-z0-9_-]{2,4096}\Z")
_MAX_RESPONSE = 16_384


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _get_user(url: str, headers: Mapping[str, str], timeout: float) -> object:
    """Bounded HTTPS request to a URL fixed at application construction."""
    opener = build_opener(_NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    request = Request(url, headers=dict(headers), method="GET")
    with opener.open(request, timeout=timeout) as response:
        if response.status != 200 or response.geturl() != url:
            return None
        raw = response.read(_MAX_RESPONSE + 1)
    if len(raw) > _MAX_RESPONSE:
        return None
    return json.loads(raw)


class SupabaseIdentity:
    """Fail-closed remote token verification; no positive auth-result caching.

    The authority is the fixed Supabase project, not claims decoded from the
    caller's JWT. In particular user_metadata is never used for authorization.
    """
    def __init__(self, project_ref: str, publishable_key: str, *,
                 timeout: float = 4.0,
                 fetch_user: Callable[[str, Mapping[str, str], float], object] = _get_user):
        if not isinstance(project_ref, str) or not _PROJECT.fullmatch(project_ref):
            raise ValueError("Supabase project reference is invalid.")
        if (not isinstance(publishable_key, str)
                or not _PUBLIC_KEY.fullmatch(publishable_key)):
            raise ValueError("A Supabase publishable/anon key is required.")
        if type(timeout) not in (int, float) or not 0 < timeout <= 8:
            raise ValueError("Authentication timeout is invalid.")
        self.url = f"https://{project_ref}.supabase.co/auth/v1/user"
        self._key = publishable_key
        self.timeout = float(timeout)
        self._fetch_user = fetch_user

    def __call__(self, token: str) -> Principal | None:
        # Reject opaque/local bearer tokens before any network request.
        if not isinstance(token, str) or len(token) > 8192 or not _JWT.fullmatch(token):
            return None
        try:
            value = self._fetch_user(self.url, {
                "Authorization": "Bearer " + token,
                "apikey": self._key,
                "Accept": "application/json",
            }, self.timeout)
            if not isinstance(value, dict):
                return None
            if value.get("role") != "authenticated" or value.get("is_anonymous") is True:
                return None
            owner = value.get("id")
            if not isinstance(owner, str):
                return None
            parsed = uuid.UUID(owner)
            if str(parsed) != owner.lower() or parsed.version is None:
                return None
            return Principal(owner_id=owner.lower())
        except (HTTPError, URLError, TimeoutError, OSError, ValueError,
                UnicodeError, json.JSONDecodeError):
            return None
