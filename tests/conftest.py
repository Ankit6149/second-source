from pathlib import Path
import sys
import pytest

from second_source.contracts import (
    Budgets, ExclusionScope, ImplementationScope, ObservationScope,
    ScopeContract, ScopeMode, TargetKind, TargetSpec,
)
from second_source.reference import CLIReferenceAdapter

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def web_scope():
    return ScopeContract(
        target=TargetSpec(kind=TargetKind.BROWSER, reference_url="https://example.test", permission_ref="authorized-001"),
        goal="Rebuild only the public marketing website",
        mode=ScopeMode.PUBLIC_ONLY,
        observation=ObservationScope(allowed_url_patterns=("/", "/features", "/pricing", "/about"),
                                     allowed_roles=frozenset({"guest"}), permitted_actions=frozenset({"navigate", "click", "type"})),
        implementation=ImplementationScope(route_patterns=("/", "/features", "/pricing", "/about"),
                                           requirements=frozenset({"REQ-HOME", "REQ-PRICING"}),
                                           allowed_subsystems=frozenset({"website_ui", "public_navigation"})),
        exclusions=ExclusionScope(url_patterns=("/login", "/app/**", "/admin/**", "/billing/**"),
                                  subsystems=frozenset({"authentication_backend", "private_dashboard", "payments"}),
                                  external_side_effects=frozenset({"email_send", "purchase", "account_creation"})),
        budgets=Budgets(),
    )


@pytest.fixture
def cli_scope():
    return ScopeContract(
        target=TargetSpec(kind=TargetKind.CLI, reference_command_id="owned-ledger-v1", permission_ref="owned-fixture"),
        goal="Reconstruct only the synthetic ledger CLI behaviors",
        mode=ScopeMode.SELECTED_FLOWS,
        observation=ObservationScope(permitted_actions=frozenset({"cli"}), allowed_commands=frozenset({"add", "list", "total", "remove"})),
        implementation=ImplementationScope(requirements=frozenset({"REQ-LEDGER"}), allowed_subsystems=frozenset({"cli_ledger"})),
    )


@pytest.fixture
def reference():
    return CLIReferenceAdapter([sys.executable, str(ROOT / "fixtures/owned_ledger/reference.py")], cwd=ROOT)


@pytest.fixture
def faulty():
    return CLIReferenceAdapter([sys.executable, str(ROOT / "fixtures/candidates/buggy.py")], cwd=ROOT)
