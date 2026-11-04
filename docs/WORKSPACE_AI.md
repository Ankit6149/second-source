# Workspace AI: always-on Muse, link capture, and where keys go

## How a visitor tests it

**Hosted (no install, no key):** open the Vercel app. Chat answers, link
capture, reports, and recorded evidence all work. AI spend comes from the
app's server key, guarded by a $15 session cap plus per-visitor daily
limits (25 chats, 25 captures, 10 investigations). Rebuild runs need the
local references, so on hosted targets honestly report `reference-missing`.

**Local (full power):** clone, set `MODEL_API_KEY`, run the engine, open
the dev server. All four rebuild targets run against your loopback
references, with Muse assisting every rebuild after one blanket consent.

```powershell
$env:MODEL_API_KEY = "<paste in this terminal only>"
$env:SECOND_SOURCE_ALLOW_MUSE_REPAIR = "true"
python scripts/investigation_engine.py
npm run dev --prefix product
# open http://127.0.0.1:5173/
```

## Where each key goes

| Secret / var | Put it here | Never here |
|---|---|---|
| `MODEL_API_KEY` (Meta) | Local terminal that starts the engine, or Render `second-source-engine` env (typed in the Render dashboard) | Vercel, Supabase, the repo, chat, browser |
| `SECOND_SOURCE_ALLOW_MUSE_REPAIR=true` | Same place as the key | Browser |
| `SECOND_SOURCE_MAX_SPEND_USD` (default 15) | Engine env | Browser |
| `VITE_ENGINE_URL` (public URL, not a key) | Vercel project env, e.g. `https://second-source-engine.onrender.com` | — |
| Supabase publishable key | Vercel (public by design) | `service_role` never leaves the server |

The browser bundle is fenced by `product/tests/noleak.test.ts`: only
`VITE_API_ORIGIN`, `VITE_SUPABASE_*`, and `VITE_ENGINE_URL` may be read.

## Endpoints (all server-side key, all capped)

- `POST /engine/v1/assist` — Muse answers workspace text (3 sentences max,
  asks one clarifying question when ambiguous). 3s cooldown, $0.50 reserve.
- `POST /engine/v1/capture` — GET-only fetch of one public link (256KB,
  no logins, private hosts refused), optional Muse summary. Observed, never
  rebuilt.
- `POST /engine/v1/investigations` — rebuilds; `muse-repair` on Vikunja and
  PocketBase, one bounded call kept only on strict public improvement.

Receipts persist to `.runs/engine/*-receipts.jsonl` (0600) and every
estimated dollar lands in `.runs/engine/spend.json` against the cap.
