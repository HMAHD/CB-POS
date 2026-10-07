"""
#598: Settings fields sit in scroll areas, and spin boxes/combos reacted to the wheel on
hover -- scrolling past VAT Rate could silently change it (18 -> 15) and Save wrote it.
A guarded field now ignores the wheel until it has focus, so the page scrolls instead.
"""

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from cbpos.ui.views.settings_pages import HardwarePage, SalesTaxPage, ShopInfoPage
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

pytestmark = pytest.mark.usefixtures("qapp")


def _wheel(widget: QWidget, steps: int = -1) -> QWheelEvent:
    """Send one wheel notch (negative = scroll down) to `widget`, as the mouse hovering it would."""
    pos = QPointF(widget.rect().center())
    event = QWheelEvent(
        pos,
        QPointF(widget.mapToGlobal(pos.toPoint())),
        QPoint(),
        QPoint(0, 120 * steps),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)
    return event


@pytest.fixture
def tax_page(qtbot):
    page = SalesTaxPage()
    qtbot.addWidget(page)
    page.load({"vat_registered": True, "tax_vat_rate": 18, "tax_sscl_rate": 2.5})
    page.resize(700, 220)  # short window, so the form has to scroll
    page.show()
    page.tabs.setCurrentWidget(page._tab_tax)
    page.activateWindow()
    qtbot.waitActive(page)
    return page


def _scroll_area(widget: QWidget) -> QScrollArea:
    parent = widget.parentWidget()
    while not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    return parent


class TestSettingsPages:
    def test_hovering_vat_and_rolling_the_wheel_leaves_it_unchanged(self, tax_page):
        spin = tax_page.spin_vat
        assert spin.isEnabled()
        assert not spin.hasFocus()

        _wheel(spin, steps=-3)

        assert spin.value() == 18

    def test_the_wheel_scrolls_the_page_instead(self, tax_page):
        spin = tax_page.spin_sscl
        bar = _scroll_area(spin).verticalScrollBar()
        assert bar.maximum() > 0, "test needs a scrollable form"
        bar.setValue(0)

        event = _wheel(spin, steps=-1)

        assert spin.value() == pytest.approx(2.5)
        # Left unaccepted, a real (spontaneous) wheel event travels on up to the scroll area. Qt6
        # never propagates synthetic wheel events, so do that hop by hand: the page scrolls.
        assert not event.isAccepted()
        _wheel(_scroll_area(spin).viewport(), steps=-1)
        assert bar.value() > 0

    def test_a_focused_field_still_takes_the_wheel(self, tax_page, qtbot):
        spin = tax_page.spin_vat
        spin.setFocus()
        qtbot.waitUntil(spin.hasFocus)

        _wheel(spin, steps=1)

        assert spin.value() == 19

    def test_focus_comes_from_click_or_tab_not_the_wheel(self, tax_page):
        assert tax_page.spin_vat.focusPolicy() == Qt.FocusPolicy.StrongFocus

    @pytest.mark.parametrize("page_cls", [ShopInfoPage, SalesTaxPage, HardwarePage])
    def test_every_spin_and_combo_on_a_settings_page_is_guarded(self, qtbot, page_cls):
        with patch("cbpos.ui.views.settings_pages.QPrinterInfo.availablePrinterNames", return_value=[]):
            page = page_cls()
        qtbot.addWidget(page)
        page.show()
        qtbot.waitExposed(page)

        fields = page.findChildren(QSpinBox) + page.findChildren(QComboBox)
        assert fields
        for field in fields:
            index = field.currentIndex() if isinstance(field, QComboBox) else field.value()
            _wheel(field, steps=-1)
            after = field.currentIndex() if isinstance(field, QComboBox) else field.value()
            assert after == index, f"{type(field).__name__} changed on hover-wheel"


class TestDialogs:
    def test_fields_added_after_install_are_guarded_too(self, qtbot):
        dialog = QDialog()
        qtbot.addWidget(dialog)
        install_wheel_guard(dialog)
        layout = QVBoxLayout(dialog)
        holder = QWidget()
        combo = QComboBox(holder)
        combo.addItems(["a", "b", "c"])
        layout.addWidget(holder)
        dialog.show()
        qtbot.waitExposed(dialog)

        _wheel(combo, steps=-1)

        assert combo.currentIndex() == 0

    def test_payment_dialog_style_no_focus_field_keeps_its_policy(self, qtbot):
        dialog = QDialog()
        qtbot.addWidget(dialog)
        spin = QSpinBox(dialog)
        spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        install_wheel_guard(dialog)

        assert spin.focusPolicy() == Qt.FocusPolicy.NoFocus

    def test_every_dialog_with_spin_boxes_or_combos_installs_the_guard(self):
        dialogs = Path(__file__).resolve().parents[2] / "cbpos" / "ui" / "dialogs"
        missing = []
        for path in sorted(dialogs.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            if re.search(r"\bQ(Double)?SpinBox\(|\bQComboBox\(|\bQDate(Time)?Edit\(", source):
                if "install_wheel_guard(self)" not in source:
                    missing.append(path.name)
        assert missing == []
