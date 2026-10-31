# Second Source — Product Design Language v0.8

**Direction:** a quiet, conversation-first behavioral intelligence workspace; not a prompt-to-website SaaS dashboard. **Status:** UI-only research prototype, not connected to the production engine.

## Product object

The primary object is an **authorized software-behavior question**, not a generated app. A user may ask to understand software, compare implementations, reconstruct narrowly scoped behavior, or inspect verification evidence. The UI prioritizes actionable answers: what was observed, what differs, what evidence supports it, and what could be delivered.

## Foundation

- **Canvas:** `#FFFFFF`. **Sidebar:** `#F8F9F7`. **Ink:** `#202A24`. **Secondary text:** `#5E6962`. **Borders:** `#E9ECE8`. **Primary green:** `#295C42`. **Pale accent:** `#E9F1E9`.
- Typography: DM Sans for interface and reading; Manrope for concise page headings and brand; IBM Plex Mono for literal example artifacts. Never substitute decorative display copy for instructional content.
- Base text 14px with 1.55–1.78 line height. Composer 15px desktop / 16px mobile to prevent iOS viewport zoom.
- Standard radii: pills `999px`; composer 24px; evidence artifact 16px; icon-only controls circular; dialogs 20px. Square corners are reserved for structural borders or the understated left edge of explanatory callouts.
- **Icons:** Lucide v0.468.0, loaded from the pinned distribution with inline accessible fallback SVG for offline review. Match 18px default and 15px secondary glyph sizes; no emoji in action chrome.
- **Layout:** one primary conversation column, optional evidence drawer, quiet left navigation. The composer is a permanent flex child of the application frame, *outside* the scrollable message history. The page root never scrolls during conversation.
- **Surface hierarchy:** whitespace > typography > soft background > hairline border. Avoid card-in-card nesting, large shadows, glow, loud accents, busy dashboards and unverified numerical claims.

## States and controls

| Element | Rest | Hover | Focus | Disabled or waiting |
|---|---|---|---|---|
| Primary action | green pill, white text | deeper green | visible 2px outline | subdued, explicit label |
| Secondary | thin-border pill | soft off-white | 2px outline | disabled semantic attribute |
| Quiet action | text/icon pill without line | subtle soft fill | 2px outline | unavailable, not hidden |
| Composer | subtle 1px border | unchanged | stronger border/soft shadow | stays anchored; draft stays editable |
| Icon action | circular 38px | light circle | visible outline | aria-label; no ambiguous glyph |
| Artifact viewer | closed by default | open on action | focusable tabs/close | never auto opens on a generic prompt |
| Feedback | text + icon | transient or persistent as appropriate | announced toast | never infer success from animation |

## Request understanding — real-product contract

1. Explicit `https://`/`http://` or `www.` addresses become user-provided reference chips.
2. Bare domains become **possible website** chips, never an authorization to visit.
3. Known brand names get a **suggested domain / not verified** chip. The curated map in the mock is only a suggestion, not a live resolver.
4. Unknown name-like strings are treated as **possible software names**, with no fabricated domain.
5. Non-web targets (CLI, API, local software) remain valid. Do not force a URL.
6. Real implementation must confirm the actual reference and source authorization before any network, credentials, actions, or payment-like operation.

## Conversation behavior

- A user can send more messages while a sample sequence is visible. These messages append in chronological order; progress does not replace the conversation.
- A response can contain natural prose, evidence notes, interactive artifacts and lightweight actions (copy, preview, compare, files, evidence, export).
- The right-hand output viewer is opt-in and independent of the chat scroll. The composer stays fixed when it opens.
- The UI does not autonomously send prompts to a model or use any client-side fetch. The example completion is always a separately labeled scripted non-AI fixture.
- One primary action per response. Secondary actions should look like small tools, not a toolbar of big blocks.

## Interaction laws and heuristics considered

1. Jakob's Law — familiar composer, Enter-send / Shift+Enter-line break.
2. Hick's Law — three task suggestions, not a mode matrix.
3. Fitts's Law — large circular or pill targets.
4. Miller's Law — group evidence in a few meaningful categories.
5. Tesler's Law — hide engine and evaluator internals by default.
6. Postel's Law — flexible incoming references, strict action authorization.
7. Doherty Threshold — immediate reference-chip feedback.
8. Aesthetic-Usability Effect — deliberate typography and restraint.
9. Von Restorff Effect — one distinct primary action.
10. Peak-End Rule — clear and transparent report outcome.
11. Zeigarnik Effect — sample progress remains visible, no unexplained abandonment.
12. Goal Gradient Effect — staged progress shown only when real or explicitly simulated.
13. Serial Position Effect — essential actions in predictable positions.
14. Law of Proximity — semantic grouping of messages and evidence actions.
15. Law of Similarity — consistent states and icon sizes.
16. Law of Common Region — artifact boundaries only where necessary.
17. Law of Prägnanz — minimal visual language.
18. Law of Continuity — conversation remains the continuous context.
19. Law of Closure — concise resolved-state summary with evidence entry points.
20. Law of Uniform Connectedness — evidence belongs to its parent answer.
21. Occam's Razor — avoid speculative complex dashboards.
22. Pareto Principle — optimize the principal user request path.
23. Parkinson's Law — no needless mandatory scope form before a preliminary question.
24. Cognitive Load Theory — progressive detail reveal.
25. Choice Overload — compact starter suggestions.
26. Information Scent — action labels name the expected output.
27. Recognition over Recall — clear recent work list.
28. Visibility of System Status — explicit simulated / running / uncertain labels.
29. User Control and Freedom — stop, close, return, edit.
30. Error Prevention — scope and high-risk action boundaries before execution.
31. Match to Real World — plain-language result, not an internal experiment queue.
32. Consistency and Standards — Lucide icons and uniform actions.
33. Flexibility and Efficiency — keyboard submission, search shortcut, optional output viewer.
34. Error Recovery — ask for a reference rather than guess a URL or claim execution.
35. Minimalist Design — white canvas, few chrome elements, limited borders.
36. Help and Documentation — optional design-system and evidence surfaces.

These are design lenses, **not empirical proof of usability**. Formal accessibility audits, mobile virtual-keyboard testing and user research are still required.

## Critical safety disclosure

The v0.8 UI never inspects targets, initiates sign-in, performs purchases, synthesizes model candidates or produces a genuine G3 score. It uses a browser-local data sample (22/25 scripted fixture control) and stores drafts locally only. A test email is not sufficient payment security; a production system needs enforceable tool/action restrictions, approval rules and sandboxed payment testing.
