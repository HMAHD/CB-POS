"""Unit tests for standardized dialog footer component and QDialogButtonBox elimination."""

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from cbpos.i18n import _t, set_language
from cbpos.ui.widgets.dialog_footer import make_dialog_footer


@pytest.fixture(autouse=True)
def app_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_make_dialog_footer_basic_order_and_styling():
    """Verify that make_dialog_footer produces [Primary, Cancel] in that order with primary styling."""
    clicked_primary = False
    clicked_cancel = False

    def on_p():
        nonlocal clicked_primary
        clicked_primary = True

    def on_c():
        nonlocal clicked_cancel
        clicked_cancel = True

    layout, btn_p, btn_c = make_dialog_footer(
        primary_key="common.save",
        on_primary=on_p,
        cancel_key="common.cancel",
        on_cancel=on_c,
    )

    # Buttons created
    assert isinstance(btn_p, QPushButton)
    assert isinstance(btn_c, QPushButton)

    # Primary styling and default behavior
    assert btn_p.property("class") == "primary"
    assert btn_p.isDefault() is True
    assert btn_c.autoDefault() is False

    # Check order in layout: stretch -> primary -> cancel
    # layout items: [0: QSpacerItem, 1: btn_p, 2: btn_c]
    assert layout.count() == 3
    assert layout.itemAt(1).widget() == btn_p
    assert layout.itemAt(2).widget() == btn_c

    # Callbacks
    btn_p.click()
    assert clicked_primary is True
    btn_c.click()
    assert clicked_cancel is True


def test_make_dialog_footer_with_left_widget():
    """Verify that left_widget is placed before stretch."""
    dummy = QLabel("Total: 500.00")
    layout, btn_p, btn_c = make_dialog_footer(left_widget=dummy)

    # layout items: [0: dummy, 1: QSpacerItem, 2: btn_p, 3: btn_c]
    assert layout.count() == 4
    assert layout.itemAt(0).widget() == dummy
    assert layout.itemAt(2).widget() == btn_p
    assert layout.itemAt(3).widget() == btn_c


def test_make_dialog_footer_translations():
    """Verify dialog buttons translate properly across supported locales."""
    for locale in ["en", "si", "ta"]:
        set_language(locale)
        save_text = _t("common.save")
        cancel_text = _t("common.cancel")
        ok_text = _t("common.ok")

        assert save_text != "" and not save_text.startswith("common.")
        assert cancel_text != "" and not cancel_text.startswith("common.")
        assert ok_text != "" and not ok_text.startswith("common.")

    # Reset back to english
    set_language("en")


def test_no_qdialogbuttonbox_in_cbpos_ui():
    """Verify that QDialogButtonBox is completely eliminated from cbpos/ui codebase."""
    ui_dir = Path(__file__).resolve().parent.parent.parent / "cbpos" / "ui"
    assert ui_dir.is_dir()

    occurrences = []
    for py_file in ui_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "QDialogButtonBox" in content:
            occurrences.append(str(py_file.relative_to(ui_dir)))

    assert occurrences == [], f"Found QDialogButtonBox in: {occurrences}"
