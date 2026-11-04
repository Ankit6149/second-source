# Second Source — 3-minute judge video recording package
**Version: 4 November 2026 | Target: 170–175 seconds, never over 180.**
This is a production and recording guide, not a claim that a new video has been recorded. The existing v3 recording is documented locally at `.runs/submission-v3/second-source-v3.mp4` (170.02 seconds); it has not been independently opened, visually approved or publicly hosted in this review.

## Before pressing Record — mandatory gate
- Confirm the current production SHA and open `/`, `/challenge/`, `/lab/`, `/evidence/`, and `/app/` signed-out in a private window.
- Review PR changes and keep REAL_MODEL / EVIDENCE_COMPILED / NON_AI labels always visible.
- If using the local application, run the **actual** local backend or deterministic engine, and confirm one full investigation succeeds before recording. Do not present a historical replay as live execution. If backend is unavailable, use the recorded lab as a labeled fallback, not a staged animation pretending to run.
- Use 1920×1080 at 30fps, ≥16px screen text at final export, a clean browser profile, 125–150% page zoom when necessary, and high-quality narration/captions. Hide secrets, private identifiers, desktop notifications and keys.
- Keep a copy of the candidate and report bundle *outside the public repository*. Do not reveal sealed gold cases.

## Shot list / final voiceover
**00:00–00:15 · Question: what does the software really do?** (Landing → Black-Box Challenge)
Narration: “A coding agent can copy a screen. But what if the rules behind that screen are missing? Second Source starts with software we’re authorized to observe and treats behavior as evidence.”

**00:15–00:42 · The 27-second surprise** (Challenge: add Milk then MILK, reveal; amount boundary, reveal; response schema, reveal)
Narration: “The two applications look identical. Yet the reference rejects a case-insensitive duplicate, rejects a hidden limit, and returns a precise response shape. A generated implementation can miss all three. Here are the actual recorded differences.”

**00:42–01:07 · The research method** (Lab timeline → public hypothesis/experiment and genuine ledger evidence)
Narration: “With Meta Muse Spark 1.3, we used evidence-linked hypotheses and controlled experiments to infer an independent behavioral specification. A separate evaluator then challenged the candidate on withheld cases.”

**01:07–01:27 · Do not conceal failures** (Evidence report on 14/25 with 9 schema + 2 error mismatches)
Narration: “The genuine Meta ledger candidate passed fourteen of twenty-five tests. Eleven failures revealed exactly what it had guessed incorrectly. We report those failures rather than claim a perfect clone.”

**01:27–02:02 · The real product workflow** (App account modal → supported target → authorized scope → execution workbench → real persisted events, if local acceptance succeeds)
Narration: “Here is the product boundary. We choose an explicitly supported target, review its authorization scope, and inspect the real persisted execution stages. This local run is a deterministic, non-AI control—not a new Muse call. Nothing is fabricated if the engine or service is unavailable.”
*Fallback if the run cannot be established:* show the existing recorded laboratory reconstruction with a visible RECORDED REPLAY label and say “This is a recorded evidence viewer; the hosted app is not running the model live.”

**02:02–02:30 · What was learned** (Reports scoreboard showing each provenance separately and candidate/version evidence)
Narration: “On Vikunja, the Muse-assisted hybrid matched six of six frozen and extended cases. So did our evidence compiler without model calls. That makes the engineering result interesting—but it does not prove the model improved on the compiler. We preserve this distinction.”

**02:30–02:48 · Artifact and verification** (Candidate preview/lineage, report export, digests, link to proof)
Narration: “The deliverable is not simply a plausible candidate. It includes the tested behavior, failures, provenance, candidate identity, unknowns, and an integrity-verifiable report. The evaluator stays independent.”

**02:48–03:00 · Close: why it matters** (Logo and concrete use case, GitHub, challenge)
Narration: “For teams maintaining undocumented systems, trustworthy reconstruction needs more than generation. Second Source helps turn observation into accountable, testable evidence. Try the Black-Box Challenge and examine the results.”

## Recording flow and timing
| Scene | Live route / asset | Interaction rule |
|---|---|---|
| Landing hook | `/` → `/challenge/` | Scroll only enough to understand the proposition; avoid extended abstract hero animations. |
| Recorded behavior challenge | `/challenge/` | Actually click choices and Reveal; no faked typing. |
| Genuine Meta results | `/lab/` and `/evidence/` | Keep 14/25 result, provider limits and recorded labels visible. |
| Product workflow | `/app/` (prefer verified local connected run) | Sign-in modal is application-level. Only show real target selection and persisted stage events. |
| Measured scorecard | App Reports or dossier | Do not conflate Muse 6/6 with NON_AI 6/6; no claimed lift. |
| Output | Real available sanitized export | Never replace a missing artifact with invented source-code screenshots. |

## Final quality gate
- The rendered MP4 is ≤180 seconds; vocals audible; text readable on a phone; labels remain visible.
- No fake AI live run, no false 100% Meta accuracy, no “autonomous website cloning” claim.
- Every score is paired with its origin and own denominator.
- Video URL publicly viewable when signed out; no login/account needed to play.
- Final public repository SHA and demo URLs agree with the submission.
- Human owner submits once through the organizer portal and saves the receipt.

If the existing 170.02-second v3 video already meets this gate, publishing it is higher priority than re-recording. Only record a new cut if it clearly improves the first thirty seconds or fixes a substantive problem.
