"""Claim-level coverage for Vikunja candidate specs (HTTP).

The CLI coverage gate (src/second_source/coverage.py) classifies spec
claims against evidence. This is the same discipline for HTTP specs:
every behavior-bearing claim in a candidate spec — route status,
validation error, permission outcome — is classified OBSERVED,
ASSUMED, UNKNOWN, or CONTRADICTED against the PUBLIC probe
observations only. Engineering priors may propose claims; only
observations may mark them OBSERVED. Held-out material is never read
here.
"""
from __future__ import annotations

import json
from pathlib import Path

OBSERVED = "OBSERVED"
ASSUMED = "ASSUMED"
UNKNOWN = "UNKNOWN"
CONTRADICTED = "CONTRADICTED"


def _matches(route_path: str, observed_action: str) -> bool:
    # Observed actions are "METHOD /path" with {pid}/{tid} templates,
    # the same templates specs use.
    parts = observed_action.split(" ", 1)
    return len(parts) == 2 and parts[1].split("?")[0] == route_path


def analyze_spec(spec: dict, observations: list[dict]) -> dict:
    claims = []

    def add(dimension, claim, state, detail=""):
        claims.append({"dimension": dimension, "claim": claim,
                       "state": state, "detail": detail})

    for route in spec.get("routes", []):
        method, path = route["method"], route["path"]
        dim = f"route.{method} {path}"
        hits = [o for o in observations
                if o["action"].startswith(method + " ") and _matches(path, o["action"])]
        statuses = {o["status"] for o in hits}
        claimed = route.get("status")
        if not hits:
            add(dim, f"{method} {path} -> {claimed}", UNKNOWN,
                "route never probed")
        elif claimed in statuses:
            add(dim, f"{method} {path} -> {claimed}", OBSERVED,
                f"observed statuses {sorted(statuses)}")
        elif statuses and all(s >= 400 for s in statuses):
            add(dim, f"{method} {path} -> {claimed}", UNKNOWN,
                f"only error statuses observed {sorted(statuses)}")
        else:
            add(dim, f"{method} {path} -> {claimed}", CONTRADICTED,
                f"observed statuses {sorted(statuses)}")

        for rule in route.get("validate", []):
            errs = [o for o in hits if o["status"] >= 400]
            if any(o["status"] == rule.get("status") for o in errs):
                add(f"{dim}.validate.{rule['field']}",
                    f"empty {rule['field']} -> {rule.get('status')}", OBSERVED)
            elif errs:
                add(f"{dim}.validate.{rule['field']}",
                    f"empty {rule['field']} -> {rule.get('status')}",
                    CONTRADICTED, f"observed error statuses "
                    f"{sorted({o['status'] for o in errs})}")
            else:
                add(f"{dim}.validate.{rule['field']}",
                    f"empty {rule['field']} -> {rule.get('status')}",
                    ASSUMED, "no validation error observed for this route")

        perm = route.get("permission")
        if perm and perm != "any_auth":
            bob = [o for o in hits if o.get("as") == "bob"]
            if perm == "owner":
                ok = any(o["status"] == 403 for o in bob)
                add(f"{dim}.permission", f"non-owner denied ({perm})",
                    OBSERVED if ok else UNKNOWN,
                    "cross-user outcome observed" if ok else
                    "no cross-user denial observed")
            elif perm == "owner_or_read":
                ok = any(o["status"] == 200 for o in bob)
                add(f"{dim}.permission", "shared read allowed",
                    OBSERVED if ok else UNKNOWN,
                    "shared read observed" if ok else
                    "no shared-read observation")
            elif perm == "owner_or_write":
                denied = any(o["status"] == 403 for o in bob)
                add(f"{dim}.permission", "read-only share cannot write",
                    OBSERVED if denied else UNKNOWN,
                    "read-only write denial observed" if denied else
                    "no read-only write attempt observed")

    counts = {s: 0 for s in (OBSERVED, ASSUMED, UNKNOWN, CONTRADICTED)}
    for claim in claims:
        counts[claim["state"]] += 1
    return {"kind": "VIKUNJA_COVERAGE_V1", "counts": counts,
            "verified_equivalence_blocked": any(
                c["state"] != OBSERVED for c in claims),
            "claims": claims}


def main() -> int:
    import sys
    root = Path(__file__).resolve().parents[1]
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    observations = json.loads(
        (root / ".runs/vikunja-benchmark/public_observations.json")
        .read_text(encoding="utf-8"))
    print(json.dumps(analyze_spec(spec, observations), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
