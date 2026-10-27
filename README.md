# Second Source · deterministic reconstruction foundation

**Status:** foundation implementation only. Scope validation, deterministic black-box fixture execution, immutable observations and independent comparison are implemented and tested. There is **no real Meta inference, automatic code generation, deployment or always-on coordinator** yet.

Read [Master PRD](docs/MASTER_PRD.md) and [Execution Playbook](docs/EXECUTION_PLAYBOOK.md) for the architecture and rollout plan.

## Setup (Python 3.11+)

```sh
python -m venv .venv
# Activate .venv for your shell (PowerShell: .venv\\Scripts\\Activate.ps1)
python -m pip install -e '.[dev]'
python -m pytest
python -m second_source.demo
```

The demo uses only local, owned synthetic targets; it makes **zero paid model calls**. In the first run, observe an original stateful JSONL CLI and compare it to an intentionally faulty candidate. Failures are expected and establish that the evaluator can detect observable divergence. It **does not prove AI reconstruction**.

## Boundaries

- No source or hidden test inputs are ever given to an AI by this foundation: currently it does not invoke an AI.
- Pydantic contracts forbid undeclared scope expansion; fixed executable argv with `shell=False` prevents an agent from constructing arbitrary system commands through this adapter.
- The reference is a trusted owned fixture. Do **not** use this local subprocess adapter to run untrusted generated programs; use isolated containers/sandboxes in the next milestone.
- No credentials, live third-party systems, purchases or remote endpoints are required.
- `scope_guard` handles authorization and excludes extra generated subsystems before execution. A later runtime must enforce the same decisions at every privileged boundary.

## Next gate

Connect Muse through server-side `ModelGateway` only after the deterministic test suite passes and the operator explicitly confirms API billing and per-run budgets. A real Muse response must propose competing hypotheses and a schema-valid, in-scope experiment. Reference and hidden evaluator must remain unreadable to the agent.
