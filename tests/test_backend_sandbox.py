"""Synthetic approval/SDK mechanics only. No provisioning or real credentials."""
from dataclasses import replace
import hashlib
import os
import threading
from types import SimpleNamespace

import pytest

from second_source.backend import sandbox as boundary
from second_source.backend.contracts import BackendError
from second_source.g2_persistence import canonical

RUNNER = b"trusted preinstalled runner fixture; never executed locally"


def approved_file(name, value, classification):
    raw = canonical(value)
    return boundary.ApprovedSandboxFile(name, classification, raw, hashlib.sha256(raw).hexdigest())


def operation(**changes):
    files = (
        approved_file("candidate.v1.json", {"kind": "already-admitted-policy-fixture"}, "candidate-policy"),
        approved_file("actions.json", {"kind": "PUBLIC_LEDGER_PROBES_V1", "actions": [{"command": "total"}]}, "public-probe-input"),
    )
    return boundary.SandboxOperation(files, **changes)


def capability(provider="e2b", **changes):
    values = dict(provider=provider, template_id="immutable-template-fixture", cpu_count=1, memory_mb=512,
        runner_sha256=hashlib.sha256(RUNNER).hexdigest(), configuration_witness_sha256="a" * 64,
        operator_reviewed=True, template_contains_no_secrets=True)
    values.update(changes)
    return boundary.TemplateCapabilityReceipt(**values)


def authorization(op, cap, **changes):
    values = dict(operation_digest=op.digest(cap), provider=cap.provider, grant_id="synthetic-grant-1",
                  approved=True, allow_provisioning=True)
    values.update(changes)
    return boundary.SandboxAuthorization(**values)


class Claims:
    def __init__(self):
        self.used, self.lock, self.calls = set(), threading.Lock(), 0

    def __call__(self, grant):
        with self.lock:
            self.calls += 1
            if grant.grant_id in self.used:
                return False
            self.used.add(grant.grant_id)
            return True


@pytest.fixture(autouse=True)
def forbid_credential_lookup(monkeypatch):
    original = os.environ.get
    def checked(key, *args):
        if key in {"E2B_API_KEY", "DAYTONA_API_KEY", "MODEL_API_KEY", "SUPABASE_SERVICE_ROLE_KEY"}:
            pytest.fail("Sandbox boundary attempted credential lookup")
        return original(key, *args)
    monkeypatch.setattr(os.environ, "get", checked)


class Stream:
    def __init__(self, raw):
        self.raw, self.closed = raw, False

    def __iter__(self):
        yield self.raw

    def close(self):
        self.closed = True


class Files:
    def __init__(self):
        self.values = {boundary.RUNNER_PATH: RUNNER,
            boundary.WORK_DIRECTORY + "/execution-result.json": b'{"result":"SDK_FIXTURE_ONLY"}',
            boundary.WORK_DIRECTORY + "/candidate-output.jsonl": b'{"ok":true}\n'}
        self.writes, self.reads, self.streams = [], [], []
        self.tamper = False

    def write(self, path, raw, **kwargs):
        assert kwargs["request_timeout"] > 0
        self.writes.append((path, raw))
        self.values[path] = b"tampered" if self.tamper else raw

    def read(self, path, **kwargs):
        assert kwargs["format"] == "stream" and kwargs["request_timeout"] > 0
        assert kwargs["gzip"] is False
        self.reads.append(path)
        stream = Stream(self.values[path])
        self.streams.append(stream)
        return stream


class Commands:
    def __init__(self):
        self.calls, self.failure = [], None
        self.stdout, self.stderr, self.exit_code = "PUBLIC_FIXTURE_OUTPUT", "", 0

    def run(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        assert cmd == boundary.RUNNER_PATH
        assert kwargs["cwd"] == boundary.WORK_DIRECTORY and kwargs["envs"] == {}
        assert kwargs["retain_output"] is False and kwargs["timeout"] > 0
        kwargs["on_stdout"](self.stdout)
        kwargs["on_stderr"](self.stderr)
        if self.failure:
            raise self.failure
        return SimpleNamespace(exit_code=self.exit_code)


class Session:
    def __init__(self):
        self.files, self.commands = Files(), Commands()
        self.info = SimpleNamespace(template_id="immutable-template-fixture", cpu_count=1,
                                    memory_mb=512, allow_internet_access=False)
        self.kills, self.kill_failure, self.kill_result = [], None, True

    def get_info(self, **kwargs):
        assert kwargs["request_timeout"] > 0
        return self.info

    def kill(self, **kwargs):
        self.kills.append(kwargs)
        if self.kill_failure:
            raise self.kill_failure
        return self.kill_result


class SDK:
    def __init__(self, session):
        self.session, self.calls, self.failure = session, [], None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return self.session


def sdk_backend(**changes):
    cap, claims, session = capability(), Claims(), Session()
    sdk = SDK(session)
    backend = boundary.E2BSandboxBackend(cap, claim_authorization=claims,
        api_key="FAKE_CONTROL_PLANE_KEY", sdk_factory=lambda: sdk, **changes)
    return cap, claims, session, sdk, backend


def test_sdk_mechanics_exact_approval_bounded_files_and_cleanup():
    cap, claims, session, sdk, backend = sdk_backend()
    op = operation(output_names=("execution-result.json", "candidate-output.jsonl"))
    grant = authorization(op, cap)
    assert sdk.calls == []
    receipt = backend.execute(op, grant)
    assert receipt.status == "completed" and receipt.exit_code == 0
    assert receipt.origin == "SDK_MECHANICS_UNVERIFIED" and receipt.isolation_verified is False
    assert receipt.creation_attempted and receipt.execution_attempted
    assert receipt.cleanup_attempted and receipt.cleanup_succeeded
    assert sdk.calls == [{"template": cap.template_id, "timeout": 60, "envs": {}, "secure": True,
        "allow_internet_access": False, "lifecycle": {"on_timeout": "kill", "auto_resume": False},
        "api_key": "FAKE_CONTROL_PLANE_KEY", "request_timeout": 10}]
    assert len(session.files.writes) == 2 and len(session.commands.calls) == 1 and len(session.kills) == 1
    assert all(stream.closed for stream in session.files.streams)
    assert len(receipt.artifacts) == 2
    for artifact in receipt.artifacts:
        assert artifact.reference.sha256 == hashlib.sha256(artifact.data).hexdigest()
        assert artifact.reference.size_bytes == len(artifact.data)
    assert "FAKE_CONTROL_PLANE_KEY" not in repr(receipt) and "PUBLIC_FIXTURE_OUTPUT" not in repr(receipt)
    assert backend.execute(op, grant).status == "blocked"
    assert len(sdk.calls) == 1 and claims.calls == 1


@pytest.mark.parametrize("changes", [{"approved": False}, {"allow_provisioning": False},
    {"provider": "daytona"}, {"operation_digest": "0" * 64}])
def test_unapproved_or_different_operation_cannot_create_or_claim(changes):
    cap, claims, _, sdk, backend = sdk_backend()
    op = operation()
    receipt = backend.execute(op, authorization(op, cap, **changes))
    assert receipt.status == "blocked" and receipt.failure_code == "AUTHORIZATION_REQUIRED"
    assert not receipt.creation_attempted and claims.calls == 0 and sdk.calls == []


def test_changed_input_limits_outputs_and_capability_invalidate_exact_grant():
    cap, claims, _, sdk, backend = sdk_backend()
    op = operation()
    grant = authorization(op, cap)
    probes = approved_file("actions.json", {"kind": "PUBLIC_LEDGER_PROBES_V1", "actions": [{"command": "list"}]}, "public-probe-input")
    for changed in (replace(op, files=(op.files[0], probes)), replace(op, limits=boundary.SandboxLimits(command_seconds=11)),
                    replace(op, output_names=())):
        assert backend.execute(changed, grant).status == "blocked"
    changed_cap = replace(cap, configuration_witness_sha256="b" * 64)
    changed_backend = boundary.E2BSandboxBackend(changed_cap, claim_authorization=claims,
        api_key="FAKE_CONTROL_PLANE_KEY", sdk_factory=lambda: sdk)
    assert changed_backend.execute(op, grant).status == "blocked"
    assert sdk.calls == [] and claims.calls == 0


@pytest.mark.parametrize("field,value", [("operator_reviewed", False), ("template_contains_no_secrets", False),
    ("cpu_count", 2), ("memory_mb", 1024)])
def test_unreviewed_or_mismatched_template_caps_block_before_provisioning(field, value):
    cap = capability(**{field: value})
    sdk, claims = SDK(Session()), Claims()
    backend = boundary.E2BSandboxBackend(cap, claim_authorization=claims, api_key="FAKE", sdk_factory=lambda: sdk)
    op = operation()
    assert backend.execute(op, authorization(op, cap)).status == "blocked"
    assert sdk.calls == [] and claims.calls == 0


@pytest.mark.parametrize("field,value", [("cpu_count", None), ("cpu_count", True), ("memory_mb", 1024),
    ("template_id", "mutable-or-other-template"), ("allow_internet_access", None), ("allow_internet_access", True)])
def test_unproven_live_capability_never_uploads_or_executes_and_always_cleans(field, value):
    cap, _, session, _, backend = sdk_backend()
    setattr(session.info, field, value)
    op = operation()
    result = backend.execute(op, authorization(op, cap))
    assert result.status == "blocked" and result.failure_code == "TEMPLATE_CAPABILITY_UNPROVEN"
    assert session.files.writes == [] and session.commands.calls == []
    assert result.cleanup_succeeded and len(session.kills) == 1


@pytest.mark.parametrize("fault", ["runner", "upload", "command", "interrupt", "download", "output", "artifact"])
def test_failure_paths_preserve_bounded_output_and_finally_cleanup(fault):
    cap, _, session, _, backend = sdk_backend()
    op = operation(limits=boundary.SandboxLimits(output_bytes=16, artifact_bytes=64))
    if fault == "runner":
        session.files.values[boundary.RUNNER_PATH] = b"UNAPPROVED_RUNNER"
    if fault == "upload":
        session.files.tamper = True
    if fault == "command":
        session.commands.failure = RuntimeError("SECRET_PROVIDER_ERROR_SENTINEL")
    if fault == "interrupt":
        session.commands.failure = KeyboardInterrupt("SECRET_PROVIDER_ERROR_SENTINEL")
    if fault == "download":
        del session.files.values[boundary.WORK_DIRECTORY + "/execution-result.json"]
    if fault == "output":
        session.commands.stdout = "x" * 1000
    else:
        session.commands.stdout = "small"
    if fault == "artifact":
        session.files.values[boundary.WORK_DIRECTORY + "/execution-result.json"] = b"x" * 1000
    result = backend.execute(op, authorization(op, cap))
    assert result.status != "completed" and result.failure_code
    assert result.cleanup_attempted and result.cleanup_succeeded and len(session.kills) == 1
    assert len(result.stdout.encode()) + len(result.stderr.encode()) <= 16
    assert "SECRET_PROVIDER_ERROR" not in repr(result)
    assert all(stream.closed for stream in session.files.streams)
    if fault in {"runner", "upload"}:
        assert not result.execution_attempted and session.commands.calls == []


def test_uncertain_create_consumes_grant_without_retry_or_fallback():
    cap, claims, _, sdk, backend = sdk_backend()
    sdk.failure = RuntimeError("SECRET_CREATE_ERROR")
    op = operation()
    grant = authorization(op, cap)
    receipt = backend.execute(op, grant)
    assert receipt.status == "unknown" and receipt.failure_code == "CREATE_OUTCOME_UNKNOWN"
    assert receipt.creation_attempted and not receipt.execution_attempted
    assert not receipt.cleanup_attempted and receipt.cleanup_succeeded is None
    assert backend.execute(op, grant).status == "blocked" and len(sdk.calls) == 1
    assert claims.calls == 1 and "SECRET_CREATE_ERROR" not in repr(receipt)


def test_cleanup_failure_is_independently_recorded_without_hiding_execution_failure():
    cap, _, session, _, backend = sdk_backend()
    session.commands.failure = RuntimeError("SECRET_COMMAND_ERROR")
    session.kill_failure = RuntimeError("SECRET_CLEANUP_ERROR")
    op = operation()
    result = backend.execute(op, authorization(op, cap))
    assert result.status == "unknown" and result.failure_code == "EXECUTION_OUTCOME_UNKNOWN"
    assert result.cleanup_failure_code == "CLEANUP_UNCONFIRMED" and result.cleanup_succeeded is False
    assert "SECRET_" not in repr(result)


def test_known_nonzero_exit_is_reported_and_cleanup_false_remains_unknown():
    cap, _, session, _, backend = sdk_backend()
    session.commands.exit_code = 7
    session.kill_result = False
    op = operation()
    result = backend.execute(op, authorization(op, cap))
    assert result.exit_code == 7 and result.failure_code == "COMMAND_NONZERO_EXIT"
    assert result.status == "unknown" and result.cleanup_failure_code == "CLEANUP_UNCONFIRMED"


@pytest.mark.parametrize("name", ["reference.py", "candidate.py", "../actions.json", "/etc/passwd", "suite.json", ".env", "MODEL_API_KEY"])
def test_source_secret_and_sealed_file_names_fail_closed(name):
    raw = b"{}"
    with pytest.raises(BackendError):
        boundary.ApprovedSandboxFile(name, "candidate-policy", raw, hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize("value", [
    {"kind": "SEALED_SUITE", "actions": [{"command": "total"}]},
    {"kind": "PUBLIC_LEDGER_PROBES_V1", "actions": [{"command": "shell", "cmd": "env"}]},
    {"kind": "PUBLIC_LEDGER_PROBES_V1", "actions": [{"command": "total", "expected_output": {}}]},
    {"kind": "PUBLIC_LEDGER_PROBES_V1", "actions": []},
    {"kind": "PUBLIC_LEDGER_PROBES_V1", "actions": [{"command": "add", "label": "api_key=secret"}]},
])
def test_only_explicit_approved_public_ledger_probe_input_is_allowed(value):
    with pytest.raises(BackendError):
        approved_file("actions.json", value, "public-probe-input")


def test_hash_size_duplicate_json_and_output_paths_fail_closed():
    with pytest.raises(BackendError):
        boundary.ApprovedSandboxFile("candidate.v1.json", "candidate-policy", b"{}", "0" * 64)
    for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b" " * 262_145):
        with pytest.raises(BackendError):
            boundary.ApprovedSandboxFile("candidate.v1.json", "candidate-policy", raw, hashlib.sha256(raw).hexdigest())
    for outputs in (("suite.json",), ("../execution-result.json",), ("execution-result.json",) * 2):
        with pytest.raises(BackendError):
            operation(output_names=outputs)
    with pytest.raises(BackendError):
        operation(network_access=True)
    with pytest.raises(TypeError):
        boundary.SandboxOperation(files=operation().files, command="arbitrary shell")


def test_durable_claim_prevents_replay_across_adapter_instances_and_no_auto_credentials():
    cap, claims = capability(), Claims()
    sdk = SDK(Session())
    op = operation()
    grant = authorization(op, cap)
    first = boundary.E2BSandboxBackend(cap, claim_authorization=claims, sdk_factory=lambda: sdk)
    receipt = first.execute(op, grant)
    assert receipt.status == "blocked" and receipt.failure_code == "EXPLICIT_PROVIDER_CREDENTIAL_REQUIRED"
    assert sdk.calls == []
    restarted = boundary.E2BSandboxBackend(cap, claim_authorization=claims, api_key="FAKE", sdk_factory=lambda: sdk)
    assert restarted.execute(op, grant).status == "blocked" and sdk.calls == []


def test_uncertain_authority_claim_is_not_retried_or_exposed():
    cap, op, calls = capability(), operation(), []
    sdk = SDK(Session())
    def uncertain(grant):
        calls.append(grant)
        raise RuntimeError("SECRET_CLAIM_TRANSACTION_SENTINEL")
    backend = boundary.E2BSandboxBackend(cap, claim_authorization=uncertain,
        api_key="FAKE", sdk_factory=lambda: sdk)
    grant = authorization(op, cap)
    for _ in range(2):
        result = backend.execute(op, grant)
        assert result.status == "blocked" and "SECRET_CLAIM" not in repr(result)
    assert len(calls) == 1 and sdk.calls == []


def test_fake_is_deterministic_non_ai_and_daytona_is_explicitly_disabled():
    cap, op = capability("fake"), operation()
    grant = authorization(op, cap)
    first = boundary.FakeSandboxBackend(cap, claim_authorization=Claims(), stdout="FIXTURE_ONLY")
    second = boundary.FakeSandboxBackend(cap, claim_authorization=Claims(), stdout="FIXTURE_ONLY")
    result = first.execute(op, grant)
    assert result == second.execute(op, grant)
    assert result.origin == "NON_AI_FAKE" and result.stdout == "FIXTURE_ONLY"
    assert result.isolation_verified is False and not result.creation_attempted
    assert first.execute(op, grant).status == "blocked"
    daytona = boundary.DaytonaSandboxBackend().execute(op, authorization(op, capability("daytona")))
    assert daytona.status == "blocked" and daytona.failure_code == "DAYTONA_CAPABILITY_UNPROVEN"
    assert not daytona.creation_attempted and not daytona.execution_attempted
