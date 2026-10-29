from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


class LandingSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).parent.parent / "landing" / "index.html").read_text(encoding="utf-8")

    def test_self_contained_no_external_assets(self):
        self.assertNotIn("<script src=", self.html)
        self.assertNotIn('<link rel="stylesheet"', self.html)
        self.assertNotIn("http://", self.html.replace("http://localhost", "").replace("http://127.0.0.1", ""))
        self.assertNotIn("localStorage", self.html)
        self.assertNotIn("sessionStorage", self.html)

    def test_required_sections_and_nav_targets(self):
        for section in ("method", "status", "verification", "uses", "trust", "start", "faq"):
            self.assertIn('id="%s"' % section, self.html)

    def test_honest_claims_present(self):
        for phrase in ("22 / 25", "NOT YET MEASURED", "NOT DEMONSTRATED",
                       "stopped before admission", "NON_AI", "Can't verify"):
            self.assertIn(phrase, self.html)

    def test_accessibility_and_motion_guards(self):
        self.assertIn('lang="en"', self.html)
        self.assertIn("prefers-reduced-motion", self.html)
        self.assertIn("Skip to content", self.html)
        self.assertIn('role="img"', self.html)

    def test_markup_balances(self):
        for tag in ("div", "section", "table", "details", "svg", "figure"):
            opens = len(re.findall(r"<%s[\s>]" % tag, self.html))
            closes = len(re.findall(r"</%s>" % tag, self.html))
            self.assertEqual(opens, closes, tag)


class LivePageSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).parent / "live.html").read_text(encoding="utf-8")

    def test_read_only_and_memory_only(self):
        self.assertIn("fetch(", self.html)
        for forbidden in ("localStorage.", "localStorage[", "sessionStorage.",
                          "sessionStorage[", "document.cookie",
                          "method: \"POST\"", "method: 'POST'", "method:\"POST\"",
                          "method: \"PUT\"", "method: \"DELETE\"",
                          "XMLHttpRequest"):
            self.assertNotIn(forbidden, self.html)
        self.assertIn("Memory-only credential", self.html)
        self.assertIn("GET requests only", self.html)

    def test_loopback_guard_and_operator_states(self):
        self.assertIn("127.0.0.1", self.html)
        for state in ("Running", "Needs you", "Finished", "Stopped", "Can't verify"):
            self.assertIn(state, self.html)

    def test_hits_documented_read_endpoints(self):
        for route in ("/health/live", "/health/ready", "/v1/capabilities",
                      "/v1/investigations", "/runs", "/events"):
            self.assertIn(route, self.html)
        # Events are investigation-scoped with after/limit paging; the page
        # must not invent a per-run query parameter the API does not define.
        self.assertIn("after=0&limit=100", self.html)
        self.assertNotIn("run_id=", self.html)
        for field in ("event_id", "event_type", "investigation_id",
                      "run.result", "estimated_cost_usd", "needs_reconciliation"):
            self.assertIn(field, self.html)


if __name__ == "__main__":
    unittest.main()
