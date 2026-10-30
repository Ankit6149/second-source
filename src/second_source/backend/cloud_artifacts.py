"""Owner-bound immutable private Storage, with existing sanitized proof contracts.

Construction never accesses credentials or the network. Only an explicitly
injected server transport can perform HTTP; no public URLs or signed links exist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import http.client
import json
import math
import re
import ssl
import time
from typing import Callable, Mapping, Protocol
from urllib.parse import urlsplit

from second_source.g2_persistence import canonical
from .artifacts import ArtifactStore, sanitized_report, verify_bundle
from .contracts import ArtifactReference, BackendError, Investigation, LifecycleEvent, Principal, Run

PROJECT_ORIGIN = "https://jpqcqqbzriizxhigvjki.supabase.co"
PRIVATE_BUCKET = "second-source-private"
MAX_ARTIFACT_BYTES = 2_000_000
_ID = re.compile(r"^[a-f0-9-]{36}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
PRIVATE_ARTIFACT_NAMES = frozenset({
    "candidate.v1.json", "broker-artifact.v1.json",
    "generation-dispatch.v1.private.json", "generation-result.v1.private.json",
    "G3_report.json", "G3_input_provenance.json",
})
_OBJECT_PATH = re.compile(
    r"^/storage/v1/object/(?:authenticated/)?second-source-private/v1/"
    r"[a-f0-9]{64}/[a-f0-9]{64}/(?:report/report.json|private/[A-Za-z0-9_.-]+)$"
)


def _error(code="CLOUD_STORAGE_UNAVAILABLE", status=503):
    return BackendError(code, "Private artifact storage is unavailable or failed integrity checks", status)


@dataclass(frozen=True)
class StorageResponse:
    status: int
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)


class StorageTransport(Protocol):
    def request(self, method: str, url: str, *, headers: Mapping[str, str], body: bytes | None,
                max_response_bytes: int, timeout_seconds: float,
                follow_redirects: bool = False) -> StorageResponse: ...


class SupabaseHTTPTransport:
    """Explicit server-only credentials, fixed HTTPS host, bounded reads, no retry.

    A privileged key bypasses Storage RLS. The owner/run authorization callback
    is therefore mandatory in the store. Never inject this object into a browser.
    """
    def __init__(self, *, access_token: str, api_key: str):
        for value in (access_token, api_key):
            if (type(value) is not str or not 1 <= len(value) <= 16_384
                    or any(ord(c) < 33 or ord(c) > 126 for c in value)):
                raise _error("INVALID_STORAGE_CONFIG", 422)
        self._access_token, self._api_key = access_token, api_key

    def request(self, method, url, *, headers, body, max_response_bytes,
                timeout_seconds, follow_redirects=False):
        connection = None
        try:
            target = urlsplit(url)
            if (method not in {"POST", "GET"} or follow_redirects is not False
                    or target.scheme != "https" or target.netloc != urlsplit(PROJECT_ORIGIN).netloc
                    or target.query or target.fragment or not _OBJECT_PATH.fullmatch(target.path)
                    or (method == "GET") != ("/object/authenticated/" in target.path)
                    or type(max_response_bytes) is not int or not 1 <= max_response_bytes <= MAX_ARTIFACT_BYTES
                    or type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                    or not 0.1 <= timeout_seconds <= 30
                    or (method == "POST" and (type(body) is not bytes or len(body) > MAX_ARTIFACT_BYTES))
                    or (method == "GET" and body is not None)):
                raise ValueError
            allowed = {"content-type", "x-upsert", "cache-control"}
            if any(type(k) is not str or k.lower() not in allowed or type(v) is not str
                   or "\r" in v or "\n" in v for k, v in headers.items()):
                raise ValueError
            if method == "POST" and {k.lower(): v for k, v in headers.items()}.get("x-upsert") != "false":
                raise ValueError
            outgoing = {**headers, "Authorization": "Bearer " + self._access_token,
                        "apikey": self._api_key, "Accept-Encoding": "identity"}
            deadline = time.monotonic() + timeout_seconds
            connection = http.client.HTTPSConnection(target.hostname, timeout=timeout_seconds,
                                                       context=ssl.create_default_context())
            connection.request(method, target.path, body=body, headers=outgoing)
            response = connection.getresponse()
            pairs = response.getheaders()
            normalized = {k.lower(): v for k, v in pairs}
            if (sum(len(k) + len(v) for k, v in pairs) > 65_536
                    or sum(k.lower() == "content-length" for k, _ in pairs) > 1
                    or normalized.get("content-encoding", "identity").lower() != "identity"):
                raise ValueError
            length = normalized.get("content-length")
            if length is not None and (not length.isascii() or not length.isdecimal()
                                       or int(length) > max_response_bytes):
                raise ValueError
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(65_536, max_response_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > max_response_bytes:
                    raise ValueError
            raw = b"".join(chunks)
            if length is not None and len(raw) != int(length):
                raise ValueError
            return StorageResponse(response.status, normalized, raw)
        except Exception:
            raise _error() from None
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass


class SupabaseArtifactStore:
    def __init__(self, transport: StorageTransport, *, authorize_run: Callable[[Principal, str], Run],
                 timeout_seconds: float = 10):
        if (not callable(getattr(transport, "request", None)) or not callable(authorize_run)
                or type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0.1 <= timeout_seconds <= 30):
            raise _error("INVALID_STORAGE_CONFIG", 422)
        self._transport, self._authorize_run, self._timeout = transport, authorize_run, timeout_seconds

    def for_owner(self, principal: Principal) -> CloudOwnerArtifacts:
        return CloudOwnerArtifacts(self, Principal.model_validate(principal))

    def for_worker(self, principal: Principal) -> CloudWorkerArtifacts:
        return CloudWorkerArtifacts(self, Principal.model_validate(principal))

    def _send(self, method, key, *, raw=None, maximum=MAX_ARTIFACT_BYTES):
        url = PROJECT_ORIGIN + "/storage/v1/object/" + ("authenticated/" if method == "GET" else "") + PRIVATE_BUCKET + "/" + key
        try:
            response = self._transport.request(method, url,
                headers={"Content-Type": "application/json", "x-upsert": "false", "Cache-Control": "no-store"},
                body=raw, max_response_bytes=maximum, timeout_seconds=self._timeout, follow_redirects=False)
            if (type(response) is not StorageResponse or type(response.status) is not int
                    or not 100 <= response.status <= 599 or type(response.body) is not bytes
                    or len(response.body) > maximum or not isinstance(response.headers, Mapping)):
                raise ValueError
            headers = {k.lower(): v for k, v in response.headers.items()}
            if any(type(k) is not str or type(v) is not str for k, v in response.headers.items()):
                raise ValueError
            length = headers.get("content-length")
            if (headers.get("content-encoding", "identity").lower() != "identity"
                    or (length is not None and (not length.isascii() or not length.isdecimal()
                                               or int(length) != len(response.body)))):
                raise ValueError
            if 300 <= response.status < 400:
                raise _error("CLOUD_STORAGE_REDIRECT", 502)
            return response
        except BackendError:
            # Transport errors are not a trusted source of error text or codes.
            raise _error() from None
        except Exception:
            raise _error() from None


class CloudOwnerArtifacts:
    def __init__(self, store: SupabaseArtifactStore, principal: Principal):
        self._store, self._principal = store, principal

    def _authorize(self, run_id):
        if type(run_id) is not str or not _ID.fullmatch(run_id):
            raise _error("INVALID_ID", 422)
        try:
            run = self._store._authorize_run(self._principal, run_id)
            if not isinstance(run, Run) or run.run_id != run_id:
                raise ValueError
            return run
        except Exception:
            raise BackendError("NOT_FOUND", "Artifact not found", 404) from None

    def _key(self, run_id, name, *, private=False):
        owner = hashlib.sha256(canonical(["SS_STORAGE_OWNER_V1", self._principal.owner_id])).hexdigest()
        run = hashlib.sha256(canonical(["SS_STORAGE_RUN_V1", run_id])).hexdigest()
        return f"v1/{owner}/{run}/{'private' if private else 'report'}/{name}"

    @staticmethod
    def _reference(raw, artifact_id="report"):
        if type(raw) is not bytes or len(raw) > MAX_ARTIFACT_BYTES:
            raise _error("ARTIFACT_TOO_LARGE", 422)
        return ArtifactReference(artifact_id=artifact_id, sha256=hashlib.sha256(raw).hexdigest(),
                                 size_bytes=len(raw), media_type="application/json")

    def _read(self, key, reference):
        response = self._store._send("GET", key)
        if response.status == 404:
            raise BackendError("NOT_FOUND", "Artifact not found", 404)
        if response.status != 200:
            raise _error()
        raw = response.body
        if len(raw) != reference.size_bytes or hashlib.sha256(raw).hexdigest() != reference.sha256:
            raise _error("ARTIFACT_INTEGRITY", 409)
        return raw

    def _publish(self, key, raw, reference):
        response = self._store._send("POST", key, raw=raw, maximum=16_384)
        duplicate = response.status == 409
        if response.status == 400:
            try:
                payload = json.loads(response.body)
                duplicate = isinstance(payload, dict) and (payload.get("error") in {"Duplicate", "AssetAlreadyExists", "ResourceAlreadyExists"}
                    or payload.get("code") in {"Duplicate", "AssetAlreadyExists", "ResourceAlreadyExists"})
            except (ValueError, TypeError):
                pass
        if response.status not in {200, 201} and not duplicate:
            raise _error()
        # Both initial acknowledgement and duplicate require bounded read-back.
        # An uncertain upload is never automatically retried or overwritten.
        if self._read(key, reference) != raw:
            raise _error("ARTIFACT_INTEGRITY", 409)
        return reference

    def publish_report(self, run_id: str, report: dict) -> ArtifactReference:
        self._authorize(run_id)
        try:
            raw = canonical(sanitized_report(report))
        except Exception:
            raise _error("INVALID_REPORT", 422) from None
        return self._publish(self._key(run_id, "report.json"), raw, self._reference(raw))

    def read(self, run_id: str, reference: ArtifactReference) -> bytes:
        self._authorize(run_id)
        if (not isinstance(reference, ArtifactReference) or reference.artifact_id != "report"
                or reference.media_type != "application/json" or reference.size_bytes > MAX_ARTIFACT_BYTES):
            raise BackendError("NOT_FOUND", "Artifact not found", 404)
        raw = self._read(self._key(run_id, "report.json"), reference)
        try:
            if canonical(sanitized_report(json.loads(raw))) != raw:
                raise ValueError
        except Exception:
            raise _error("ARTIFACT_INTEGRITY", 409) from None
        return raw

    def export_bundle(self, investigation: Investigation, run: Run, events: list[LifecycleEvent]) -> bytes:
        admitted = self._authorize(run.run_id)
        if (investigation.owner_id != self._principal.owner_id
                or investigation.investigation_id != admitted.investigation_id or admitted != run):
            raise BackendError("NOT_FOUND", "Artifact not found", 404)
        raw = ArtifactStore.export_bundle(self, investigation, run, events)
        verify_bundle(raw)
        return raw


class CloudWorkerArtifacts(CloudOwnerArtifacts):
    """Trusted worker retention only; these methods are never an HTTP API."""
    def retain_private(self, run_id: str, name: str, raw: bytes, *, expected_sha256: str) -> ArtifactReference:
        self._authorize(run_id)
        if type(name) is not str or name not in PRIVATE_ARTIFACT_NAMES:
            raise _error("UNSUPPORTED_PRIVATE_ARTIFACT", 422)
        reference = self._reference(raw, "private:" + name)
        if type(expected_sha256) is not str or not _SHA.fullmatch(expected_sha256) or reference.sha256 != expected_sha256:
            raise _error("ARTIFACT_INTEGRITY", 409)
        return self._publish(self._key(run_id, name, private=True), raw, reference)

    def read_private(self, run_id: str, reference: ArtifactReference) -> bytes:
        self._authorize(run_id)
        if not isinstance(reference, ArtifactReference) or not reference.artifact_id.startswith("private:"):
            raise BackendError("NOT_FOUND", "Artifact not found", 404)
        name = reference.artifact_id.removeprefix("private:")
        if (name not in PRIVATE_ARTIFACT_NAMES or reference.media_type != "application/json"
                or reference.size_bytes > MAX_ARTIFACT_BYTES):
            raise BackendError("NOT_FOUND", "Artifact not found", 404)
        return self._read(self._key(run_id, name, private=True), reference)
