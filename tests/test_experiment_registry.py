"""Experiment registry: seeded frozen results, append-only, unknowns."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import experiment_registry as reg  # noqa: E402


def _seed():
    return reg.load_seed()


def test_seed_contains_only_verified_frozen_scores():
    registry = _seed()
    scores = {r["run_id"]: reg.display(r["held_out"]) for r in registry}
    assert scores == {
        "gemma-prior-vikunja": "0/6",
        "gemma-grounded-vikunja": "2/6",
        "gemma-hybrid-vikunja": "3/6",
        "gemma-repair-vikunja": "2/6",
        "muse-grounded-vikunja": "2/6",
        "muse-active-vikunja": "1/6",
        "compiler-vikunja": "6/6",
        "ledger-real-model-25": "14/25",
        "muse-hybrid-per-route-vikunja": "6/6",
    }
    by_id = {r["run_id"]: r for r in registry}
    assert by_id["gemma-prior-vikunja"]["provenance"] == "GEMMA_TEST"
    assert by_id["compiler-vikunja"]["provenance"] == "NON_AI"
    assert by_id["muse-grounded-vikunja"]["provenance"] == "REAL_MODEL"
    assert by_id["ledger-real-model-25"]["provenance"] == "REAL_MODEL"
    # Ledger is a different suite: never merged into the Vikunja total.
    assert by_id["ledger-real-model-25"]["target"] != "vikunja"


def test_unknown_cells_render_unknown_never_zero():
    rows = {r["run_id"]: r for r in _seed().comparison_table()}
    assert rows["gemma-prior-vikunja"]["cost_usd"] == "unknown"
    assert rows["gemma-prior-vikunja"]["public_conformance"] == "unknown"
    assert rows["gemma-hybrid-vikunja"]["public_conformance"] == "7/19"
    for row in rows.values():
        assert row["held_out"] != "unknown"  # every seed run is scored


def test_append_only_never_overwrites(tmp_path):
    registry = _seed()
    with pytest.raises(reg.DuplicateRunError):
        registry.append(copy.deepcopy(list(registry)[0]))
    path = tmp_path / "runs.jsonl"
    run = list(registry)[0]
    reg.append_jsonl(run, path)
    with pytest.raises(reg.DuplicateRunError):
        reg.append_jsonl(run, path)
    assert reg.load_jsonl(path).run_ids == (run["run_id"],)


def test_infra_and_model_failures_are_separate():
    registry = _seed()
    run = copy.deepcopy(list(registry)[0])
    run["run_id"] = "unscored-infra"
    run["held_out"] = None
    run["failure_class"] = "infrastructure"
    run["provider_failures"] = ["provider 429"]
    registry.append(run)
    assert registry.get("unscored-infra")["model_failures"] == []
    rows = {r["run_id"]: r for r in registry.comparison_table()}
    assert rows["unscored-infra"]["held_out"] == "unknown"  # not 0/6
    bad = copy.deepcopy(run)
    bad["run_id"] = "bad-infra"
    bad["provider_failures"] = []
    with pytest.raises(ValueError):
        registry.append(bad)


def test_filters_and_ablation_views_exclude_unknowns():
    registry = _seed()
    assert len(registry.filter(provenance="GEMMA_TEST")) == 4
    assert len(registry.filter(provenance="REAL_MODEL", target="vikunja")) == 3
    assert len(registry.comparison_table(arm="C_grounded")) == 2
    by_prov = {g["group"]: g for g in registry.ablation_view("provenance")}
    assert by_prov["GEMMA_TEST"]["held_out"] == "7/24"
    assert by_prov["NON_AI"]["held_out"] == "6/6"
    # REAL_MODEL ablation mixes suites only if caller asks for it;
    # target filter keeps the Vikunja ablation comparable.
    vikunja = {g["group"]: g
               for g in registry.ablation_view("provenance", target="vikunja")}
    assert vikunja["REAL_MODEL"]["held_out"] == "9/18"


def test_validation_rejects_invented_or_malformed_runs():
    registry = _seed()
    run = copy.deepcopy(list(registry)[0])
    run["run_id"] = "bad"
    run["provenance"] = "MODEL"
    with pytest.raises(ValueError):
        registry.append(run)
    run["provenance"] = "GEMMA_TEST"
    run["held_out"] = {"passed": 7, "total": 6}
    with pytest.raises(ValueError):
        registry.append(run)

