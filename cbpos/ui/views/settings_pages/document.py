"""Document numbering and formatting settings page."""

from PyQt6.QtWidgets import QComboBox, QLabel, QLineEdit

from cbpos.core.services.document_service import (
    DOC_NUMBER_MAX_LENGTH,
    DocumentService,
    validate_doc_pattern,
)
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.utils.style_helpers import set_status_class
from cbpos.ui.views.settings_pages.base import SettingsPage


class DocumentPage(SettingsPage):
    """Documents + Terminal ID."""

    def init_ui(self):
        """Build the document numbering tab (terminal ID, reset period, number formats)."""
        _, self.tabs = self._create_page_layout("", "")

        self._tab_docs, self._form_docs = self._build_form_tab()

        self.input_terminal_id = QLineEdit()
        self.input_terminal_id.setMaximumWidth(420)
        self._lbl_terminal_id = QLabel()
        self._form_docs.addRow(self._lbl_terminal_id, self.input_terminal_id)

        self.combo_reset_period = QComboBox()
        self.combo_reset_period.setMaximumWidth(420)
        self._lbl_reset_period = QLabel()
        self._form_docs.addRow(self._lbl_reset_period, self.combo_reset_period)

        self.input_fmt_sale = QLineEdit()
        self.input_fmt_sale.setMaximumWidth(420)
        self._lbl_sale_fmt = QLabel()
        self._form_docs.addRow(self._lbl_sale_fmt, self.input_fmt_sale)
        self._preview_sale = self._add_preview_row()

        self.input_fmt_purchase = QLineEdit()
        self.input_fmt_purchase.setMaximumWidth(420)
        self._lbl_purchase_fmt = QLabel()
        self._form_docs.addRow(self._lbl_purchase_fmt, self.input_fmt_purchase)
        self._preview_purchase = self._add_preview_row()

        self.input_fmt_return = QLineEdit()
        self.input_fmt_return.setMaximumWidth(420)
        self._lbl_return_fmt = QLabel()
        self._form_docs.addRow(self._lbl_return_fmt, self.input_fmt_return)
        self._preview_return = self._add_preview_row()

        self._lbl_fmt_legend = QLabel()
        self._lbl_fmt_legend.setProperty("class", "muted")
        self._lbl_fmt_legend.setWordWrap(True)
        self._form_docs.addRow("", self._lbl_fmt_legend)

        # (input, label, preview, document type the format numbers)
        self._fmt_fields = [
            (self.input_fmt_sale, self._lbl_sale_fmt, self._preview_sale, "SALE"),
            (self.input_fmt_purchase, self._lbl_purchase_fmt, self._preview_purchase, "PURCHASE"),
            (self.input_fmt_return, self._lbl_return_fmt, self._preview_return, "RETURN"),
        ]
        for field, *_ in self._fmt_fields:
            field.textChanged.connect(self._update_previews)
        self.input_terminal_id.textChanged.connect(self._update_previews)
        self.combo_reset_period.currentIndexChanged.connect(self._update_previews)

        self.tabs.addTab(self._tab_docs, "")

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def retranslate_ui(self) -> None:
        """Update all widget text and tab labels from the translation system."""
        self._page_title.setText(_t("settings.documents.title"))
        self.btn_reset_defaults.setText(_t("settings.btn_reset_defaults"))
        self._page_subtitle.setText(_t("settings.documents.subtitle"))

        self.tabs.setTabText(0, _t("settings.documents.tab_numbering"))

        self._lbl_terminal_id.setText(_t("settings.documents.terminal_id"))
        self.input_terminal_id.setPlaceholderText(_t("settings.documents.terminal_id_placeholder"))

        self._lbl_reset_period.setText(_t("settings.documents.reset_period"))

        # Re-populate reset period combo preserving selection
        current_data = self.combo_reset_period.currentData()
        self.combo_reset_period.clear()
        self.combo_reset_period.addItem(_t("settings.documents.reset_yearly"), "YEARLY")
        self.combo_reset_period.addItem(_t("settings.documents.reset_monthly"), "MONTHLY")
        self.combo_reset_period.addItem(_t("settings.documents.reset_never"), "NEVER")
        if current_data:
            idx = self.combo_reset_period.findData(current_data)
            if idx >= 0:
                self.combo_reset_period.setCurrentIndex(idx)

        self._lbl_sale_fmt.setText(_t("settings.documents.sale_format"))
        self.input_fmt_sale.setPlaceholderText(_t("settings.documents.sale_format_placeholder"))
        self._lbl_purchase_fmt.setText(_t("settings.documents.purchase_format"))
        self.input_fmt_purchase.setPlaceholderText(_t("settings.documents.purchase_format_placeholder"))
        self._lbl_return_fmt.setText(_t("settings.documents.return_format"))
        self.input_fmt_return.setPlaceholderText(_t("settings.documents.return_format_placeholder"))
        self._lbl_fmt_legend.setText(_t("settings.documents.fmt_legend"))
        self._update_previews()
        self.equalize_form_labels()

    def _add_preview_row(self) -> QLabel:
        """Add an empty preview/error label under the format field just added."""
        label = QLabel()
        label.setWordWrap(True)
        label.setVisible(False)
        self._form_docs.addRow("", label)
        return label

    def _update_previews(self) -> int:
        """Refresh each format's preview or inline error.

        Returns:
            The number of invalid formats.
        """
        terminal_id = self.input_terminal_id.text().strip() or "TERM-01"
        reset_period = self.combo_reset_period.currentData() or "YEARLY"
        invalid = 0
        for field, _label, preview, doc_type in self._fmt_fields:
            error = validate_doc_pattern(field.text().strip(), terminal_id)
            if error:
                invalid += 1
                # Only the length message takes a parameter; the others show
                # literal {seq}-style codes that str.format would choke on.
                text = _t(error, max=DOC_NUMBER_MAX_LENGTH) if error.endswith("too_long") else _t(error)
            else:
                number = DocumentService.preview_number(field.text().strip(), reset_period, terminal_id, doc_type)
                text = _t("settings.documents.fmt_preview_next", number=number)
                if DocumentService.adds_terminal_prefix(field.text().strip(), doc_type):
                    text += "\n" + _t("settings.documents.fmt_terminal_added")
            preview.setText(text)
            preview.setVisible(bool(text))
            css_class = "error" if error else "muted"
            if preview.property("class") != css_class:
                set_status_class(preview, css_class)
        return invalid

    def validate(self) -> None:
        """Block saving an invalid number format; the error shows under the field.

        Raises:
            ValueError: naming the first invalid field and why.
        """
        if not self._update_previews():
            return
        for field, label, preview, _doc_type in self._fmt_fields:
            if preview.property("class") == "error":
                field.setFocus()
                raise ValueError(f"{label.text()} {preview.text()}")

    def load(self, settings: dict):
        """Populate terminal ID, reset period and document number formats from the settings dict."""
        self.input_terminal_id.setText(settings.get("terminal_id", "TERM-01"))
        period = settings.get("doc_reset_period", "YEARLY")
        idx = self.combo_reset_period.findData(period)
        if idx >= 0:
            self.combo_reset_period.setCurrentIndex(idx)
        self.input_fmt_sale.setText(settings.get("doc_format_sale", "INV-{Y}-{seq:05d}"))
        self.input_fmt_purchase.setText(settings.get("doc_format_purchase", "GRN-{Y}-{seq:05d}"))
        self.input_fmt_return.setText(settings.get("doc_format_return", "CN-{Y}-{seq:05d}"))

    def save(self) -> dict:
        """Return terminal ID, reset period and document number formats as a settings dict."""
        return {
            "terminal_id": self.input_terminal_id.text().strip() or "TERM-01",
            "doc_reset_period": self.combo_reset_period.currentData() or "YEARLY",
            "doc_format_sale": self.input_fmt_sale.text().strip(),
            "doc_format_purchase": self.input_fmt_purchase.text().strip(),
            "doc_format_return": self.input_fmt_return.text().strip(),
        }


__all__ = ["DocumentPage"]
