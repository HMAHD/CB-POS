"""AST guardrails and lifecycle tests for Qt object destruction and owner callbacks (#918)."""

import ast
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QMainWindow

from cbpos.ui.widgets.modal_dimmer import install_modal_dimmer_filter

CBPOS_ROOT = Path(__file__).resolve().parents[2] / "cbpos"
UI_ROOT = CBPOS_ROOT / "ui"


def _find_destroyed_connect_calls() -> list[str]:
    violations = []
    for path in sorted(CBPOS_ROOT.rglob("*.py")):
        # destroy_hooks.py is the only sanctioned place to connect to .destroyed
        if path.name == "destroy_hooks.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "connect"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "destroyed"
            ):
                rel = path.relative_to(CBPOS_ROOT.parent)
                violations.append(f"{rel}:{node.lineno}")
    return violations


def _find_ownerless_language_callbacks() -> list[str]:
    violations = []
    for path in sorted(UI_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                is_target_call = False
                if (isinstance(node.func, ast.Name) and node.func.id == "register_language_callback") or (
                    isinstance(node.func, ast.Attribute) and node.func.attr == "register_language_callback"
                ):
                    is_target_call = True

                if is_target_call and not any(kw.arg == "owner" for kw in node.keywords):
                    rel = path.relative_to(CBPOS_ROOT.parent)
                    violations.append(f"{rel}:{node.lineno}")
    return violations


@pytest.mark.guardrails
def test_no_destroyed_connect_outside_destroy_hooks():
    """No Python code outside destroy_hooks.py may call .destroyed.connect(...) (#918)."""
    violations = _find_destroyed_connect_calls()
    assert violations == [], (
        f"Forbidden .destroyed.connect() call(s) found outside destroy_hooks.py: {violations}. "
        "Use call_on_destroyed(obj, callback, *args) instead to avoid segfaults."
    )


@pytest.mark.guardrails
def test_every_register_language_callback_in_ui_passes_owner():
    """Every register_language_callback call in cbpos/ui must pass owner= keyword (#918)."""
    violations = _find_ownerless_language_callbacks()
    assert violations == [], (
        f"Ownerless register_language_callback call(s) found in cbpos/ui: {violations}. "
        "Always pass owner= to prevent dangling callbacks when widgets are destroyed."
    )


def test_modal_dimmer_lifecycle_restores_dimmer_state(qapp, qtbot):
    """ModalDimmer dims target window on modal show, hides on close, and safely cleans up (#918)."""
    manager = install_modal_dimmer_filter(qapp)

    main_win = QMainWindow()
    main_win.resize(800, 600)
    main_win.show()
    qtbot.waitUntil(lambda: main_win.isVisible(), timeout=2000)

    dialog = QDialog(main_win)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.resize(300, 200)

    # 1. Show modal dialog
    dialog.show()
    qtbot.waitUntil(lambda: len(manager._active_modals) > 0, timeout=2000)

    target_key = id(main_win) if id(main_win) in manager._dimmers else main_win
    dimmer = manager._dimmers.get(target_key)
    assert dimmer is not None
    assert dimmer.isVisible()

    # 2. Hide / close modal dialog
    dialog.accept()
    qtbot.waitUntil(lambda: not dimmer.isVisible(), timeout=2000)
    assert not dimmer.isVisible()

    # 3. Destroy dialog and window cleanly
    dialog.deleteLater()
    main_win.close()
    main_win.deleteLater()
