"""
#274: this app has an established button-class convention (primary
green, danger red, secondary neutral outlined), but three dialogs
skipped it for buttons that clearly fit an existing class. Category
Manager and Unit Manager's Clear/Close fell back to plain default
styling instead of class="secondary"; Label Print's Remove Selected/
Clear All (destructive) and Preview Labels (safe) all rendered as
identical plain gray buttons with no differentiation.
"""

import pytest
from PyQt6.QtWidgets import QPushButton

from cbpos.i18n import _t
from cbpos.ui.dialogs.category_manager import CategoryManagerDialog
from cbpos.ui.dialogs.label_print_dialog import LabelPrintDialog
from cbpos.ui.dialogs.unit_manager import UnitManagerDialog

pytestmark = pytest.mark.usefixtures("qapp")


def _button_by_text(dialog, text: str) -> QPushButton:
    for btn in dialog.findChildren(QPushButton):
        if btn.text() == text:
            return btn
    raise AssertionError(f"No button with text {text!r} found")


class TestCategoryManagerButtonClasses:
    def test_clear_button_is_secondary(self, db_session):
        dialog = CategoryManagerDialog()
        assert dialog.btn_clear.property("class") == "secondary"

    def test_close_button_is_secondary(self, db_session):
        dialog = CategoryManagerDialog()
        assert dialog.btn_close.property("class") == "secondary"


class TestUnitManagerButtonClasses:
    def test_clear_button_is_secondary(self, db_session):
        dialog = UnitManagerDialog()
        assert dialog.btn_clear.property("class") == "secondary"

    def test_close_button_is_secondary(self, db_session):
        dialog = UnitManagerDialog()
        assert dialog.btn_close.property("class") == "secondary"


class TestLabelPrintDialogButtonClasses:
    def test_remove_selected_is_danger(self, db_session):
        dialog = LabelPrintDialog()
        btn = _button_by_text(dialog, _t("label_print.remove_selected"))
        assert btn.property("class") == "danger"

    def test_clear_all_is_danger(self, db_session):
        dialog = LabelPrintDialog()
        btn = _button_by_text(dialog, _t("label_print.clear_all"))
        assert btn.property("class") == "danger"

    def test_preview_is_secondary_not_left_as_bare_default(self, db_session):
        dialog = LabelPrintDialog()
        btn = _button_by_text(dialog, _t("label_print.preview_label"))
        assert btn.property("class") == "secondary"

    def test_print_labels_stays_primary(self, db_session):
        dialog = LabelPrintDialog()
        btn = _button_by_text(dialog, _t("label_print.print_labels"))
        assert btn.property("class") == "primary"
