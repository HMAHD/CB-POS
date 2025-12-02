from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QInputDialog,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.email_service import EmailService
from cbpos.core.models import Sale


class ReceiptOptionsDialog(QDialog):
    def __init__(self, sale: Sale, parent=None):
        super().__init__(parent)
        self.sale = sale
        self.setWindowTitle("Receipt Options")
        self.setFixedSize(500, 300)
        self.setStyleSheet("background-color: #001F3F; color: white;")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        lbl_title = QLabel("Transaction Completed!")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet("font-size: 24px; font-weight: bold; color: #39FF14;")
        layout.addWidget(lbl_title)

        lbl_info = QLabel(
            f"Order #{self.sale.document_number}\n"
            f"Total: Rs. {self.sale.total_amount:,.2f}"  # noqa: E231
        )
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setStyleSheet("font-size: 16px; color: #AAAAAA;")
        layout.addWidget(lbl_info)

        # Buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)

        # Print Thermal
        btn_print = QPushButton("Print Receipt (Thermal)")
        btn_print.setStyleSheet(self._get_btn_style("#00BCEB"))
        btn_print.clicked.connect(self.print_thermal)
        btn_layout.addWidget(btn_print)

        # Email
        btn_email = QPushButton("Email Receipt")
        btn_email.setStyleSheet(self._get_btn_style("#FF851B"))
        btn_email.clicked.connect(self.email_receipt)
        btn_layout.addWidget(btn_email)

        # Close
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(self._get_btn_style("#AAAAAA"))
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _get_btn_style(self, color):
        return (
            "QPushButton {{"
            "    background-color: {0};"  # noqa: E702
            "    color: black;"
            "    font-weight: bold;"
            "    font-size: 16px;"
            "    padding: 10px;"
            "    border-radius: 5px;"
            "}}"
            "QPushButton:hover {{"
            "    background-color: white;"
            "}}"
        ).format(color)

    def print_thermal(self):
        # In a real app, this would trigger the printer
        # For now, we just simulate
        QMessageBox.information(self, "Printing", "Sending to Thermal Printer...")

    def email_receipt(self):
        # Pre-fill email if customer exists
        default_email = ""
        if self.sale.customer and self.sale.customer.email:
            default_email = self.sale.customer.email

        email, ok = QInputDialog.getText(self, "Email Receipt", "Enter Email Address:", text=default_email)

        if ok and email:
            # Send in background
            self.worker = EmailService.send_receipt(email, self.sale.document_number)
            self.worker.finished.connect(self.on_email_finished)
            QMessageBox.information(self, "Sending", "Email is being sent in the background.")

    def on_email_finished(self, success, message):
        if not success:
            QMessageBox.warning(self, "Email Failed", f"Failed to send email: {message}")
