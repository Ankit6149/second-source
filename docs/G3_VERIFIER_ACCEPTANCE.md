# G3-B independent verifier acceptance — engineering controls only

Starting coordinator commit: `bfd605d593e0a7d0868f8bb674430d3a1b0aaa9f`.
Branch: `g3/verifier`. No merges, paid requests, credential reads or G3-A edits.
The implementation commit is the Git commit containing this report; final SHA
and remote CI are recorded in the handoff. **G3 is not accepted and no genuine
model-generated candidate accuracy is claimed.**

## Implemented boundary

- `verifier.py` preserves its public APIs. It validates every result/observation,
  strictly compares finite JSON types, distinguishes business errors from harness
  errors, sanitizes exceptions, snapshots all inputs before execution, gives each
  executor an independent copy, and replaces hidden case names with opaque
  transport IDs. Invalid reference => indeterminate; invalid candidate => failed.
  All cases remain in the denominator. Empty/duplicate suites are rejected.
- `candidate_adapter.py` loads immutable artifact bytes through the G3-A loader
  and retains its digest. Every sequence receives a fresh isolated-mode Python
  process and a staged allowlist of trusted runtime modules. No model-written
  executable code is admitted. The environment is constructed without copying
  credentials, user paths, proxies or Python configuration; inherited descriptors
  are closed. Python startup `.pth`/user-site execution is disabled with `-I -S`.
- Input bytes/depth, action count, record count, per-response/cumulative output,
  bounded stdout/stderr pipes, wall time, CPU use and memory have trusted limits.
  Defaults: 64 actions, 128000 input/output bytes, 10000 records, 5 wall seconds,
  3 CPU seconds, 256 MiB. Unsupported backends/failed resource admission have no
  in-process fallback. A containment preflight runs before reference evaluation.
- Windows uses Job Objects for memory/process-tree limits, plus an independent
  `GetProcessTimes` CPU watchdog. The native Job CPU-time flag alone did not
  terminate the busy-loop probe on this host despite a successful configuration
  query; the external watchdog is therefore required. Linux uses address-space,
  CPU, core/file limits and an independent `/proc` CPU watchdog. Linux execution
  still requires exact-commit CI confirmation.
- `OwnedLedgerReferenceAdapter` runs the unchanged original owned fixture in a
  separate bounded worker. Only that privileged worker receives reference source.
  Its digest is pinned; changes during evaluation block execution. The existing
  G0 adapter remains available, with a conformance regression comparing both.

## Sealed material and generation isolation

`seal_owned_ledger_suite(directory, contract)` creates an external, create-once
suite with random synthetic values/opaque IDs. `load_sealed_suite` requires its
exact digest and matching scope. Storage inside any Git checkout, symlink/junction
paths, hard-linked suite files, malformed JSON and oversized input are rejected.
Suite bytes are immutable; case objects are detached on access. Repairs must load
the identical bytes/digest, never regenerate a suite. Tests use disposable external
storage; no hidden input/expected-output file is committed.

`evaluate_sealed_suite` validates the complete suite and scope before either
executor runs, checks action/reference budgets, and retains all indeterminate
cases when the overall time budget is exhausted. Commands outside the trusted
registry never run. Unknown-command robustness is tested on the candidate only;
reference unknown-command probes require a separately authorized scope extension.

`prepare_generation_request(context, approved_evidence=..., forbidden_markers=...)`
checks each observation against a trusted exact-content registry, not merely
digest syntax. It invokes the existing G3-A request builder and the actual gateway
schema injection inside a staged, nonbillable worker, capturing the final request
with MockProvider before any response. The staged generation bundle excludes the
fixture source, suite, evaluator module and repository history. A Python I/O guard
denies filesystem opens, networking, subprocesses and common mutation operations.
The final request is scanned for protected canaries and contains no model tools.

The approved registry must come from permitted redacted observation evidence,
never sealed evaluation. `EvaluationReport.model_feedback()` remains the only
repair-visible evaluation signal: counts and fixed aggregate categories, with no
case IDs/actions/outputs/paths. Feedback dictionaries are detached from reports.

**Boundary limit:** the I/O guard is defense in depth for trusted Python executing
data-only input, not an OS filesystem/network sandbox for arbitrary Python or
native exploits. No separate Windows service account/container is provisioned.
POSIX creation modes are 0700/0600; Windows uses the operator's external storage
ACLs. Do not grant general file/browser/shell tools to the inference model.
The G3-D provider broker must wire this gate and approved evidence registry before
any real inference, keeping credentials outside workers. The captured request is
a wire-inspection artifact: do not feed it back through schema injection a second
time; broker integration must preserve the inspected messages exactly.

## Controls and behavioral coverage

The private suite contains **25 cases**. Categories only: empty state, creation,
amount boundaries, invalid amounts, invalid labels, missing fields, duplicates,
case/whitespace normalization, Unicode, removal present/missing/type handling,
ordering, aggregates, and reset-sensitive trajectories. No hidden values or
expected outputs are published here.

Every control is **TRUSTED_CONTROL / NON_AI**, never Meta-generated:

| Control | Passed | Failed | Indeterminate | Total |
|---|---:|---:|---:|---:|
| Hand-authored positive DSL fixture, checked against the reference | 25 | 0 | 0 | 25 |
| Deliberately broken case-insensitive uniqueness | 23 | 2 | 0 | 25 |
| Deliberately broken whitespace handling | 23 | 2 | 0 | 25 |
| Deliberately broken amount boundary | 24 | 1 | 0 | 25 |
| Persistent-state public negative control | 1 | 1 | 0 | 2 |
| Broken protocol public negative control | 0 | 1 | 0 | 1 |
| Timeout public negative control | 0 | 1 | 0 | 1 |
| Invalid reference public control | 0 | 0 | 1 | 1 |

Positive replay on unchanged private bytes reproduces all case outcomes and
aggregate counts. Reports retain candidate/suite/scope/comparator/interpreter/
adapter/reference hashes, trusted limits, Python, platform and Pydantic version.
Reference hash is explicitly unknown when an arbitrary caller-supplied reference
protocol has no attested identity.

## Observed local verification

Windows / Python 3.12.4 / Pydantic 2.14.1 / pytest 9.1.1. Tests execute under an
explicit minimal child environment: no API keys, spend 0, external pytest plugin
autoload disabled, Python bytecode/cache writes disabled. The two live-model
tests see no credentials and skip. Windows unprivileged symlink creation is
unavailable on this host; the junction test executes successfully instead.

Baseline false-pass regressions were run against `bfd605d`'s committed verifier
before accepting the fix: **24 failed, 2 passed**, including bool/integer/float
substitutions, inconsistent statuses/exits/IDs/input receipts, malformed reference
outputs, shared mutation, leaked transport IDs and unsanitized exceptions.
Those probes are now executable regression tests.

First complete nonbillable run: **248 passed, 3 skipped, 0 failed** (168.78 s).
Final complete Windows run after resource/reference hardening:
**250 passed, 3 skipped, 0 failed** (184.66 s). Strict comparator probes:
**26 passed** (0.09 s). The bounded CLI ran the positive TRUSTED_CONTROL against
25 privately sealed cases: **25 passed / 0 failed / 0 indeterminate**, exit 0.
Its comparator hash was
`sha256:54073f6727406a44a5850a40b15b1a3cd737d2ec5f92d5cb32afea7796132449`;
reference hash was
`sha256:0df0ddc164428c3c062d68f06bc5030cc8f2d5bfcec7a115611af940766384b9`.
Control suite storage was disposable and is not the future real-run holdout.
The full-suite command is:

```powershell
python -B -m pytest -q -o addopts= -p no:cacheprovider
```

Run it with `SECOND_SOURCE_MAX_RUN_USD=0` and no provider credentials in the
test process. Never load `.env` for these checks.

## Reproduction and integration

The API path is:

```python
# contract: existing approved ScopeContract; directory: evaluator-owned outside Git
path, digest = seal_owned_ledger_suite(directory, contract)  # one time only
suite = load_sealed_suite(path, digest, contract)
candidate = CandidateReferenceAdapter(spec_bytes, contract)
reference = OwnedLedgerReferenceAdapter(contract, limits=candidate.limits)
report = evaluate_sealed_suite(suite, contract, reference, candidate)
# Only report.model_feedback() may be returned to repair.
```

Equivalent nonbillable CLI:

```text
python -m second_source.g3_verification --scope <approved-scope.json> --seal-directory <external-evaluator-directory>
python -m second_source.g3_verification --scope <approved-scope.json> --suite <external-suite.json> --suite-digest <recorded-sha256> --candidate <candidate.json>
```

The CLI prints hashes/aggregate counts, never cases or exception text, and exits
nonzero for mismatch/indeterminate/blocked evaluation. Neither command generates
a candidate or makes a model call. Scope files and sealed material are owner-local.

## Remaining coordinator findings

1. **G3-A validation precedence remains representation-sensitive.** Loading the
   same fixture as text vs a key-sorted dictionary changes which parameter error
   wins for a public synthetic multiple-invalid-fields probe. G3-A's real
   generation loader accepts dictionaries. The evaluator regression measures this
   defect without repairing it; Muse must define action validation order explicitly.
   Relevant code: `candidate_spec.parse_spec` and
   `candidate_runtime.CandidateInterpreter._validate_params`. No G3-A file was edited.
2. Real generation, the credential-owning provider broker, bounded repair and
   final release acceptance remain outside this implementation window. The new
   generation gate must be integrated before a paid run is authorized.
3. Exact-commit Linux/Windows CI and independent coordinator review remain release
   gates. This local result is not G3 acceptance, real candidate accuracy or a
   universal equivalence claim. Model calls/spend/uncertain spend: **0 / $0 / $0**.

Resource reference documentation: [Windows Job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information),
[Job memory limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information),
and [Python audit-hook limitations](https://docs.python.org/3/library/sys.html#sys.addaudithook).
