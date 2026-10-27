# G3 Acceptance Log — candidate synthesis mechanism (MOCK/TRUSTED CONTROL ONLY)

**Gate under test:** G3 contract — a real Muse model generates a runnable
candidate spec from authorized black-box observations; a trusted runtime
executes it; the independent verifier scores it on a sealed suite.

**Verdict: G3 NOT DEMONSTRATED.** No real candidate generation has occurred.
Everything in this branch is engineering evidence for the G3-A mechanism.
Nothing below is a Muse-generated candidate score.

## Independent review correction — 28 October 2026

ChatGPT reviewed Muse's first G3-A checkpoint at
`8f881cd37c99acb5c8045bf9c3441e06920d373e` and found a **blocking protocol
mismatch**: `CandidateInterpreter` accepted nested
`{"command":"add","params":{...}}` actions while the trusted G0 reference
and sealed verifier use flat `{"command":"add","label":"...","amount":...}`
actions. The original mock demo asserted only `total == 3`, so its tests
could pass even when all candidate/reference comparisons failed.

That checkpoint is therefore **not accepted as a clean G3-A interface** even
though its document reported 49 local G3 tests. Those local counts were not
GitHub-CI verified because the branch had no PR/workflow run.

The follow-up branch fixes:
- pin the candidate runtime to the exact flat G0 ReferenceProtocol action wire;
- make the non-sealed trusted control demo fail unless all public control cases
  pass;
- pin generated command effects to the operator-owned public contract so
  `list`/`total` cannot mutate state and `remove` cannot create/aggregate;
- restrict v1 lookup to in-memory id lookup and reject contradictory bounds;
- close the top-level generation context and redact again immediately before
  the model boundary;
- preserve mock / trusted-test-fixture / real origin separation.

**New test counts and CI status must be taken from the next GitHub Actions run,
not inferred from this document.**

## G3-A deliverables now present on `g3/candidate-synthesis`

| # | Deliverable | Files | Acceptance state |
|---|---|---|---|
| 1 | Versioned `CandidateSpec` / manifest + scope-pinned loader | `src/second_source/candidate_spec.py` | code present; CI pending |
| 2 | Trusted data-only interpreter implementing G0 ReferenceProtocol | `src/second_source/candidate_runtime.py` | protocol mismatch fixed; CI pending |
| 3 | Malformed/adversarial rejection and effect-smuggling tests | `tests/test_g3_candidate_*.py` | code present; CI pending |
| 4 | Mock generation boundary + real adapter skeleton | `src/second_source/candidate_generation.py` | no billable call made |
| 5 | Non-sealed trusted positive-control demo | `src/second_source/g3_mock_demo.py` | must report 3/3 or exit nonzero |
| 6 | G3-B verifier contract | `docs/G3_CANDIDATE_INTERFACE.md` | ready for independent read-only audit after CI |

## What this still does NOT prove

- No genuine Muse-generated CandidateSpec exists.
- No Codex-authored G3-B sealed suite or adapter has been committed.
- No sealed candidate score exists.
- No real repair or before/after lift exists.
- No active-vs-fixed baseline result exists.
- No production sandbox or website adapter exists.

## Next acceptance sequence

1. Current branch passes full Linux/Windows CI and the trusted mock control is
   3/3 with explicit NON-AI / NON-SEALED labels.
2. Codex performs the independent read-only G3-B audit against the committed
   interface and publishes findings before writing evaluator files.
3. Codex implements only its assigned evaluator/adaptor files after a disjoint
   write handoff.
4. Owner explicitly authorizes a bounded paid Muse candidate-generation call.
5. The real generated spec is validated, executed by the trusted interpreter,
   and scored by the sealed evaluator with exact counts.
6. Repair is optional and may be claimed only with a genuine unchanged-suite
   before/after result.
