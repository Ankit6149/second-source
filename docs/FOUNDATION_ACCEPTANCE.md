# G0/G1 foundation acceptance report

**Date:** 2026-10-27 (implementation environment UTC may differ)  
**Scope:** deterministic local foundation, no real model calls, no product cloud worker.

## Implemented

| Component | Path | What is actually implemented |
|---|---|---|
| ScopeContract | `src/second_source/contracts.py` | Strict typed target/observation/implementation/exclusion scope, budgets, actor constraints, CLI command identifiers |
| ScopeGuard | `src/second_source/scope_guard.py` | Reject missing permission mappings, excluded routes, foreign origins, role/auth violations, unapproved external effects, out-of-scope candidate modules, unsafe generated paths |
| Original reference fixture | `fixtures/owned_ledger/reference.py` | Stateful JSONL program with deterministic fresh-process reset; duplicate rules, numeric constraints, item IDs and removal |
| CLI target adapter | `src/second_source/reference.py` | Fixed trusted process argv, no shell, bounded time/output, strict JSONL parsing, stable per-sequence observations |
| Safe experiment boundary | `src/second_source/runner.py` | Validates *all* proposed actions before invoking the reference, blocks command overriding, counts attempts against budget |
| Evidence ledger | `src/second_source/evidence.py` | Hash-addressed original observations, integrity checking, redacted model-visible JSON views |
| Differential verifier | `src/second_source/verifier.py` | Runs identical withheld action sequences against separate reference/candidate executions; distinguishes pass/fail/indeterminate; model sees aggregated feedback only |
| Negative candidates | `fixtures/candidates/` | Deliberately buggy implementation, bad JSONL protocol, hung process |
| Local demonstration | `python -m second_source.demo` | Executes 4 sample cases: 1 pass / 3 intentional failures (harness verification, **not AI performance**) |

## Reproduction

```sh
python -m pip install -e '.[dev]'
python -m pytest
python -m second_source.demo
```

**Observed results in authoring environment:** Python 3.13.5, pytest 9.0.2: **42 passed**; deterministic verifier demo **1 passed / 3 failed / 0 indeterminate**. No model calls, billable services, deployments or candidate generation were performed. Python 3.11/Windows are declared compatibility targets but not yet exercised here.

## Explicit blockers and limitations

1. **Not a full security sandbox:** CLI adapter is suitable for trusted original synthetic fixtures only; candidate-generated/untrusted code must execute in an isolated Docker/Modal backend with filesystem/network/CPU/memory constraints before real autonomy.
2. **Not fully sealed from network-capable model:** The fixture source is necessarily visible in the public repo. Runtime model, tools and candidate must be separated from source and gold test files, including network access if such exposure matters. The current harness performs no inference, so no leakage to a model occurred.
3. **Limited sanitizer:** evidence `model_view` redacts common sensitive *field names* and Bearer tokens, but does not guarantee removal of arbitrary PII from free text, screenshots or unknown JSON structures. Do not run on real private data.
4. **No Meta API yet:** the model gateway, hypothesis generator and experiment planner come in G2. Mock and verifier tests are not proof of genuine AI functionality.
5. **No authentication driver:** OAuth/SSO/OTP/human gates are architected, not implemented in G0; guest/CLI synthetic fixture only.
6. **No persistent cloud orchestration:** job queue, restart recovery, mobile monitoring and paid sandboxes follow later acceptance gates.
7. **Output size and runtime limits:** subprocess timeout and post-capture byte caps exist, but CPU/memory/file/network budgets need actual sandbox isolation before accepting model-generated programs.
8. **No hidden leakage prevention beyond process tools:** the gold evaluation suite must be deployed separately from any future model-controlled code/tool system.
9. **One scope per runner:** scope changes should create a new versioned run rather than mutate the existing approved contract.
10. **No guaranteed functional equivalence:** verifier scores only specified test cases, not all possible behaviors.

## Next go/no-go gate

Connect the real Meta model only after authenticating with an operator-controlled API key, verifying billing balance and enforcing separate model-call/token/USD budgets; require schema-constrained proposals, deterministic policy checks, and a visible evidence trail for actual experiments.
