import logging

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.models import Sale
from cbpos.core.services.email_service import EmailService
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.printer_service import PrinterService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.core.services.theme_service import ThemeService
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.formatters import format_currency
from cbpos.core.utils.validators import is_valid_email
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.receipt_preview_dialog import ReceiptPreviewDialog
from cbpos.ui.resources.icons import Icons

logger = logging.getLogger(__name__)


class ReceiptOptionsDialog(QDialog):
    """Post-checkout dialog offering to preview, print, or email the receipt for a completed sale."""

    def __init__(self, sale: Sale, parent=None):
        """Build the dialog for the given completed `sale`."""
        super().__init__(parent)
        self.sale = sale
        self._print_job_id: str | None = None
        PrintWorker.instance().job_result.connect(self._on_print_job_result)
        self.setWindowTitle(_t("receipt_options.title"))
        self.setMinimumSize(440, 528)
        self.resize(440, 528)
        self.setObjectName("ReceiptOptionsDialog")
        self.init_ui()

    def init_ui(self) -> None:
        """Build the success icon, order info card, and preview/print/email/close buttons."""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(32, 28, 32, 24)

        # ── Success Icon ───────────────────────────────────────────
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setObjectName("ReceiptSuccessIcon")
        icon_label.setPixmap(Icons.get("fa5s.check-circle", "#39FF14").pixmap(48, 48))
        layout.addWidget(icon_label)
        layout.addSpacing(12)

        # ── Title ──────────────────────────────────────────────────
        self.lbl_title = QLabel("")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setObjectName("ReceiptTitle")
        layout.addWidget(self.lbl_title)
        layout.addSpacing(16)

        # ── Order Info Card ────────────────────────────────────────
        info_card = QWidget()
        info_card.setObjectName("ReceiptInfoCard")
        info_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(4)

        self.lbl_order = QLabel("")
        self.lbl_order.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_order.setObjectName("ReceiptInfoOrder")
        info_layout.addWidget(self.lbl_order)

        lbl_total = QLabel(format_currency(self.sale.total_amount))
        lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_total.setObjectName("ReceiptInfoTotal")
        info_layout.addWidget(lbl_total)

        layout.addWidget(info_card)
        layout.addSpacing(24)

        # ── Action Buttons ─────────────────────────────────────────
        is_dark = ThemeService.current_theme.lower() == "dark"
        icon_clr = "#FFFFFF" if is_dark else "#212529"

        self.btn_preview = QPushButton("")
        self.btn_preview.setObjectName("ReceiptBtnPreview")
        self.btn_preview.setIcon(Icons.get("fa5s.eye", icon_clr))
        self.btn_preview.setIconSize(QSize(18, 18))
        self.btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview.setFixedHeight(44)
        self.btn_preview.clicked.connect(self.show_preview)
        layout.addWidget(self.btn_preview)
        layout.addSpacing(10)

        self.btn_print = QPushButton("")
        self.btn_print.setObjectName("ReceiptBtnPrint")
        self.btn_print.setIcon(Icons.get("fa5s.print", icon_clr))
        self.btn_print.setIconSize(QSize(18, 18))
        self.btn_print.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_print.setFixedHeight(44)
        self.btn_print.clicked.connect(self.print_thermal)
        layout.addWidget(self.btn_print)
        layout.addSpacing(10)

        self.btn_email = QPushButton("")
        self.btn_email.setObjectName("ReceiptBtnEmail")
        self.btn_email.setIcon(Icons.get("fa5s.envelope", icon_clr))
        self.btn_email.setIconSize(QSize(18, 18))
        self.btn_email.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_email.setFixedHeight(44)
        self.btn_email.clicked.connect(self.email_receipt)
        layout.addWidget(self.btn_email)
        layout.addSpacing(10)

        self.btn_save_pdf = QPushButton("")
        self.btn_save_pdf.setObjectName("ReceiptBtnSavePdf")
        self.btn_save_pdf.setIcon(Icons.get("fa5s.file-pdf", icon_clr))
        self.btn_save_pdf.setIconSize(QSize(18, 18))
        self.btn_save_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_pdf.setFixedHeight(44)
        self.btn_save_pdf.clicked.connect(self.save_as_pdf)
        layout.addWidget(self.btn_save_pdf)

        layout.addStretch(1)

        # ── Close Button (centered, subtle) ────────────────────────
        close_row = QHBoxLayout()
        close_row.addStretch()

        self.btn_close = QPushButton("")
        self.btn_close.setObjectName("ReceiptBtnClose")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setFixedSize(120, 36)
        self.btn_close.clicked.connect(self.accept)
        close_row.addWidget(self.btn_close)

        close_row.addStretch()
        layout.addLayout(close_row)

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("receipt_options.title"))
        self.lbl_title.setText(_t("receipt_options.completed"))
        self.lbl_order.setText(_t("receipt_options.order_number", number=self.sale.document_number))
        self.btn_preview.setText("  " + _t("receipt_options.btn_preview"))
        self.btn_print.setText("  " + _t("receipt_options.btn_print"))
        self.btn_email.setText("  " + _t("receipt_options.btn_email"))
        self.btn_save_pdf.setText("  " + _t("receipt_options.btn_save_pdf"))
        self.btn_close.setText(_t("receipt_options.btn_close"))

        configured = EmailService.is_configured()
        self.btn_email.setEnabled(configured)
        if not configured:
            self.btn_email.setToolTip(_t("receipt.email_not_configured"))
        else:
            self.btn_email.setToolTip("")

    def show_preview(self) -> None:
        """Show what will actually print, built from the real completed sale."""
        try:
            commands = ReceiptBuilder.build_receipt(self.sale)
            ReceiptPreviewDialog(commands, self).exec()
        except Exception as e:
            logger.error("Receipt preview failed: %s", e)
            QMessageBox.warning(
                self,
                _t("receipt_options.print_error_title"),
                _t("receipt_options.print_error_message", error=translate_error(str(e))),
            )

    def print_thermal(self) -> None:
        """Print receipt via thermal printer. Auto-closes on success, shows retry on failure."""
        try:
            self.btn_print.setEnabled(False)
            # Same ReceiptBuilder commands the Preview shows, with the
            # configured number of copies, as one job.
            self._print_job_id = PrinterService.print_receipt(self.sale)
        except Exception as e:
            self.btn_print.setEnabled(True)
            logger.error("Receipt print failed: %s", e)
            QMessageBox.warning(
                self,
                _t("receipt_options.print_error_title"),
                _t("receipt_options.print_error_message", error=translate_error(str(e))),
            )

    def _on_print_job_result(self, job_id: str, ok: bool, message: str) -> None:
        """Handle print job completion for receipt options."""
        if self._print_job_id is None or job_id != self._print_job_id:
            return
        self._print_job_id = None
        if ok:
            self._on_print_finished()
        else:
            self._on_print_error(message)

    def _on_print_finished(self) -> None:
        """Auto-close the dialog when the print job completes successfully."""
        self.btn_print.setEnabled(True)
        self.accept()

    def _on_print_error(self, message: str) -> None:
        """Show print error with Retry/Skip options."""
        self.btn_print.setEnabled(True)
        logger.error("Receipt print failed: %s", message)
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(_t("receipt_options.print_error_title"))
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText(_t("receipt_options.print_error_message", error=translate_error(message)))
        retry_btn = msg_box.addButton(_t("receipt_options.print_error_retry"), QMessageBox.ButtonRole.AcceptRole)
        msg_box.addButton(_t("receipt_options.print_error_skip"), QMessageBox.ButtonRole.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == retry_btn:
            self.print_thermal()
        else:
            self.accept()

    def email_receipt(self) -> None:
        """Prompt for an email address (pre-filled from the customer, if any) and send the receipt."""
        if not EmailService.is_configured():
            return

        default_email = ""
        try:
            if self.sale.customer and self.sale.customer.email:
                default_email = self.sale.customer.email
        except Exception as e:
            logger.debug("Sale may be detached; skip customer email pre-fill: %s", e)

        email, ok = QInputDialog.getText(
            self, _t("receipt_options.email_title"), _t("receipt_options.email_prompt"), text=default_email
        )

        if not ok:
            return

        email = email.strip()
        if not is_valid_email(email):
            QMessageBox.warning(self, _t("common.error"), _t("customer_editor.invalid_email"))
            return

        self._last_email = email
        self.btn_email.setEnabled(False)
        self.worker = EmailService.send_receipt(self.sale, email)
        self.worker.finished.connect(self.on_email_finished)

    def on_email_finished(self, success: bool, message: str) -> None:
        """Show status message when the background email send finishes."""
        self.btn_email.setEnabled(EmailService.is_configured())
        if success:
            email = getattr(self, "_last_email", "")
            QMessageBox.information(
                self,
                _t("receipt_options.title"),
                _t("receipt.email_sent", email=email),
            )
        else:
            QMessageBox.warning(
                self,
                _t("receipt_options.email_failed_title"),
                _t("receipt.email_failed", reason=translate_error(message)),
            )

    def save_as_pdf(self) -> None:
        """Prompt for a save location and write a PDF copy of the receipt (#482)."""
        default_name = f"{self.sale.document_number}.pdf"
        filepath, _ = QFileDialog.getSaveFileName(
            self, _t("receipt_options.save_pdf_title"), default_name, _t("receipt_options.pdf_filter")
        )
        if not filepath:
            return

        try:
            InvoiceService.generate_pdf(self.sale, filepath)
            QMessageBox.information(
                self, _t("receipt_options.pdf_saved_title"), _t("receipt_options.pdf_saved_message", path=filepath)
            )
        except Exception as e:
            logger.error("Receipt PDF save failed: %s", e)
            QMessageBox.warning(
                self,
                _t("receipt_options.pdf_error_title"),
                _t("receipt_options.pdf_error_message", error=translate_error(str(e))),
            )
