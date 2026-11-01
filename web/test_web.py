"""Public preview route and packaging boundaries; no provider or credentials."""
from html.parser import HTMLParser
import json
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
                with urlopen(self.origin + "/" + reference[2:]) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_server_exposes_no_repository_or_source_routes(self):
        for path in ("/pyproject.toml", "/.env", "/preview.py", "/assets/../../pyproject.toml", "/assets/%2e%2e/README.md", "/v1/capabilities"):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.origin + path)
            self.assertEqual(caught.exception.code, 404)

    def test_static_package_reuses_canonical_console_and_only_public_files(self):
        output = build()
        expected = {"index.html", "styles.css", "release.css", "script.js", "console/index.html"}
        expected.update("assets/" + name for name in ASSETS)
        actual = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        self.assertEqual((output / "console/index.html").read_bytes(), (ROOT.parent / "demo/index.html").read_bytes())

    def test_vercel_publishes_only_built_site(self):
        config = json.loads((ROOT.parent / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(config["buildCommand"], "python3 web/build.py")
        self.assertEqual(config["outputDirectory"], "web/dist")
        self.assertEqual(config["installCommand"], "")
        # This integration-only branch should not deploy each acceptance commit.
        self.assertFalse(config["git"]["deploymentEnabled"]["integrate/product-completion-20261030"])


if __name__ == "__main__":
    unittest.main()
