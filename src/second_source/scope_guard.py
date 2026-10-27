"""Deterministic authorization, intent and overbuild controls.

The LLM may propose actions, but must never be the enforcement authority.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from .contracts import PolicyDecision, ProposedAction, ProposedFile, ScopeContract, ScopeMode, SideEffect, TargetKind


def _match_path(path: str, patterns: tuple[str, ...]) -> bool:
    """Explicit anchored glob rules. /foo/** includes /foo itself and descendants."""
    for pattern in patterns:
        if pattern.endswith("/**") and (path == pattern[:-3] or path.startswith(pattern[:-2])):
            return True
        if pattern.endswith("/*") and not pattern.endswith("/**"):
            parent = pattern[:-2]
            if path.startswith(parent + "/") and "/" not in path[len(parent) + 1:]:
                return True
        if "*" not in pattern and path == pattern:
            return True
        # Only exact segment globs are accepted; prevent fnmatch matching slashes.
        if "*" in pattern and not pattern.endswith(("/*", "/**")):
            ps, xs = pattern.split("/"), path.split("/")
            if len(ps) == len(xs) and all(fnmatchcase(x, p) for x, p in zip(xs, ps)):
                return True
    return False


def _safe_url_path(raw: str, root: str) -> str | None:
    """Return path only for strictly same-origin URLs, with no encoded path tricks."""
    try:
        anchor = urlsplit(root)
        candidate = urlsplit(raw)
        if candidate.scheme or candidate.netloc:
            if (candidate.scheme.lower(), candidate.hostname, candidate.port) != (anchor.scheme.lower(), anchor.hostname, anchor.port):
                return None
            if candidate.username or candidate.password:
                return None
        if candidate.fragment or candidate.username or candidate.password:
            return None
        if "\\" in raw:
            return None
        path = candidate.path or "/"
        for _ in range(3):
            decoded = unquote(path)
            if decoded == path:
                break
            path = decoded
        if "%" in path or "\\" in path or "//" in path:
            return None
        components = path.split("/")
        if not path.startswith("/") or "." in components or ".." in components:
            return None
        return path.rstrip("/") or "/"
    except (ValueError, TypeError):
        return None


def allow() -> PolicyDecision:
    return PolicyDecision(allowed=True, code="ALLOWED", reason="Within authorized scope")


def deny(code: str, reason: str) -> PolicyDecision:
    return PolicyDecision(allowed=False, code=code, reason=reason)


class ScopeGuard:
    def __init__(self, contract: ScopeContract):
        self.contract = contract

    def validate_action(self, action: ProposedAction) -> PolicyDecision:
        spec, obs, exclusions = self.contract.target, self.contract.observation, self.contract.exclusions
        if action.requirement_id not in self.contract.implementation.requirements:
            return deny("REQUIREMENT_NOT_IN_SCOPE", "Action has no approved requirement")
        if action.kind not in obs.permitted_actions:
            return deny("ACTION_NOT_ALLOWED", "Action type is not on the observation allowlist")
        if action.role not in obs.allowed_roles:
            return deny("ROLE_NOT_ALLOWED", "Actor role is not explicitly authorized")
        if action.requires_auth and obs.authenticated_access == "not_required":
            return deny("AUTH_OUT_OF_SCOPE", "Authentication was not authorized or required")
        if action.side_effect == SideEffect.SENSITIVE:
            return deny("SENSITIVE_ACTION_BLOCKED", "Sensitive target effects require separate authorization and executor policy")
        if action.external_effect_name and action.external_effect_name in exclusions.external_side_effects:
            return deny("EXCLUDED_SIDE_EFFECT", "Side effect was expressly excluded")
        if action.side_effect == SideEffect.EXTERNAL_MUTATION and not action.approval_granted:
            return deny("HUMAN_APPROVAL_REQUIRED", "External mutation requires explicit operator approval")
        if spec.kind == TargetKind.CLI:
            if action.kind != "cli" or action.target not in obs.allowed_commands:
                return deny("COMMAND_NOT_ALLOWED", "Only named trusted CLI commands may run")
        else:
            if action.kind == "cli":
                return deny("WRONG_ADAPTER", "A network target cannot execute CLI commands")
            path = _safe_url_path(action.target, str(spec.reference_url))
            if path is None:
                return deny("UNSAFE_URL", "Cross-origin, malformed, or traversing URL")
            if _match_path(path, exclusions.url_patterns):
                return deny("EXCLUDED_ROUTE", "Target route is explicitly excluded")
            if not _match_path(path, obs.allowed_url_patterns):
                return deny("ROUTE_NOT_ALLOWED", "Target route is not on the observation allowlist")
        return allow()

    def validate_candidate_files(self, files: list[ProposedFile]) -> PolicyDecision:
        if self.contract.mode == ScopeMode.ANALYSIS_ONLY:
            return deny("ANALYSIS_ONLY", "Source generation was not requested")
        seen: set[str] = set()
        impl, exclusions = self.contract.implementation, self.contract.exclusions
        for file in files:
            path = file.path.replace("\\", "/")
            pp = PurePosixPath(path)
            if path.startswith("/") or path.startswith("./") or ".." in pp.parts or ":" in path or "//" in path:
                return deny("UNSAFE_OUTPUT_PATH", f"Unsafe generated output path: {file.path}")
            if path in seen:
                return deny("DUPLICATE_OUTPUT_PATH", f"Duplicate generated output: {file.path}")
            seen.add(path)
            if file.subsystem in exclusions.subsystems:
                return deny("OVERBUILD_EXCLUDED", f"Explicitly excluded subsystem: {file.subsystem}")
            if file.subsystem not in impl.allowed_subsystems:
                return deny("OVERBUILD_UNREQUESTED", f"Unrequested subsystem: {file.subsystem}")
            if not file.requirement_ids.issubset(impl.requirements):
                return deny("UNMAPPED_FILE", "Every generated file must link to approved requirements")
        return allow()
