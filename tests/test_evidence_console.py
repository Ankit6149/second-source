"""Static investigation console checks; no network or model calls."""
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess

import pytest

HTML = (Path(__file__).resolve().parents[1] / "demo" / "index.html").read_text(encoding="utf-8")


class Nodes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.buttons = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if "id" in attr:
            self.ids.add(attr["id"])
        if tag == "button":
            self.buttons.append(attr)


def test_console_exposes_interactive_controls_and_honest_provenance():
    p = Nodes()
    p.feed(HTML)
    for name in ("fileInput", "import-label", "exportBtn", "metrics", "runlist",
                 "timeline", "provenance", "tabContent", "statusBadge", "notice-text"):
        assert name in p.ids
    assert len([b for b in p.buttons if "data-route" in b]) == 4
    assert len([b for b in p.buttons if "data-tab" in b]) == 4
    assert "NON_AI" in HTML
    assert "No candidate was admitted" in HTML
    assert "Failed before admission" in HTML or "failed before candidate admission" in HTML.lower()
    assert "not independently authenticated" in HTML.lower()


def test_console_is_static_no_auto_model_transport():
    assert '<script src=' not in HTML
    assert 'fetch(' not in HTML
    assert 'XMLHttpRequest' not in HTML
    assert 'localStorage' not in HTML
    assert 'MODEL_API_KEY' not in HTML
    assert '<form' not in HTML


def test_embedded_javascript_syntax(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js unavailable for JS syntax inspection")
    match = re.search(r"<script>\s*([\s\S]+?)</script>", HTML)
    assert match, "missing embedded controller"
    path = tmp_path / "console.js"
    path.write_text(match.group(1), encoding="utf-8")
    proc = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stderr
