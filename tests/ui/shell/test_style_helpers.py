"""Tests for issue #694: canonicalize QSS dynamic property refresh into a shared helper."""

from PyQt6.QtWidgets import QLabel, QPushButton, QWidget


def test_set_status_class_updates_property_and_refreshes_style(qapp, monkeypatch):
    from cbpos.ui.utils.style_helpers import set_status_class

    widget = QWidget()
    unpolish_called = []
    polish_called = []
    style = widget.style()
    monkeypatch.setattr(style, "unpolish", lambda w: unpolish_called.append(w))
    monkeypatch.setattr(style, "polish", lambda w: polish_called.append(w))

    set_status_class(widget, "success-hint")

    assert widget.property("class") == "success-hint"
    assert unpolish_called == [widget]
    assert polish_called == [widget]


def test_set_status_class_with_text(qapp):
    from cbpos.ui.utils.style_helpers import set_status_class

    label = QLabel()
    set_status_class(label, "debit", "Failure message")

    assert label.property("class") == "debit"
    assert label.text() == "Failure message"


def test_set_status_class_without_text_preserves_existing_text(qapp):
    from cbpos.ui.utils.style_helpers import set_status_class

    btn = QPushButton("Click Me")
    set_status_class(btn, "primary")

    assert btn.property("class") == "primary"
    assert btn.text() == "Click Me"


def test_refresh_style_invokes_unpolish_and_polish(qapp, monkeypatch):
    from cbpos.ui.utils.style_helpers import refresh_style

    widget = QWidget()
    unpolish_called = []
    polish_called = []
    style = widget.style()
    monkeypatch.setattr(style, "unpolish", lambda w: unpolish_called.append(w))
    monkeypatch.setattr(style, "polish", lambda w: polish_called.append(w))

    refresh_style(widget)

    assert unpolish_called == [widget]
    assert polish_called == [widget]


def test_style_helpers_also_importable_from_styles_package(qapp):
    from cbpos.ui.styles.style_helpers import refresh_style, set_status_class

    assert callable(set_status_class)
    assert callable(refresh_style)


def test_no_direct_unpolish_calls_in_ui_modules():
    """Ensure no UI modules invoke widget.style().unpolish() directly outside style_helpers."""
    from pathlib import Path

    ui_dir = Path("cbpos/ui")
    violations = []
    for py_file in ui_dir.rglob("*.py"):
        if py_file.name == "style_helpers.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        if ".style().unpolish(" in content or ".style().polish(" in content:
            violations.append(str(py_file))

    assert not violations, f"Direct style unpolish/polish calls found in: {violations}"
