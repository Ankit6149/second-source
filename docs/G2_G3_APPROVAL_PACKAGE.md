# G2 to G3 execution approval package

Prepared 28 October 2026 for the consolidated engineering milestone on
`integrate/g3-reconstruct`, [PR #5](https://github.com/Ankit6149/second-source/pull/5).
This is a nonbillable preparation record, **not input, spending or merge
authorization**. Preserve prior accepted `936492d` as historical evidence. The
[delivery board](G3_DELIVERY_BOARD.md) remains the authoritative delivery board;
this document records recovery evidence and the future approval boundary.

**Consolidated implementation:** source/tests
`bc16552cf4c204bbe3f3fb8fb136353e898156fb` combine Muse c0e82b5/0849b48 with the
reviewed Codex journal/preflight and retained Muse progress/results. The
version-2 journal is the only supported new-discovery persistence path.
Independent persistence, inspector and G2/G3 binding review pass, with
[exact-source CI40701890631](https://github.com/Ankit6149/second-source/actions/runs/40701890631)
green: Linux425 passed/0 failed/3 skipped, Windows426/0/2, bootstrap426/0/2
BOOTSTRAP_OK. Documentation-only descendants also require their own exact-head
CI, recorded by the final PR review. See the [consolidation review](G2_PERSISTENCE_REVIEW.md). The
previous local49fa288/3d1334e and blocked c0e82b5 are historical inputs to
this consolidation, not additional supported implementations.

## Current decision

**STOP before real G3 approval:** an authentic complete historical G2 hypothesis
batch has not been recovered. Observation hashes and recorded response IDs do
not supply the absent statements, alternatives or evidence citations. Do not
derive them from hypothesis/proposal identifiers, replace them with mock
hypotheses, or use a mock context digest for actual-input approval.

The earlier accepted zero-cost checkpoint remains valid at its historical
SHA. The consolidated result above includes all preserved G3 gates. Trusted positive and
offline replay **25/25**, negative sensitivity **2/2/1**, and scripted mock
**22/25** are all **NON_AI** controls, not Meta reconstruction results.

## Read-only recovery audit

Audit boundary: tracked repository files, local Git history/all available refs,
and project-local `.runs` in the original and verifier checkouts. No `.env`,
credentials, unrelated private sessions, provider account or remote response
retrieval was accessed. The audit made no provider calls or reference actions.
It cannot rule out an authentic owner-held export outside that boundary.

The original checkout has four historical `real-g2-*` directories, containing
15 files total: four reports and eleven hash-addressed observations. Every
directory contains only `run_report.json` and `evidence/*.json`. No complete
hypothesis batch, model response body, original proposal body or request
archive was found. Git path/history inspection found no committed historical
run reports or response/hypothesis exports; `.runs` remains ignored.

| Historical run | Report raw SHA-256 | Recorded result |
|---|---|---|
| `real-g2-20261027T184607Z-73bbd66a` | `8e39a104d367b60b63406ad9590c0ec6d5e33943af06801f7a9f3ae6ada4c1a7` | Incomplete; failed hypothesis receipt |
| `real-g2-20261027T190034Z-530e42f8` | `6ad250139efdac64fc01f41b8c0e6d91f8fee7180537b47b01b156da49d2dd0b` | Incomplete; failed hypothesis receipt |
| `real-g2-20261027T190454Z-f43553c6` | `ac8519c8fed5fa6b1beb9edbe166e991cc2a311d6da6c02d6d00e1d196af8a30` | Incomplete; two successful model receipts, no model-selected reference experiment |
| `real-g2-20261027T192406Z-5482abee` | `05aa16f05ff2a0a4d707369fcb06a210726e43449c50409b92dbd50ebf9c2c0e` | `REAL_EXPERIMENT_OBSERVED` |

The successful run's report records `meta-direct`, `muse-spark-1.3`, real
origin, and these two successful receipts:

| Stage | Response ID | Input/output tokens | Internal estimate USD |
|---|---|---|---:|
| Hypothesize | `chatcmpl-01a17ed1-f2e4-74d6-b083-b02322104905` | 1068 / 539 | 0.00362575 |
| Propose | `chatcmpl-01a17ed2-138c-764c-a60b-a4253349c220` | 1614 / 1664 | 0.00908950 |

Historical estimated total: **$0.012715**, recorded uncertain cost **$0**.
These are retained local receipt fields, not newly reproduced calls, signed
provider attestations or independently verified charges. Meta billing remains
authoritative. Response IDs alone do not recover response contents.

The five successful-run observation files rehash exactly to their filenames,
validate as existing `Observation` records, and pass the current owned-fixture
scope guard using public command effect declarations. The current redactor
does not change their contents. This establishes local integrity/schema/scope
checks; it does not itself authorize sending these observations to a model.

| Observation ID | Raw content SHA-256 |
|---|---|
| `e01842cce6654892b49cb2b0af82a0e9:0` | `d595e04012fa6601d53607c9673583118821c6a72915d3ebfc668965767023c9` |
| `e01842cce6654892b49cb2b0af82a0e9:1` | `9252f018c2b2829bc93daf9a9a752b5cc9c8fd5019043fc998653caacd65a68d` |
| `658b367c4d744f3da685cf0e09099790:0` | `22c8ea2c18d56e8abcd7936bb738c23367cc4996868077e3590fcdb4952b4fc4` |
| `658b367c4d744f3da685cf0e09099790:1` | `07b6d01d357dc9f0eebc955e705d1e590369161502fd845bb4d3ddf9b2b631bc` |
| `658b367c4d744f3da685cf0e09099790:2` | `1be90f95e06f8483aa9b5d5f749d4d9949b556f56fda7215efa4cc3683ccc341` |

No raw action/output payload is reproduced here. The report's
`independent_fixture_verifier` field is synthetic negative-control feedback;
it is evaluator evidence and must not be supplied as model observation data.

Source inspection explains the gap: the historical `DiscoveryLoop`/planner
kept complete hypotheses in `HypothesisStore` memory. `live_experiment`
serialized round hypothesis IDs/status counts and gateway receipts, but not
the validated hypothesis batch, cited digest set or original response body.
The four reports lack those omitted records. Do not silently convert that
historical limitation into a claim of complete G2 input provenance.

Recovery options, in priority order:

1. The owner can supply a contemporaneous original structured response/export
   or authenticated provider retrieval containing the missing batch and a
   verifiable link to these response identities. Review this independently;
   do not infer content from report identifiers. Retrieval requiring account
   credentials or paid operations needs separate explicit authorization.
2. If recovery fails, independently verify durable G2 persistence with
   nonbillable fixtures, then request approval for a **new** bounded G2 run.
   Preserve the old run as historical incomplete input evidence. A new run is
   new provenance, never recovery of old statements.

## Stage A: nonbillable persistence prerequisite

Extend the existing G2 modules/CLI, not a second discovery orchestrator.
Before approving a new run, require durable complete validated hypothesis
batches, exact cited observation digest references, original model response
identity/content where safely retained, model/provider/real-origin receipts,
scope/run identity, attempt/token/estimated/uncertain counters and explicit
terminal or interrupted state. Keep sanitized export separate from private
local model-response records. Never persist credentials or reference/gold
source as model inputs.

Required independent fixture evidence: success/restart/reload; citations
resolve to hash-valid observations; malformed/unknown-citation responses are
not promoted to complete inputs; partial/provider/schema/budget/interruption
failures preserve truthful accounting and incompleteness; artifact changes or
missing receipts block completeness; no overwrites or mock-to-real relabeling.
Offline restart/reload means inspecting preserved state, not automatically
resuming paid model dispatch. It must not issue another model request.

**Interface status:** the consolidated persistence path adds journaled original
response text, validated batch/receipt association, zero-call G2 preflight,
offline inspection and create-once export through the existing CLI. It supersedes the
earlier incomplete export. Its independent review and local tests are recorded in
the follow-up review; full exact-source Linux/Windows CI is green as recorded above.
The commands below document the consolidated interface; they grant no approval:

```powershell
# NON_AI discovery plumbing; no credentials or model transport.
.venv/Scripts/python.exe -m second_source.live_experiment --mode mock `
  --run-dir <new-exclusive-mock-directory>

# Offline reload, no execution resume or inference. Prints receipt SHA-256.
.venv/Scripts/python.exe -m second_source.live_experiment `
  --inspect-run <discovery-directory>

# Revalidate the externally retained receipt hash and export a complete batch.
.venv/Scripts/python.exe -m second_source.live_experiment `
  --inspect-run <discovery-directory> --receipt-sha256 <retained-receipt-hash> `
  --export-batch <new-exclusive-batch.json>

# Thin read-only view of that SAME journal, including unsettled reservations.
.venv/Scripts/python.exe -m second_source.g2_inspect <discovery-directory> `
  --receipt-sha256 <retained-receipt-hash>
```

Retain the initial `G2_receipt.json` hash outside the mutable run archive;
local hash chains alone do not detect wholesale replacement. A complete mock
export remains NON_AI and cannot become genuine G2 input through approval
terminology. Offline inspection must fail closed or classify interruption
when responses, events, observations or receipts are missing. A known settled
budget must survive response-archive publication failure without reverting
to pre-dispatch counters. Independent nonbillable fault probes now confirm the
consolidated path preserves settled usage with `response_archive_complete=false` after
result publication failure, and preserves one attempted reservation with zero
dispatch/cost after pre-dispatch publication failure. Both remain incomplete
and reject batch export. Full exact-source cross-platform CI is green.

The thin inspector exposes `pending_attempt` and `pending_uncertain_cost_usd`
separately from settled `budget`. An interrupted dispatch does not display a
zero pending exposure merely because no terminal receipt was written. Both
inspectors are offline; neither retries nor authorizes transport.

## Stage B: proposed bounded new G2 discovery

First freeze the independently tested source and prepare the proposed G2
operation with the existing entrypoint's zero-call mode:

```powershell
# No credentials, provider construction, reference execution or paid calls.
.venv/Scripts/python.exe -m second_source.live_experiment --mode preflight `
  --max-usd 0.25 --rounds 1 --run-dir <new-exclusive-G2-preflight-directory>
```

Retain the create-once `G2_preflight.json` file and its printed raw receipt
hash outside the run directory. Its `manifest_sha256` binds the canonical
scope/budget, round count, exact source/reference/public-manifest byte hashes,
seed actions, token caps, configured Meta model and pricing snapshot. The
receipt labels itself `inspection-only` with `provider_calls=0`; the manifest
describes the proposed real operation and does not authorize it. Recompute
after any source, scope, budget or round-count change and seek fresh approval.

Independent consolidation checks exercised three fresh processes with hash seeds
`1`, `37` and `99`: manifest pins agreed, no credential reads or
provider/reference construction occurred. Wrong pin, changed budget, changed
rounds and missing confirmation all returned a block before credential access
or provider construction. Exact source and full CI are pinned above.

Only after Stage A is verified and the owner explicitly approves this exact
manifest, scope, inputs and spend, use the entrypoint for **one round**:

```powershell
# BILLABLE TEMPLATE ONLY. Not authorized or executed by this preparation.
# Owner configures MODEL_API_KEY securely; never put a key in this document.
$env:SECOND_SOURCE_MAX_RUN_USD = "0.25"
.venv/Scripts/python.exe -m second_source.live_experiment --mode real `
  --max-usd 0.25 --rounds 1 --confirm-real-run `
  --operator-manifest-pin <owner-approved-G2-manifest-sha256>
```

Expected model operations: one `hypothesize` and one `propose` request to
`meta-direct` using `muse-spark-1.3`; **at most one** corrective `propose` after
a successfully received but guard-rejected proposal. Maximum **three model
attempts**. The current request output ceilings are 2400 hypothesis tokens
and 2800 per proposal. The owned reference baseline is executed through the
existing guarded runner; model-selected actions remain subject to that guard
and the fixed fresh-process-per-sequence reset boundary.

Exact proposed target: `owned-ledger-v1`, permission `owned-fixture`, guest
CLI commands `add/list/remove/total`, requirement `REQ-LEDGER`. Seed sequence:
add Alpha/3 then total. Scope bounds:3 reference sequences,240 wall seconds,
3 model attempts,200000 input/60000 aggregate output token caps; per-request
limits above are tighter. Configured price snapshot is USD1.25 input/4.25
output per million tokens, an internal estimate to recheck before approval.
No provider pricing or account balance was queried during this phase.

The proposed **$0.25 application ceiling** is not a quote, an expected charge,
a provider billing guarantee or spending approval. Worst-case reservation
must fit the exact finite budget before each attempt; uncertainty counts
against it. No extra smoke/ping calls, implicit retries or repairs are included.
On provider failure or uncertain accounting, stop and review before another
paid run. Record any unused allowance; it is not transferable authorization.

Freeze the reviewed source SHA, G2 preflight receipt/hash and manifest pin,
public manifest, reference identity, target permission, scope/budget, seed
selection and expected maximum operations in the owner approval record before
dispatch. Real mode checks the exact approved manifest pin and confirmation
before reading the provider key. After the run, authenticate its
durable observations, complete hypothesis batch, response/usage receipts and
failure/completeness state. Do not approve a G3 input solely because the CLI
reported `REAL_EXPERIMENT_OBSERVED`.

## Stage C: actual-input zero-call G3 preflight

This existing command requires no provider credentials and performs no
inference. Run it only with an authentic complete G2 export selected for
review, never with guessed historical hypotheses:

```powershell
.venv/Scripts/python.exe -m second_source.reconstruct --mode preflight `
  --max-usd 0.50 --ledger-dir <actual-G2-evidence-directory> `
  --hypotheses-file <authentic-validated-batch.json> `
  --observation-digests <exact-approved-comma-separated-digests> `
  --g2-receipt <actual-G2-directory/G2_receipt.json> `
  --g2-receipt-sha256 <externally-retained-G2-receipt-hash> `
  --seal-dir <new-private-external-seal-directory> `
  --run-dir <new-exclusive-preflight-directory>
```

Require `provider_calls=0`, `origin=inspection-only`, no credential access or
provider construction, and a create-once `G3_preflight.json`. Record its raw
file hash plus evaluator-authoritative `approved_context_digest`,
`observation_registry_digest`, `hypothesis_registry_digest`, `scope_digest`,
public `manifest_digest`, `suite_digest`, `plan_digest`, `code_pins`,
`reference_identity` and `reference_source_digest`. Capture exact selected
input file hashes and the hypothesis-response receipt association alongside
the existing evaluator receipt. The proposed budget is part of the frozen
scope: changing it requires a new preflight and new approval.

The G2 receipt and external witness are mandatory for real G3. They bind the
complete original batch (all fields), full observation digest set, actual
target and reference/public-manifest bytes through the single journal reader.
Missing/altered receipts, substituted inputs and mock origin block before
credential access or transport. `G3_input_provenance.json` is published before
dispatch and retained if later generation fails. `--g2-manifest` is a flag
alias for the version-2 receipt, not support for the retired legacy format.

Repeat inspection of the same frozen inputs/suite in separate processes and
hash seeds; all authoritative pins must agree. Attempt altered/missing inputs,
invalid approval, changed suite/scope and insufficient/nonfinite budgets with
mock transport sentinels; all must block before provider transport. Keep
sealed inputs, original source, credentials and private signing authority
outside model context. The private ephemeral broker signing key is not
exported; local HMAC evidence is not portable provider attestation.

## Stage D: separately approved single G3 generation

**Approval remains pending and cannot be filled in now.** Supply the owner
with the exact Stage C receipt and source SHA, actual immutable input pins,
scope/permission, private suite identity, selected Meta model/endpoint,
operation bound and budget. The G3 proposal is **one candidate-generation
model attempt, no repair**, maximum output 2000 tokens at the current default,
with a proposed **$0.50 application ceiling**. Input tokens depend on the
approved frozen context and must pass reservation checks. No paid call is
needed for sealed scoring or offline replay.

The new-G2 plus G3 proposals total at most **$0.75 in application allowances**
across two separately approved stages. This is not a combined authorization,
an expected invoice or a guarantee against provider charges. Actual estimates,
uncertain reservations and provider-confirmed billing remain distinct.

Only after explicit owner input/spending authorization:

```powershell
# BILLABLE TEMPLATE ONLY. Requires separate owner approval after preflight.
# Owner configures MODEL_API_KEY securely outside transcripts/artifacts.
$env:SECOND_SOURCE_MAX_RUN_USD = "0.50"
.venv/Scripts/python.exe -m second_source.reconstruct --mode real `
  --max-usd 0.50 --confirm-real-run `
  --operator-context-pin <owner-approved-actual-input-context-digest> `
  --ledger-dir <same-actual-G2-evidence-directory> `
  --hypotheses-file <same-authentic-validated-batch.json> `
  --observation-digests <same-exact-digest-list> `
  --g2-receipt <same-actual-G2-directory/G2_receipt.json> `
  --g2-receipt-sha256 <same-externally-retained-G2-receipt-hash> `
  --suite <same-private-suite.json> --suite-digest <same-suite-digest> `
  --run-dir <new-exclusive-real-run-directory>
```

Acceptance requires exact archived broker payload/envelope and candidate
bytes, genuine real-provider response identity, complete budget counters,
the pinned independent evaluation receipt and immutable sanitized report.
Re-score the exact candidate offline against unchanged sealed bytes; report
passed/failed/indeterminate/total, behavioral differences and actual provenance
without presenting a control score as model success. Failure, invalid candidate,
interruption or indeterminate evaluation remains an honest outcome, not a
reason for an unapproved retry. Repair is outside this approval package.

## Owner decision checklist and next action

- Merge PR #5: separate owner authorization; accepted engineering checkpoint
  is prepared for review and remains unmerged.
- Historical input recovery: authentic complete original export is missing;
  owner may identify one without recreating it.
- New G2: persistence verification and explicit up-to-$0.25 authorization
  required; no credentials have been used by this audit.
- G3: authentic input approval, zero-call receipt and separate up-to-$0.50
  authorization required; no genuine G3 reconstruction has run.
- Submission/demo: label NON_AI controls and historical discovery correctly;
  do not claim genuine reconstruction or full product readiness until the
  real candidate, independent result and reproducible evidence package exist.

Next action after engineering acceptance: owner reviews the new G2 proposal
and frozen manifest; do not dispatch until separately authorized. If the
owner identifies a contemporaneous original export first, authenticate it
before deciding whether new discovery is needed.
Source changes, future approval pins and their CI must be reviewed at their
own exact SHA; this document does not extend accepted CI to unverified work.

## Recorded nonbillable continuous workflow demonstration

Source `bc16552cf4c204bbe3f3fb8fb136353e898156fb`, verifier-local run
`.runs/codex-g2-final-20261028T140316Z-fe8cbe99/verification.json`.
This ignored private artifact is not a portable public evidence export;
the identities below permit local independent checking. No raw response,
hypothesis text, source/gold inputs or private suite is published here.

| Artifact | Exact SHA-256 (raw bytes unless prefixed) |
|---|---|
| G2 mock receipt | `1645597891d22760120daf32d907eda2612c27bc2e028b8957b8b42fca4285cc` |
| Complete original mock batch export | `5dc3728770dbe6357a45cb69e5680611108e80043b05fd2ffb5a5755ff63d436` |
| Proposed REAL G2 manifest, zero-call preparation only | `7f2b52132136b228d3fd32f36537cc7ddec0b601cac83e868f17c5bacd6193ec` |
| G2 zero-call preflight receipt | `d14f5cdae49c5a5847748d32990da513bae1396320ea1a1d622bce89b43a1555` |
| G3 mock-input zero-call preflight receipt | `d04fc8850287d4a767dcb9b8e155380db6fc02c7a1807ee551bdf38a76d659cf` |
| G3 mock-input context (NEVER real approval) | `sha256:7d2d9de2edad6231dda763769ae6a92e8586a21c2e0ba3d0762082ef11d54df2` |
| Bound mock candidate | `sha256:a36d5922f8fd2d17e926ebd0710a1a08ad8c6ee5466734d06e806bc55ebe0ae8` |
| Bound mock broker envelope | `019ba3c99b04945c7091ccc5af331df1085db506520a2967fe3c017ef44e4f21` |
| Bound mock G3 report | `c0dba84af4def63797e4843064acf58c4ea0d0369d7f4e5535d6ec62535d15df` |

The G2 mock produced3 observations/2 mock receipts, then a fresh process
reloaded and exported the complete original batch against its retained
witness. Both preflights recorded provider_calls0. Bound G3 consumed that
exact ledger/batch/digest set and receipt witness, with no replacement mock
observations/hypotheses, and published G3 input provenance before dispatch.
Default scripted candidate:22 passed/3 failed/0 indeterminate/25, one mock
generation attempt,1774 synthetic input/236 output tokens. Estimated/uncertain
spendUSD0, genuine calls0, real candidate absent. The independently tested
hand-authored25/25 and defect sensitivity2/2/1 remain separate NON_AI controls.

Reproduce using the same CLI, after Stage A mock export (never real mode):

```powershell
.venv/Scripts/python.exe -m second_source.reconstruct --mode mock `
  --ledger-dir <mock-G2-run/evidence> --hypotheses-file <exported-original-batch.json> `
  --observation-digests <full-comma-separated-digests-from-inspection> `
  --g2-receipt <mock-G2-run/G2_receipt.json> `
  --g2-receipt-sha256 <externally-retained-mock-receipt-hash> `
  --seal-dir <new-private-external-directory> --run-dir <new-exclusive-G3-mock-run>
```

Complete mock inspection yields `approvable=false` and
`real_input_eligible=false`. The proposed real G2 manifest is a distinct
future operation, not a relabeled mock receipt. Its pin is applicable only
to these exact checked-out source/reference bytes and scope. Before owner
authorization, reproduce zero-call preflight on the actual execution machine
and retain its full receipt externally; changed bytes/OS setup need review.
