"""Controlled NON_AI experiment: prior-guess synthesis vs coverage+grounded.

Question: on fresh targets, does (a) a generic dimension-probe ladder plus
(b) a deterministic evidence-only synthesizer beat a prior-driven spec
(the genuine Meta candidate's approach) under the same evaluator?

NOT a model result: both synthesizers are deterministic engineering
controls. The genuine Meta baseline is the historical candidate spec
itself (14/25 sealed, reproduced here only on public held-out cases).
Held-out cases are disjoint from probe sequences. No sealed material.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from second_source.candidate_runtime import CandidateInterpreter
from second_source.candidate_spec import load_candidate
from second_source.contracts import (
    ImplementationScope, ObservationScope, ScopeContract, ScopeMode,
    TargetKind, TargetSpec,
)
from second_source.coverage import analyze_cli_candidate

SCOPE = ScopeContract(
    target=TargetSpec(kind=TargetKind.CLI, reference_command_id="owned-ledger-v1", permission_ref="owned-fixture"),
    goal="Controlled coverage experiment on owned fixtures",
    mode=ScopeMode.SELECTED_FLOWS,
    observation=ObservationScope(permitted_actions=frozenset({"cli"}), allowed_commands=frozenset({"add", "list", "total", "remove"})),
    implementation=ImplementationScope(requirements=frozenset({"REQ-LEDGER"}), allowed_subsystems=frozenset({"cli_ledger"})),
)

TARGETS = {
    "ledger": ROOT / "fixtures/owned_ledger/reference.py",
    "ledger_variant": ROOT / "fixtures/owned_ledger_variant/reference.py",
}

PROBES = [
    [{"command": "add", "label": "Milk", "amount": 2}, {"command": "list"}, {"command": "total"}],
    [{"command": "add", "label": "Milk", "amount": 2}, {"command": "add", "label": "Milk", "amount": 3}],
    [{"command": "add", "label": "Milk", "amount": 2}, {"command": "add", "label": "MILK", "amount": 3}],
    [{"command": "add", "label": "", "amount": 2}, {"command": "add", "label": "   ", "amount": 2}],
    [{"command": "add", "label": "A", "amount": 0}, {"command": "add", "label": "A", "amount": -5}, {"command": "add", "label": "A", "amount": 1}],
    [{"command": "add", "label": "A", "amount": 100}, {"command": "add", "label": "B", "amount": 101},
     {"command": "add", "label": "C", "amount": 500}, {"command": "add", "label": "D", "amount": 501},
     {"command": "add", "label": "E", "amount": 100000}],
    [{"command": "add", "label": "x" * n, "amount": 1} for n in (24, 25, 48, 49, 100, 101)],
    [{"command": "add", "label": "Milk", "amount": 2}, {"command": "remove", "id": "1"},
     {"command": "remove", "id": "1"}, {"command": "remove", "id": "999"}, {"command": "total"}],
    [{"command": "bogus"}],
    [{"command": "add", "label": "  Pad  ", "amount": 2}, {"command": "list"}],
]

HELD_OUT = [
    [{"command": "add", "label": "Eggs", "amount": 12}, {"command": "add", "label": "Ham", "amount": 30}, {"command": "total"}],
    [{"command": "add", "label": "Eggs", "amount": 12}, {"command": "add", "label": "eggs", "amount": 5}],
    [{"command": "add", "label": "Eggs", "amount": 12}, {"command": "add", "label": "Eggs", "amount": 5}],
    [{"command": "add", "label": "Z", "amount": 99}, {"command": "add", "label": "Y", "amount": 100}, {"command": "total"}],
    [{"command": "add", "label": "Z", "amount": 250}, {"command": "add", "label": "Y", "amount": 499}, {"command": "total"}],
    [{"command": "add", "label": "Z", "amount": 500}, {"command": "add", "label": "Y", "amount": 750}],
    [{"command": "add", "label": "q" * 20, "amount": 3}, {"command": "add", "label": "q" * 30, "amount": 3}],
    [{"command": "add", "label": "q" * 47, "amount": 3}, {"command": "add", "label": "q" * 60, "amount": 3}],
    [{"command": "add", "label": "Solo", "amount": 7}, {"command": "remove", "id": "1"}, {"command": "list"}, {"command": "total"}],
    [{"command": "add", "label": "Solo", "amount": 7}, {"command": "remove", "id": "42"}],
    [{"command": "add", "label": "  Trim Me  ", "amount": 4}, {"command": "list"}],
    [{"command": "add", "label": "Zero", "amount": 0}],
    [{"command": "add", "label": "", "amount": 5}],
    [{"command": "bogus", "label": "x"}],
    [{"command": "add", "label": "One", "amount": 1}, {"command": "add", "label": "Two", "amount": 2},
     {"command": "remove", "id": "1"}, {"command": "add", "label": "One", "amount": 9}, {"command": "total"}],
    [{"command": "list"}, {"command": "total"}],
]


def run_reference(path: Path, actions: list[dict]) -> list[dict]:
    inp = "".join(json.dumps(a) + "\n" for a in actions)
    proc = subprocess.run([sys.executable, str(path)], input=inp,
                          capture_output=True, text=True, cwd=ROOT)
    return [json.loads(line) for line in proc.stdout.strip().splitlines()]


def collect_observations(path: Path) -> list[dict]:
    obs = []
    for i, seq in enumerate(PROBES):
        outs = run_reference(path, seq)
        for j, (action, output) in enumerate(zip(seq, outs)):
            obs.append({"sequence_id": f"probe-{i}", "action_index": j,
                        "input_action": action, "output": output})
    return obs


def grounded_spec(obs: list[dict]) -> dict:
    """Deterministic evidence-only synthesizer (NON_AI grounded control)."""
    def outs(cmd, ok=None):
        return [o["output"] for o in obs if o["input_action"].get("command") == cmd
                and (ok is None or o["output"].get("ok") is ok)]

    def first_err(cmd, pred):
        for o in obs:
            if o["input_action"].get("command") == cmd and o["output"].get("ok") is False and pred(o["input_action"]):
                return o["output"].get("error")
        return None

    add_ok = outs("add", True)
    respond_add = {k: k for k in (add_ok[0] if add_ok else {}) if k != "ok"} or {"id": "id"}
    list_ok = outs("list", True)
    respond_list = {"items": "items"} if list_ok and "items" in list_ok[0] else {}
    total_ok = outs("total", True)
    respond_total = {k: k for k in (total_ok[0] if total_ok else {}) if k != "ok"}
    remove_ok = outs("remove", True)
    _fields = {"id", "label", "amount"}
    respond_remove = {
        k: (k if k in _fields else "id")
        for k in (remove_ok[0] if remove_ok else {}) if k != "ok"
    } or {"id": "id"}

    label_err = first_err("add", lambda a: not str(a.get("label", "")).strip()) or "invalid_label"
    amount_err = first_err("add", lambda a: isinstance(a.get("amount"), int) and a.get("amount", 1) < 1) or "invalid_amount"
    dup_err = None
    casefold = False
    seen: dict[str, str] = {}
    for o in obs:
        a, out = o["input_action"], o["output"]
        if a.get("command") != "add" or not isinstance(a.get("label"), str):
            continue
        raw = a["label"].strip()
        if raw.casefold() in seen and seen[raw.casefold()] != raw and out.get("ok") is False:
            casefold, dup_err = True, out.get("error")
        if raw in seen.values() and out.get("ok") is False and dup_err is None:
            dup_err = out.get("error")
        if out.get("ok") is True:
            seen[raw.casefold()] = raw
    dup_err = dup_err or "duplicate_label"
    notfound_err = first_err("remove", lambda a: True) or "not_found"

    def bound(param, lengths=False):
        acc, rej = [], []
        for o in obs:
            a, out = o["input_action"], o["output"]
            if a.get("command") != "add":
                continue
            v = a.get(param)
            v = len(str(v).strip()) if lengths and isinstance(v, str) else v
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            (acc if out.get("ok") is True else rej).append(v)
        return (max(acc) if acc else None), (min(rej) if rej else None)

    amt_acc, amt_rej = bound("amount")
    lab_acc, lab_rej = bound("label", lengths=True)
    amount_max = amt_acc if amt_acc is not None else 1000000
    if amt_rej is not None and amt_rej - 1 >= (amt_acc or 0):
        amount_max = amt_rej - 1 if amt_rej - 1 >= (amt_acc or 0) else amount_max
    label_max = lab_acc if lab_acc is not None else 100
    if lab_rej is not None and lab_rej - 1 >= (lab_acc or 0):
        label_max = lab_rej - 1

    return {
        "spec_version": "1", "subsystem": "cli_ledger", "requirement_ids": ["REQ-LEDGER"],
        "unknown_command_error": first_err("bogus", lambda a: True) or "unknown_command",
        "invalid_input_error": "invalid_input",
        "commands": {
            "add": {
                "params": {
                    "label": {"type": "string", "required": True, "trim": True,
                              "min_length": 1, "max_length": int(label_max), "error": label_err},
                    "amount": {"type": "integer", "required": True, "minimum": 1,
                               "maximum": int(amount_max), "error": amount_err},
                },
                "unique_field": "label", "unique_casefold": casefold, "unique_error": dup_err,
                "store_record": True, "respond": respond_add,
            },
            "list": {"respond": respond_list},
            "total": {"aggregate_count": True, "aggregate_sum_field": "amount", "respond": respond_total},
            "remove": {
                "params": {"id": {"type": "string", "required": True, "error": notfound_err}},
                "lookup_by": "id", "lookup_param": "id", "not_found_error": notfound_err,
                "delete_after_lookup": True, "respond": respond_remove,
            },
        },
    }


def evaluate(spec_doc: dict, path: Path) -> tuple[int, int]:
    interp = CandidateInterpreter(load_candidate(spec_doc, SCOPE).spec)
    passed = 0
    for actions in HELD_OUT:
        ref = run_reference(path, actions)
        interp.reset()
        cand = [o.output for o in interp.execute_sequence(actions, sequence_id="held").observations]
        if ref == cand:
            passed += 1
    return passed, len(HELD_OUT)


def main() -> int:
    prior_path = ROOT / "docs/evidence/g3-rev6-sanitized/candidate.v1.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else None
    results = {}
    for name, path in TARGETS.items():
        obs = collect_observations(path)
        grounded = grounded_spec(obs)
        entry = {"probes": len(PROBES), "observations": len(obs)}
        if prior is not None:
            p, n = evaluate(prior, path)
            entry["prior_guess"] = {"passed": p, "total": n, "coverage": analyze_cli_candidate(prior, obs).counts()}
        g, n = evaluate(grounded, path)
        entry["grounded"] = {"passed": g, "total": n, "coverage": analyze_cli_candidate(grounded, obs).counts()}
        results[name] = entry
        print(json.dumps({name: entry}, indent=1))
    print(json.dumps({"experiment": "prior_vs_grounded", "results": results}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
