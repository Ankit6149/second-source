# Browser adapter + second-target slice (Gate C evidence)

Zero paid calls. Everything below was run locally in this checkout.

## A. Browser / motion

- **Adapter:** `scripts/browser_adapter.mjs` â€” generic Playwright/Chromium
  (CDP, pinned viewport 1280x800, `@playwright/test` 1.64.1 from
  `product/node_modules`). Given a URL + JSON plan (selectors only, no
  product logic) it records DOM/a11y summary, layout boxes, computed
  styles, hover/focus, keyboard/form input, drag trajectory
  (frame-indexed), scroll/parallax, and final state text.
- **Shared compare:** `src/second_source/browser_compare.py` â€”
  functional state equality, layout max-diff, trajectory RMSE on a
  common 8 ms grid, overshoot presence, settling time, parallax diff.
  Used for both `browser-slice` (recorded RMSE **1.054 px**) and
  `browser-slice-v2` (recorded RMSE **1.741 px**) baselines; recorded
  `verdict.json` files are untouched frozen evidence. Independent
  re-evaluation in this run re-observed pass=true on both slices but
  with jittered RMSE (8.0 / 5.8 px) â€” frame timing on this machine is
  noisier than the recorded run; the recorded numbers stand as the
  baseline, the re-run confirms sensitivity (adversarial variants
  35â€“46 px, still detected).
- **Adapter run (this slice):** generic adapter on v2 reference vs the
  independently generated `candidate.html`, held-out drag 150 px:
  functional match, layout max diff 0 px, parallax max diff 0 px,
  overshoot present in both (-18.6 / -15.9 px), settling 0.59 / 0.46 s,
  trajectory RMSE **2.44 px** (pass, threshold 8 px). Evidence in
  `.runs/browser-adapter/` (`ref.json`, `cand.json`, `compare.json`).
  Tests: `tests/test_browser_compare.py` (identical/wrong-spring/
  no-overshoot/layout/state negative controls).
- **rrweb / AALpy / PySINDy:** not adopted. rrweb records/replays DOM
  events but yields no fitted motion parameters; AALpy learns automata
  over discrete alphabets, not continuous spring trajectories; PySINDy
  fits sparse ODEs and could in principle refine `(k, c)`, but the
  current grid-search fit already reaches 1.05â€“2.44 px held-out RMSE,
  so no measurable gain is available to claim on these baselines.
  Revisit only if a baseline exceeds the 8 px threshold.
- **No Canvas/WebGL/3D claim** is made: no tests exist for them.

## B. Second target: File Browser v2.63.23

- **Pin/legal/reproducible:** File Browser **v2.63.23** (Apache-2.0),
  local binary, seeded via CLI (`config init`, `users add genadmin
  --perm.admin`), fresh DB per run, port 3471, public budget $0 local.
- **Key finding (prior gap closed):** user create/delete require a
  top-level `current_password` field in the JSON body; the earlier
  400 ("the current password is incorrect") was that missing field,
  not a payload-shape mystery. DELETE also requires it in the body.
- **Candidate:** NON_AI only â€” `scripts/filebrowser_benchmark.py` runs
  public probes â†’ `evidence_compiler.compile_spec` (zero target code)
  â†’ generic interpreter (`scripts/vikunja_candidate_server.py`).
  Generic fixes made en route: top-level `POST /users` is a create,
  not a share (share requires a `{param}` parent segment); raw-header
  token auth (`X-Auth`, header name from `spec.auth`); `{id}` path
  params resolve entities; DELETE removes the resolved entity;
  non-JSON create bodies synthesize the entity from the request
  payload. No File Browser field names in compiler/interpreter.
- **Frozen cases** (status + normalized body, fresh reference and
  candidate; duplicate/relation are negative/relation controls):
  **7/7 pass** â€” FB-STATE-1 createâ†’list, FB-ERROR-1 wrong-password
  403, FB-ERROR-2 unauthenticated 401, FB-MULTI-1
  createâ†’loginâ†’deleteâ†’404, FB-CONTROL-MUTATED (flipped
  `login_error_status` correctly detected as different).
- **Measured divergences (Gate C blockers, not hidden):**
  FB-REL-1 non-admin `GET /users` is 403 on the reference but 200
  (filtered list) on the candidate â€” admin-only list semantics are
  not inferred from alice-only probes; FB-NEG-1 duplicate create is
  500 on the reference but 201 on the candidate â€” uniqueness is not
  compiled from observations. Both need either a probe that observes
  the denial plus interpreter enforcement, or model-authored claims.
- **Model baselines:** none run (no paid calls authorized). NON_AI is
  never relabeled; no model score is claimed on this target.
- **Gitea:** not attempted; File Browser was reproducible in-window,
  so per contract Gitea is documented as the deferred alternative
  only if File Browser had blocked. It did not.

Artifacts: `.runs/filebrowser-benchmark/` (`public_observations.json`,
`spec_compiled.json`, `verdict.json`), `.runs/browser-adapter/`.

