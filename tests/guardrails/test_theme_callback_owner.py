"""Every theme callback registered from UI code must pass ``owner=``.

Without an owner the callback outlives its widget, and every later theme
change calls into a deleted Qt object (see test_theme_callback_lifecycle).
"""

import ast
from pathlib import Path

UI_ROOT = Path(__file__).resolve().parents[2] / "cbpos" / "ui"


def _ownerless_registrations() -> list[str]:
    found = []
    for path in sorted(UI_ROOT.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "register_theme_callback"
                and not any(kw.arg == "owner" for kw in node.keywords)
            ):
                found.append(f"{path.relative_to(UI_ROOT.parent.parent)}:{node.lineno}")
    return found


def test_every_ui_theme_callback_has_an_owner():
    assert _ownerless_registrations() == []
