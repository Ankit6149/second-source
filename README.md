# Second Source · scope-aware behavioral reconstruction

Second Source studies an explicitly authorized black-box program, forms
evidence-linked hypotheses, generates a scoped independent candidate and
compares its behavior with a separate withheld evaluator.

**Current status — 28 October 2026:** the zero-cost G3 engineering workflow
is verified at `af477b2daf0b676ad49be3959bcd28de868f76be`:
[Linux/Windows CI](https://github.com/Ankit6149/second-source/actions/runs/40666652416)
passes, including Windows bootstrap. The workflow is in open, unmerged
[PR #5](https://github.com/Ankit6149/second-source/pull/5) on the existing
`integrate/g3-reconstruct` branch. PRs #3/#4 are merged; `main` contains
the earlier foundation at `9c8bcc4eba5e8bf4b1b3e5dfc75273c2eb0ea203`.

**Real G3 reconstruction remains NO-GO.** A historical G2 run has locally
audited observations and recorded real Meta response IDs, but its original
hypothesis statements/citations were not retained. No genuine G3 candidate,
real score or repair lift exists. Recover authentic inputs or separately
authorize a correctly recorded G2 discovery before seeking G3 approval.

The [delivery board](docs/G3_DELIVERY_BOARD.md) is the single current status
source, with exact evidence, remaining gates and severity-ranked risks.
The [Master PRD](docs/MASTER_PRD.md) and
[implementation contract](docs/G3_IMPLEMENTATION_CONTRACT.md) define the
product; a passing mock suite does not mean the full product is complete.

## Reproduce the verified engineering workflow

Use Python 3.11+ and the reviewed source checkpoint, rather than assuming
the open PR is already in `main`:

```sh
git clone https://github.com/Ankit6149/second-source.git
cd second-source
git checkout --detach af477b2daf0b676ad49be3959bcd28de868f76be
python -m venv .venv
# Linux: . .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
python -m second_source.reconstruct --mode mock
```

The mock command observes the owned fixture, registers explicitly scripted
hypotheses, passes a naive scripted candidate through the mock broker,
archives candidate/broker bytes and writes `.runs/<id>/G3_report.json`.
The default candidate scores **22 passed / 3 failed / 0 indeterminate / 25**;
it is plumbing evidence, never AI reconstruction success. The independent
hand-authored positive control scores **25/25**; deliberate defects trigger
**2/2/1** failures. All these results are **NON_AI**.

No key or paid call is required. Sealed material stays outside Git and model
context. Run directories, candidate versions and reports are create-once.
For explicit run/seal locations and zero-call actual-input inspection, see
the [operator runbook](docs/G3_RECONSTRUCT.md). A mock digest never approves
historical G2 inputs. Preflight proposes pins for separate review; it does
not grant spending permission.

## Windows setup

From the reviewed checkout, PowerShell can install and test using one
consistent Python environment:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/bootstrap-windows.ps1
.\.venv\Scripts\python.exe -m second_source.reconstruct --mode mock
```

The bootstrap script installs `.[dev]`, checks imports and runs nonbillable
tests. Avoid mixing a global Python executable with the project virtualenv.

## Trust and release limits

- ScopeGuard and typed contracts enforce separate observation,
  implementation and exclusion boundaries. Generation receives approved
  redacted observations/public signatures, never original source or gold cases.
- The trusted data-only DSL runs in bounded staged workers. This is not an
  arbitrary generated-code OS sandbox or a universal equivalence proof.
- Archived broker signatures preserve local integrity; the private signing
  key is not exported. They are not portable provider attestations.
- Provider/model/usage provenance and uncertainty must remain explicit.
  Real inference requires authentic approved inputs, frozen scope/suite pins
  and separate finite owner spending authorization. No inference is authorized
  by this README; application estimates are not provider billing guarantees.
- The current deliverable is a local CLI milestone. Full status/report UX,
  evidence export, genuine reconstruction quality, optional repair, web/cloud
  capability and submission have separate gates on the delivery board.

See [independent verification](docs/G3_VERIFIER_ACCEPTANCE.md),
[G3 acceptance](docs/G3_ACCEPTANCE.md) and the
[submission runbook](docs/HACKATHON_SUBMISSION_RUNBOOK.md).
