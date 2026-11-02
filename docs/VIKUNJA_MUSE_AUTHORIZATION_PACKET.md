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
- Arm C context digest: `sha256:1a04b39d3cc2c61a27bafeb9678940966059e6e8f88fdb8f32c0edbcc8d4eb4d`
- Arm D selection digest: `sha256:cafbaf6a057d2bc38314ec6fb747f802796a96e2d622884b0900db582978d30d`
- Public observations: `.runs/vikunja-benchmark/public_observations.json`
  (8,675 bytes; authorized probes only).
- Held-out evaluator: `scripts/vikunja_held_out.py`
  sha256 `57d07a9224c09d82bfebfde76799751a9845247892ddfa44145fe18a0e80c1fa`
  — never included in any prompt.
- Interpreter sha256: `40228af10333780e9d01b99e6872826de1b5277992b48369baa51f0c133ebfc0`
- Evaluator sha256: `6b8c37bd8434ec8717354ad2426ce5fca2b20b44f495bcdb24d0347af2578ed1`

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
