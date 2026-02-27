from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QStackedWidget,
    QWidget,
    QFormLayout,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtPrintSupport import QPrinterInfo


class SetupWizard(QDialog):
    """First-run 3-step setup wizard for new CB-POS installations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CB POS - Setup Wizard")
        self.setFixedSize(600, 500)
        self.setObjectName("SetupWizard")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        # Title
        self.lbl_title = QLabel("Welcome to Ceylon Byte POS")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setObjectName("WizardTitle")
        layout.addWidget(self.lbl_title)

        # Step indicator
        self.lbl_step = QLabel("Step 1 of 3 - Shop Information")
        self.lbl_step.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_step.setProperty("class", "muted")
        layout.addWidget(self.lbl_step)

        # Stacked pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # Step 1: Shop Information
        self.page_shop = QWidget()
        shop_layout = QVBoxLayout(self.page_shop)
        shop_form = QFormLayout()
        shop_form.setVerticalSpacing(15)
        shop_form.setHorizontalSpacing(20)

        self.input_shop_name = QLineEdit()
        self.input_shop_name.setPlaceholderText("e.g., Lanka Super Mart")
        shop_form.addRow("Shop Name *:", self.input_shop_name)

        self.input_address = QLineEdit()
        self.input_address.setPlaceholderText("e.g., 123 Galle Road, Colombo 03")
        shop_form.addRow("Address:", self.input_address)

        self.input_phone = QLineEdit()
        self.input_phone.setPlaceholderText("e.g., +94771234567")
        shop_form.addRow("Phone:", self.input_phone)

        self.input_vat = QLineEdit()
        self.input_vat.setPlaceholderText("e.g., VAT123456")
        shop_form.addRow("VAT Number:", self.input_vat)

        shop_layout.addLayout(shop_form)
        shop_layout.addStretch()
        self.stack.addWidget(self.page_shop)

        # Step 2: Hardware
        self.page_hardware = QWidget()
        hw_layout = QVBoxLayout(self.page_hardware)
        hw_form = QFormLayout()
        hw_form.setVerticalSpacing(15)
        hw_form.setHorizontalSpacing(20)

        available_printers = QPrinterInfo.availablePrinterNames() or ["(None detected)"]

        self.combo_receipt_printer = QComboBox()
        self.combo_receipt_printer.addItem("(None)")
        self.combo_receipt_printer.addItems(available_printers)
        hw_form.addRow("Receipt Printer:", self.combo_receipt_printer)

        self.combo_a4_printer = QComboBox()
        self.combo_a4_printer.addItem("(None)")
        self.combo_a4_printer.addItems(available_printers)
        hw_form.addRow("A4 Printer:", self.combo_a4_printer)

        self.combo_paper_width = QComboBox()
        self.combo_paper_width.addItems(["80mm", "58mm"])
        hw_form.addRow("Paper Width:", self.combo_paper_width)

        hw_layout.addLayout(hw_form)
        hw_layout.addStretch()
        self.stack.addWidget(self.page_hardware)

        # Step 3: Security
        self.page_security = QWidget()
        sec_layout = QVBoxLayout(self.page_security)
        sec_form = QFormLayout()
        sec_form.setVerticalSpacing(15)
        sec_form.setHorizontalSpacing(20)

        lbl_info = QLabel("Set the admin PIN used to log into the POS system.")
        lbl_info.setProperty("class", "muted")
        lbl_info.setWordWrap(True)
        sec_layout.addWidget(lbl_info)

        self.input_pin = QLineEdit()
        self.input_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pin.setPlaceholderText("4-6 digit PIN")
        self.input_pin.setMaxLength(6)
        sec_form.addRow("Admin PIN *:", self.input_pin)

        self.input_pin_confirm = QLineEdit()
        self.input_pin_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pin_confirm.setPlaceholderText("Confirm PIN")
        self.input_pin_confirm.setMaxLength(6)
        sec_form.addRow("Confirm PIN *:", self.input_pin_confirm)

        sec_layout.addLayout(sec_form)
        sec_layout.addStretch()
        self.stack.addWidget(self.page_security)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(15)

        self.btn_back = QPushButton("Back")
        self.btn_back.setFixedSize(120, 40)
        self.btn_back.setObjectName("BtnCancel")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_back.setVisible(False)

        nav_layout.addWidget(self.btn_back)
        nav_layout.addStretch()

        self.btn_next = QPushButton("Next")
        self.btn_next.setFixedSize(120, 40)
        self.btn_next.setObjectName("BtnSave")
        self.btn_next.clicked.connect(self.go_next)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedSize(120, 40)
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.clicked.connect(self.reject)

        nav_layout.addWidget(self.btn_cancel)
        nav_layout.addWidget(self.btn_next)

        layout.addLayout(nav_layout)

    def go_next(self):
        current = self.stack.currentIndex()

        if current == 0:
            # Validate shop name
            if not self.input_shop_name.text().strip():
                QMessageBox.warning(self, "Required", "Shop name is required.")
                self.input_shop_name.setFocus()
                return
            self.stack.setCurrentIndex(1)
            self.lbl_step.setText("Step 2 of 3 - Hardware Setup")
            self.btn_back.setVisible(True)

        elif current == 1:
            self.stack.setCurrentIndex(2)
            self.lbl_step.setText("Step 3 of 3 - Security")
            self.btn_next.setText("Finish")

        elif current == 2:
            # Validate PIN
            pin = self.input_pin.text()
            pin_confirm = self.input_pin_confirm.text()

            if not pin or len(pin) < 4:
                QMessageBox.warning(self, "Required", "PIN must be at least 4 digits.")
                self.input_pin.setFocus()
                return

            if not pin.isdigit():
                QMessageBox.warning(self, "Invalid", "PIN must contain only digits.")
                self.input_pin.setFocus()
                return

            if pin != pin_confirm:
                QMessageBox.warning(self, "Mismatch", "PINs do not match.")
                self.input_pin_confirm.setFocus()
                return

            self.finish_wizard()

    def go_back(self):
        current = self.stack.currentIndex()
        if current > 0:
            self.stack.setCurrentIndex(current - 1)
            if current - 1 == 0:
                self.btn_back.setVisible(False)
                self.lbl_step.setText("Step 1 of 3 - Shop Information")
            elif current - 1 == 1:
                self.lbl_step.setText("Step 2 of 3 - Hardware Setup")
            self.btn_next.setText("Next")

    def finish_wizard(self):
        """Save all wizard settings and update admin PIN."""
        from cbpos.core.services.config_service import ConfigService

        # Save config
        settings = {
            "shop_name": self.input_shop_name.text().strip(),
            "shop_address": self.input_address.text().strip(),
            "shop_phone": self.input_phone.text().strip(),
            "vat_number": self.input_vat.text().strip(),
            "paper_width": self.combo_paper_width.currentText(),
        }

        # Printer settings (skip if "(None)" selected)
        receipt_printer = self.combo_receipt_printer.currentText()
        if receipt_printer != "(None)":
            settings["receipt_printer_name"] = receipt_printer

        a4_printer = self.combo_a4_printer.currentText()
        if a4_printer != "(None)":
            settings["a4_printer_name"] = a4_printer

        ConfigService.update_all(settings)

        # Update admin PIN
        try:
            from cbpos.core.services.user_service import UserService

            UserService.update_admin_pin(self.input_pin.text())
        except Exception as e:
            import logging

            logging.getLogger(__name__).error("Failed to update admin PIN: %s", e)
            QMessageBox.warning(self, "Warning", f"Admin PIN could not be updated: {e}")

        self.accept()
