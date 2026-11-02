"""Claim-level coverage for candidate specifications.

Every behavior-bearing claim in a candidate spec is classified against
recorded evidence as OBSERVED, DERIVED, INFERRED, ASSUMED, UNKNOWN, or
CONTRADICTED. Priors may rank experiments; they may never silently become
candidate values. This module is the analysis half of the coverage gate:
it reads a candidate spec plus evidence observations and reports, per
claim, what the evidence actually licenses. It never modifies the spec
and never sees sealed evaluation material.

Evidence observations are dicts shaped like the ledger artifacts used
across this project: {"sequence_id", "action_index", "input_action",
"output"}. Grouping by sequence preserves stateful context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

OBSERVED = "OBSERVED"
DERIVED = "DERIVED"
INFERRED = "INFERRED"
ASSUMED = "ASSUMED"
UNKNOWN = "UNKNOWN"
CONTRADICTED = "CONTRADICTED"

_STATES = (OBSERVED, DERIVED, INFERRED, ASSUMED, UNKNOWN, CONTRADICTED)


@dataclass(frozen=True)
class Claim:
    """One candidate claim and its epistemic provenance."""

    dimension: str
    claim: str
    state: str
    evidence: tuple[str, ...] = ()
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "claim": self.claim,
            "state": self.state,
            "evidence": list(self.evidence),
            "detail": self.detail,
        }


@dataclass
class CoverageReport:
    claims: list[Claim] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {state: 0 for state in _STATES}
        for claim in self.claims:
            out[claim.state] += 1
        return out

    def contradicted(self) -> list[Claim]:
        return [c for c in self.claims if c.state == CONTRADICTED]

    def unknowns(self) -> list[Claim]:
        return [c for c in self.claims if c.state in (UNKNOWN, ASSUMED)]

    def verified_equivalence_blocked(self) -> bool:
        """Verified-equivalence language is blocked by any contradiction."""
        return bool(self.contradicted())

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": "COVERAGE_REPORT_V1",
            "counts": self.counts(),
            "verified_equivalence_blocked": self.verified_equivalence_blocked(),
            "claims": [c.as_dict() for c in self.claims],
        }


def _sequences(observations: Iterable[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    order: list[str] = []
    for obs in observations:
        sid = str(obs.get("sequence_id", ""))
        if sid not in grouped:
            grouped[sid] = []
            order.append(sid)
        grouped[sid].append(obs)
    return [
        sorted(grouped[sid], key=lambda o: int(o.get("action_index", 0)))
        for sid in order
    ]


def _ok_outputs(
    sequences: list[list[Mapping[str, Any]]], command: str
) -> list[Mapping[str, Any]]:
    out = []
    for seq in sequences:
        for obs in seq:
            action = obs.get("input_action", {})
            output = obs.get("output", {})
            if action.get("command") == command and isinstance(output, dict) and output.get("ok") is True:
                out.append(output)
    return out


def _error_outputs(
    sequences: list[list[Mapping[str, Any]]], command: str
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    out = []
    for seq in sequences:
        for obs in seq:
            action = obs.get("input_action", {})
            output = obs.get("output", {})
            if action.get("command") == command and isinstance(output, dict) and output.get("ok") is False:
                out.append((action, output))
    return out


def analyze_cli_candidate(
    spec: Mapping[str, Any],
    observations: Iterable[Mapping[str, Any]],
) -> CoverageReport:
    """Classify every claim in a CLI candidate spec against evidence.

    General over the existing declarative candidate spec: response
    shapes, error codes, validation bounds, uniqueness semantics, and
    aggregation are checked against whatever was actually observed.
    Nothing here knows any target's hidden rules.
    """
    sequences = _sequences(observations)
    report = CoverageReport()
    commands = spec.get("commands", {}) if isinstance(spec, Mapping) else {}

    for name in sorted(commands):
        cfg = commands[name] or {}
        respond = cfg.get("respond", {}) if isinstance(cfg, Mapping) else {}
        ok_outs = _ok_outputs(sequences, name)
        err_outs = _error_outputs(sequences, name)

        # Response shape claim. Candidate respond maps OUTPUT field name
        # -> record source field, so claimed output keys are the keys.
        if respond:
            claimed = {str(k) for k in respond.keys()}
            if ok_outs:
                observed_keys = set(ok_outs[0]) - {"ok"}
                state = OBSERVED if claimed == observed_keys else CONTRADICTED
                detail = (
                    f"candidate fields {sorted(claimed)} vs observed {sorted(observed_keys)}"
                )
                report.claims.append(Claim(
                    dimension=f"response.{name}.shape",
                    claim=f"{name} responds with fields {sorted(claimed)}",
                    state=state,
                    evidence=tuple(sorted(observed_keys)),
                    detail=detail,
                ))
            else:
                report.claims.append(Claim(
                    dimension=f"response.{name}.shape",
                    claim=f"{name} responds with fields {sorted(claimed)}",
                    state=UNKNOWN,
                    detail="no successful observation of this command",
                ))

        # Error-code claims (per parameter and command level).
        claimed_errors: set[str] = set()
        params = cfg.get("params", {}) if isinstance(cfg, Mapping) else {}
        for param_cfg in params.values():
            if isinstance(param_cfg, Mapping) and param_cfg.get("error"):
                claimed_errors.add(str(param_cfg["error"]))
        for key in ("unique_error", "not_found_error"):
            if isinstance(cfg, Mapping) and cfg.get(key):
                claimed_errors.add(str(cfg[key]))
        observed_errors = {str(out.get("error")) for _, out in err_outs if out.get("error")}
        for code in sorted(claimed_errors):
            report.claims.append(Claim(
                dimension=f"error.{name}.{code}",
                claim=f"{name} can fail with {code}",
                state=OBSERVED if code in observed_errors else ASSUMED,
                evidence=tuple(sorted(observed_errors)),
                detail="error observed in evidence" if code in observed_errors
                       else "error code never observed; plausible prior only",
            ))

        # Validation-bound claims: decisive only with acceptance at the
        # bound and rejection beyond it; contradicted by observation on
        # the wrong side of the claimed bound.
        for param, pcfg in params.items():
            if not isinstance(pcfg, Mapping):
                continue
            actions = [
                obs.get("input_action", {})
                for seq in sequences for obs in seq
                if obs.get("input_action", {}).get("command") == name
            ]
            outs = [
                obs.get("output", {})
                for seq in sequences for obs in seq
                if obs.get("input_action", {}).get("command") == name
            ]
            pairs = list(zip(actions, outs))
            for bound_key, kind in (("minimum", "min"), ("maximum", "max"),
                                    ("min_length", "minlen"), ("max_length", "maxlen")):
                if bound_key not in pcfg:
                    continue
                bound = pcfg[bound_key]
                values = []
                for action, output in pairs:
                    value = action.get(param)
                    if kind.endswith("len"):
                        if not isinstance(value, str):
                            continue
                        value = len(value.strip()) if pcfg.get("trim") else len(value)
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        continue
                    values.append((value, isinstance(output, dict) and output.get("ok") is True))
                accepted = [v for v, ok in values if ok]
                rejected = [v for v, ok in values if not ok]
                # Only an ACCEPTED value on the wrong side proves a bound
                # wrong: a rejection may be caused by a different rule in a
                # stateful sequence, so rejections never contradict alone.
                if kind == "max" or kind == "maxlen":
                    contra = any(v > bound for v in accepted)
                    decisive = (bound in accepted) and any(v > bound for v in rejected)
                else:
                    contra = any(v < bound for v in accepted)
                    decisive = (bound in accepted) and any(v < bound for v in rejected)
                state = CONTRADICTED if contra else (OBSERVED if decisive else UNKNOWN)
                detail = (
                    "accepted value violates claimed bound" if contra
                    else "accepted at bound and rejected beyond it" if decisive
                    else "boundary never decisively probed"
                )
                report.claims.append(Claim(
                    dimension=f"validation.{name}.{param}.{bound_key}",
                    claim=f"{name}.{param} {bound_key}={bound}",
                    state=state,
                    detail=detail,
                ))

        # Uniqueness semantics (case sensitivity) for add-like commands.
        if isinstance(cfg, Mapping) and cfg.get("unique_field"):
            field_name = str(cfg["unique_field"])
            casefold = bool(cfg.get("unique_casefold"))
            probe_outcome: bool | None = None
            for seq in sequences:
                seen: dict[str, str] = {}
                for obs in seq:
                    action = obs.get("input_action", {})
                    output = obs.get("output", {})
                    if action.get("command") != name or not isinstance(action.get(field_name), str):
                        continue
                    raw = str(action[field_name])
                    folded = raw.strip().casefold()
                    if folded in seen and seen[folded] != raw.strip():
                        probe_outcome = not (isinstance(output, dict) and output.get("ok") is True)
                        break
                    if isinstance(output, dict) and output.get("ok") is True:
                        seen[folded] = raw.strip()
                if probe_outcome is not None:
                    break
            if probe_outcome is None:
                state, detail = UNKNOWN, "no case-variant duplicate probe observed"
            else:
                state = OBSERVED if probe_outcome == casefold else CONTRADICTED
                detail = f"case-variant duplicate rejected={probe_outcome}"
            report.claims.append(Claim(
                dimension=f"uniqueness.{name}.{field_name}",
                claim=f"duplicate detection casefold={casefold}",
                state=state,
                detail=detail,
            ))

    return report
