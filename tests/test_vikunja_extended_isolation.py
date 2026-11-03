"""Isolation guards for the frozen extended Vikunja suite (evaluator-only).

The extended suite must stay out of every prompt/model path, exactly
like vikunja_held_out.py, and must not duplicate the original suite.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

PROMPT_SIDE = [
    "vikunja_hybrid_experiment.py",
    "vikunja_model_experiment.py",
    "protected_compiler.py",
    "behavioral_ir.py",
    "behavioral_interpreter.py",
]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_extended_suite_never_imported_prompt_side():
    for name in PROMPT_SIDE:
        mods = _imports(SCRIPTS / name)
        assert not any("held_out_extended" in m or "EXTENDED_HELD_OUT" in m for m in mods), name


def test_extended_sequences_are_new_and_well_formed():
    import sys

    sys.path.insert(0, str(SCRIPTS))
    from vikunja_held_out import HELD_OUT
    from vikunja_held_out_extended import EXTENDED_HELD_OUT, EXTENDED_SUITE_VERSION

    assert EXTENDED_SUITE_VERSION == 1
    assert len(EXTENDED_HELD_OUT) == 6
    frozen = {tuple(map(str, seq)) for seq in HELD_OUT}
    for seq in EXTENDED_HELD_OUT:
        assert seq, "empty sequence"
        assert tuple(map(str, seq)) not in frozen, "duplicates frozen suite"
        for method, path, _body, user in seq:
            assert method in {"PUT", "POST", "GET", "DELETE", "PATCH"}
            assert path.startswith("/")
            assert user in {"alice", "bob", "anon"}
