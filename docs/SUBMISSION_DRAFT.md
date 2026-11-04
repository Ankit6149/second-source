# Second Source — Meta Global AI Developer Hackathon / Indie submission

**Owner submission draft — not a submission receipt.** Last aligned with the repository: 5 November 2026. Before submitting, confirm the live `main` SHA, the published video URL, and any new Meta Model API evidence. Official deadline: **4 November 2026, 9:00 PM Eastern / 5 November 2026, 7:30 AM IST**.

**Project:** [Second Source](https://second-source-alpha.vercel.app/)  
**Repository:** https://github.com/Ankit6149/second-source  
**Interactive architecture:** https://second-source-alpha.vercel.app/architecture/  
**Working application:** https://second-source-alpha.vercel.app/app/  
**Evidence and measurements:** https://second-source-alpha.vercel.app/reports/  
**Demo video:** `demos/second-source-v3.mp4` in the repository; **replace this note with a verified public/unlisted streaming URL before submission.**

## Title

**Second Source — Reconstruct software from what it does, not what it looks like**

## One-line pitch

An AI-assisted software reconstruction system that investigates authorized running software, learns hidden behavior, builds an independent implementation, and independently verifies what actually matches.

## Why this matters / Impact

A working application is often its only accurate specification. Undocumented APIs, legacy systems, access rules, state transitions, validation logic, and unexpected edge cases can make a replacement look right while still being incompatible.

Our long-term goal is simple to describe but technically ambitious: **give Second Source a reference to software you own or are permitted to investigate, and receive an independently reconstructed, runnable replacement—alongside the tests and evidence that explain its limits.**

Second Source approaches that goal scientifically: experiments against the original system establish observable behavior; an evidence compiler records facts; Meta Muse reasons over unresolved rules; a separate candidate is executed; an independent evaluator checks reference-versus-candidate behavior. **Verification is part of the product, not an afterthought.**

Potential uses include authorized legacy/API migration, compatibility verification, preserving undocumented internal workflows, and reducing the risk of rebuilding critical software from guesses.

## What we actually built

This submission demonstrates the **working foundation of that larger system**:

- A local professional-target engine that probes bounded, authorized versions of real software, compiles observed contracts into an independent behavioral candidate, runs that candidate, and measures it against a fresh reference.
- A server-side, genuine **Meta Muse Spark 1.3 Model API** integration with recorded real model experiments. In the local product, an optional, explicitly authorized public-repair stage makes at most one model call with a **$0.50 estimated spending ceiling** and accepts changed behavior only after an independently measured public improvement.
- A provenance-separated evaluation system: REAL_MODEL results, evidence-compiled NON_AI candidates, frozen/held-out tests and provider failures are not conflated.
- A working web product for supported, bounded investigations, authentication, reports and exports; a separate interactive architecture explaining the current engine and the full authorized-link-to-rebuild roadmap.

**Today this does not clone arbitrary websites, generate any app from any URL, or run the full professional-target engine in the hosted backend.** Judges can run the supported-target local engine on localhost; the hosted worker offers a narrower bounded NON_AI workflow.

## Evidence from real software

| Target / test suite | Recorded result | Provenance and meaning |
|---|---|---|
| Vikunja v2.4.0 | **19/19** public action checks; separately **6/6 frozen** and **6/6 extended** last recorded | NON_AI evidence-compiled candidate on supported routes; fresh-reference replay. Muse identified a default-project behavior that informed a generic compiler fix. |
| File Browser 2.63.23 | **7/7** public checks | NON_AI generic compiler/interpreter, bounded subsystem |
| Gitea 1.22.6 | **6/6** public checks | NON_AI generic compiler/interpreter, bounded subsystem; sealed cases not claimed |
| PocketBase 0.28.4 | **9/9** public baseline | NON_AI evidence-compiled; model review proposals did not improve the baseline |
| Owned HTTP workflow | **30/30** | NON_AI bounded end-to-end workflow |
| Browser motion slice | **PASS, 2.505 px RMSE** | NON_AI measured trajectory on an owned slice |
| Owned ledger (Meta Muse Spark 1.3 alone) | **14/25** | Genuine model-authored candidate independently evaluated; 11 mismatches retained, provider attestation incomplete |

**These scores are not one combined accuracy rate**, and public conformance of a bounded subsystem does not prove full software equivalence. Research records, negative results and uncertainty remain available in [the reports](docs/reports/PER_SOFTWARE_RESULTS.md).

## What Meta AI contributes

Meta Muse is a real, bounded reasoning participant rather than a decorative label:

1. **Discover:** use observed reference behavior to form or refine hypotheses, including Vikunja's default-project initialization rule (`Inbox`, `My Open Tasks`), identified in a genuine recorded Muse call.
2. **Propose:** generate bounded candidate route-rule changes through the server-side Meta Model API; never expose credentials to the browser or let model output overwrite immutable observed templates.
3. **Test:** run independent public conformance before admitting a proposed improvement. Model attempts can be rejected; a successful API call is not equivalent to successful reconstruction.
4. **Extend:** the planned autonomous agent selects discriminating experiments, synthesizes ordinary source-code projects, builds them in isolated environments, measures behavioral and UI differences, and iterates under human approval and spending constraints.

**The 19/19 Vikunja score is a measured evidence-compiled candidate**, not a claim that Muse authored the entire finished implementation. Muse's scientifically meaningful contribution was a recorded missing-rule discovery; the compiler subsequently derived that rule generically from observations. Additional current model experiments should be added here **only with exact run IDs, local receipts and accepted independent scores**.

## Technical differentiation

Second Source distinguishes **observation, inference, construction and proof**. It uses explicit authorized scopes, versioned public probe ladders, an evidence-derived behavioral specification, isolated candidate state, canonicalized differential evaluation, fresh-reference replays, separated test ownership, bounded model calls, and exportable evidence. This prevents an AI-generated implementation from grading itself and makes failures actionable.

The system is deliberately modular: adding a new target should require a reviewed adapter and an evaluation contract, not a handcrafted reconstruction engine for each app.

## Demo experience (target: up to 3 minutes)

The demo should make the **end goal visible from the first 15 seconds**, while showing current working evidence without implying that planned nodes already execute:

| Time | Shot | Purpose |
|---|---|---|
| 0:00–0:20 | Website / product promise | **Authorized reference in → independent replacement out, with proof**; the future ambition |
| 0:20–0:45 | Architecture: switch **Working core → End-goal product** | Explain Meta Muse, the reference explorer, source generation, sandbox build, independent verification and export; mark future nodes clearly |
| 0:45–1:45 | Localhost: actual supported-target reconstruction | Real reference probes, compiled candidate, fresh-reference differential score, inspect and download the result |
| 1:45–2:15 | Genuine Muse API evidence | Show a real model request/response or verified recorded packet and the independent acceptance/rejection gate; do not invent success |
| 2:15–2:45 | Cross-target verified results | Vikunja 19/19, File Browser 7/7, Gitea 6/6, explain bounded scope |
| 2:45–3:00 | User value and expansion | Legacy modernization, compatibility testing, the ambition of general authorized link-to-working-software |

**Use localhost for the strongest supported-target reconstruction.** The public website and hosted executor have a smaller capability surface. No API keys, private receipts, sealed tests or personal local paths should appear in the video.

## Additional Muse source branch — pending verification

[Draft PR #81](https://github.com/Ankit6149/second-source/pull/81) (`fb26af6`) contains an AI-first local workbench, PocketBase reference adapter, server-side Muse assist, permission-gated public-link observation, a $15 estimated-cost ledger and a SAM-compatible segmentation adapter. **This branch is not merged into this submission release yet.** PocketBase **8/12** is an owner-reported local run and must not be added to the verified scoreboard without a fresh-reference receipt.

The SAM adapter currently requires a configured external vision service; it is **not verified as a working frontend segmentation experience**. The proposed public-engine deployment is **not yet authorized**: frontend remote-engine wiring, server-side authentication, spoof-resistant rate limits and atomic spending reservations must be verified before using shared Meta API credits.

## Scope and limitations

- Software must be owned or explicitly authorized, with action and resource budgets.
- The current generic candidate is predominantly an executable **behavioral specification**, not a fully generated source repository for arbitrary targets.
- Hosted execution is bounded NON_AI; professional-target engine and Meta repair are currently local.
- Reported numbers are suite-specific, with distinct provenance. Provider failure, rejected edits, indeterminate outcomes and incomplete attestation remain in the research record.
- The architecture's browser observation, autonomous experiment planner, generated source projects, sandbox repair and universal link ingestion are a **roadmap**, not shipped functionality.

## Original work and build process

Built for the hackathon from October 26, 2026 onward. The owner directed product vision, decisions, demonstrations and code review, with AI coding agents assisting implementation. Technical history and attribution are recorded in [HACKATHON_ORIGINALITY.md](HACKATHON_ORIGINALITY.md) and the repository's PR/commit history.

## Owner-only submission checklist

- [ ] Verify the current public website and README in a signed-out browser.
- [ ] Confirm local engine actually runs and produces the recorded candidate, measured report and export.
- [ ] Verify any newly added Meta API contribution via real receipts and an independent improvement gate.
- [ ] Publish `demos/second-source-v3.mp4` or a corrected final video to a publicly accessible/unlisted video URL; test playback signed-out.
- [ ] Copy the exact latest `main` SHA and the verified public video URL into the portal.
- [ ] Submit through https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit before the deadline; save the confirmation receipt (ID, screenshot, timestamp) privately.

**Until a portal receipt exists, label this project `readying submission`, not `submitted`.**
