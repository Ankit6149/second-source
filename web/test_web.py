"""Public preview route and packaging boundaries; no provider or credentials."""
from html.parser import HTMLParser
import json
import re
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

from build import build, ASSETS
from preview import PreviewHandler, ROOT


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.references = []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        for key in ("src", "href"):
            if key in attributes:
                self.references.append(attributes[key])


class PublicPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PreviewHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_every_local_landing_destination_resolves(self):
        page = Links()
        page.feed((ROOT / "index.html").read_text(encoding="utf-8"))
        for reference in page.references:
            if reference.startswith("#"):
                self.assertIn(reference[1:], page.ids)
            elif reference.startswith("./"):
                if reference == "./app/" and not (ROOT / "dist/app/index.html").is_file():
                    # The Python-only suite does not install frontend dependencies.
                    continue
                with urlopen(self.origin + "/" + reference[2:]) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    @unittest.skipUnless((ROOT.parent / "product/node_modules/.bin/vite").exists()
                         or (ROOT.parent / "product/node_modules/.bin/vite.cmd").exists(),
                         "Frontend dependencies are not installed")
    def test_combined_build_serves_the_workspace_and_assets(self):
        output = build(include_app=True)
        page = (output / "app/index.html").read_text(encoding="utf-8")
        self.assertIn('/app/assets/', page)
        with urlopen(self.origin + "/app/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"Investigation workspace", response.read())
        with urlopen(self.origin + "/app/fonts/dm-sans.ttf") as response:
            self.assertEqual(response.status, 200)

    def test_server_exposes_no_repository_or_source_routes(self):
        for path in ("/pyproject.toml", "/.env", "/preview.py", "/assets/../../pyproject.toml", "/assets/%2e%2e/README.md", "/v1/capabilities"):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.origin + path)
            self.assertEqual(caught.exception.code, 404)

    def test_static_package_reuses_canonical_console_and_only_public_files(self):
        output = build()
        expected = {"index.html", "styles.css", "release.css", "script.js", "console/index.html", "evidence/index.html", "lab/index.html", "handoff/index.html"}
        expected.update("assets/" + name for name in ASSETS)
        actual = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        self.assertEqual((output / "console/index.html").read_bytes(), (ROOT.parent / "demo/index.html").read_bytes())

    def test_evidence_replay_questions_are_precise_and_answerable(self):
        html = (ROOT / "evidence/index.html").read_text(encoding="utf-8")
        questions = re.findall(
            r'<article class="probe" data-probe data-answer="([^"]+)">(.*?)</article>',
            html, flags=re.DOTALL,
        )
        self.assertEqual(len(questions), 3)
        self.assertEqual({answer for answer, _ in questions}, {"duplicate", "invalid", "removed"})
        self.assertNotIn("rejects-or-differs", html)
        for correct, markup in questions:
            choices = re.findall(r'data-pick="([^"]+)"', markup)
            self.assertEqual(len(choices), 2)
            self.assertIn(correct, choices)
            self.assertEqual(len(set(choices)), 2)

    def test_lab_no_js_fallback_states_recorded_scores_and_pending_genuine_http(self):
        html = (ROOT / "lab/index.html").read_text(encoding="utf-8")
        match = re.search(r"<noscript>(.*?)</noscript>", html, flags=re.DOTALL)
        self.assertIsNotNone(match)
        fallback = match.group(1)
        self.assertIn("14/25", fallback)
        self.assertIn("25/30", fallback)
        self.assertIn("NON_AI", fallback)
        self.assertIn("has not been run", fallback)

    def test_lab_verdict_style_derives_from_canonical_sequence_match(self):
        html = (ROOT / "lab/index.html").read_text(encoding="utf-8")
        self.assertIn("var seqMatch=", html)
        self.assertIn('seqMatch?"v-match":"v-diff"', html)
        self.assertNotIn('p.match?"v-match"', html)
        data = json.loads(re.search(r'id="lab-data">(.*?)</script>', html, flags=re.DOTALL).group(1))
        canon = lambda v: json.dumps(v, sort_keys=True, separators=(",", ":"))
        for probes in data.values():
            for probe in probes.values():
                computed = len(probe["reference"]) == len(probe["candidate"]) and all(
                    canon(a) == canon(b) for a, b in zip(probe["reference"], probe["candidate"]))
                self.assertEqual(probe["match"], computed)

    def test_vercel_publishes_only_built_site(self):
        config = json.loads((ROOT.parent / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(config["buildCommand"], "python3 web/build.py --with-app")
        self.assertEqual(config["outputDirectory"], "web/dist")
        self.assertEqual(config["installCommand"], "npm ci --prefix product --no-audit --no-fund")
        # This integration-only branch should not deploy each acceptance commit.
        self.assertFalse(config["git"]["deploymentEnabled"]["integrate/product-completion-20261030"])


if __name__ == "__main__":
    unittest.main()
