"""Unit tests verifying Issue #573 [UI-017-A]:

- On every Settings page all fields start at the same x position (equalized label widths).
- No row mixes control heights (32px standard row height for buttons, inputs, help icons).
- The barcode prefix field rejects letters and is not full width (width 80 + QIntValidator(0, 99)).
- Document format fields capped at max width 420px.
- Receipt preview width selector moved into preview header.
- Label equalization holds across languages (en, si, ta).
"""

import pytest
from PyQt6.QtGui import QIntValidator, QValidator
from PyQt6.QtWidgets import QFormLayout, QLabel

from cbpos.i18n import set_language, unregister_language_callback
from cbpos.ui.views.settings_pages import (
    DocumentPage,
    HardwarePage,
    NetworkPage,
    ReceiptPage,
    SalesTaxPage,
    ShopInfoPage,
    SystemPage,
)

pytestmark = pytest.mark.usefixtures("qapp")


class TestBarcodePrefixField:
    """The barcode prefix field rejects letters and is not full width."""

    def test_barcode_prefix_validator_and_width(self):
        page = HardwarePage()
        try:
            assert page.input_scale_prefix.maximumWidth() == 80
            assert page.input_scale_prefix.maxLength() == 2

            validator = page.input_scale_prefix.validator()
            assert isinstance(validator, QIntValidator)
            assert validator.bottom() == 0
            assert validator.top() == 99

            # Rejects non-digits
            assert validator.validate("AB", 0)[0] == QValidator.State.Invalid
            assert validator.validate("20", 0)[0] == QValidator.State.Acceptable
            assert validator.validate("5", 0)[0] == QValidator.State.Acceptable
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()


class TestControlHeightsConsistency:
    """No row mixes control heights; secondary buttons and help icons standardize to 32px."""

    def test_receipt_logo_row_heights(self):
        page = ReceiptPage()
        try:
            assert page.btn_browse_logo.maximumHeight() == 32
            assert page.btn_clear_logo.maximumHeight() == 32
            assert page.btn_logo_help.maximumHeight() == 32
            assert page.btn_logo_help.height() == 32
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()

    def test_email_helper_row_heights(self):
        page = ShopInfoPage()
        try:
            assert page.btn_gmail.maximumHeight() == 32
            assert page.btn_help.maximumHeight() == 32
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()

    def test_backup_browse_button_height(self):
        page = SystemPage()
        try:
            assert page.btn_browse_backup.maximumHeight() == 32
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()


class TestDocumentFieldWidths:
    """Document fields do not stretch full-width across wide displays."""

    def test_document_format_fields_capped_at_420(self):
        page = DocumentPage()
        try:
            assert page.input_terminal_id.maximumWidth() == 420
            assert page.combo_reset_period.maximumWidth() == 420
            assert page.input_fmt_sale.maximumWidth() == 420
            assert page.input_fmt_purchase.maximumWidth() == 420
            assert page.input_fmt_return.maximumWidth() == 420
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()


class TestReceiptPreviewHeader:
    """Preview width selector is located in the preview's header alongside preview title."""

    def test_preview_header_elements(self):
        page = ReceiptPage()
        try:
            assert hasattr(page, "_lbl_preview_title")
            assert hasattr(page, "_lbl_preview_width")
            assert hasattr(page, "combo_preview_width")
            assert page._lbl_preview_title.text() != ""
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()


class TestLabelColumnAlignmentAcrossSections:
    """On every Settings page, all fields start at the same X position (equal label widths)."""

    @pytest.mark.parametrize(
        "page_cls",
        [
            HardwarePage,
            ReceiptPage,
            ShopInfoPage,
            SalesTaxPage,
            DocumentPage,
            SystemPage,
            NetworkPage,
        ],
    )
    def test_all_labels_equalized_on_page(self, page_cls):
        page = page_cls()
        try:
            forms = page.findChildren(QFormLayout)
            labels = []
            for form in forms:
                for row in range(form.rowCount()):
                    item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                    if item and item.widget() and isinstance(item.widget(), QLabel):
                        lbl = item.widget()
                        if lbl.text().strip():
                            labels.append(lbl)

            if len(labels) > 1:
                widths = {lbl.width() for lbl in labels}
                assert len(widths) == 1, (
                    f"Expected all labels on {page_cls.__name__} to have equal width, got: {widths}"
                )
        finally:
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()

    def test_equalization_holds_in_sinhala_and_tamil(self):
        page = HardwarePage()
        try:
            for lang in ["si", "ta", "en"]:
                set_language(lang)
                page.retranslate_ui()
                forms = page.findChildren(QFormLayout)
                labels = [
                    form.itemAt(r, QFormLayout.ItemRole.LabelRole).widget()
                    for form in forms
                    for r in range(form.rowCount())
                    if form.itemAt(r, QFormLayout.ItemRole.LabelRole)
                    and isinstance(form.itemAt(r, QFormLayout.ItemRole.LabelRole).widget(), QLabel)
                    and form.itemAt(r, QFormLayout.ItemRole.LabelRole).widget().text().strip()
                ]
                widths = {lbl.width() for lbl in labels}
                assert len(widths) == 1, f"Label widths should be identical in {lang}, got {widths}"
        finally:
            set_language("en")
            unregister_language_callback(page.retranslate_ui)
            page.deleteLater()
