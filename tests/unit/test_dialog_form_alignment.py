"""Unit tests for dialog form alignment and day grid behavior (#574)."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFormLayout, QSizePolicy

from cbpos.i18n import _t, set_language
from cbpos.ui.dialogs.proforma_dialog import ProformaDialog
from cbpos.ui.views.promotion_view import PromotionDialog


@pytest.fixture(autouse=True)
def app_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_promotion_dialog_alignment_and_quick_days(monkeypatch):
    """Verify PromotionDialog has right-aligned labels, 480 min width, and 4+3 day grid."""
    monkeypatch.setattr("cbpos.ui.views.promotion_view.CategoryService.get_all", list)

    dialog = PromotionDialog()
    assert dialog.minimumWidth() >= 480

    # Locate QFormLayout
    form = None
    for i in range(dialog.layout().count()):
        item = dialog.layout().itemAt(i)
        if item.layout() and isinstance(item.layout(), QFormLayout):
            form = item.layout()
            break

    assert form is not None
    assert form.labelAlignment() == Qt.AlignmentFlag.AlignRight

    # Verify day checkboxes are 7 and quick select buttons work
    assert len(dialog.day_checkboxes) == 7

    # Weekdays select (Mon-Fri)
    dialog.btn_weekdays.click()
    assert all(cb.isChecked() for cb in dialog.day_checkboxes[:5])
    assert not dialog.day_checkboxes[5].isChecked()
    assert not dialog.day_checkboxes[6].isChecked()

    # Weekend select (Sat-Sun)
    dialog.btn_weekend.click()
    assert not any(cb.isChecked() for cb in dialog.day_checkboxes[:5])
    assert dialog.day_checkboxes[5].isChecked()
    assert dialog.day_checkboxes[6].isChecked()

    # All days select
    dialog.btn_all_days.click()
    assert all(cb.isChecked() for cb in dialog.day_checkboxes)


def test_promotion_dialog_translations():
    """Verify quick day keys exist and translate in all three languages."""
    for lang in ["en", "si", "ta"]:
        set_language(lang)
        all_text = _t("promotion.quick_all")
        weekdays_text = _t("promotion.quick_weekdays")
        weekend_text = _t("promotion.quick_weekend")

        assert all_text and not all_text.startswith("promotion.")
        assert weekdays_text and not weekdays_text.startswith("promotion.")
        assert weekend_text and not weekend_text.startswith("promotion.")

    set_language("en")


def test_proforma_dialog_form_alignment(monkeypatch):
    """Verify ProformaDialog right-aligned labels, expanding customer combo, and search row in form."""
    monkeypatch.setattr(
        "cbpos.ui.dialogs.proforma_dialog.CustomerService.get_all_customers",
        lambda self: [],
    )
    monkeypatch.setattr(
        "cbpos.ui.dialogs.proforma_dialog.ProductService.get_all_products",
        lambda self: [],
    )

    dialog = ProformaDialog()

    # Locate QFormLayout
    form = None
    for i in range(dialog.layout().count()):
        item = dialog.layout().itemAt(i)
        if item.layout() and isinstance(item.layout(), QFormLayout):
            form = item.layout()
            break

    assert form is not None
    assert form.labelAlignment() == Qt.AlignmentFlag.AlignRight
    assert dialog.customer_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding

    # Verify search row is part of the form (at least 4 rows: customer, validity, notes, add_product)
    assert form.rowCount() >= 4
