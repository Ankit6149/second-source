# Second Source · evidence-backed software reconstruction

**An AI scientist for authorized software behavior:** observe a black box, form evidence-linked hypotheses, run controlled experiments, generate a scoped independent candidate, and measure it against a withheld evaluator.

## Current outcome — 28 October 2026

- **Engineering:** merged PR [#5](https://github.com/Ankit6149/second-source/pull/5) at `bc9f9c11`, including one durable G2 journal and a sealed, bounded G3 evaluation workflow. Merged PR [#6](https://github.com/Ankit6149/second-source/pull/6) at `ceb28b6`, preserving sanitized future broker failure diagnostics. The latest PR #6 head passed cross-platform CI; post-merge main CI is tracked separately.
- **Genuine Meta G2:** an operator-run discovery on 28 October recorded 3 original hypotheses, 5 observations, 1 model-selected experiment and 2 real Muse Spark 1.3 responses. Independently audited local receipt estimates: USD `0.013486`, not provider-confirmed charges. Original evidence and the externally witnessed receipt remain local, not checked into this public repo.
- **Genuine Meta G3:** one authorized real synthesis attempt consumed, estimated `$0.0103305`; failed **before candidate admission**, with no independent model-generated score. Its exact rejection category was not preserved by that old run. The PR #6 diagnostic fix cannot retroactively recover it. No second paid attempt or repair is authorized by a merge.
- **NON_AI controls:** scripted candidate `22/25` on the sealed suite, trusted hand-authored positive `25/25`, negative sensitivity `2/2/1`. **None represents real Muse reconstruction quality.**
- **Operator experience:** [read-only demo console](demo/) in [PR #7](https://github.com/Ankit6149/second-source/pull/7), showing real/mock status, local report import, evidence counts, score/no-score and sanitized summary download. This does not dispatch real inference, start/stop runs or export an independently signed complete evidence bundle.
- **Submission:** Not submitted. A scored genuine G3 candidate, full product UI acceptance, judge video and final public reproducibility remain outstanding.

The canonical product contract is [docs/MASTER_PRD.md](docs/MASTER_PRD.md). Current engineering/result evidence and remaining release gates are in [docs/G3_DELIVERY_BOARD.md](docs/G3_DELIVERY_BOARD.md). The [submission runbook](docs/HACKATHON_SUBMISSION_RUNBOOK.md) remains a checklist, not evidence of completion.

## Reproduce the verified engineering workflow

Use Python 3.11+ and a frozen, reviewed `main` checkpoint:

```sh
git clone https://github.com/Ankit6149/second-source.git
cd second-source
git checkout --detach ceb28b6f2f2292f75f766fbd3fbefc0822cfef98
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
- The current deliverable is a local CLI milestone. Full status/report UX,
  evidence export, genuine reconstruction quality, optional repair, web/cloud
  capability and submission have separate gates on the delivery board.

See [independent verification](docs/G3_VERIFIER_ACCEPTANCE.md),
[G3 acceptance](docs/G3_ACCEPTANCE.md) and the
[submission runbook](docs/HACKATHON_SUBMISSION_RUNBOOK.md).
