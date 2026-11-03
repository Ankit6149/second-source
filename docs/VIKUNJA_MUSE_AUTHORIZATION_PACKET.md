# Authorization packet — genuine Muse Spark Vikunja experiment

Status: **EXECUTED**. 3 calls made total (C synthesis, D selection, D synthesis). Packet digests matched the run record. Results (`REAL_MODEL`, genuine Meta `muse-spark-1.3` only): C_grounded **2/6** held-out (cases 1, 3); D_active **1/6** (case 3; model selected probes D1, D4, D5, D6, D7; 22 probe observations). Spend was reservation-capped at **$0.50**. Gateway receipts were lost to a driver crash after both arms completed - stated plainly: no receipts survive, so no billing figure beyond the $0.50 reservation cap is claimed. Run record: `.runs/vikunja-model/meta_arms_result.json`. This packet is consumed; it does not authorize further calls.
Executed under separate owner authorization for this packet; the earlier $0.50 G4 approval did not extend to it.


## What ran

The same measured protocol as the Gemma development arms
(`scripts/vikunja_model_experiment.py`), with the provider swapped to
Meta. Only the two strongest arms, to protect the remaining balance:

| Arm | Semantics | Model calls | Result (REAL_MODEL) |
|---|---|---|---|
| C_grounded | coverage-grounded prompting over public observations | 1 synthesis | **2/6 held-out (cases 1, 3), admitted** |
| D_active | model selects probes, executed on fresh reference, then synthesis | 1 selection + 1 synthesis | **1/6 held-out (case 3), admitted; selected D1, D4, D5, D6, D7; 22 probe observations** |

Total: **3 calls made. No retries, no escalation, no fallback were used.**
Both candidates were admitted. The digests below matched `packet_digests` in the run record (`C_grounded` and `D_selection` as listed).


## Exact inputs (frozen at preflight, 2026-11-03 refresh)

Refreshed because the interpreter gained `compiled_*` evidence-compiled
kinds and observations were regenerated losslessly; the 2026-11-02
digests below the line are void. Preflight was re-run
(zero calls); those values matched the run record at dispatch.


- Model: `muse-spark-1.3` via the existing gateway (`MetaProvider`).
- Arm C context digest: `sha256:1a3702799d8d8f39b21e57de1c02749015ad697ced2cd1ff53939d545833db3c`
- Arm D selection digest: `sha256:01878a24b5d18fdabd85ae8aa14496de58050ad474b399320b6d6ac150829956`
- Public observations: `.runs/vikunja-benchmark/public_observations.json`
  (30,960 bytes, 20 probes with lossless request recording,
  sha256 `40f23ce95eb9199a3c9cef33b8dd440f2f9afd0f0a298a9fdfb07342a5f66777`;
  verified to contain no held-out titles or outcomes).
- Held-out evaluator: `scripts/vikunja_held_out.py`
  sha256 `57d07a9224c09d82bfebfde76799751a9845247892ddfa44145fe18a0e80c1fa`
  — never included in any prompt.
- Interpreter sha256: `5b869354d8652d06ef90acd9e07b0719701cc036999c68818476bdca6bf8d8dc`
- Evaluator sha256: `8454aa93739c7dcf032ac91581abaf7ffb84edf4380f6d47e1a3323765081497`

Arm D's synthesis prompt could not be frozen in advance (it contains
the probe outcomes the model selects). Its digest is recorded in the
run record before the synthesis call and reported with the result;
the frozen part was the selection prompt above.


Spec digests in the record: C `sha256:e0dd3fbe...`, D `sha256:39e3e2c4...` (full values in the run record).


## Budget

- Hard ceiling applied: **$0.50 total**, reservation-capped during the run by `RunBudget` (record wording). No actual billing total is claimed because gateway receipts were lost to a driver crash.
- Gateway layer cap was `SECOND_SOURCE_MAX_RUN_USD=0.50`.

- Prompts were 1.5K-11K chars with <=8K output tokens per call (packet estimate).


- Muse Spark token pricing was not independently verified at packet
  time; that is precisely why the hard cap, not an estimate, governed.

## Preconditions as executed (historical; do not re-run from this packet)

```powershell
setx MODEL_API_KEY "<Meta Model API key>"
setx SECOND_SOURCE_MAX_RUN_USD "0.50"
```

Credentials were kept local (never pasted in chat).



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

## Stop conditions (as applied)

Run stopped after the 3 planned calls. Further calls would have stopped if digests differed,
this packet, the gateway cannot enforce the cap, the reference or
evaluator fails its self-check (6/6), or the owner withdraws approval.
