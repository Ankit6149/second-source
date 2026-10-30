# Second Source public research preview

A static landing page and an actual local evidence viewer. No account, model,
backend, database, telemetry or external font request is made by these pages.
The landing experiment is illustrative; the console distinguishes historical
operator-reported real attempts, NON_AI controls and unverified local imports.
No control launches inference or authorizes spending.

From the repository root:

```console
python web/preview.py
```

Open `http://127.0.0.1:8766/`. The same server exposes the canonical
`demo/index.html` at `/console/`; it does not expose the rest of the repository.
Press Ctrl+C to stop it. No dependencies beyond Python 3.11+ are needed.

For an independently hosted static preview:

```console
python web/build.py
python -m http.server 8766 --bind 127.0.0.1 --directory web/dist
```

The build copies an explicit list of public frontend files and the canonical
console. `web/dist/` is generated and ignored. Publishing requires owner approval
and is not performed by either script. Existing production remains untouched.
The self-hosted fonts and license files remain in the static artifact.

## Provenance and design

The HTML, CSS, JavaScript, brand marks and scientific instrument began with the
owner-provided first-party reference at
<https://second-source-motion-refined.vercel.app/> (retrieved October 29, 2026).
This implementation preserves that direction and its geometric artwork. It adds
truthful availability, use cases, evidence-viewer entry and documentation links;
fixes navigation and menu accessibility; and makes animation optional and bounded.
No HackerRank code, text, branding or assets are used.

DM Sans and Manrope are self-hosted from the Google Fonts repository under their
included SIL Open Font Licenses. Asset origin:

- `assets/dm-sans.ttf`: `google/fonts/ofl/dmsans/DMSans[opsz,wght].ttf`
- `assets/manrope.ttf`: `google/fonts/ofl/manrope/Manrope[wght].ttf`

The token layer is `release.css`: dark `#0d1512`, light `#f5f5f0`, dark text
`#18211d`, light text `#f4f6f0`, restrained accent `#afdba9`, 1200px container,
Manrope headings and DM Sans body. It inherits the first-party layout; it does
not introduce another visual template. Source CSS is retained for traceability.

## Verification and limits

```console
python -m unittest discover -s web -p "test_*.py" -v
python -m unittest discover -s demo -p "test_*.py" -v
```

Browser QA uses CUA, without Playwright. Static checks and screenshots do not certify accessibility, performance,
provider provenance or cloud readiness. The console exports a display summary,
not an authoritative signed evidence archive. Imported data never executes code.

No Supabase, OAuth or real-run interface is installed. Backend integration must
use the reviewed API contracts rather than inferring state from animation. The
public preview must continue to describe live G3 admission and measured repair
improvement as unproven until independently accepted evidence exists.

## GitHub-connected Vercel project

The repository-root `vercel.json` builds only the allowlisted `web/dist` output.
For a new, separate project, import this repository on Vercel with the repository
root as its root directory and the Other framework preset. The configuration sets
the build command to `python3 web/build.py` and the output directory to `web/dist`;
no environment variables or service credentials are required. Select the reviewed
landing branch for a preview. Confirm the generated deployment and test its routes
before linking or promoting it. Do not repoint the existing production project.
