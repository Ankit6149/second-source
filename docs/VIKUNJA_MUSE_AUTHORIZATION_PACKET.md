# Authorization packet — genuine Muse Spark Vikunja experiment

Status: PREPARED, zero calls made. This packet requires separate owner
authorization. The earlier $0.50 approval covered the G4 HTTP fixture
only and does **not** extend to this experiment.

## What would run

The same measured protocol as the Gemma development arms
(`scripts/vikunja_model_experiment.py`), with the provider swapped to
Meta. Only the two strongest arms, to protect the remaining balance:

| Arm | Semantics | Model calls |
|---|---|---|
| C_grounded | coverage-grounded prompting over public observations | 1 synthesis |
| D_active | model selects probes → executed on fresh reference → synthesis | 1 selection + 1 synthesis |

Total: **3 calls maximum. No retries, no escalation, no fallback.**
Any failure (non-JSON, schema rejection, evaluator error) is recorded
and the run stops for that arm; nothing is re-sent.

## Exact inputs (frozen at preflight, 2026-11-02)

- Model: `muse-spark-1.3` via the existing gateway (`MetaProvider`).
- Arm C context digest: `sha256:8b88e0fd183314f9ca40233173804b088d62dbba58b1db57b42b1e0fd38eebc0`
- Arm D selection digest: `sha256:23c3446d9d855ba5f69e5a08210416eb1316e95ead63622277b2a72d5e4ae39f`
- Public observations: `.runs/vikunja-benchmark/public_observations.json`
  (16,969 bytes, 19 probes, regenerated on a fresh reference DB;
  verified to contain no held-out titles or outcomes).
- Held-out evaluator: `scripts/vikunja_held_out.py`
  sha256 `57d07a9224c09d82bfebfde76799751a9845247892ddfa44145fe18a0e80c1fa`
  — never included in any prompt.
- Interpreter sha256: `40228af10333780e9d01b99e6872826de1b5277992b48369baa51f0c133ebfc0`
- Evaluator sha256: `d94624265ce79f8cea4a1a5709b09d381e3e43405c8153ad42725e4af899a86a`

Arm D's synthesis prompt cannot be frozen in advance (it contains
the probe outcomes the model selects). Its digest is recorded in the
run record before the synthesis call and reported with the result;
the frozen part is the selection prompt above. If that is not
acceptable, authorize Arm C only (1 call, fully frozen).

If any prompt, held-out file, or interpreter changes, digests change
and this packet is void — re-preflight before spending.

## Budget

- Hard ceiling: **$0.50 total** for this experiment, enforced at the
  gateway layer (`SECOND_SOURCE_MAX_RUN_USD=0.50`) in addition to this
  packet. The ~$15 reported balance is not authorization to spend $15.
- Expected cost: prompts are 1.5K–11K chars with ≤8K output tokens per
  call; expected well under the ceiling, but the run fails closed at
  $0.50 regardless of expectations.
- Muse Spark token pricing was not independently verified at packet
  time; that is precisely why the hard cap, not an estimate, governs.

## Preconditions (owner, local — never paste keys in chat)

```powershell
setx MODEL_API_KEY "<Meta Model API key>"
setx SECOND_SOURCE_MAX_RUN_USD "0.50"
```

Then confirm in chat: "Meta key is set for the Vikunja packet."
The agent verifies credential presence without printing it, re-runs
zero-call preflight, and shows the digests again before the first call.

## Evaluation and reporting

- Per-arm fresh Vikunja v2.4.0 instance (new SQLite DB, own port);
  candidate runs in a fresh interpreter process.
- Score admitted only if the spec passes schema validation AND the
  evaluator exits 0 with a parseable held-out result (6 cases).
- Successful and failed candidates reported separately, with failure
  class (MODEL_OUTPUT_NOT_JSON / SCHEMA_REJECTED / EVALUATOR_ERROR /
  score). Gemma and oracle results are never substituted for Muse.
- Honest delimiter: the model authors a declarative spec; the generic
  interpreter supplies state machine, storage, auth plumbing, and
  permission enforcement. Report as spec-level reconstruction.

## Stop conditions

Stop and report, spending nothing further, if: digests differ from
this packet, the gateway cannot enforce the cap, the reference or
evaluator fails its self-check (6/6), or the owner withdraws approval.
