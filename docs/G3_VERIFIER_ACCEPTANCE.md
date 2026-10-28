# G3-B independent verifier acceptance — engineering controls only

Starting coordinator commit: `bfd605d593e0a7d0868f8bb674430d3a1b0aaa9f`.
Branch: `g3/verifier`. No PR merges, paid requests, credential reads or direct G3-A edits.
The implementation commit is the Git commit containing this report; verified code SHA
and remote CI are recorded in the handoff; later documentation-only commits do not change that code receipt. **G3 is not accepted and no genuine
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
  CPU, core/file limits and an independent `/proc` CPU watchdog. Linux execution was also verified by exact-code CI.
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

Historical controls at `aeed582`, before the later Muse validation change,
are **TRUSTED_CONTROL / NON_AI**, never Meta-generated. Current combined results
are recorded in the continuation below; this table is not current acceptance:

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
3. Real-run evaluation still needs attested reference identity/digest and immutable candidate origin/receipt; generic caller-provided adapters are control interfaces, not a real accuracy guarantee. Exact-code Linux/Windows CI is green and coordinator review is conditional; future combined changes require new CI/review. No G3 acceptance, real candidate accuracy or universal equivalence claim. Model calls/spend/uncertain spend: **0 / $0 / $0**.

Resource reference documentation: [Windows Job limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information),
[Job memory limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information),
and [Python audit-hook limitations](https://docs.python.org/3/library/sys.html#sys.addaudithook).

## Session-boundary update ? 28 October 2026

Verified code SHA: `aeed582483cbf0f2d57bfb53a4fef948273d9ec6`.
[CI 40581058875](https://github.com/Ankit6149/second-source/actions/runs/40581058875) completed successfully: Linux/Python 3.11 **250 passed/3 skipped**; Windows/Python 3.12 **251 passed/2 skipped**, including bootstrap replay and `BOOTSTRAP_OK`. Local Windows remains **250 passed/3 skipped**. The difference is unprivileged symlink availability.

Coordinator [review](https://github.com/Ankit6149/second-source/pull/4#pullrequestreview-5674191802) is CONDITIONAL GREEN for this NON_AI engineering slice. The [latest continuation direction](https://github.com/Ankit6149/second-source/pull/4#issuecomment-6461226733) requires additional real-run provenance work in existing owned modules: attested reference identity/digest; frozen suite/comparator; immutable candidate origin/receipt; authenticated G2 observation/hypothesis and pinned scope/public-manifest binding; exact inspected broker request. Caller-provided mappings/marker scans and arbitrary reference protocols must not establish a real accuracy claim.

Muse's text/dict parameter-error-precedence correction must be independently verified once committed; none has been observed at the last integration-head fetch (`bfd605d...`). Fetch/integrate cleanly on `g3/verifier`, keep both PRs draft/unmerged, and re-run combined CI. No new branches, paid calls, credential access or G3 acceptance claim. This session ends with a documentation-only handoff; implementation continues next session per the user's instruction.

## Autonomous continuation: combined G3-B/G3-D preparation, 28 October 2026

**Current disposition: BLOCKED for integration and real inference.** Earlier green
control counts above apply to the earlier baseline. The new independent regressions
are ordinary failing tests, with no skip/xfail or weakened acceptance threshold.

Baseline verifier head: `646d90168ad88b8cda805e32b0c6efdbea95a796`.
Imported Muse head: `da6cc9f532befdf37d51e9aca4270083593f72ce`, including
`1a39863`'s validation change, through clean local merge
`b643439462de757f6b71b80e193c280dade4b812` on the existing `g3/verifier`.
No new branch or GitHub PR merge. The requested starter file was read and deleted;
no other pre-existing file was deleted. All implementation/test/document changes
remain within the existing verifier ownership boundary. Muse-owned modules were
imported without editing them.

### Pinned evaluator and broker API

`PinnedEvaluatorRun` in `g3_verification.py` is the release-oriented entry point.
The original `evaluate_sealed_suite` remains a generic **TRUSTED_CONTROL** API;
its metadata now explicitly says `TRUSTED_CONTROL_EVALUATION_NOT_MODEL_PROVENANCE`.
Generic adapters, caller dictionaries and claimed generation receipts cannot
produce an accepted real-model evaluation through the pinned API.

- Before generation, the run freezes the complete scope, suite bytes/digest,
  trusted limits, public manifest, evaluator/comparator/runtime/generation/gateway
  and transitive local module hashes. The original fixture must match the committed
  reviewed reference digest `sha256:0df0ddc164428c3c062d68f06bc5030cc8f2d5bfcec7a115611af940766384b9`.
  Scoring constructs the fixed bounded original adapter internally; it takes no
  caller-selected reference. Code pins are checked before and after generation
  and evaluation; both workers retain the existing containment/resource checks.
- Approved observations are read by content address from `EvidenceLedger`,
  integrity-checked and redacted. Commands/statuses are scope-checked. Hypotheses
  are taken from the trusted `HypothesisStore`, schema/citation-checked and frozen
  including statements/statuses. A syntactically valid citation does not authorize
  a different hypothesis. Later mutation of the ledger/store or a context mapping
  cannot alter the frozen inputs.
- `prepare()` inspects the final gateway request in the existing credential-free
  generation worker. An immutable `BrokerArtifact` binds the inspected bytes to
  the frozen plan and a single-use nonce. `generate()` reconstructs the logical
  request and compares **all final ModelRequest fields** at the provider boundary,
  after exactly one schema injection. No tools are added. Tampering, request drift,
  sequential/concurrent replay and cross-run artifacts are rejected.
- The credential-owning provider stays in the trusted parent. Only exact registered
  provider types are accepted. Real dispatch needs separate owner spending approval,
  a positive budget within the frozen contract, and an independently approved
  context digest supplied from trusted operator configuration. **A locally populated
  ledger/store or matching caller mapping alone never enables real dispatch.**
  The run budget cannot be swapped/reset/widened. Attempts are capped at one initial
  plus at most two subsequent attempts; a failed real attempt blocks further real
  dispatch pending fresh independent preflight. No real transport was exercised.
- Broker-issued candidate origins bind exact immutable spec bytes, loader digest,
  response/provider/model metadata, request/plan hashes, tokens and estimated/uncertain
  costs. Local HMAC authentication rejects relabeling a mock as real, changing the
  spec/receipt or moving it to a different run. `evaluate(..., claim="REAL_MODEL")`
  rejects all mock/control origins. Neither score nor receipt implies G3 acceptance.
- `evaluate()` returns sanitized metadata/counts and retains only its computed
  `model_feedback()` for `repair_feedback()`. Arbitrary caller reports are never
  accepted as repair feedback. Case inputs, outputs, names, paths and credentials
  are absent. This prepares the feedback interface; it does not implement a real
  repair prompt/CLI or claim observed repair lift.

Local attestation is an in-process trusted-orchestrator boundary, **not** a provider
signature, historical G2 authentication, protection against malicious same-process
Python, or an arbitrary-code sandbox. The operator must independently approve the
actual G2 registry/context from local receipts before supplying
`operator_approved_context_digest`; the shared historical projection lacks the
actual action payloads and cannot be used to invent them. Authority keys are
ephemeral and never written/read from credential storage. A new process does not
silently trust a serialized caller receipt; durable attestation/restart recovery
requires a separately reviewed authority mechanism. Reports include code,
registry, receipt and environment digests without persisting keys.

Nonbillable integration skeleton (trusted orchestrator only):

```python
run = PinnedEvaluatorRun(suite, contract, ledger=approved_ledger,
                        observation_digests=approved_digests,
                        hypotheses=approved_hypothesis_store)
ticket = run.prepare()  # isolated inspection only
origin = run.generate(ticket, mock_provider, zero_spend_budget)
report = run.evaluate(origin)  # PINNED_TRUSTED_CONTROL_EVALUATION
feedback = run.repair_feedback(origin)  # detached aggregates only
# Supplying REAL_MODEL for this mock origin is rejected.
```

### Independently reproduced Muse blockers

1. **`candidate_runtime.py::_validate_params` now sorts alphabetically.** Text
   and canonical dictionary representations agree, but both disagree with the
   original on the coordinator's two public multiple-invalid/missing-field probes.
   The reference returns `invalid_label`; candidates return `invalid_amount`.
   `test_parameter_precedence_matches_original_for_both_representations` requires
   both representations to pass the original. The original private positive suite
   consequently scores **24 passed / 1 failed / 0 indeterminate / 25 total**.
   The evaluator does not change candidate behavior to hide this defect.
2. **`candidate_generation.py::request_candidate_spec` permits all pins omitted
   for a real gateway.** Independent `test_muse_direct_real_function_must_not_allow_omitting_all_pins`
   uses a synthetic placeholder and replaces `complete()` with a local sentinel.
   The sentinel is reached with no scope/manifest/evidence pins, so the test fails.
   No network request or actual credential is involved. Partial-pin rejection does
   not close this omission path. The new pinned broker protects its own entry point,
   but Muse's direct path must also fail closed or be removed from real integration.

Muse's own `da6cc9f` CI [40637254976](https://github.com/Ankit6149/second-source/actions/runs/40637254976)
is green on Ubuntu/Python 3.11 and Windows/Python 3.12 (Windows bootstrap succeeds).
That run does not contain the independent verifier regressions above and is not
combined acceptance. New combined CI and coordinator review remain required.

### Verification record

All local runs use Windows/Python 3.12.4, a minimal child environment with no
provider credentials, model spend cap zero, pytest plugin autoload disabled,
and bytecode/cache writes disabled. No `.env` was loaded. Initial combined full
run: **273 passed / 4 failed / 3 skipped**, 58.35 seconds. The four failures are
the missing-pin sentinel, sealed positive control and two positive precedence
regressions. Final complete local run on the committed implementation:
**285 passed / 4 failed / 3 skipped**, 86.98 seconds. All resource, strict comparator,
worker isolation, pinned-provenance, request drift/replay, reference substitution,
mock-origin and aggregate-feedback controls passed; the same four Muse-boundary
regressions failed. Skips are the two credential-gated live tests and unavailable
unprivileged Windows symlink creation; the Windows junction probe passed.

Current 25-case controls (NON_AI): positive **24/1/0**; broken uniqueness
**22/3/0**; broken whitespace **22/3/0**; broken amount boundary **23/2/0**
(passed/failed/indeterminate). The deliberate negatives add **2, 2, 1** failures
beyond the shared precedence regression. Denominators remain 25 throughout.
Exact-head combined CI is checked after push; its result is reported in the
completion message. G3 calls/spend/uncertain spend: **0 / $0 / $0**.

Integration is not ready until Muse's two blocking corrections are published,
cleanly integrated into this branch and the unchanged full Linux/Windows checks
pass. Then the new evaluator/broker boundary still needs independent coordinator
review. Real model inference and final G3 acceptance remain separately gated.
