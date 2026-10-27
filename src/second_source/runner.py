"""Safe typed execution boundary between proposed experiments and reference adapter.

No arbitrary subprocess argv, shell input, or unvalidated model action passes through.
"""
from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Sequence

from .contracts import ProposedAction, ScopeContract, SequenceResult, TargetKind
from .evidence import EvidenceLedger
from .reference import CLIReferenceAdapter
from .scope_guard import ScopeGuard


class PolicyViolation(Exception):
    pass


class BudgetExhausted(Exception):
    pass


class SafeCLIExperimentRunner:
    def __init__(self, contract: ScopeContract, reference: CLIReferenceAdapter, ledger: EvidenceLedger):
        if contract.target.kind != TargetKind.CLI:
            raise ValueError("SafeCLIExperimentRunner requires CLI scope")
        self.guard = ScopeGuard(contract)
        self.reference = reference
        self.ledger = ledger
        self.contract = contract
        self.count = 0
        self.start = monotonic()

    def run(self, proposed: Sequence[ProposedAction]) -> SequenceResult:
        if not proposed:
            raise PolicyViolation("Cannot execute an empty proposed action sequence")
        if self.count >= self.contract.budgets.max_reference_experiments:
            raise BudgetExhausted("Reference experiment budget exhausted")
        if monotonic() - self.start > self.contract.budgets.max_wall_seconds:
            raise BudgetExhausted("Investigation time budget exhausted")
        executable: list[dict] = []
        for p in proposed:
            decision = self.guard.validate_action(p)
            if not decision.allowed:
                raise PolicyViolation(f"{decision.code}: {decision.reason}")
            if "command" in p.payload:
                raise PolicyViolation("Payload cannot override approved CLI command label")
            # Command labels come from an explicitly allowed registry; not from command-line text.
            executable.append({"command": p.target, **p.payload})
        self.count += 1   # even timed-out attempts consume the experiment budget
        result = self.reference.execute_sequence(executable)
        for observation in result.observations:
            self.ledger.store(observation)
        return result
