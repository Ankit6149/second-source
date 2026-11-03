"""Append-only experiment registry + comparison/ablation data slice.

Stores every genuine run once; history is never overwritten. Unknown
values stay ``None`` and render as ``"unknown"`` in comparison rows --
they are never coerced to 0. Infrastructure (provider) failures are
kept separate from model failures, and an unscored run (held_out=None)
is never reported as 0.

Seed data (``experiment_registry_seed.json``) contains only verified
frozen results; see that file's ``_source`` notes per run.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

UNKNOWN_LABEL = "unknown"
PROVENANCES = ("REAL_MODEL", "GEMMA_TEST", "NON_AI")
FAILURE_CLASSES = ("none", "infrastructure", "model", "evaluator")
FIDELITY_DIMENSIONS = (
    "multi_step", "state", "field", "schema",
    "error", "auth", "visual", "temporal",
)

RUN_FIELDS = (
    "run_id", "target", "target_version", "reference_hash",
    "candidate_hash", "model", "provider", "model_version", "arm",
    "budget", "probe_strategy", "probes", "observations", "coverage",
    "unknown_claims", "contradicted_claims", "model_calls", "tokens",
    "cost_usd", "latency_ms", "compile_status", "public_conformance",
    "held_out", "fidelity", "repairs", "regressions",
    "provider_failures", "model_failures", "failure_class",
    "evaluator_version", "provenance", "reproducibility", "source_refs",
)


class DuplicateRunError(ValueError):
    """Raised when a run_id is appended twice (history is immutable)."""


def _score(value, field):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"passed", "total"}:
        raise ValueError(f"{field} must be {{passed, total}} or None")
    passed, total = value["passed"], value["total"]
    if not isinstance(passed, int) or not isinstance(total, int):
        raise ValueError(f"{field} passed/total must be ints")
    if total <= 0 or not 0 <= passed <= total:
        raise ValueError(f"{field} must satisfy 0 <= passed <= total, total > 0")
    return {"passed": passed, "total": total}


def validate_run(run: dict) -> dict:
    """Return a normalized deep copy; raise ValueError on bad shape."""
    if not isinstance(run, dict):
        raise ValueError("run must be a dict")
    missing = [f for f in RUN_FIELDS if f not in run]
    extra = [f for f in run if f not in RUN_FIELDS]
    if missing:
        raise ValueError(f"run missing fields: {missing}")
    if extra:
        raise ValueError(f"run has unknown fields: {extra}")
    out = copy.deepcopy(run)
    if not isinstance(out["run_id"], str) or not out["run_id"]:
        raise ValueError("run_id must be a non-empty string")
    if out["provenance"] not in PROVENANCES:
        raise ValueError(f"provenance must be one of {PROVENANCES}")
    if out["failure_class"] not in FAILURE_CLASSES:
        raise ValueError(f"failure_class must be one of {FAILURE_CLASSES}")
    out["held_out"] = _score(out["held_out"], "held_out")
    out["public_conformance"] = _score(
        out["public_conformance"], "public_conformance")
    fidelity = out["fidelity"]
    if fidelity is not None:
        if not isinstance(fidelity, dict) or set(fidelity) != set(FIDELITY_DIMENSIONS):
            raise ValueError(
                f"fidelity must cover exactly {FIDELITY_DIMENSIONS} or be None")
        for dim, val in fidelity.items():
            if val is not None:
                fidelity[dim] = _score(val, f"fidelity.{dim}")
    # Infra/model separation: a classified failure needs its own list.
    if out["failure_class"] == "infrastructure" and not out["provider_failures"]:
        raise ValueError("infrastructure failure requires provider_failures")
    if out["failure_class"] == "model" and not out["model_failures"]:
        raise ValueError("model failure requires model_failures")
    return out


def display(value) -> str:
    if value is None:
        return UNKNOWN_LABEL
    if isinstance(value, dict) and set(value) == {"passed", "total"}:
        return f"{value['passed']}/{value['total']}"
    return str(value)


class ExperimentRegistry:
    """In-memory append-only registry; run_ids are immutable."""

    def __init__(self, runs=()):
        self._runs: list[dict] = []
        self._ids: set[str] = set()
        for run in runs:
            self.append(run)

    def __len__(self):
        return len(self._runs)

    def __iter__(self):
        return iter(copy.deepcopy(self._runs))

    @property
    def run_ids(self):
        return tuple(r["run_id"] for r in self._runs)

    def get(self, run_id):
        for run in self._runs:
            if run["run_id"] == run_id:
                return copy.deepcopy(run)
        return None

    def append(self, run: dict) -> dict:
        normalized = validate_run(run)
        run_id = normalized["run_id"]
        if run_id in self._ids:
            raise DuplicateRunError(
                f"run_id {run_id!r} already registered; history is never overwritten")
        self._ids.add(run_id)
        self._runs.append(normalized)
        return copy.deepcopy(normalized)

    def filter(self, provenance=None, arm=None, target=None, model=None,
               provider=None, failure_class=None, probe_strategy=None):
        criteria = {"provenance": provenance, "arm": arm, "target": target,
                    "model": model, "provider": provider,
                    "failure_class": failure_class,
                    "probe_strategy": probe_strategy}
        active = {k: v for k, v in criteria.items() if v is not None}
        return [copy.deepcopy(r) for r in self._runs
                if all(r[k] == v for k, v in active.items())]

    def comparison_table(self, **filters) -> list[dict]:
        rows = []
        for run in self.filter(**filters):
            rows.append({
                "run_id": run["run_id"],
                "target": display(run["target"]),
                "arm": display(run["arm"]),
                "provenance": run["provenance"],
                "model": display(run["model"]),
                "held_out": display(run["held_out"]),
                "public_conformance": display(run["public_conformance"]),
                "model_calls": display(run["model_calls"]),
                "cost_usd": display(run["cost_usd"]),
                "failure_class": run["failure_class"],
                "compile_status": display(run["compile_status"]),
            })
        return rows

    def ablation_view(self, group_by="arm", **filters) -> list[dict]:
        if group_by not in ("arm", "provenance", "probe_strategy", "model", "target"):
            raise ValueError(f"cannot ablate by {group_by!r}")
        groups: dict[str, dict] = {}
        for run in self.filter(**filters):
            key = display(run[group_by])
            group = groups.setdefault(key, {
                "group": key, "runs": 0, "scored_runs": 0,
                "held_out_passed": 0, "held_out_total": 0})
            group["runs"] += 1
            if run["held_out"] is not None:  # unknown excluded, never 0
                group["scored_runs"] += 1
                group["held_out_passed"] += run["held_out"]["passed"]
                group["held_out_total"] += run["held_out"]["total"]
        for group in groups.values():
            total = group["held_out_total"]
            group["held_out"] = (
                f"{group['held_out_passed']}/{total}" if total else UNKNOWN_LABEL)
            group["held_out_rate"] = (
                group["held_out_passed"] / total if total else None)
        return [groups[k] for k in sorted(groups)]


def default_seed_path() -> Path:
    return Path(__file__).resolve().parent / "experiment_registry_seed.json"


def load_seed(path=None) -> ExperimentRegistry:
    data = json.loads(Path(path or default_seed_path()).read_text(encoding="utf-8"))
    return ExperimentRegistry(data["runs"])


def append_jsonl(registry_run: dict, path) -> dict:
    """Persist one run as a JSON line; refuses to overwrite an id on disk."""
    run = validate_run(registry_run)
    path = Path(path)
    existing = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.add(json.loads(line)["run_id"])
    if run["run_id"] in existing:
        raise DuplicateRunError(
            f"run_id {run['run_id']!r} already on disk; history is never overwritten")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run, sort_keys=True) + "\n")
    return run


def load_jsonl(path) -> ExperimentRegistry:
    registry = ExperimentRegistry()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            registry.append(json.loads(line))
    return registry
