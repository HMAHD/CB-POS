import logging
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QInputDialog,
    QWidget,
)
from PyQt6.QtCore import Qt, QSize
from cbpos.core.services.email_service import EmailService
from cbpos.core.services.theme_service import ThemeService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.receipt_service import ReceiptService
from cbpos.core.services.receipt_builder import ReceiptBuilder
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.core.models import Sale
from cbpos.core.utils.formatters import format_currency
from cbpos.ui.resources.icons import Icons
from cbpos.ui.dialogs.receipt_preview_dialog import ReceiptPreviewDialog
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class ReceiptOptionsDialog(QDialog):
    def __init__(self, sale: Sale, parent=None):
        super().__init__(parent)
        self.sale = sale
        self.setWindowTitle(_t("receipt_options.title"))
        self.setFixedSize(440, 474)
        self.setObjectName("ReceiptOptionsDialog")
        self.init_ui()

    def init_ui(self) -> None:
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
        self.btn_close.setText(_t("receipt_options.btn_close"))

    def show_preview(self) -> None:
        """Show what will actually print, built from the real completed sale."""
        try:
            commands = ReceiptBuilder.build_receipt(self.sale)
            ReceiptPreviewDialog(commands, self).exec()
        except Exception as e:
            logger.error("Receipt preview failed: %s", e)
            QMessageBox.warning(
                self, _t("receipt_options.print_error_title"), _t("receipt_options.print_error_message", error=str(e))
            )

    def print_thermal(self) -> None:
        """Print receipt via thermal printer. Auto-closes on success, shows retry on failure."""
        try:
            worker = PrintWorker.instance()
            language = ConfigService.get("language") or "en"

            # PrintWorker.instance() is one shared, persistent object for
            # the app's lifetime, and the Retry button on _on_print_error
            # below calls print_thermal() again -- connecting without
            # guarding would add another duplicate connection on every
            # retry, so a later failure would show once per accumulated
            # connection instead of once. Disconnect any previous
            # connection first, and connect before add_job() so a job
            # that finishes fast can't emit before we're listening.
            try:
                worker.error_occurred.disconnect(self._on_print_error)
            except TypeError:
                pass  # not connected yet
            try:
                worker.job_completed.disconnect(self._on_print_finished)
            except TypeError:
                pass
            worker.error_occurred.connect(self._on_print_error)
            worker.job_completed.connect(self._on_print_finished)

            if language == "en":
                receipt_text = ReceiptService.build_receipt_text(self.sale)
                worker.add_job("print_receipt", receipt_text)
            else:
                receipt_image = ReceiptService.build_receipt_image(self.sale)
                worker.add_job("print_image", receipt_image)
        except Exception as e:
            logger.error("Receipt print failed: %s", e)
            QMessageBox.warning(
                self, _t("receipt_options.print_error_title"), _t("receipt_options.print_error_message", error=str(e))
            )

    def _on_print_finished(self) -> None:
        """Auto-close the dialog when the print job completes successfully."""
        self.accept()

    def _on_print_error(self, message: str) -> None:
        """Show print error with Retry/Skip options."""
        logger.error("Receipt print failed: %s", message)
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(_t("receipt_options.print_error_title"))
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText(_t("receipt_options.print_error_message", error=message))
        retry_btn = msg_box.addButton(_t("receipt_options.print_error_retry"), QMessageBox.ButtonRole.AcceptRole)
        msg_box.addButton(_t("receipt_options.print_error_skip"), QMessageBox.ButtonRole.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == retry_btn:
            self.print_thermal()
        else:
            self.accept()

    def email_receipt(self) -> None:
        default_email = ""
        try:
            if self.sale.customer and self.sale.customer.email:
                default_email = self.sale.customer.email
        except Exception:
            pass  # Sale may be detached; skip customer email pre-fill

        email, ok = QInputDialog.getText(
            self, _t("receipt_options.email_title"), _t("receipt_options.email_prompt"), text=default_email
        )

        if ok and email:
            self.worker = EmailService.send_receipt(email, self.sale.document_number)
            self.worker.finished.connect(self.on_email_finished)
            QMessageBox.information(self, _t("receipt_options.sending_title"), _t("receipt_options.sending_message"))

    def on_email_finished(self, success: bool, message: str) -> None:
        if not success:
            QMessageBox.warning(
                self,
                _t("receipt_options.email_failed_title"),
                _t("receipt_options.email_failed_message", error=message),
            )
