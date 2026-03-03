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
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.core.models import Sale
from cbpos.core.utils.formatters import format_currency
from cbpos.ui.resources.icons import Icons

logger = logging.getLogger(__name__)


class ReceiptOptionsDialog(QDialog):
    def __init__(self, sale: Sale, parent=None):
        super().__init__(parent)
        self.sale = sale
        self.setWindowTitle("Receipt Options")
        self.setFixedSize(440, 420)
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
        lbl_title = QLabel("Transaction Completed!")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setObjectName("ReceiptTitle")
        layout.addWidget(lbl_title)
        layout.addSpacing(16)

        # ── Order Info Card ────────────────────────────────────────
        info_card = QWidget()
        info_card.setObjectName("ReceiptInfoCard")
        info_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(4)

        lbl_order = QLabel(f"Order  #{self.sale.document_number}")
        lbl_order.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_order.setObjectName("ReceiptInfoOrder")
        info_layout.addWidget(lbl_order)

        lbl_total = QLabel(format_currency(self.sale.total_amount))
        lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_total.setObjectName("ReceiptInfoTotal")
        info_layout.addWidget(lbl_total)

        layout.addWidget(info_card)
        layout.addSpacing(24)

        # ── Action Buttons ─────────────────────────────────────────
        is_dark = ThemeService.current_theme.lower() == "dark"
        icon_clr = "#FFFFFF" if is_dark else "#212529"

        btn_print = QPushButton("  Print Receipt")
        btn_print.setObjectName("ReceiptBtnPrint")
        btn_print.setIcon(Icons.get("fa5s.print", icon_clr))
        btn_print.setIconSize(QSize(18, 18))
        btn_print.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_print.setFixedHeight(44)
        btn_print.clicked.connect(self.print_thermal)
        layout.addWidget(btn_print)
        layout.addSpacing(10)

        btn_email = QPushButton("  Email Receipt")
        btn_email.setObjectName("ReceiptBtnEmail")
        btn_email.setIcon(Icons.get("fa5s.envelope", icon_clr))
        btn_email.setIconSize(QSize(18, 18))
        btn_email.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_email.setFixedHeight(44)
        btn_email.clicked.connect(self.email_receipt)
        layout.addWidget(btn_email)

        layout.addStretch(1)

        # ── Close Button (centered, subtle) ────────────────────────
        close_row = QHBoxLayout()
        close_row.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setObjectName("ReceiptBtnClose")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setFixedSize(120, 36)
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)

        close_row.addStretch()
        layout.addLayout(close_row)

    def print_thermal(self) -> None:
        """Print receipt via thermal printer and close dialog."""
        try:
            worker = PrintWorker()
            language = ConfigService.get("language") or "en"

            if language == "en":
                receipt_text = ReceiptService.build_receipt_text(self.sale)
                worker.add_job("print_receipt", receipt_text)
            else:
                receipt_image = ReceiptService.build_receipt_image(self.sale)
                worker.add_job("print_image", receipt_image)

            self._print_worker = worker  # prevent GC
            self.accept()
        except Exception as e:
            logger.error("Receipt print failed: %s", e)
            QMessageBox.warning(self, "Print Error", f"Failed to print receipt: {e}")

    def email_receipt(self) -> None:
        default_email = ""
        try:
            if self.sale.customer and self.sale.customer.email:
                default_email = self.sale.customer.email
        except Exception:
            pass  # Sale may be detached; skip customer email pre-fill

        email, ok = QInputDialog.getText(self, "Email Receipt", "Enter Email Address:", text=default_email)

        if ok and email:
            self.worker = EmailService.send_receipt(email, self.sale.document_number)
            self.worker.finished.connect(self.on_email_finished)
            QMessageBox.information(self, "Sending", "Email is being sent in the background.")

    def on_email_finished(self, success: bool, message: str) -> None:
        if not success:
            QMessageBox.warning(self, "Email Failed", f"Failed to send email: {message}")
