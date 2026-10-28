# Second Source — read-only investigation console

This is a working, dependency-free, responsive investigation and result viewer for the **hackathon demo**, not the G2/G3 inference operator. It provides clickable run selection, independent score visualization, evidence/provenance metadata, detail tabs, local JSON import and a strictly sanitized JSON summary download.

## Run

From the repo root, `python -m http.server 8000 --directory demo`, then visit `http://localhost:8000`. You may also open `demo/index.html` directly in a browser.

Select built-in example records to inspect:
- **Real G2 discovery** — summary numbers from an operator-reported genuine Meta run, not a signed or portable provider attestation.
- **Real G3 failed synthesis** — one consumed attempt with no admitted candidate and **no sealed score**.
- **NON_AI scripted baseline** — 22/25 in an independent evaluator; it is *not* Meta-generated model performance.

To inspect your own run, generate a nonbillable report using `python -m second_source.reconstruct --mode mock`. Click **Import report** and select the generated `.runs/<id>/G3_report.json` from your local filesystem. The viewer also accepts a summary-form G2 run report with its available counters. Imported values are labeled unverified locally; to authenticate them, use the existing CLI journal receipt and evaluator verification workflow.

## Privacy and limitations

- Entire viewer runs in the browser. No external libraries, fonts, telemetry, network calls, storage or provider requests.
- File import is client-local. The renderer uses an allowlist of public counter/metadata fields; it does **not** display raw model response text, private hypotheses, full evidence payloads, file paths, keys, original source or hidden suites.
- The **Export summary** button downloads a *sanitized display projection* only. It is **not** the authoritative evidence bundle required by FR-035/FR-042.
- Buttons do not launch real Meta inference, paid runs or repair. Genuine G3 admission and model accuracy are still not proven.
- Source of example numbers: operator-reported checkpoints from 28 Oct 2026, independently summarized in PR #5/#6 discussion; use the actual local signed/witnessed artifacts to substantiate judging claims.
- This console addresses a useful read-only slice of FR-040/FR-043. Full live stage timestamps, start/pause/resume/stop authorization, and portable signed evidence export remain incomplete.

## Smoke checks

`python -m unittest discover -s demo -p 'test_*.py' -v` verifies the asset is present, has the expected controls, and contains honest mock/real disclaimers. Run a browser-based inspection for layout, import and keyboard usability before claiming UI acceptance.
