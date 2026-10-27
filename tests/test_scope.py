import pytest
from pydantic import ValidationError
from second_source.contracts import ProposedAction, ProposedFile, ScopeContract, SideEffect
from second_source.scope_guard import ScopeGuard


def action(target="/", kind="navigate", **kwargs):
    return ProposedAction(target=target, kind=kind, requirement_id=kwargs.pop("requirement_id", "REQ-HOME"), **kwargs)


def test_public_route_allowed(web_scope):
    assert ScopeGuard(web_scope).validate_action(action("https://example.test/features")).allowed
    assert ScopeGuard(web_scope).validate_action(action("/")).allowed


@pytest.mark.parametrize("target,expected_code", [
    ("/login", "EXCLUDED_ROUTE"),
    ("/app", "EXCLUDED_ROUTE"),
    ("/app/settings", "EXCLUDED_ROUTE"),
    ("/pricing/wrong", "ROUTE_NOT_ALLOWED"),
    ("https://evil.example.test/", "UNSAFE_URL"),
    ("https://example.test.evil.net/", "UNSAFE_URL"),
    ("https://evil.net@another.example/", "UNSAFE_URL"),
    ("//evil.net/", "UNSAFE_URL"),
    ("/%2e%2e/admin", "UNSAFE_URL"),
    ("/%252e%252e/login", "UNSAFE_URL"),
    ("/pricing#secret", "UNSAFE_URL"),
    ("/pricing\\admin", "UNSAFE_URL"),
])
def test_reject_unsafe_or_excluded_targets(web_scope, target, expected_code):
    assert ScopeGuard(web_scope).validate_action(action(target)).code == expected_code


def test_reject_unapproved_actions_and_roles(web_scope):
    guard = ScopeGuard(web_scope)
    assert guard.validate_action(action("/", kind="execute_shell")).code == "ACTION_NOT_ALLOWED"
    assert guard.validate_action(action("/", role="admin")).code == "ROLE_NOT_ALLOWED"
    assert guard.validate_action(action("/", requires_auth=True)).code == "AUTH_OUT_OF_SCOPE"
    assert guard.validate_action(action("/", requirement_id="REQ-NOPE")).code == "REQUIREMENT_NOT_IN_SCOPE"


def test_side_effect_policy(web_scope):
    guard = ScopeGuard(web_scope)
    assert guard.validate_action(action("/", side_effect=SideEffect.EXTERNAL_MUTATION)).code == "HUMAN_APPROVAL_REQUIRED"
    assert guard.validate_action(action("/", side_effect=SideEffect.SENSITIVE, approval_granted=True)).code == "SENSITIVE_ACTION_BLOCKED"
    assert guard.validate_action(action("/", external_effect_name="purchase", approval_granted=True)).code == "EXCLUDED_SIDE_EFFECT"


def test_candidate_overbuild(web_scope):
    guard = ScopeGuard(web_scope)
    files = [ProposedFile(path="src/home.tsx", subsystem="website_ui", requirement_ids=frozenset({"REQ-HOME"}))]
    assert guard.validate_candidate_files(files).allowed
    assert guard.validate_candidate_files(files + [ProposedFile(path="src/auth.ts", subsystem="authentication_backend", requirement_ids=frozenset({"REQ-HOME"}))]).code == "OVERBUILD_EXCLUDED"
    assert guard.validate_candidate_files([ProposedFile(path="src/weather.ts", subsystem="weather", requirement_ids=frozenset({"REQ-HOME"}))]).code == "OVERBUILD_UNREQUESTED"
    assert guard.validate_candidate_files([ProposedFile(path="src/home.tsx", subsystem="website_ui", requirement_ids=frozenset({"REQ-HACK"}))]).code == "UNMAPPED_FILE"


@pytest.mark.parametrize("path", ["../evil", "/tmp/file", "src/../../bad", "C:\\Windows\\file", "src//bad"])
def test_candidate_path_escape(web_scope, path):
    assert ScopeGuard(web_scope).validate_candidate_files([ProposedFile(path=path, subsystem="website_ui", requirement_ids=frozenset({"REQ-HOME"}))]).code == "UNSAFE_OUTPUT_PATH"


def test_duplicate_files(web_scope):
    file = ProposedFile(path="x.py", subsystem="website_ui", requirement_ids=frozenset({"REQ-HOME"}))
    assert ScopeGuard(web_scope).validate_candidate_files([file, file]).code == "DUPLICATE_OUTPUT_PATH"


def test_cli_requires_registered_label(cli_scope):
    guard = ScopeGuard(cli_scope)
    assert guard.validate_action(ProposedAction(kind="cli", target="add", requirement_id="REQ-LEDGER")).allowed
    assert guard.validate_action(ProposedAction(kind="cli", target="rm -rf /", requirement_id="REQ-LEDGER")).code == "COMMAND_NOT_ALLOWED"
    assert guard.validate_action(ProposedAction(kind="navigate", target="/", requirement_id="REQ-LEDGER")).code == "ACTION_NOT_ALLOWED"


def test_schema_rejects_invalid_and_scope_overlap(web_scope):
    d = web_scope.model_dump(mode="json")
    d["observation"]["authenticated_access"] = "authorized_test_account"
    with pytest.raises(ValidationError):
        ScopeContract.model_validate(d)
    d = web_scope.model_dump(mode="json")
    d["implementation"]["allowed_subsystems"].append("payments")
    with pytest.raises(ValidationError):
        ScopeContract.model_validate(d)
    d = web_scope.model_dump(mode="json")
    d["extra"] = "no"
    with pytest.raises(ValidationError):
        ScopeContract.model_validate(d)
