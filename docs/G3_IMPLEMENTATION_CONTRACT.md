# G3 Implementation Contract — Second Source
**State:** BUILD SPEC / NOT YET VERIFIED OR DEPLOYED
**Parent:** [MASTER_PRD.md](MASTER_PRD.md) · [EXECUTION_PLAYBOOK.md](EXECUTION_PLAYBOOK.md)
**Prerequisite:** G2 observed real Muse experiment; merge only after operator's detailed local receipt review.
**Target:** one reproducible end-to-end independently generated, behaviorally tested, scope-restricted owned CLI replacement before the Meta hackathon submission.

## Single demonstration promise

Given (i) an authorized, stateful, black-box JSONL ledger executable, (ii) owner-authored public command signatures, (iii) a strict Observe/Implement/Exclude ScopeContract, and (iv) bounded redacted observation history, real Muse must independently propose a runnable **candidate behavior specification** for the requested ledger subsystem. A *trusted* constrained runtime interprets the spec. An external evaluator scores it against a sealed sequence suite unavailable to Muse. A bounded Meta repair step may improve the candidate using **aggregate category feedback only**, with all artifacts and costs recorded.

No model-written Python/JS is executed on the user's Windows host. Use a small, typed, declarative candidate DSL with no imports, shell, eval, subprocess, dynamic code execution, arbitrary filesystem writes or network. If genuine free-form generated code must execute, postpone until a separate disposable sandbox with resource/egress enforcement is verified. Do not rename a scripted template or hard-coded perfect fixture as a model-generated candidate.

## Deliverable contracts (ordered)

### G3-A — candidate manifest + restricted implementation representation
- Input to Muse: ScopeContract **public projection**, operator-owned command signature manifest, **redacted** G2 observations, model-generated G2 hypotheses/statuses; never reference source, gold cases, secret env, local machine paths or unknown private data.
- Output: versioned `CandidateSpec` / `CandidateManifest` with each output artifact mapped to the permitted implementation subsystem and requirement ID, and with declarative rules for command validation, state transitions, normalization, and response shaping.
- Runtime: trust-owned interpreter/compiler that implements only the DSL operations and JSONL input/output; no model-supplied executable strings.
- Model output is **one Meta-generated typed artifact** with real provider receipt; the product must fail closed if output invalid and cannot substitute canned rules to claim a successful reconstruction.
- Validate `ScopeGuard.validate_candidate_files`, every declared capability, no extra subsystem, no absolute/traversal path, no forbidden effect. Save spec digest and sanitized generation receipt; never log credentials.
- Use one candidate file initially (example `candidate.json`) plus a trusted interpreter reference; don't build a general plug-in ecosystem.
- Add malformed/adversarial DSL tests and negative tests that attempt to sneak a shell command, HTTP egress, credential reads, admin-only module or output outside implementation scope.

### G3-B — independent differential evaluation
- Reuse G0 `DifferentialVerifier`, extending the adapter only as necessary to run the **trusted DSL interpreter** against a validated candidate manifest.
- Gold suite remains fully outside model messages and generation workspace. No case IDs, exact hidden inputs or expected outputs are sent to the model or included in repair prompts.
- Use strictly the SAME reset boundary on reference and candidate, the SAME action sequence, stable comparison rules and an explicit count of `passed / failed / indeterminate / total`.
- Define deterministic acceptance suite covering valid add, invalid amount/label, duplicates and case/whitespace handling, remove, list, total and ordered reset-sensitive sequences. Make sure model cannot access the test cases as tools or prompt content.
- Verify against known intentionally-bad and reference-equivalent controls to demonstrate evaluator sensitivity/specificity, **but neither control may be presented as Muse output**.
- Include a test that prevents the current model/generator boundary from loading `fixtures/owned_ledger/reference.py` or `tests/gold*` while building candidate.
- Never claim full behavioral equivalence; metrics refer strictly to the authorized scope and the exact sealed suite.

### G3-C — bounded evidence-only repair
- If a generated candidate fails, send Muse ONLY deterministic aggregate information such as mismatch category counts, failing-command-type coverage (if safe), and documented acceptance criteria. Never reveal gold input/output pairs, gold case IDs, reference source, or the evaluator's hidden assertions.
- At most 2 repair attempts on the same valid scope; each repair yields a **new immutable spec digest** and a real model receipt. Prevent tests or observations from poisoning model instructions.
- Re-run the **identical** sealed suite after every accepted repair and report actual lift `delta_passed`; also disclose regressions, skips and uncertainty.
- Repair must not widen ObservationScope, ImplementationScope, ExclusionScope, action permissions, or allowed DSL capabilities.

### G3-D — local CLI + reproducible evidence package
Current implementation status and executable flags are in the
[delivery board](G3_DELIVERY_BOARD.md) and [operator runbook](G3_RECONSTRUCT.md).
The command below is a planned contract example; the current operator uses
`--mode mock|preflight|real` and does not implement `--repairs` yet.

- A single explicit operator command, e.g. `python -m second_source.reconstruct --fixture owned-ledger --max-usd 0.50 --repairs 2`, gated by a local real API key and run budget. Initial spend must remain low and explicitly authorized; there is no background billing.
- A nonbillable `--mock` path is permitted for engineering tests **only** and clearly labeled MOCK. The real demo must use actual Meta response IDs.
- Write `.runs/<id>/G3_report.json` (Git-ignored) including scope digest; G2 evidence digest; spec hashes; model receipts; experiment/reference counts; before/after evaluation; counts by failure category; estimated usage; failed/uncertain charges; stop reason; excluded features; and environment hashes. Do not persist keys.
- A public redacted `docs/G3_ACCEPTANCE.md` must contain only confirmed, shareable evidence, actual command results, and all still-unverified claims.
- Add `python -m second_source.g3_demo` that reproduces deterministic nonbillable evaluator checks on a fresh clone and labels them NON_AI, separate from the real Muse run.

## Release gate and cut line

**Gate PASS only if all are observed:**
1. A real Muse model generated the candidate spec from authorized black-box observations without reference source or hidden tests.
2. The spec passed deterministic scope and declarative-runtime validation and ran without evaluating model-supplied code.
3. The independent verifier compared candidate vs reference on >0 sealed in-scope sequence cases and reported exact counts.
4. Positive and negative controls distinguish known good/bad behavior; secret, out-of-scope and gold-leak checks pass.
5. At least one real generated candidate result is reproducible; if the product claims repair, before/after numbers must be genuine.
6. The tested branch passes Linux/Windows CI and has a reproducible fresh-clone command.

**Prioritize G3-A+B first.** G3-C repair is valuable but secondary to one honest end-to-end evaluation. If time runs short, drop repair, second target, cloud workers, login automation and polished dashboard—not evaluator isolation or origin attribution.

## Handoff for Muse Code and reviewer
- Build in the existing `second-source` repository. After the separately reviewed G2 merge, use **one** short-lived branch/PR for all G3 work; no duplicate G0/G2 architecture, no stale local `main`, no force push.
- Start with a failing G3 test + exact interface; land candidate DSL schema/validator + constrained interpreter + positive/negative controls; then implement Meta candidate spec generation; then connect verifier and report; finally optionally repair.
- Keep commits reviewable; run full tests before pushes; require Linux/Windows CI; record actual outcomes, never just intentions.
- End each report with exact commit SHA, mock/real run counts, verifier pass/total, budget consumed/uncertain and acceptance blockers.
- Never broaden scope or access credentials without operator approval.
