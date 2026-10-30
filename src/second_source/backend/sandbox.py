"""Disabled-by-default, operation-approved sandbox boundary; no engine or scorer.

Only public owned-ledger probes and admitted declarative policy bytes cross this
boundary. A reviewed template supplies the trusted runner, never model code.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
import threading
from typing import Callable, Literal, Protocol

from second_source.g2_persistence import canonical
from .contracts import ArtifactReference, BackendError

_SHA = re.compile(r"^[a-f0-9]{64}$")
_LABEL = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
RUNNER_PATH = "/opt/second-source/run-owned-ledger"
WORK_DIRECTORY = "/home/user/second-source"
INPUT_NAMES = {"candidate.v1.json": "candidate-policy", "actions.json": "public-probe-input"}
OUTPUT_NAMES = frozenset({"execution-result.json", "candidate-output.jsonl"})
_FORBIDDEN = (b"api_key", b"service_role", b"access_token", b"authorization",
              b"sealed_suite", b"gold_cases", b"expected_output", b"reference.py")


def _blocked():
    return BackendError("INVALID_SANDBOX_OPERATION", "Sandbox operation or authorization is invalid", 422)


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise _blocked()


def _digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _unique_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise _blocked()
        result[key] = value
    return result


@dataclass(frozen=True)
class ApprovedSandboxFile:
    name: str
    classification: Literal["candidate-policy", "public-probe-input"]
    data: bytes = field(repr=False)
    sha256: str

    def __post_init__(self):
        if (type(self.name) is not str or INPUT_NAMES.get(self.name) != self.classification
                or type(self.data) is not bytes or len(self.data) > 262_144
                or type(self.sha256) is not str or not _SHA.fullmatch(self.sha256)
                or hashlib.sha256(self.data).hexdigest() != self.sha256
                or any(marker in self.data.lower() for marker in _FORBIDDEN)):
            raise _blocked()
        try:
            value = json.loads(self.data, object_pairs_hook=_unique_pairs,
                parse_constant=lambda value: (_ for _ in ()).throw(_blocked()))
            if not isinstance(value, dict):
                raise _blocked()
            if self.classification == "public-probe-input":
                if set(value) != {"kind", "actions"} or value["kind"] != "PUBLIC_LEDGER_PROBES_V1":
                    raise _blocked()
                actions = value["actions"]
                if type(actions) is not list or not 1 <= len(actions) <= 100:
                    raise _blocked()
                for action in actions:
                    if (type(action) is not dict or action.get("command") not in {"add", "remove", "list", "total"}
                            or not set(action) <= {"command", "label", "amount", "id"}):
                        raise _blocked()
            # Also reject JSON numbers overflowing to infinity and bound canonical
            # data. Candidate admission remains the existing trusted engine's job.
            canonical(value)
        except Exception:
            raise _blocked() from None


@dataclass(frozen=True)
class SandboxLimits:
    cpu_count: int = 1
    memory_mb: int = 512
    lifetime_seconds: int = 60
    command_seconds: int = 10
    output_bytes: int = 65_536
    artifact_bytes: int = 262_144

    def __post_init__(self):
        for value, low, high in ((self.cpu_count, 1, 2), (self.memory_mb, 128, 1024),
            (self.lifetime_seconds, 10, 120), (self.command_seconds, 1, 30),
            (self.output_bytes, 1, 262_144), (self.artifact_bytes, 1, 524_288)):
            _integer(value, low, high)
        if self.command_seconds >= self.lifetime_seconds:
            raise _blocked()


@dataclass(frozen=True)
class TemplateCapabilityReceipt:
    provider: Literal["e2b", "fake", "daytona"]
    template_id: str
    cpu_count: int
    memory_mb: int
    runner_sha256: str
    configuration_witness_sha256: str
    operator_reviewed: bool = False
    template_contains_no_secrets: bool = False

    def __post_init__(self):
        if (self.provider not in {"e2b", "fake", "daytona"} or type(self.template_id) is not str
                or not _LABEL.fullmatch(self.template_id) or ":" in self.template_id
                or any(type(value) is not str or not _SHA.fullmatch(value)
                       for value in (self.runner_sha256, self.configuration_witness_sha256))
                or type(self.operator_reviewed) is not bool or type(self.template_contains_no_secrets) is not bool):
            raise _blocked()
        _integer(self.cpu_count, 1, 2)
        _integer(self.memory_mb, 128, 1024)

    @property
    def digest(self):
        return _digest({"kind": "SANDBOX_TEMPLATE_CAPABILITY_V1", **asdict(self)})


@dataclass(frozen=True)
class SandboxOperation:
    files: tuple[ApprovedSandboxFile, ...]
    limits: SandboxLimits = field(default_factory=SandboxLimits)
    output_names: tuple[str, ...] = ("execution-result.json",)
    kind: Literal["owned-ledger-execution"] = "owned-ledger-execution"
    network_access: Literal[False] = False

    def __post_init__(self):
        if (self.kind != "owned-ledger-execution" or self.network_access is not False
                or type(self.files) is not tuple or len(self.files) != 2
                or any(type(item) is not ApprovedSandboxFile for item in self.files)
                or {item.name for item in self.files} != set(INPUT_NAMES)
                or sum(len(item.data) for item in self.files) > 524_288
                or type(self.limits) is not SandboxLimits or type(self.output_names) is not tuple
                or len(set(self.output_names)) != len(self.output_names)
                or not 0 <= len(self.output_names) <= 2
                or any(name not in OUTPUT_NAMES for name in self.output_names)):
            raise _blocked()

    def digest(self, capability: TemplateCapabilityReceipt):
        return _digest({"kind": self.kind, "network_access": False,
            "files": sorted([{"name": item.name, "classification": item.classification,
                "sha256": item.sha256, "size_bytes": len(item.data)} for item in self.files], key=lambda item: item["name"]),
            "limits": asdict(self.limits), "output_names": list(self.output_names),
            "template_capability_digest": capability.digest, "runner_path": RUNNER_PATH})


@dataclass(frozen=True)
class SandboxAuthorization:
    operation_digest: str
    provider: Literal["e2b", "fake", "daytona"]
    grant_id: str
    approved: bool = False
    allow_provisioning: bool = False

    def __post_init__(self):
        if (type(self.operation_digest) is not str or not _SHA.fullmatch(self.operation_digest)
                or self.provider not in {"e2b", "fake", "daytona"} or type(self.grant_id) is not str
                or not _LABEL.fullmatch(self.grant_id) or type(self.approved) is not bool
                or type(self.allow_provisioning) is not bool):
            raise _blocked()


@dataclass(frozen=True)
class DownloadedSandboxArtifact:
    reference: ArtifactReference
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class SandboxExecutionReceipt:
    operation_digest: str
    provider: str
    origin: Literal["NON_AI_FAKE", "SDK_MECHANICS_UNVERIFIED"]
    status: Literal["completed", "failed", "blocked", "unknown"]
    failure_code: str | None = None
    exit_code: int | None = None
    stdout: str = field(default="", repr=False)
    stderr: str = field(default="", repr=False)
    artifacts: tuple[DownloadedSandboxArtifact, ...] = field(default=(), repr=False)
    creation_attempted: bool = False
    execution_attempted: bool = False
    cleanup_attempted: bool = False
    cleanup_succeeded: bool | None = None
    cleanup_failure_code: str | None = None
    isolation_verified: Literal[False] = False


class SandboxBackend(Protocol):
    def execute(self, operation: SandboxOperation, authorization: SandboxAuthorization) -> SandboxExecutionReceipt: ...


class _OutputLimit(Exception):
    pass


class _BoundedOutput:
    def __init__(self, maximum):
        self.maximum, self.size, self.stdout, self.stderr = maximum, 0, [], []

    def append(self, stream, text):
        if type(text) is not str:
            raise _OutputLimit
        remaining = self.maximum - self.size
        encoded = text[:remaining + 1].encode("utf-8")
        getattr(self, stream).append(encoded[:remaining])
        self.size += min(remaining, len(encoded))
        if len(text) > remaining or len(encoded) > remaining:
            raise _OutputLimit

    def text(self, stream):
        return b"".join(getattr(self, stream)).decode("utf-8", errors="ignore")


def _stream_bytes(files, path, maximum, timeout):
    stream = files.read(path, format="stream", request_timeout=timeout, gzip=False)
    result, size = [], 0
    try:
        for chunk in stream:
            if type(chunk) is not bytes:
                raise _OutputLimit
            size += len(chunk)
            if size > maximum:
                raise _OutputLimit
            result.append(chunk)
        return b"".join(result)
    finally:
        stream.close()


class E2BSandboxBackend:
    def __init__(self, capability: TemplateCapabilityReceipt, *,
                 claim_authorization: Callable[[SandboxAuthorization], bool],
                 api_key: str | None = None, sdk_factory: Callable | None = None):
        if (type(capability) is not TemplateCapabilityReceipt or capability.provider != "e2b"
                or not callable(claim_authorization) or (sdk_factory is not None and not callable(sdk_factory))
                or (api_key is not None and (type(api_key) is not str or not 1 <= len(api_key) <= 16_384
                                             or any(ord(c) < 33 or ord(c) > 126 for c in api_key)))):
            raise _blocked()
        self.capability, self._claim = capability, claim_authorization
        self._api_key, self._sdk_factory = api_key, sdk_factory
        self._used, self._lock = set(), threading.Lock()

    def _approved(self, operation, authorization):
        if type(operation) is not SandboxOperation or type(authorization) is not SandboxAuthorization:
            return False
        cap = self.capability
        if (not cap.operator_reviewed or not cap.template_contains_no_secrets
                or operation.limits.cpu_count != cap.cpu_count or operation.limits.memory_mb != cap.memory_mb
                or authorization.provider != cap.provider or authorization.approved is not True
                or authorization.allow_provisioning is not True or authorization.operation_digest != operation.digest(cap)):
            return False
        with self._lock:
            if authorization.grant_id in self._used:
                return False
            # A lost claim response can conceal a committed durable claim. Do
            # not call the authority again with this grant in this instance.
            self._used.add(authorization.grant_id)
            try:
                if self._claim(authorization) is not True:
                    return False
            except Exception:
                return False
        return True

    def execute(self, operation, authorization):
        digest = operation.digest(self.capability) if type(operation) is SandboxOperation else "0" * 64
        base = {"operation_digest": digest, "provider": self.capability.provider, "origin": "SDK_MECHANICS_UNVERIFIED"}
        if not self._approved(operation, authorization):
            return SandboxExecutionReceipt(**base, status="blocked", failure_code="AUTHORIZATION_REQUIRED")
        sandbox, creation, execution, cleanup, cleaned = None, False, False, False, None
        cleanup_failure = None
        failure, status, exit_code, artifacts = None, "unknown", None, []
        output = _BoundedOutput(operation.limits.output_bytes)
        phase = "create"
        try:
            if self._api_key is None:
                failure, status = "EXPLICIT_PROVIDER_CREDENTIAL_REQUIRED", "blocked"
            else:
                factory = self._sdk_factory
                if factory is None:
                    from e2b import Sandbox
                    factory = lambda: Sandbox
                sdk = factory()
                creation = True
                sandbox = sdk.create(template=self.capability.template_id,
                    timeout=operation.limits.lifetime_seconds, envs={}, secure=True,
                    allow_internet_access=False, lifecycle={"on_timeout": "kill", "auto_resume": False},
                    api_key=self._api_key, request_timeout=operation.limits.command_seconds)
                phase = "capability"
                info = sandbox.get_info(request_timeout=operation.limits.command_seconds)
                if (getattr(info, "template_id", None) != self.capability.template_id
                        or type(getattr(info, "cpu_count", None)) is not int or info.cpu_count != operation.limits.cpu_count
                        or type(getattr(info, "memory_mb", None)) is not int or info.memory_mb != operation.limits.memory_mb
                        or getattr(info, "allow_internet_access", None) is not False):
                    raise _blocked()
                runner = _stream_bytes(sandbox.files, RUNNER_PATH, 262_144, operation.limits.command_seconds)
                if hashlib.sha256(runner).hexdigest() != self.capability.runner_sha256:
                    raise _blocked()
                phase = "upload"
                for item in operation.files:
                    sandbox.files.write(WORK_DIRECTORY + "/" + item.name, item.data,
                                        request_timeout=operation.limits.command_seconds)
                    uploaded = _stream_bytes(sandbox.files, WORK_DIRECTORY + "/" + item.name,
                                             len(item.data), operation.limits.command_seconds)
                    if hashlib.sha256(uploaded).hexdigest() != item.sha256:
                        raise _blocked()
                phase, execution = "execute", True
                result = sandbox.commands.run(RUNNER_PATH, cwd=WORK_DIRECTORY, envs={},
                    timeout=operation.limits.command_seconds, retain_output=False,
                    on_stdout=lambda text: output.append("stdout", text),
                    on_stderr=lambda text: output.append("stderr", text))
                exit_code = getattr(result, "exit_code", None)
                if type(exit_code) is not int or not -255 <= exit_code <= 255:
                    raise _blocked()
                status, failure = ("completed", None) if exit_code == 0 else ("failed", "COMMAND_NONZERO_EXIT")
                phase = "download"
                total = 0
                for name in operation.output_names:
                    raw = _stream_bytes(sandbox.files, WORK_DIRECTORY + "/" + name,
                        operation.limits.artifact_bytes - total, operation.limits.command_seconds)
                    total += len(raw)
                    reference = ArtifactReference(artifact_id="sandbox:" + name, sha256=hashlib.sha256(raw).hexdigest(),
                        size_bytes=len(raw), media_type="application/json" if name.endswith(".json") else "application/x-ndjson")
                    artifacts.append(DownloadedSandboxArtifact(reference, raw))
        except BaseException as exc:
            if isinstance(exc, _OutputLimit):
                failure, status = "OUTPUT_OR_ARTIFACT_LIMIT", "failed"
            elif phase == "capability":
                failure, status = "TEMPLATE_CAPABILITY_UNPROVEN", "blocked"
            elif (phase == "execute" and type(getattr(exc, "exit_code", None)) is int
                  and -255 <= exc.exit_code <= 255):
                exit_code, failure, status = exc.exit_code, "COMMAND_NONZERO_EXIT", "failed"
            elif phase == "create" and not creation:
                failure, status = "SDK_UNAVAILABLE", "blocked"
            else:
                failure = {"create": "CREATE_OUTCOME_UNKNOWN", "upload": "UPLOAD_FAILED",
                           "execute": "EXECUTION_OUTCOME_UNKNOWN", "download": "ARTIFACT_READ_FAILED"}[phase]
                status = "unknown" if phase in {"create", "execute"} else "failed"
        finally:
            if sandbox is not None:
                cleanup = True
                try:
                    cleaned = sandbox.kill(request_timeout=operation.limits.command_seconds) is True
                except BaseException:
                    cleaned = False
                if not cleaned:
                    status, cleanup_failure = "unknown", "CLEANUP_UNCONFIRMED"
        return SandboxExecutionReceipt(**base, status=status, failure_code=failure, exit_code=exit_code,
            stdout=output.text("stdout"), stderr=output.text("stderr"), artifacts=tuple(artifacts),
            creation_attempted=creation, execution_attempted=execution,
            cleanup_attempted=cleanup, cleanup_succeeded=cleaned, cleanup_failure_code=cleanup_failure)


class FakeSandboxBackend:
    """Deterministic fixture output; does not run a target or assign any score."""
    def __init__(self, capability: TemplateCapabilityReceipt, *, claim_authorization,
                 stdout: str = "", stderr: str = "", exit_code: int = 0):
        if capability.provider != "fake" or type(stdout) is not str or type(stderr) is not str:
            raise _blocked()
        _integer(exit_code, -255, 255)
        # Share static approval semantics, not provider dispatch or execution.
        self.capability, self._claim = capability, claim_authorization
        self._used, self._lock = set(), threading.Lock()
        self._stdout, self._stderr, self._exit = stdout, stderr, exit_code

    _approved = E2BSandboxBackend._approved

    def execute(self, operation, authorization):
        base = {"operation_digest": operation.digest(self.capability), "provider": "fake", "origin": "NON_AI_FAKE"}
        if not self._approved(operation, authorization):
            return SandboxExecutionReceipt(**base, status="blocked", failure_code="AUTHORIZATION_REQUIRED")
        output = _BoundedOutput(operation.limits.output_bytes)
        failure = None
        try:
            output.append("stdout", self._stdout)
            output.append("stderr", self._stderr)
        except _OutputLimit:
            failure = "OUTPUT_OR_ARTIFACT_LIMIT"
        return SandboxExecutionReceipt(**base, status="failed" if failure or self._exit else "completed",
            failure_code=failure or ("COMMAND_NONZERO_EXIT" if self._exit else None), exit_code=self._exit,
            stdout=output.text("stdout"), stderr=output.text("stderr"), execution_attempted=True)


class DaytonaSandboxBackend:
    """Alternative boundary only. No verified resource/network SDK mapping yet."""
    def execute(self, operation, authorization):
        return SandboxExecutionReceipt(operation_digest=authorization.operation_digest, provider="daytona",
            origin="SDK_MECHANICS_UNVERIFIED", status="blocked", failure_code="DAYTONA_CAPABILITY_UNPROVEN")
