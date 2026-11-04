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

    def test_static_package_contains_only_public_files(self):
        output = build()
        expected = {"index.html", "landing.css", "research.css", "reports/index.html",
                    "experiments/index.html", "console/index.html", "evidence/index.html",
                    "lab/index.html", "challenge/index.html", "handoff/index.html"}
        expected.update("assets/" + name for name in ASSETS)
        actual = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)

    def test_live_report_and_experiment_routes_are_accessible(self):
        output = build()
        for route, expected in (("reports", "14 / 25"), ("experiments", "Measured investigations")):
            source = (ROOT / route / "index.html").read_text(encoding="utf-8")
            self.assertEqual(source, (output / route / "index.html").read_text(encoding="utf-8"))
            self.assertIn(expected, source)
            with urlopen(self.origin + f"/{route}/") as response:
                self.assertEqual(response.status, 200)
                self.assertIn(expected.encode(), response.read())

    def test_retired_routes_redirect_to_current_destination(self):
        output = build()
        for route, destination in (("evidence", "/reports/"), ("challenge", "/reports/"),
                                   ("lab", "/experiments/"), ("console", "/app/"), ("handoff", "/app/")):
            stub = (output / route / "index.html").read_text(encoding="utf-8")
            self.assertIn(destination, stub)
            try:
                with urlopen(self.origin + f"/{route}/") as response:
                    self.assertTrue(response.url.endswith(destination))
            except HTTPError as exc:
                if destination != "/app/" or exc.code != 503:
                    raise

    def test_no_public_judge_lab_routes_or_hidden_reference_data(self):
        config = json.loads((ROOT.parent / "vercel.json").read_text(encoding="utf-8"))
        redirects = {item["source"]: item["destination"] for item in config["redirects"]}
        self.assertEqual(redirects["/challenge/"], "/reports/")
        self.assertEqual(redirects["/lab/"], "/experiments/")
        self.assertEqual(redirects["/evidence/"], "/reports/")
        for page in ("index.html", "reports/index.html", "experiments/index.html"):
            text = (ROOT / page).read_text(encoding="utf-8")
            self.assertNotIn("GEMMA_TEST", text)
            self.assertNotIn("Sealed evaluation cases:", text)

    def test_landing_tabs_are_real_accessible_recorded_comparisons(self):
        text = (ROOT / "index.html").read_text(encoding="utf-8")
        for case in ("duplicate", "limit", "schema"):
            self.assertIn(f'data-case="{case}"', text)
        self.assertIn('role="group" aria-label="Choose observed case"', text)
        self.assertIn("button.setAttribute", text) if False else self.assertIn("aria-pressed", text)
        self.assertIn("Recorded public probe", text)
        self.assertIn("prefers-reduced-motion: reduce", text)
        self.assertNotIn("LIVE_MODEL", text)
        self.assertNotIn("gemma", text.lower())

    def test_vercel_publishes_only_built_site(self):
        config = json.loads((ROOT.parent / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(config["buildCommand"], "python3 web/build.py --with-app")
        self.assertEqual(config["outputDirectory"], "web/dist")
        self.assertEqual(config["installCommand"], "npm ci --prefix product --no-audit --no-fund")
        # This integration-only branch should not deploy each acceptance commit.
        self.assertFalse(config["git"]["deploymentEnabled"]["integrate/product-completion-20261030"])


if __name__ == "__main__":
    unittest.main()
