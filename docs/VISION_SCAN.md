# Vision scan: regions + motion physics

`scripts/vision_scan.py` answers "what is on this screen, and how does it move?"
in two independent stages. Nothing is guessed: unmeasured stays unmeasured.

## 1. Regions (needs a configured service, server-side only)

Any segmentation/vision service works, including Meta SAM (Segment Anything).
The contract is provider-neutral, so SAM or any other AI can back it:

- `POST` PNG bytes to `<SECOND_SOURCE_VISION_ENDPOINT>/segment`
- Service returns `{"regions": [{"label", "x", "y", "w", "h", "score"}]}`
- Optional `SECOND_SOURCE_VISION_API_KEY` travels only on that TLS call

Without `SECOND_SOURCE_VISION_ENDPOINT`, region scans report
`available: false` — no local fallback invents boxes.

```bash
python scripts/vision_scan.py --capabilities
python scripts/vision_scan.py --image shot.png [--backend sam]
```

## 2. Motion / physics (always local, NON_AI)

`scan_motion` reads one browser-slice capture directory and summarizes the
already-fitted spring physics plus held-out trajectory error. No model call.

```bash
python scripts/vision_scan.py --motion browser-slice-v2
```

## Session AI spend cap

The local engine enforces `SECOND_SOURCE_MAX_SPEND_USD` (default **15**).
Every Muse receipt adds its estimated cost to `.runs/engine/spend.json`;
at the cap, new `muse-repair` runs are refused with HTTP 402. Health
reports `{used_usd, cap_usd}` so the UI can display the budget.
