from html.parser import HTMLParser
from pathlib import Path
import unittest


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])


class ConsoleSmoke(unittest.TestCase):
    def test_viewer_ui_has_working_inputs(self):
        html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        parser = Markup()
        parser.feed(html)
        for required in (
            "fileInput", "exportBtn", "metrics", "runlist", "timeline",
            "provenance", "tabContent", "statusBadge",
        ):
            self.assertIn(required, parser.ids)
        self.assertIn("addEventListener", html)
        self.assertIn("NON_AI", html)
        self.assertIn("No candidate was admitted", html)
        self.assertIn("local file", html.lower())
        self.assertNotIn("fetch(", html)
        self.assertNotIn("XMLHttpRequest", html)
        self.assertNotIn("localStorage", html)

    def test_no_external_script_or_stylesheet(self):
        html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('<script src=', html)
        self.assertNotIn('<link rel="stylesheet"', html)


if __name__ == "__main__":
    unittest.main()
