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

**Disposition at `05b0f4a`: BLOCKED for integration and real inference.** Earlier green
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
  reviewed LF-normalized Git source digest
  `sha256:539cf592cee4c22c9abfece562e258aecb2d887a6a48368fce3ebc081bdde832`.
  Raw checkout/worker bytes are independently pinned for the run, so LF and CRLF
  checkouts share the source identity while any within-run byte change is rejected.
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

25-case controls at `05b0f4a` (NON_AI): positive **24/1/0**; broken uniqueness
**22/3/0**; broken whitespace **22/3/0**; broken amount boundary **23/2/0**
(passed/failed/indeterminate). The deliberate negatives add **2, 2, 1** failures
beyond the shared precedence regression. Denominators remain 25 throughout.
Exact-head combined CI is checked after push; its result is reported in the
completion message. G3 calls/spend/uncertain spend: **0 / $0 / $0**.

Integration is not ready until Muse's two blocking corrections are published,
cleanly integrated into this branch and the unchanged full Linux/Windows checks
pass. Then the new evaluator/broker boundary still needs independent coordinator
review. Real model inference and final G3 acceptance remain separately gated.

### Cross-platform reference identity correction

Initial published implementation: `f65d1726a803abf3d1b89e7218163619cd2e0d1d`.
[CI 40639620878](https://github.com/Ankit6149/second-source/actions/runs/40639620878)
confirmed the four expected Muse-boundary failures on Windows and exposed an
additional Codex defect on Linux: the first fixed reference hash represented the
Windows CRLF checkout, rather than the Git LF blob. This failed closed but prevented
Linux provenance controls from running. The follow-up separates the normalized
reviewed source identity from the exact raw bytes staged into the worker. The
committed Git blob and LF-normalized Windows file both hash to `539cf592...`;
the raw Windows worker bytes retain `0df0ddc...`. A public regression proves both
checkout newline forms are admitted, raw byte pins remain distinct, source changes
are rejected, and the generic reference-adapter module has its own separate pin.
Follow-up complete local run: **286 passed / 4 failed / 3 skipped**, 92.00 seconds.
The newline/raw-pin regression and all new provenance controls pass. The four
failures remain exactly the Muse omission/precedence blockers listed above.
Exact follow-up Linux/Windows CI is checked after push and reported with its SHA.

## Verified Muse corrections and combined integration

Continuation follows the coordinator's
[independent verification and integration direction](https://github.com/Ankit6149/second-source/pull/4#issuecomment-6461975311).
Starting verifier head: `05b0f4accf1e3d080b90c6622daad82bae1ea988`.
Muse correction: `b27fa690bf226732a924f003d77d7fe13e6cb780`.
Clean local integration commit: `cee89525bcb0a4913a8d9b8cd3cc5b45e231f9c7`.
The final pushed head also includes this acceptance-record update. No new branch,
force push, paid call, credential read or PR merge was performed.

Independent diff review confirms the focused Muse change touches only its runtime,
generation adapter, associated tests and interface document. Runtime validation
now uses explicit `add` order `label, amount` and `remove` order `id`, preserving
candidate-declared error codes and representation independence. The direct real
generation path checks every required provenance pin before request construction
or gateway dispatch; unpinned mock generation remains available. The low-level
pin check does not replace the release evaluator's trusted ledger/hypothesis and
operator-approved-context boundary.

**All existing independent verifier assertions and security implementations are
unchanged from `05b0f4a`.** Verified with `git diff --exit-code 05b0f4a HEAD --`
over the four verifier test modules, `verifier.py`, `candidate_adapter.py` and
`g3_verification.py`. No xfail/skip, expected error, positive threshold or negative
control was changed to obtain passing results. No owned source fix was needed.

Complete combined local suite under the same minimal credential-free environment:
**292 passed / 0 failed / 3 skipped**, 103.19 seconds, Windows/Python 3.12.4.
The two live credential-gated tests and unavailable unprivileged symlink capability
remain the only skips; the Windows junction probe passes. The formerly failing
two reference-precedence probes, private 25-case positive control and real
missing-pin transport sentinel now all pass. Full coverage also retains:

- Strict typed JSON and result-envelope comparisons, reset/snapshot independence,
  invalid-reference indeterminacy and failed-candidate accounting.
- Original normalized reference identity and exact worker-byte pins; frozen suite,
  comparator/code/manifest/scope/observation/hypothesis digests.
- Sealed material excluded from generation; source/gold reads, egress, subprocesses,
  inherited descriptors and environment leakage denied at the worker boundary.
- Mandatory CPU/memory/wall/input/output bounds with no uncontained fallback.
- Immutable broker candidate/spec/receipt binding; mock-as-real and substituted
  reference rejection; final request drift and sequential/concurrent replay denial.
- Operator input/spend approval requirements, non-resettable bounded run budget,
  and detached aggregate-only repair feedback.

Exact combined Linux/Windows CI, final pushed SHA and control run hashes are
reported on PR #4 and in the completion report after remote verification.
An additional nonbillable control run exercised the **pinned** evaluator against
the bounded original reference over a freshly sealed external 25-case suite:

| NON_AI control | Passed | Failed | Indeterminate | Total |
|---|---:|---:|---:|---:|
| Hand-authored positive through the inspected mock broker and pinned evaluator | 25 | 0 | 0 | 25 |
| Deliberately broken case-insensitive uniqueness | 23 | 2 | 0 | 25 |
| Deliberately broken whitespace handling | 23 | 2 | 0 | 25 |
| Deliberately broken amount boundary | 24 | 1 | 0 | 25 |

All four controls used identical sealed bytes; candidate state reset per sequence.
The pinned positive's detached `repair_feedback()` exactly matched its aggregate
evaluation. Its broker origin remained `mock`, `real=false`; no paid inference,
credentials, hidden case details or actual G2 payloads were involved. Disposable
test material was removed and is not the future real-run holdout. Observed hashes:

- Suite: `sha256:ec355b50a4e3c1eab136d409c7e3a6b472e40de065cc2a057453a0d9136b861d`.
- Positive candidate: `sha256:225627a06c3d18fcac9fa30ddb40165bfdf8fc46ceede1e788af2887923c88e3`.
- Comparator: `sha256:54073f6727406a44a5850a40b15b1a3cd737d2ec5f92d5cb32afea7796132449`.
- Frozen pinned-run plan: `sha256:93bab081555451f39d2cee05c2fb03ceb9082d3bb094897f32c78eb2adf57b88`.

Engineering integration still requires coordinator review. This is **NON_AI
engineering evidence**, not a real Muse candidate, historical G2 authentication,
observed repair lift, G3 acceptance or arbitrary-code sandbox certification.
Remaining real-run work includes independently approved actual G2 input context,
fresh preflight and explicit owner spend authorization, operator CLI/report wiring,
and separately reviewed durable attestation if restart/replay across processes is
required. Real model calls / spend / uncertain spend remain **0 / $0 / $0**.

## Independent real-run readiness audit of the operator workflow

**Verdict: NO-GO for real inference.** Engineering foundation `main` is now merged
at `9c8bcc4eba5e8bf4b1b3e5dfc75273c2eb0ea203`; its
[post-merge CI 40652322539](https://github.com/Ankit6149/second-source/actions/runs/40652322539)
is successful on Linux/Python 3.11 and Windows/Python 3.12, including Windows
bootstrap. This does not certify the newly proposed operator workflow.

Muse published that workflow as `bf3f0a1a43cd75b0d8b2f1f175f20c70757500ae`,
[PR #5](https://github.com/Ankit6149/second-source/pull/5), on the single shared
`integrate/g3-reconstruct` branch. Codex audits that exact published implementation
and adds only independent verifier tests plus this owned acceptance record.
No Muse-owned runtime/generation/operator code is edited. No additional feature
branch, force push, PR merge, genuine real-model execution or paid call is made.
Pushes follow the published Muse checkpoint and are ordinary fast-forwards to
the same shared branch after verifying the remote head and file ownership.

### Existing G2 artifact identities and approval limits

Read-only local audit found the actual successful run at
`.runs/real-g2-20261027T192406Z-5482abee/` in the operator's existing checkout.
The saved `run_report.json` has SHA-256
`05aa16f05ff2a0a4d707369fcb06a210726e43449c50409b92dbd50ebf9c2c0e`.
It agrees with the previously reported result, run ID, two real `meta-direct`
`muse-spark-1.3` receipts, token/cost estimates, three experiment observations
and one supported hypothesis ID. The historical response identities are:

- Hypothesize: `chatcmpl-01a17ed1-f2e4-74d6-b083-b02322104905`.
- Propose: `chatcmpl-01a17ed2-138c-764c-a60b-a4253349c220`.

All five files under that run's `evidence/` validate as `Observation`, and each
filename equals the SHA-256 of its actual stored bytes. Every action is allowed
by the current reconstruction ScopeGuard; all statuses are `ok` with exit zero,
and the existing redactor leaves their content unchanged. No credential fields,
original source or evaluator cases are present in these observation envelopes.
The following are **candidates for explicit operator approval**, not a permission
to send them to a model or a cryptographic provider attestation:

| SHA-256 artifact filename (append `.json`) | Observation identity | Recorded origin |
|---|---|---|
| `d595e04012fa6601d53607c9673583118821c6a72915d3ebfc668965767023c9` | `e01842cce6654892b49cb2b0af82a0e9:0` | Operator seed observation |
| `9252f018c2b2829bc93daf9a9a752b5cc9c8fd5019043fc998653caacd65a68d` | `e01842cce6654892b49cb2b0af82a0e9:1` | Operator seed observation |
| `22c8ea2c18d56e8abcd7936bb738c23367cc4996868077e3590fcdb4952b4fc4` | `658b367c4d744f3da685cf0e09099790:0` | Model-selected experiment observation |
| `07b6d01d357dc9f0eebc955e705d1e590369161502fd845bb4d3ddf9b2b631bc` | `658b367c4d744f3da685cf0e09099790:1` | Model-selected experiment observation |
| `1be90f95e06f8483aa9b5d5f749d4d9949b556f56fda7215efa4cc3683ccc341` | `658b367c4d744f3da685cf0e09099790:2` | Model-selected experiment observation |

**Blocking missing artifact:** the successful run records hypothesis ID
`H1-add-creates-record` and its supported status, but neither its original
statement, alternatives nor evidence citations. The run directory contains only
the five observation files and `run_report.json`. The G2 implementation keeps
the `HypothesisStore` in memory and serializes IDs/counts, not the original batch.
An ID, proposal name or status count is insufficient to recreate a Muse hypothesis.
No replacement text or citations have been fabricated, and no such file is approved.
The operator has been asked whether an authentic original response export exists
elsewhere. Without it, the full required G2 input context cannot be authenticated.

Never use `run_report.json` wholesale as generation input: its
`independent_fixture_verifier` is a synthetic evaluator-only negative control,
not observational evidence or a real candidate score. Likewise, the new mock
workflow's freshly observed data and deterministic hypotheses must not be relabeled
as this historical real G2 run. Local content hashes establish byte integrity;
the report's real/provider flags remain local operator receipts, not signed Meta
responses or independently verified provider billing.

### Published workflow findings and independent acceptance tests

`tests/test_g3_verifier_workflow.py` executes the actual mock broker, trusted
candidate worker and sealed evaluator. A hand-authored positive fixture is injected
only as an explicitly labeled mock response; no scoring or isolation gate is
bypassed. The workflow's actual score and its trusted evaluator return are compared.
The tests also exercise the CLI in a fresh credential-free subprocess, create-once
suite/digest checks, input approval mutation, origin tampering, request replay,
provider/schema failure and nonfinite budget preflight. Existing strict-comparator,
negative-control and resource/isolation suites are preserved unchanged.

Targeted independent run: **9 passed / 8 failed / 0 skipped**, 75.36 seconds,
Windows/Python 3.12.4. These eight are ordinary blocking failures with no xfail or
skip. They demonstrate these findings at `bf3f0a1`:

1. **P0 — candidate persistence.** The wrapper saves a candidate hash but discards
   the exact admitted candidate bytes and local broker artifact when the process
   ends. A digest alone cannot reproduce or independently re-score the real baseline
   or preserve immutable candidate versions for later repairs.
2. **P0 — failed-run accounting.** Provider failure or invalid generated spec exits
   without `G3_report.json`. The real-mode failure handler similarly returns before
   writing a report. The trusted budget may hold spent/uncertain charges in memory,
   but the operator loses the durable failure, attempts and budget receipt. Tests
   reproduce this with local mocks only; no real failure or charge is claimed.
3. **P1 — report provenance loss.** The wrapper drops comparator/interpreter/adapter,
   raw reference, environment, origin-receipt and observation/hypothesis registry
   digests already supplied by the pinned evaluator. Retain that sanitized receipt
   rather than reducing the completed artifact to an unattested score summary.
4. **P1 — overwrite/replay.** Existing explicit run directories are accepted, and
   `_write_report` silently replaces an existing receipt. Distinct attempts must
   not overwrite an already recorded run/report/candidate version.
5. **P1 — invalid spend authorization.** Environment ceilings `nan` and positive
   `inf` reach input loading instead of being rejected as invalid approval values.
   This does not bypass the separate $0.50 hard cap; it violates finite positive
   preflight. Tests stop at an input-loader sentinel before provider construction.

The runbook also proposes taking `approved_context_digest` from a mock run and
using it for a real G2 run. That pin identifies the mock observations/hypotheses,
whose IDs/timings and origin differ from the actual G2 artifacts. It is not approval
of the real G2 context, nor does the CLI currently provide a nonbillable prepare/
inspect step for the actual operator-supplied G2 context. The frozen suite must
also match the real scope, including its approved budget; a mock-scope suite is
not automatically a real-run suite. Correct these instructions before any spending
approval, without substituting synthetic inputs or disabling pin equality.

### Observed mock execution and residual gates

The published standalone command was independently executed with a minimal
credential-free environment, zero spend, an external disposable sealed directory
and an external run directory. Result: **MOCK 22 passed / 3 failed / 0 indeterminate
/ 25 total**, exit zero as a plumbing run, origin `mock`, `real=false`, estimated
and uncertain spend both zero. No candidate file was saved. This is an honest
scripted naive control, not model-generated reconstruction accuracy.

The independent workflow fixture separately reproduces the **25/25** hand-authored
positive through the real mock broker/pinned evaluator. Existing model/source/gold
isolation, reference identity, receipt authentication, input mutation and request
replay checks pass; report persistence/provenance failures above prevent real-run
readiness. Exact complete-suite and shared-branch Linux/Windows CI results are
reported with the pushed audit SHA after verification. The foundation's earlier
green CI and Muse's standalone workflow CI do not include these new assertions.
The complete local suite with the new independent gates reports **310 passed /
8 failed / 3 skipped**, 272.55 seconds. All eight failures are the workflow checks
listed above; every pre-existing verifier assertion and negative-control regression
passes. Existing 25-case control sensitivity remains positive **25/0/0**, broken
uniqueness **23/2/0**, broken whitespace **23/2/0**, broken amount boundary
**24/1/0** (passed/failed/indeterminate; total 25 each).

**GO:** continue nonbillable engineering corrections and independent review.
**NO-GO:** genuine G3 inference, real baseline/repair claims, merge or spending.
Before an owner-authorized run: recover/authenticate the actual G2 hypothesis
batch (or separately approve a new correctly recorded discovery operation), fix
the workflow failures, inspect and approve the exact actual G2 context out of band,
freeze the correct scope/suite/comparator/reference, rerun clean Windows/Linux
verification, and obtain a finite per-run dollar approval plus credential handling
in the trusted broker. No key has been read or requested in this audit.

G3-C remains **NOT STARTED**: no genuine generated baseline exists. Once that
baseline is independently verified and separately authorized, at most two repair
attempts may use the identical sealed bytes, approved aggregate feedback, fresh
immutable candidate versions and honest before/after/regression accounting. Existing
bounded-attempt/aggregate/replay controls remain in force; no real repair is run now.
Audit phase real model calls / spend / uncertain spend: **0 / $0 / $0**.

## Product-integration follow-up — coordinator review of PR #5

Review: [coordinator instructions](https://github.com/Ankit6149/second-source/pull/5#issuecomment-6464647743).
Published Muse correction audited independently:
`626fcac87d94164d9c6e7c77a17a517e3d6e9dde`, on the same
`integrate/g3-reconstruct` branch. Codex changes only owned independent tests
and this record. The eight original failures remain unchanged ordinary tests.
All eight now pass: exact candidate bytes, complete evaluator metadata,
provider/schema failure reports, prior nonempty run/report protection and
finite environment ceilings. This closes those reproduced regressions; it
does not establish the entire durable-workflow requirement.

Independent extended targeted run at this published source: **37 passed /
4 failed / 0 skipped**, 83.85 seconds, Windows/Python 3.12.4. It includes
all original workflow tests, new preflight tests and initial receipt faults.
Two additional receipt scenarios were then added; that final receipt module
alone reports **2 passed / 5 failed / 0 skipped**, 3.33 seconds. Counts from
these overlapping runs must not be added together.

Verified without provider construction or transport:

- Preflight's context, observation/hypothesis registries and scope match a
  separately constructed existing `PinnedEvaluatorRun` on the exact supplied
  fixture inputs. The suite binds the actual proposed $0.35 budget and rejects
  a $0.50 scope. Plan IDs are intentionally fresh; their hashes must not be
  compared as stable cross-run approval identities.
- Changed hypotheses, corrupted observation bytes, changed budget/suite and
  an incorrect approved context pin all block before provider construction.
- NaN, infinity, negative infinity, zero and negative CLI caps block before
  input loading in both preflight and real-mode approval checks.
- A missing original hypothesis file fails closed, with no fallback to
  `mock_hypotheses` and no ready receipt. All successful preflight fixtures
  are explicitly synthetic NON_AI tests of input binding, **not historical
  G2 authentication or actual-input approval**.
- The hand-authored candidate's persisted bytes independently re-score
  **25 passed / 0 failed / 0 indeterminate / 25 total** through the existing
  sealed evaluator. This remains trusted NON_AI replay.
- Concurrent report collision permits one complete winner, and fsync failure
  leaves no completed report. Existing provenance, isolation, sealed-suite,
  origin-tampering and single-use request checks remain intact.

Remaining failures at `626fcac`, sent to Muse through PR #5:

1. Exact broker payload/signature is not archived. The admitted candidate
   and evaluator origin hash are insufficient to restore that local receipt.
   Preserve the artifact immediately after generation; do not export the
   private HMAC authority or mistake it for a portable Meta signature.
2. A fault after a partial write exposes truncated JSON at the final report
   filename before cleanup. Exclusive creation plus fsync prevents overwrite
   but does not make publication atomic to readers.
3. Empty prior run directories remain reusable, including an interrupted
   run whose ID was already allocated.
4. An evaluator fault is mislabeled `broker_failed`, resets reported tokens
   to zero and discards the already admitted candidate. It must preserve
   the artifact and actual budget, with a distinct evaluation failure.
5. Keyboard interruption at that same boundary escapes without a durable
   stopped receipt, despite an admitted candidate and accounted attempt.
6. A schema-valid but semantically invalid candidate records token usage
   in the existing gateway budget, then the failure wrapper writes zero
   tokens. The test compares the report directly with the actual budget.

The runbook correctly separates mock and actual-input context pins now,
but its `REAL-RUN-READY` heading still overstates readiness. There is no
genuine G3 baseline and no authenticated historical hypothesis batch.

### G2 recovery and product acceptance limits

Read-only searches of tracked/untracked project files and all four local
historical `.runs` directories found no original structured hypothesis
export/response body. The successful run still contains only the five
hash-valid observations and its report, identified above. The original
hypothesis text/citations are **unrecoverable from these retained artifacts**;
this does not assert that an owner-held export elsewhere cannot exist.
No text or citations were inferred from the hypothesis ID or its status.

A future separately owner-authorized G2 discovery must retain the complete
original validated hypothesis batch (statements, citations, alternatives,
statuses), its observation content addresses, sanitized provider/model/
response identity and token/cost/failure receipts. Preserve immutable bytes
before later hypothesis reconciliation, and link that batch and its updates
to the same durable run. The existing discovery/gateway modules should be
extended by their owner; Codex does not create another discovery workflow.
That operation is not authorized or executed by this verification.

PRD v2.0 sections 6–7, 9–10 and 17 require more than a final CLI score:
durable meaningful stage/status events, recoverable interruption, an
inspectable approval/evidence chain, candidate replay and trustworthy export.
Current CLI progress is a final summary; no premium investigation UI,
keyboard/responsive audit, restart recovery or complete export workflow is
demonstrated here. These remain product acceptance gates. Do not expand
cosmetics before the shared mock gate is green.

**NO-GO for merge or real inference** until remaining durability failures
are fixed, exact shared-head Linux/Windows CI is green and engineering review
is obtained. Actual inference additionally needs authentic approved G2
inputs, reviewed preflight/scope/suite/reference pins and explicit finite
spend authorization. G3-C remains unstarted. This audit's real model calls /
estimated spend / uncertain spend: **0 / $0 / $0**.

### Exact CI and cross-process approval correction

The independent audit commit `4448fc6a4cbcb9ea11db3128c079bbce86a169b3`
preserves all eight original tests and adds the durable-boundary/preflight
checks described above. [CI 40661184379](https://github.com/Ankit6149/second-source/actions/runs/40661184379)
completed **FAILURE**, with independently inspected job logs:

| Environment | Passed | Failed | Skipped | Setup errors |
|---|---:|---:|---:|---:|
| Ubuntu / Python 3.11, job `122724317966` | 341 | 6 | 3 | 0 |
| Windows / Python 3.12, job `122724317621` | 342 | 6 | 2 | 0 |

The six failures are exactly the six remaining cases enumerated above. All
original workflow regressions pass. Fresh checkout/install succeeds; demo
and Windows bootstrap skip after the failed test gate. Local Windows/Python
3.12.4 independently reports **341 passed / 6 failed / 3 skipped**, 274.02
seconds. Neither OS is claimed green.

Muse flagged possible process-local frozenset serialization. A zero-call
independent reproduction using the exact same synthetic observations and
one three-citation hypothesis under `PYTHONHASHSEED=1,2,3,41,99` produced
**four distinct approved-context hashes and four hypothesis-registry hashes**.
This affects real approval equality across separate preflight/real CLI
processes, beyond a cosmetic report discrepancy.

The Codex-owned verifier correction sorts only the set-valued citation
identities before freezing the context. It retains citation membership,
hypothesis/observation sequence order, statement text, scope checks and exact
request equality. It does not reorder arbitrary model output or repair a
candidate. Old inspected contexts must be inspected and approved afresh;
no old digest is translated into an approval.

`PinnedEvaluatorRun.inspection_manifest()` now returns detached authoritative
plan/scope/suite/code/reference/context/registry pins, with no signing key,
ticket, score, provider authentication or spending approval. `evaluate()`
uses the same accessor; callers can stop duplicating registry serialization.
Existing candidate generation/runtime and Muse-owned operator files remain
unchanged by Codex.

Targeted verifier/preflight/isolation verification after this correction:
**59 passed**, 30.81 seconds. Subsequent fresh-process tests separately check
the actual operator preflight receipt: **2 passed / 1 failed**, 17 deselected,
5.68 seconds. The verifier's cross-seed equality and detached manifest pass;
the operator still reports its independently recomputed unsorted hypothesis
hash. This is an additional hard integration gate for Muse: consume
`run.inspection_manifest()` instead of recomputing the admitted registries.
The strengthened test checks five fresh processes and never constructs a
provider. No global fixed hash seed is used to hide the defect.

## Release-quality verification resumed — 28 October 2026

Scope: [latest coordinator disposition](https://github.com/Ankit6149/second-source/pull/5#issuecomment-6465261695).
The seven independent failures at `44f47803efcb0046c353942e42c36be1b34ca957`
remain unchanged hard regressions. Muse's unpublished operator edits are not
verification evidence. Complete-suite reruns and documentation reconciliation
will follow the published correction, with exact source/CI identities.

### Rechecked authentic G2 retention

Read-only re-audit of all four historical local G2 run directories finds no
original hypothesis/response/trace export. The successful run retains exactly
the five evidence JSON files and `run_report.json`; its SHA-256 remains
`05aa16f05ff2a0a4d707369fcb06a210726e43449c50409b92dbd50ebf9c2c0e`.
All five observations still pass content-address/schema checks, have `ok`
status/zero exit and are unchanged by redaction. Their identities above are
unchanged. These are local integrity checks, not independent provider
signatures or billing verification.

The original hypothesis statement/citations cannot be recovered from the
retained identifiers/statuses. Recover an authentic original owner-held
response export if it exists; otherwise request a separately approved new
G2 discovery that durably records the original complete validated batch,
observation citations, provider/model/response identity and all actual/uncertain
usage before subsequent reconciliation. No discovery call or fabricated
replacement batch is authorized by this audit.

### Reproduced transport-interruption accounting risk

At `44f4780`, a local `MetaProvider(test_mode=True)` with a synthetic key and
`urllib.request.urlopen` replaced by a function raising `KeyboardInterrupt`
leaves `RunBudget.attempts=1`, unresolved reservation `$0.00028325`, public
`uncertain_cost_usd=0` and no gateway receipt. The reservation is only in
private in-memory state. This probe makes **zero network/genuine model calls**;
the amount is a synthetic reservation, not observed spending or provider billing.

Severity: **P0 for real-run release** under the existing interruption/accounting
requirement. Copying only public counters into an interrupted report could
lose a possible charge. Acceptance: inject interruption after reservation
without network access; persist a sanitized stopped outcome with attempt one
and the unresolved reservation conservatively accounted as uncertain (or
explicitly durably exposed for reconciliation). Preserve already reported
usage, avoid double counting settled reservations and prevent silent retry.
The source owner must implement or coordinate a narrow accounting correction;
Codex does not edit Muse-owned gateway/operator code. This is a reproduced
error path with a defined acceptance condition, not an added speculative gate.

### Published Muse corrections and owned accounting closure

Muse published `0021906248855f20754ac24e1ebfc6437ac65937`; independent
diff inspection confirms changes only to operator implementation/tests/runbook.
All seven previous independent regressions remain unchanged. Targeted
workflow/preflight/receipt verification: **46 passed / 0 failed**, 147.24
seconds. Authoritative cross-process input pins, exact broker archival,
partial-write/fsync/concurrent no-clobber checks, empty interrupted run IDs,
evaluator failures, interruption and token accounting now pass those gates.

The additional focused interruption probe reproduces an unresolved synthetic
broker reservation of `$0.0104525`; a second scenario reproduces a retry after
interruption following already committed provider usage. Neither issues a
candidate origin artifact or makes a network/genuine model call. Synthetic
response identity is explicitly `NON_AI_SIMULATION_NOT_PROVIDER_EVIDENCE`;
no simulated result is historical G2/G3 evidence or a model-quality score.

The narrow Codex-owned `PinnedEvaluatorRun` correction handles interruption
before returning control to the operator: it books only the existing ledger's
pending reservation through `RunBudget.fail(Reservation(...))`, marks the
real attempt failed and propagates interruption for the stopped report.
Already committed/failed reservations have zero pending balance, so their
actual tokens/costs are preserved without adding uncertain spend twice.
The existing budget model/API, gateway and Muse-owned operator source are
unchanged. It deliberately reads the current RunBudget's private pending
balance; a future public accessor would reduce coupling, but is not a new
release gate or a second accounting model.

Focused tests verify conservative uncertainty, settled usage, exact durable
stopped counters, consumed request replay rejection and fresh-preflight
requirement before another transport. Combined targeted verifier isolation,
receipt and preflight run: **69 passed / 0 failed**, 56.52 seconds. Complete
exact-head CI and repository reconciliation follow this source checkpoint;
no green CI or engineering certification is inferred from a targeted run.
