"""Coverage gate: claim provenance against recorded evidence only."""
from second_source.coverage import (
    ASSUMED, CONTRADICTED, OBSERVED, UNKNOWN, analyze_cli_candidate,
)


def obs(seq, idx, action, output):
    return {"sequence_id": seq, "action_index": idx,
            "input_action": action, "output": output}


def spec(**add_over):
    add = {
        "params": {
            "label": {"type": "string", "required": True, "trim": True,
                      "min_length": 1, "max_length": 24, "error": "invalid_label"},
            "amount": {"type": "integer", "required": True, "minimum": 1,
                       "maximum": 100, "error": "invalid_amount"},
        },
        "unique_field": "label", "unique_casefold": True,
        "unique_error": "duplicate_label",
        "respond": {"id": "id"},
    }
    add.update(add_over)
    return {"commands": {"add": add}}


def boundary_evidence():
    return [
        obs("s1", 0, {"command": "add", "label": "x" * 24, "amount": 100}, {"ok": True, "id": "1"}),
        obs("s2", 0, {"command": "add", "label": "x" * 25, "amount": 5}, {"ok": False, "error": "invalid_label"}),
        obs("s3", 0, {"command": "add", "label": "A", "amount": 101}, {"ok": False, "error": "invalid_amount"}),
        obs("s4", 0, {"command": "add", "label": "B", "amount": 0}, {"ok": False, "error": "invalid_amount"}),
        obs("s5", 0, {"command": "add", "label": "", "amount": 5}, {"ok": False, "error": "invalid_label"}),
        obs("s6", 0, {"command": "add", "label": "C", "amount": 1}, {"ok": True, "id": "2"}),
    ]


def states(report):
    return {c.dimension: c.state for c in report.claims}


def test_decisive_boundaries_are_observed():
    s = states(analyze_cli_candidate(spec(), boundary_evidence()))
    assert s["validation.add.label.max_length"] == OBSERVED
    assert s["validation.add.amount.maximum"] == OBSERVED
    assert s["validation.add.amount.minimum"] == OBSERVED
    assert s["response.add.shape"] == OBSERVED


def test_accepted_out_of_bound_value_contradicts():
    ev = boundary_evidence() + [
        obs("s6", 0, {"command": "add", "label": "y" * 30, "amount": 5}, {"ok": True, "id": "9"})]
    s = states(analyze_cli_candidate(spec(), ev))
    assert s["validation.add.label.max_length"] == CONTRADICTED


def test_rejection_alone_never_contradicts():
    # In-bound value rejected for an unrelated reason (duplicate) must not
    # be read as evidence against the bound.
    ev = boundary_evidence() + [
        obs("s7", 0, {"command": "add", "label": "Dup", "amount": 50}, {"ok": False, "error": "duplicate_label"})]
    s = states(analyze_cli_candidate(spec(), ev))
    assert s["validation.add.amount.maximum"] != CONTRADICTED


def test_unprobed_claims_are_unknown_or_assumed_not_observed():
    s = states(analyze_cli_candidate(spec(), []))
    assert s["response.add.shape"] == UNKNOWN
    assert s["error.add.duplicate_label"] == ASSUMED
    assert s["uniqueness.add.label"] == UNKNOWN


def test_casefold_claim_contradicted_by_case_variant_acceptance():
    ev = [
        obs("s1", 0, {"command": "add", "label": "Milk", "amount": 1}, {"ok": True, "id": "1"}),
        obs("s1", 1, {"command": "add", "label": "MILK", "amount": 1}, {"ok": True, "id": "2"}),
    ]
    s = states(analyze_cli_candidate(spec(), ev))
    assert s["uniqueness.add.label"] == CONTRADICTED


def test_verified_equivalence_blocked_only_by_contradiction():
    clean = analyze_cli_candidate(spec(), boundary_evidence())
    assert clean.verified_equivalence_blocked() is False
    dirty = analyze_cli_candidate(spec(), boundary_evidence() + [
        obs("s8", 0, {"command": "add", "label": "z" * 40, "amount": 5}, {"ok": True, "id": "3"})])
    assert dirty.verified_equivalence_blocked() is True
