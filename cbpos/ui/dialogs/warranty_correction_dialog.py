"""Warranty Admin Correction Dialog (#825)."""

import logging
from datetime import date

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.warranty_dto import WarrantyDTO
from cbpos.core.services.warranty_service import WarrantyService
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class WarrantyCorrectionDialog(QDialog):
    """Modal dialog allowing authorized staff to correct serial numbers or dates on a warranty (#825)."""

    def __init__(self, warranty: WarrantyDTO, user_id: int | None = None, parent=None):
        super().__init__(parent)
        self.warranty = warranty
        self._user_id = user_id
        self.setObjectName("WarrantyCorrectionDialog")
        self.setWindowTitle(_t("warranty_lookup.correction_title"))
        install_wheel_guard(self)
        self.setMinimumWidth(480)
        self.init_ui()

    def init_ui(self) -> None:
        """Initialize form fields, labels, and action buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        # Read-only Warranty Code & Product
        lbl_code_val = QLabel(self.warranty.code)
        lbl_code_val.setStyleSheet("font-weight: bold;")
        form.addRow(_t("warranty_lookup.code_label") + ":", lbl_code_val)

        lbl_prod_val = QLabel(self.warranty.product_name)
        form.addRow(_t("warranty_lookup.product_label") + ":", lbl_prod_val)

        lbl_doc_val = QLabel(self.warranty.sale_document_number)
        form.addRow(_t("warranty_lookup.sale_label") + ":", lbl_doc_val)

        # Editable Serial
        self.txt_serial = QLineEdit(self.warranty.serial_number or "")
        self.txt_serial.setPlaceholderText(_t("warranty_lookup.serial_placeholder"))
        form.addRow(_t("warranty_lookup.col_serial") + ":", self.txt_serial)

        # Editable Start Date
        self.dt_start = QDateEdit()
        self.dt_start.setCalendarPopup(True)
        self.dt_start.setDisplayFormat("yyyy-MM-dd")
        if self.warranty.start_date:
            self.dt_start.setDate(
                QDate(self.warranty.start_date.year, self.warranty.start_date.month, self.warranty.start_date.day)
            )
        form.addRow(_t("warranty_lookup.start_date_label") + ":", self.dt_start)

        # Editable End Date
        self.dt_end = QDateEdit()
        self.dt_end.setCalendarPopup(True)
        self.dt_end.setDisplayFormat("yyyy-MM-dd")
        if self.warranty.end_date:
            self.dt_end.setDate(
                QDate(self.warranty.end_date.year, self.warranty.end_date.month, self.warranty.end_date.day)
            )
        form.addRow(_t("warranty_lookup.end_date_label") + ":", self.dt_end)

        # Mandatory Reason
        self.txt_reason = QTextEdit()
        self.txt_reason.setPlaceholderText(_t("warranty_lookup.reason_placeholder"))
        self.txt_reason.setMaximumHeight(80)
        self.txt_reason.textChanged.connect(self._validate_inputs)
        form.addRow(_t("warranty_lookup.reason_label") + " *:", self.txt_reason)

        layout.addLayout(form)

        # Footer
        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self._on_save,
            cancel_key="common.cancel",
            on_cancel=self.reject,
            primary_object_name="BtnSaveCorrection",
        )
        self.btn_save.setEnabled(False)
        layout.addLayout(footer_layout)

    def _validate_inputs(self) -> None:
        """Enable save button only when a non-empty reason is entered."""
        reason = self.txt_reason.toPlainText().strip()
        self.btn_save.setEnabled(bool(reason))

    def _on_save(self) -> None:
        """Validate inputs and invoke admin warranty correction service."""
        reason = self.txt_reason.toPlainText().strip()
        if not reason:
            QMessageBox.warning(self, _t("common.error"), _t("warranty_lookup.reason_required"))
            return

        q_start = self.dt_start.date()
        q_end = self.dt_end.date()
        start = date(q_start.year(), q_start.month(), q_start.day())
        end = date(q_end.year(), q_end.month(), q_end.day())

        if start > end:
            QMessageBox.warning(self, _t("common.error"), _t("warranty_lookup.error_invalid_dates"))
            return

        actor_id = self._user_id
        if actor_id is None:
            curr = AuthService.get_current_user()
            if curr:
                actor_id = curr.id

        if actor_id is None:
            QMessageBox.critical(self, _t("common.error"), _t("errors.permission_denied"))
            return

        serial = self.txt_serial.text().strip() or None

        try:
            WarrantyService.update_warranty_admin(
                warranty_id=self.warranty.id,
                user_id=actor_id,
                reason=reason,
                serial_number=serial,
                start_date=start,
                end_date=end,
            )
            self.accept()
        except PermissionError:
            QMessageBox.critical(self, _t("common.error"), _t("errors.permission_denied"))
        except ValueError as e:
            QMessageBox.warning(self, _t("common.error"), str(e))
        except Exception as e:
            logger.error("Admin warranty update failed: %s", e)
            QMessageBox.critical(self, _t("common.error"), str(e))
