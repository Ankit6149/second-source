# Second Source · scope-aware behavioral reconstruction

**Status:** G0/G1 deterministic foundation and G2 Muse experiment engine implemented on the integration branch. Mock tests and cross-platform CI exist. A **real Meta API experiment is not yet verified**; candidate generation, deployment, production isolation, and always-on coordination are not built.

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

## Windows: install once, run without Python-path confusion

The package lives under `src/second_source/`. Directly running global
`C:\miniconda\python.exe -m second_source.live_experiment` before installing the
project can produce `ModuleNotFoundError`. Always use the same Python environment
for installation, tests and experiments.

From an **up-to-date `integrate/g2-discovery` working tree**, run in PowerShell:

```powershell
git fetch origin
git switch integrate/g2-discovery
git pull --ff-only
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap-windows.ps1
.\.venv\Scripts\python.exe -m second_source.demo
```

The script creates a local `.venv`, installs `.[dev]`, verifies the import and
runs the entire non-billable test suite. **It does not ask for or use API keys.**

To run the first *real* Muse experiment, use a separate **human-interactive**
PowerShell window (not an unattended Muse command runner):

```powershell
$secure = Read-Host "Meta Model API key" -AsSecureString
$env:MODEL_API_KEY = [System.Net.NetworkCredential]::new("", $secure).Password
$env:SECOND_SOURCE_MAX_RUN_USD = "0.25"
.\.venv\Scripts\python.exe -m second_source.live_experiment --max-usd 0.25 --rounds 1
Remove-Item Env:MODEL_API_KEY
Remove-Item Env:SECOND_SOURCE_MAX_RUN_USD
```

The final command **makes real billable requests** if credentials and the budget
are valid. Inspect only the sanitized `.runs/*/run_report.json`. Do not paste the
API key or share raw credentials. `Read-Host` is interactive: using it inside a
noninteractive agent tool can simply hang until timeout. The budget is an
application-level estimate for this one run, **not a provider billing guarantee**.

## Boundaries

- No source or hidden test inputs are ever given to an AI by this foundation: currently it does not invoke an AI.
- Pydantic contracts forbid undeclared scope expansion; fixed executable argv with `shell=False` prevents an agent from constructing arbitrary system commands through this adapter.
- The reference is a trusted owned fixture. Do **not** use this local subprocess adapter to run untrusted generated programs; use isolated containers/sandboxes in the next milestone.
- No credentials, live third-party systems, purchases or remote endpoints are required.
- `scope_guard` handles authorization and excludes extra generated subsystems before execution. A later runtime must enforce the same decisions at every privileged boundary.

## Next gate

Connect Muse through server-side `ModelGateway` only after the deterministic test suite passes and the operator explicitly confirms API billing and per-run budgets. A real Muse response must propose competing hypotheses and a schema-valid, in-scope experiment. Reference and hidden evaluator must remain unreadable to the agent.
