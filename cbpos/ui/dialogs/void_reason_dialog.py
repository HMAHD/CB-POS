from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class VoidReasonDialog(QDialog):
    """Confirm a void and pick a VoidReason, plus an optional free-text note (#627)."""

    def __init__(
        self, reasons: list[dict], require_reason: bool, doc_number: str, parent: QWidget | None = None
    ) -> None:
        """Build the dialog.

        Args:
            reasons: ``{"id", "code", "description"}`` dicts to offer.
            require_reason: When True the Void button stays disabled until a reason is chosen.
            doc_number: Document number shown in the confirmation question.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setObjectName("VoidReasonDialog")
        self.setMinimumWidth(420)
        self._require_reason = require_reason
        self._doc_number = doc_number
        self.reason_id: int | None = None
        self.reason_text = ""

        layout = QVBoxLayout(self)
        self.lbl_question = QLabel()
        self.lbl_question.setWordWrap(True)
        layout.addWidget(self.lbl_question)
        self.lbl_warning = QLabel()
        self.lbl_warning.setProperty("class", "debit")
        layout.addWidget(self.lbl_warning)

        self.lbl_reason = QLabel()
        layout.addWidget(self.lbl_reason)
        self.cmb_reason = QComboBox()
        self.cmb_reason.addItem("", None)  # placeholder, text set in retranslate_ui
        for reason in reasons:
            self.cmb_reason.addItem(reason["description"], reason["id"])
        layout.addWidget(self.cmb_reason)

        self.lbl_note = QLabel()
        layout.addWidget(self.lbl_note)
        self.txt_note = QLineEdit()
        layout.addWidget(self.txt_note)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        self.btn_void = QPushButton()
        self.btn_void.setObjectName("BtnVoid")
        self.btn_void.setProperty("class", "danger")
        self.btn_void.clicked.connect(self._accept)
        btn_row.addWidget(self.btn_void)
        self.btn_cancel = QPushButton()
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.setProperty("class", "secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        self.cmb_reason.currentIndexChanged.connect(self._update_void_enabled)
        self._update_void_enabled()
        self.btn_cancel.setDefault(True)
        self.retranslate_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def retranslate_ui(self) -> None:
        """Apply translated text."""
        self.setWindowTitle(_t("document_browser.confirm_void_title"))
        self.lbl_question.setText(_t("document_browser.void_question", doc_number=self._doc_number))
        self.lbl_warning.setText(_t("document_browser.void_warning"))
        self.lbl_reason.setText(_t("void_reason_dialog.reason"))
        self.cmb_reason.setItemText(0, _t("void_reason_dialog.select_reason"))
        self.lbl_note.setText(_t("void_reason_dialog.note"))
        self.txt_note.setPlaceholderText(_t("void_reason_dialog.note_placeholder"))
        self.btn_cancel.setText(_t("common.cancel"))
        self.btn_void.setText(_t("document_browser.btn_void"))

    def _update_void_enabled(self) -> None:
        self.btn_void.setEnabled(not self._require_reason or self.cmb_reason.currentData() is not None)

    def _accept(self) -> None:
        self.reason_id = self.cmb_reason.currentData()
        note = self.txt_note.text().strip()
        description = self.cmb_reason.currentText() if self.reason_id is not None else ""
        self.reason_text = " - ".join(part for part in (description, note) if part)
        self.accept()
