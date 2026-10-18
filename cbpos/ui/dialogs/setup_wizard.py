from PyQt6.QtCore import Qt
from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.constants.hardware import PrinterType
from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class SetupWizard(QDialog):
    """First-run 3-step setup wizard for new CB-POS installations."""

    def __init__(self, parent=None):
        """Build the wizard, starting on step 1 (shop information)."""
        super().__init__(parent)
        self.setWindowTitle(_t("setup_wizard.title"))
        self.setMinimumSize(600, 500)
        self.resize(600, 500)
        self.setObjectName("SetupWizard")
        self.init_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def init_ui(self):
        """Build the three stacked pages (shop info, hardware, admin PIN) and navigation buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        # Title
        self.lbl_title = QLabel("")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setObjectName("WizardTitle")
        layout.addWidget(self.lbl_title)

        # Step indicator
        self.lbl_step = QLabel("")
        self.lbl_step.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_step.setProperty("class", "muted")
        layout.addWidget(self.lbl_step)

        # Stacked pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # Step 1: Shop Information
        self.page_shop = QWidget()
        shop_layout = QVBoxLayout(self.page_shop)
        self.shop_form = QFormLayout()
        self.shop_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.shop_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.shop_form.setVerticalSpacing(15)
        self.shop_form.setHorizontalSpacing(20)

        self.input_shop_name = QLineEdit()
        self.input_shop_name.setPlaceholderText(_t("setup_wizard.shop_name_placeholder"))

        self.input_address = QLineEdit()
        self.input_address.setPlaceholderText(_t("setup_wizard.address_placeholder"))

        self.input_phone = QLineEdit()
        self.input_phone.setPlaceholderText(_t("setup_wizard.phone_placeholder"))

        self.input_vat = QLineEdit()
        self.input_vat.setPlaceholderText(_t("setup_wizard.vat_placeholder"))

        self.shop_form.addRow(_t("setup_wizard.shop_name"), self.input_shop_name)
        self.shop_form.addRow(_t("setup_wizard.address"), self.input_address)
        self.shop_form.addRow(_t("setup_wizard.phone"), self.input_phone)
        self.shop_form.addRow(_t("setup_wizard.vat_number"), self.input_vat)

        shop_layout.addLayout(self.shop_form)
        shop_layout.addStretch()
        self.stack.addWidget(self.page_shop)

        # Step 2: Hardware
        self.page_hardware = QWidget()
        hw_layout = QVBoxLayout(self.page_hardware)
        self.hw_form = QFormLayout()
        self.hw_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.hw_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.hw_form.setVerticalSpacing(15)
        self.hw_form.setHorizontalSpacing(20)

        # Only real printer names carry data -- the "none detected" filler
        # used to be saved as if it were a printer.
        system_printers = QPrinterInfo.availablePrinterNames()

        # Same connection choice as Settings -> Hardware, saved to the same
        # printer_type / printer_path keys the print driver reads (#622).
        self.combo_printer_type = QComboBox()
        for p_type, key in zip(PrinterType.REAL, ("conn_win32", "conn_network", "conn_usb"), strict=True):
            self.combo_printer_type.addItem(_t(f"settings.hardware.{key}"), p_type)

        self.combo_receipt_printer = QComboBox()
        self.combo_receipt_printer.addItem(_t("setup_wizard.printer_none"), None)
        for p in system_printers:
            self.combo_receipt_printer.addItem(p, p)
        if not system_printers:
            self.combo_receipt_printer.addItem(_t("setup_wizard.none_detected"), None)

        self.input_printer_ip = QLineEdit()
        self.input_printer_ip.setPlaceholderText(_t("settings.hardware.printer_ip_placeholder"))
        self.input_usb_id = QLineEdit()
        self.input_usb_id.setPlaceholderText(_t("settings.hardware.usb_id_placeholder"))

        self.combo_a4_printer = QComboBox()
        self.combo_a4_printer.addItem(_t("setup_wizard.printer_none"), None)
        for p in system_printers or [_t("setup_wizard.none_detected")]:
            self.combo_a4_printer.addItem(p, p if system_printers else None)

        self.combo_paper_width = QComboBox()
        self.combo_paper_width.addItem(_t("setup_wizard.paper_80mm"), "80mm")
        self.combo_paper_width.addItem(_t("setup_wizard.paper_58mm"), "58mm")

        self.hw_form.addRow(_t("settings.hardware.connection_type"), self.combo_printer_type)
        self.hw_form.addRow(_t("setup_wizard.receipt_printer"), self.combo_receipt_printer)
        self.hw_form.addRow(_t("settings.hardware.printer_ip"), self.input_printer_ip)
        self.hw_form.addRow(_t("settings.hardware.usb_id"), self.input_usb_id)
        self.hw_form.addRow(_t("setup_wizard.a4_printer"), self.combo_a4_printer)
        self.combo_printer_type.currentIndexChanged.connect(self._update_connection_fields)
        self._update_connection_fields()
        self.hw_form.addRow(_t("setup_wizard.paper_width"), self.combo_paper_width)

        hw_layout.addLayout(self.hw_form)
        hw_layout.addStretch()
        self.stack.addWidget(self.page_hardware)

        # Step 3: Security
        self.page_security = QWidget()
        sec_layout = QVBoxLayout(self.page_security)
        self.sec_form = QFormLayout()
        self.sec_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.sec_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.sec_form.setVerticalSpacing(15)
        self.sec_form.setHorizontalSpacing(20)

        self.lbl_sec_info = QLabel("")
        self.lbl_sec_info.setProperty("class", "muted")
        self.lbl_sec_info.setWordWrap(True)
        sec_layout.addWidget(self.lbl_sec_info)

        self.input_pin = QLineEdit()
        self.input_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pin.setPlaceholderText(_t("setup_wizard.pin_placeholder"))
        self.input_pin.setMaxLength(6)

        self.input_pin_confirm = QLineEdit()
        self.input_pin_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pin_confirm.setPlaceholderText(_t("setup_wizard.pin_confirm_placeholder"))
        self.input_pin_confirm.setMaxLength(6)

        self.sec_form.addRow(_t("setup_wizard.admin_pin"), self.input_pin)
        self.sec_form.addRow(_t("setup_wizard.confirm_pin"), self.input_pin_confirm)

        sec_layout.addLayout(self.sec_form)
        sec_layout.addStretch()
        self.stack.addWidget(self.page_security)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(15)

        self.btn_back = QPushButton("")
        self.btn_back.setFixedSize(120, 40)
        self.btn_back.setObjectName("BtnCancel")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_back.setVisible(False)

        nav_layout.addWidget(self.btn_back)
        nav_layout.addStretch()

        self.btn_next = QPushButton("")
        self.btn_next.setFixedSize(120, 40)
        self.btn_next.setObjectName("BtnSave")
        self.btn_next.clicked.connect(self.go_next)

        self.btn_cancel = QPushButton("")
        self.btn_cancel.setFixedSize(120, 40)
        self.btn_cancel.setObjectName("BtnCancel")
        self.btn_cancel.clicked.connect(self.reject)

        nav_layout.addWidget(self.btn_cancel)
        nav_layout.addWidget(self.btn_next)

        layout.addLayout(nav_layout)

        # Apply translations
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("setup_wizard.title"))
        self.lbl_title.setText(_t("setup_wizard.welcome"))
        self.lbl_step.setText(_t("setup_wizard.step1"))
        self.lbl_sec_info.setText(_t("setup_wizard.security_info"))
        self.btn_back.setText(_t("setup_wizard.btn_back"))
        self.btn_next.setText(_t("setup_wizard.btn_next"))
        self.btn_cancel.setText(_t("setup_wizard.btn_cancel"))

    def go_next(self):
        """Validate the current step and advance, or run `finish_wizard()` on the last step."""
        current = self.stack.currentIndex()

        if current == 0:
            # Validate shop name
            if not self.input_shop_name.text().strip():
                QMessageBox.warning(self, _t("setup_wizard.required_title"), _t("setup_wizard.shop_name_required"))
                self.input_shop_name.setFocus()
                return
            self.stack.setCurrentIndex(1)
            self.lbl_step.setText(_t("setup_wizard.step2"))
            self.btn_back.setVisible(True)

        elif current == 1:
            error = self._printer_error()
            if error:
                QMessageBox.warning(self, _t("setup_wizard.invalid_title"), error)
                return
            self.stack.setCurrentIndex(2)
            self.lbl_step.setText(_t("setup_wizard.step3"))
            self.btn_next.setText(_t("setup_wizard.btn_finish"))

        elif current == 2:
            # Validate PIN
            pin = self.input_pin.text()
            pin_confirm = self.input_pin_confirm.text()

            if not pin or len(pin) < 4:
                QMessageBox.warning(self, _t("setup_wizard.required_title"), _t("setup_wizard.pin_min_length"))
                self.input_pin.setFocus()
                return

            if not pin.isdigit():
                QMessageBox.warning(self, _t("setup_wizard.invalid_title"), _t("setup_wizard.pin_digits_only"))
                self.input_pin.setFocus()
                return

            if pin != pin_confirm:
                QMessageBox.warning(self, _t("setup_wizard.mismatch_title"), _t("setup_wizard.pin_mismatch"))
                self.input_pin_confirm.setFocus()
                return

            self.finish_wizard()

    def _update_connection_fields(self) -> None:
        """Show only the field that belongs to the chosen connection type."""
        p_type = self.combo_printer_type.currentData()
        self.hw_form.setRowVisible(self.combo_receipt_printer, p_type == PrinterType.WIN32)
        self.hw_form.setRowVisible(self.input_printer_ip, p_type == PrinterType.NETWORK)
        self.hw_form.setRowVisible(self.input_usb_id, p_type == PrinterType.USB)

    def printer_target(self) -> tuple[str, str]:
        """The receipt printer chosen on the hardware step.

        Returns:
            (printer_type, printer_path), as Settings -> Hardware saves them;
            a Windows printer with nothing chosen is ("NONE", "").
        """
        p_type = self.combo_printer_type.currentData() or PrinterType.WIN32
        if p_type == PrinterType.NETWORK:
            return p_type, self.input_printer_ip.text().strip()
        if p_type == PrinterType.USB:
            return p_type, self.input_usb_id.text().strip()
        name = self.combo_receipt_printer.currentData() or ""
        return (PrinterType.WIN32, name) if name else (PrinterType.NONE, "")

    def _printer_error(self) -> str:
        """Translated problem with the hardware step's printer fields, or "" if they are fine."""
        from cbpos.infrastructure.hardware.escpos_driver import parse_usb_id

        p_type, p_path = self.printer_target()
        if p_type == PrinterType.NETWORK and not p_path:
            return _t("settings.hardware.ip_required")
        if p_type == PrinterType.USB and parse_usb_id(p_path) is None:
            return _t("settings.hardware.usb_id_invalid")
        return ""

    def go_back(self):
        """Return to the previous step, updating the step label and button text."""
        current = self.stack.currentIndex()
        if current > 0:
            self.stack.setCurrentIndex(current - 1)
            if current - 1 == 0:
                self.btn_back.setVisible(False)
                self.lbl_step.setText(_t("setup_wizard.step1"))
            elif current - 1 == 1:
                self.lbl_step.setText(_t("setup_wizard.step2"))
            self.btn_next.setText(_t("setup_wizard.btn_next"))

    def finish_wizard(self):
        """Save all wizard settings and update admin PIN."""
        from cbpos.core.services.config_service import ConfigService

        # Save config
        settings = {
            "shop_name": self.input_shop_name.text().strip(),
            "shop_address": self.input_address.text().strip(),
            "shop_phone": self.input_phone.text().strip(),
            "vat_number": self.input_vat.text().strip(),
            "paper_width": self.combo_paper_width.currentData(),
        }

        # Receipt printer: the same keys Settings -> Hardware writes
        p_type, p_path = self.printer_target()
        settings["printer_type"] = p_type
        settings["printer_path"] = p_path
        settings["receipt_printer_name"] = p_path if p_type == PrinterType.WIN32 else ""

        a4_printer = self.combo_a4_printer.currentData()
        if a4_printer is not None:
            settings["a4_printer_name"] = a4_printer

        ConfigService.update_all(settings)

        # Update admin PIN
        try:
            from cbpos.core.services.user_service import UserService

            UserService.update_admin_pin(self.input_pin.text())
        except Exception as e:
            import logging

            logging.getLogger(__name__).error("Failed to update admin PIN: %s", e)
            QMessageBox.warning(self, _t("common.warning"), _t("setup_wizard.pin_update_failed", error=str(e)))

        self.accept()
