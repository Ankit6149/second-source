# Sandbox backend boundary

`backend.sandbox` defines an optional operation-approved execution boundary.
The public API continues to use the existing trusted local mock worker. No E2B or
Daytona backend is activated, no authorization is created by this module, and no
sandbox was provisioned during implementation or testing.

`SandboxOperation` accepts exactly two immutable, SHA-256-checked data files:
`candidate.v1.json` classified as `candidate-policy`, and `actions.json` classified
as `public-probe-input`. The latter must contain:

```json
{"kind":"PUBLIC_LEDGER_PROBES_V1","actions":[{"command":"total"}]}
```

This is explicitly approved public observation/probe input. Sealed evaluation
inputs, evaluator cases and candidate-generation payloads do not belong here.
Only the existing ledger commands are allowed. There are no user command, source
code, environment, network or arbitrary-path fields. Candidate policy admission
remains the existing engine's responsibility; this module adds no interpreter,
planner, scoring or repair logic. Obvious secret/sealed markers are rejected as
defense in depth, which cannot prove the provenance of arbitrary mislabeled data.
Trusted callers remain responsible for supplying genuinely authorized public data.

A `TemplateCapabilityReceipt` binds an exact template identity, CPU/memory,
trusted preinstalled runner hash and an externally retained configuration witness.
Its operator-reviewed and no-secrets flags must be explicit. The template must
already provide `/opt/second-source/run-owned-ledger`, which reads these data
files from `/home/user/second-source`. This runner/template contract is not
implemented or provisioned here. A mutable template alias is unsuitable; template
immutability and the witness require independent operator review.

The operation digest includes all input hashes/classifications/sizes, requested
output names, resource/time/output limits, template receipt digest and fixed runner
path. `SandboxAuthorization` must approve that exact digest and provider with
explicit provisioning permission. The injected `claim_authorization` callback
must atomically consume a previously approved durable grant before dispatch. An
authorization callback must capture the verified owner/run and enforce expiry and
scope there; an HTTP caller must not select the grant's owner. An
in-memory replay guard supplements that callback; it cannot replace durable
authorization across process restarts. No callback, grant or dataclass alone
confers owner consent. Rejected or uncertain operations never fall back to a
different provider and never automatically retry.

`E2BSandboxBackend` requires an explicit server-side API key after approval. It
does not read environment keys. SDK import is lazy, and an injected SDK supports
offline mechanics tests. Creation requests an exact reviewed template, bounded
lifetime, empty custom environment, internet disabled and kill-on-timeout with
auto-resume disabled. CPU/memory are template capabilities, not invented create
arguments. Before any data write or command, `get_info` must report the expected
template, CPU and memory and explicit `allow_internet_access=False`; absent or
unknown properties fail closed as `TEMPLATE_CAPABILITY_UNPROVEN`. The runner bytes
are streamed and hashed before use. Each approved upload is read back and hashed.

Only the fixed runner command executes. Stream callbacks enforce a combined
stdout/stderr cap with SDK `retain_output=False`; command connections have an
explicit timeout. Optional returned artifacts are restricted to
`execution-result.json` and `candidate-output.jsonl`, streamed under a combined
byte limit, and returned with the existing `ArtifactReference` SHA-256/size shape.
These artifacts and output are private data, not scientific acceptance results.
They must not be copied wholesale into public API responses or proof bundles.

The sandbox is killed in `finally` after creation, including command failures,
timeouts, output overflow and interrupts. Receipts distinguish attempted creation,
attempted execution, bounded private output, known exit code, primary failure and
cleanup confirmation. A lost creation response has no handle to kill: its outcome
stays unknown, the grant stays consumed and no automatic recovery dispatch occurs.
Cleanup failure stays unknown even when the command exit is known. Provider
exceptions, credentials and private paths are excluded from diagnostics.

The `FakeSandboxBackend` returns deterministic configured fixture output labelled
`NON_AI_FAKE`. It executes no target and assigns no score. The Daytona alternative
boundary returns `DAYTONA_CAPABILITY_UNPROVEN`; it imports no SDK or credentials
and is never an automatic fallback. Daytona's documented tier policies need live
review before any adapter can claim block-all enforcement.

The optional Python package version `e2b==2.62.0` was confirmed in the public PyPI
metadata and official SDK reference on October 30, 2026. It is **not installed or
tested against a real SDK in this checkout**. No dependency was added. Tests inject
SDK-shaped fakes and prove local gating, bounded mechanics and cleanup handling;
all SDK receipts retain `isolation_verified=False`. Neither SDK method availability
on the deployed account, resource limits, host isolation, outbound blocking,
template contents, billing availability nor live cleanup has been accepted.

Protocol references checked:

- [E2B Python SDK 2.62.0](https://docs.e2b.dev/sdk-reference/python-sdk/v2.62.0/sandbox_sync)
- [E2B internet access](https://docs.e2b.dev/network/internet-access)
- [E2B lifecycle](https://docs.e2b.dev/sandbox)
- [E2B streamed commands](https://docs.e2b.dev/commands/streaming)
- [E2B file reads and writes](https://docs.e2b.dev/filesystem/read-write)
- [Daytona network limits](https://www.daytona.io/docs/en/network-limits/)

The current E2B reference marks `secure=True` as deprecated and ignored; it is
included for compatibility and is not independent security evidence. Live
acceptance needs exact SDK installation, verified template/resource/network
evidence, cost permission, independently reviewed operation authorization and a
bounded real run. Those gates remain closed.

Run hermetic checks with `python -m pytest tests/test_backend_sandbox.py`.
