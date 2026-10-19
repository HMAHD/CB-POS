"""Automated enterprise design system guardrail tests.

Enforces zero-regression rules:
1. Zero inline stylesheets in cbpos/ui/ (all styling must reside in theme QSS).
2. No window-level setFixedSize() calls on dialogs (dialogs must use responsive sizing with setMinimumSize/resize).
3. #BtnCancel must never be styled with danger/red colors in dark.qss or light.qss.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UI_DIR = REPO_ROOT / "cbpos" / "ui"
DIALOGS_DIR = UI_DIR / "dialogs"
STYLES_DIR = UI_DIR / "styles"


def test_zero_inline_stylesheets_in_ui():
    """Ensure no .setStyleSheet(...) calls exist anywhere in cbpos/ui/."""
    violations: list[str] = []
    for py_file in UI_DIR.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as err:
            violations.append(f"{py_file.relative_to(REPO_ROOT)}: Failed to parse: {err}")
            continue

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setStyleSheet"
            ):
                rel_path = py_file.relative_to(REPO_ROOT)
                violations.append(f"{rel_path}:{node.lineno} calls setStyleSheet()")

    assert not violations, (
        f"Found {len(violations)} inline setStyleSheet() call(s) in cbpos/ui/.\n"
        "All component styling must use QSS selectors or semantic classes:\n" + "\n".join(violations)
    )


def test_no_window_level_fixed_size_on_dialogs():
    """Ensure dialog classes in cbpos/ui/dialogs/ do not call self.setFixedSize(...)."""
    violations: list[str] = []

    for py_file in DIALOGS_DIR.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as err:
            violations.append(f"{py_file.relative_to(REPO_ROOT)}: Failed to parse: {err}")
            continue

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            # Identify if class inherits from QDialog or contains 'Dialog' in its name/bases
            is_dialog = False
            for base in node.bases:
                if (isinstance(base, ast.Name) and "Dialog" in base.id) or (
                    isinstance(base, ast.Attribute) and "Dialog" in base.attr
                ):
                    is_dialog = True
                    break
            if not is_dialog and "Dialog" in node.name:
                is_dialog = True

            if is_dialog:
                for sub in ast.walk(node):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "self"
                        and sub.func.attr == "setFixedSize"
                    ):
                        rel_path = py_file.relative_to(REPO_ROOT)
                        violations.append(f"{rel_path}:{sub.lineno} in {node.name}: calls self.setFixedSize(...)")

    assert not violations, (
        f"Found {len(violations)} dialog window-level setFixedSize() call(s).\n"
        "Dialogs must use responsive sizing (setMinimumSize + resize) to avoid viewport clipping on smaller screens:\n"
        + "\n".join(violations)
    )


def test_cancel_button_never_mapped_to_danger_in_qss():
    """Ensure #BtnCancel is never mapped to danger classes or red hex colors in stylesheets."""
    qss_files = [STYLES_DIR / "dark.qss", STYLES_DIR / "light.qss"]
    violations: list[str] = []

    comment_re = re.compile(r"/\*.*?\*/", re.DOTALL)
    rule_re = re.compile(r"([^{}]+)\{([^{}]+)\}")
    btn_cancel_re = re.compile(r"#BtnCancel\b")

    danger_indicators = [
        '[class="danger"]',
        "[class='danger']",
        "#ff4136",
        "#dc3545",
    ]

    for qss_file in qss_files:
        assert qss_file.exists(), f"QSS file does not exist: {qss_file}"
        raw = qss_file.read_text(encoding="utf-8")
        clean = comment_re.sub("", raw)

        for match in rule_re.finditer(clean):
            selector = match.group(1).strip()
            body = match.group(2).strip()

            if btn_cancel_re.search(selector):
                block = f"{selector} {{ {body} }}".lower()
                found = [ind for ind in danger_indicators if ind in block]
                if found:
                    rel_path = qss_file.relative_to(REPO_ROOT)
                    violations.append(f"{rel_path}: Rule '{selector}' matched danger indicator(s) {found}: {body}")

    assert not violations, (
        f"Found {len(violations)} rule(s) mapping #BtnCancel to danger colors/classes:\n" + "\n".join(violations)
    )
