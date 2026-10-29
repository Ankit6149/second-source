# Second Source · evidence-backed software reconstruction

**Status pointer - 29 October 2026 IST.** Use the [single current delivery board](docs/G3_DELIVERY_BOARD.md) for exact published SHA/CI, both consumed real G3 attempts, evidence and backend acceptance. This document does not authorize inference, credentials or deployment.

**An AI scientist for authorized software behavior:** observe a black box, form evidence-linked hypotheses, run controlled experiments, generate a scoped independent candidate, and measure it against a withheld evaluator.

## Current outcome - 29 October 2026 IST

- Verified main `1ba89054b7335aa7c26a0fa9e347d7d766eeeafe`, including merged PR #11. [Post-merge CI 40849690763](https://github.com/Ankit6149/second-source/actions/runs/40849690763): Linux **521 passed / 0 failed / 3 skipped**, Windows **522 / 0 / 2**, bootstrap **522 / 0 / 2 BOOTSTRAP_OK**.
- Genuine new G2: 3 original hypotheses, 5 observations, one model-selected experiment, 2 real receipts; estimate USD0.013486, uncertain 0. Original evidence operator-local; older missing hypotheses not reconstructed.
- Genuine G3: **two consumed attempts, no admitted candidate or behavioral score**; estimates USD0.0103305 and USD0.00985025, uncertain 0. Exact historical field rejection causes unknown. No further inference/repair authorized.
- NON_AI trusted positive 25/25, negative 2/2/1, mock 22/25: never real reconstruction quality.
- Backend control plane/API/worker/artifact packaging merged in PR #10: local SQLite/single-host mock-only profile reuses the CLI engine, reproducing **22/25 NON_AI** through durable state and verified sanitized export. See [backend operations](docs/BACKEND_OPERATIONS.md) and [API contracts](docs/BACKEND_API.md). Cloud database/authentication and genuine paid-engine integration are not enabled.
- [Guided verifier binding PR #11](https://github.com/Ankit6149/second-source/pull/11) is merged with independent review and cross-platform CI. Explicit `--synthesis guided` has a protocol-bound zero-call preflight; full synthesis remains default. The actual operator packet remains frozen and **unauthorized**; see the delivery board. Muse owns intelligence/admission. Frontend expansion remains stopped; merged PR #7 is read-only, not full product acceptance.
- Submission completion, final video and organizer acceptance **unverified**.

[Master PRD](docs/MASTER_PRD.md) defines product; [single delivery board](docs/G3_DELIVERY_BOARD.md) records current evidence/gates; [owner backend directive](https://github.com/Ankit6149/second-source/issues/2#issuecomment-6477673246) sets execution priority. No production-ready infrastructure claim.

## Reproduce the verified engineering workflow

Use Python 3.11+ and a frozen, reviewed `main` checkpoint:

```sh
git clone https://github.com/Ankit6149/second-source.git
cd second-source
git checkout --detach 1ba89054b7335aa7c26a0fa9e347d7d766eeeafe
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

For the continuous G2 -> G3 mock demonstration, run
`python -m second_source.live_experiment --mode mock`, inspect/export its
complete journal using the externally retained receipt hash, then pass that
same ledger/batch/digest set and receipt witness to G3 mock. The
[approval package](docs/G2_G3_APPROVAL_PACKAGE.md) has the exact argument
recipe and recorded evidence identities. Both zero-call preflights and
offline inspection require no model key; mock evidence cannot approve real
dispatch. Earlier final-manifest persistence is retired.

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
- The current deliverable includes the local CLI and owner-scoped SQLite
  mock-only API/worker profile with sanitized integrity export. Genuine
  reconstruction, paid-engine integration, repair, web/cloud capability and
  submission have separate acceptance gates on the delivery board.

See [independent verification](docs/G3_VERIFIER_ACCEPTANCE.md),
[G3 acceptance](docs/G3_ACCEPTANCE.md) and the
[submission runbook](docs/HACKATHON_SUBMISSION_RUNBOOK.md).
