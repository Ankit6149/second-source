"""Target + adapter registry. Registration never authorizes execution."""
from __future__ import annotations
from second_source.g2_persistence import scope_digest_of
from second_source.backend.contracts import BackendError
from .schemas import TargetRegistrationV1

_ADAPTERS: dict[str, dict] = {
    "mock-adapter": {"adapter_id": "mock-adapter", "kind": "mock", "real": False, "paid": False},
    "http-probe-adapter": {"adapter_id": "http-probe-adapter", "kind": "http", "real": False, "paid": False},
}

class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters = dict(_ADAPTERS)

    def register(self, adapter_id: str, kind: str, *, real: bool = False, paid: bool = False) -> None:
        if paid and real:
            # Paid adapters may be registered but stay disabled without packet (guard).
            pass
        self._adapters[adapter_id] = {"adapter_id": adapter_id, "kind": kind, "real": real, "paid": paid}

    def get(self, adapter_id: str) -> dict:
        if adapter_id not in self._adapters:
            raise BackendError("UNKNOWN_ADAPTER", "Adapter is not registered", 422)
        return dict(self._adapters[adapter_id])

    def list(self) -> list[dict]:
        return [dict(v) for v in self._adapters.values()]

class TargetRegistry:
    def __init__(self, adapters: AdapterRegistry | None = None) -> None:
        self.adapters = adapters or AdapterRegistry()
        self._targets: dict[str, TargetRegistrationV1] = {}

    def register_target(self, target_id: str, label: str, adapter_id: str, scope,
                        *, execution_enabled: bool = False) -> TargetRegistrationV1:
        self.adapters.get(adapter_id)  # fail closed on unknown adapter
        digest = scope_digest_of(scope).removeprefix("sha256:")
        reg = TargetRegistrationV1(target_id=target_id, label=label, adapter_id=adapter_id,
                                   scope=scope, scope_digest=digest,
                                   execution_enabled=execution_enabled)
        self._targets[target_id] = reg
        return reg

    def get(self, target_id: str) -> TargetRegistrationV1:
        if target_id not in self._targets:
            raise BackendError("UNSUPPORTED_TARGET", "Requested target is not supported", 422)
        return self._targets[target_id]

    def list(self) -> list[TargetRegistrationV1]:
        return list(self._targets.values())

    def assert_authorized(self, target_id: str, scope, scope_digest: str) -> TargetRegistrationV1:
        reg = self.get(target_id)
        expected = scope_digest_of(scope).removeprefix("sha256:")
        if expected != reg.scope_digest or scope_digest != reg.scope_digest:
            raise BackendError("SCOPE_MISMATCH", "Approval does not match registered target scope", 409)
        return reg

def default_registry() -> TargetRegistry:
    """Seed the two existing owned fixtures (same scopes as backend/api.py)."""
    from second_source.reconstruct import create_scope
    from second_source.g4_http_reconstruct import create_g4_http_scope
    reg = TargetRegistry()
    reg.register_target("owned-ledger-v1", "Owned ledger fixture", "mock-adapter",
                        create_scope(0), execution_enabled=True)
    reg.register_target("owned-http-task-workflow-v1", "Owned HTTP task-workflow fixture",
                        "http-probe-adapter", create_g4_http_scope(0), execution_enabled=True)
    return reg
