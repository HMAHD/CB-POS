"""Hardware settings page (printers, paper cut, cash drawer, weighing scale)."""

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QIntValidator
from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
)

from cbpos.core.constants.hardware import DEFAULT_DRAWER_PIN, DRAWER_PINS, PrinterType
from cbpos.core.services.hardware_test_service import HardwareTestResult
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.views.settings_pages.base import SettingsPage


class HardwarePage(SettingsPage):
    """Hardware + Paper Width."""

    def init_ui(self):
        """Build the Printers, Paper Cut & Drawer, and Weighing Scale tabs."""
        _, self.tabs = self._create_page_layout("", "")

        # --- Tab 1: Printers ---
        tab_printer, vbox_printer = self._build_vbox_tab()

        system_printers = QPrinterInfo.availablePrinterNames()
        available_printers = system_printers or [_t("settings.hardware.no_printers")]

        # Section: Printer Selection
        self._header_printer_sel = self._make_section_header("settings.hardware.section_printer_selection")
        vbox_printer.addWidget(self._header_printer_sel)

        sel_form = QFormLayout()
        self.configure_form_layout(sel_form)
        sel_form.setContentsMargins(0, 0, 0, 0)
        sel_form.setVerticalSpacing(10)
        self._sel_form = sel_form

        # How the receipt printer is reached (#622). Only the field for the
        # chosen connection is shown; Windows printer is the default because
        # it works with the vendor driver most shops already installed.
        self.combo_printer_type = QComboBox()
        for p_type in PrinterType.REAL:
            self.combo_printer_type.addItem("", p_type)
        self._lbl_printer_type = QLabel()
        sel_form.addRow(self._lbl_printer_type, self.combo_printer_type)

        self.combo_receipt_printer = QComboBox()
        self._fill_receipt_printer_combo(system_printers)
        self._lbl_receipt_printer = QLabel()
        sel_form.addRow(self._lbl_receipt_printer, self.combo_receipt_printer)

        self.input_printer_ip = QLineEdit()
        self._lbl_printer_ip = QLabel()
        sel_form.addRow(self._lbl_printer_ip, self.input_printer_ip)

        self.input_usb_id = QLineEdit()
        self._lbl_usb_id = QLabel()
        sel_form.addRow(self._lbl_usb_id, self.input_usb_id)
        self.lbl_usb_hint = QLabel()
        self.lbl_usb_hint.setProperty("class", "muted")
        self.lbl_usb_hint.setWordWrap(True)
        sel_form.addRow("", self.lbl_usb_hint)

        self.combo_printer_type.currentIndexChanged.connect(self._update_connection_fields)
        self._update_connection_fields()

        self.combo_a4_printer = QComboBox()
        self.combo_a4_printer.addItems(available_printers)
        self._lbl_a4_printer = QLabel()
        sel_form.addRow(self._lbl_a4_printer, self.combo_a4_printer)

        # Printer detection only ever ran once, here at construction time,
        # and this page is built once and kept alive for the rest of the
        # session -- a printer plugged in after launch needed a full app
        # restart to appear (#323).
        self.btn_refresh_printers = QPushButton()
        self.btn_refresh_printers.setProperty("class", "secondary")
        self.btn_refresh_printers.clicked.connect(self._refresh_printer_list)
        sel_form.addRow("", self.btn_refresh_printers)

        self.combo_paper_width = QComboBox()
        self.combo_paper_width.addItems(["80mm", "58mm"])
        self._lbl_paper_width = QLabel()
        sel_form.addRow(self._lbl_paper_width, self.combo_paper_width)
        vbox_printer.addLayout(sel_form)

        # Section: Print Behavior
        self._header_print_beh = self._make_section_header("settings.hardware.section_print_behavior")
        vbox_printer.addWidget(self._header_print_beh)

        beh_form = QFormLayout()
        self.configure_form_layout(beh_form)
        beh_form.setContentsMargins(0, 0, 0, 0)
        beh_form.setVerticalSpacing(10)

        self.chk_auto_print = QCheckBox()
        beh_form.addRow("", self.chk_auto_print)

        self.spin_copies = QSpinBox()
        self.spin_copies.setRange(1, 5)
        self.spin_copies.setFixedWidth(200)
        self._lbl_copies = QLabel()
        beh_form.addRow(self._lbl_copies, self.spin_copies)
        vbox_printer.addLayout(beh_form)

        # Test Buttons
        self._header_test_hw = self._make_section_header("settings.hardware.section_test_hardware")
        vbox_printer.addWidget(self._header_test_hw)
        test_row = QHBoxLayout()
        self.btn_test_print = QPushButton()
        self.btn_test_print.setProperty("class", "accent")
        self.btn_test_print.clicked.connect(self._test_print)
        test_row.addWidget(self.btn_test_print)

        self.btn_open_drawer = QPushButton()
        self.btn_open_drawer.clicked.connect(self._test_drawer)
        test_row.addWidget(self.btn_open_drawer)

        # Drawers are wired to kick pin 2 or 5 depending on the cable (#624).
        self._lbl_drawer_pin = QLabel()
        test_row.addWidget(self._lbl_drawer_pin)
        self.combo_drawer_pin = QComboBox()
        for pin in DRAWER_PINS:
            self.combo_drawer_pin.addItem(str(pin), pin)
        test_row.addWidget(self.combo_drawer_pin)

        # Test outcome, styled success/warning next to the buttons (#624).
        self.lbl_test_result = QLabel()
        self.lbl_test_result.setWordWrap(True)
        self.lbl_test_result.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        test_row.addWidget(self.lbl_test_result, 1)
        vbox_printer.addLayout(test_row)

        self.tabs.addTab(tab_printer, "")

        # --- Tab: Paper Cut & Drawer ---
        tab_cut, vbox_cut = self._build_vbox_tab()

        # Section: Paper Cut
        self._header_paper_cut = self._make_section_header("settings.hardware.section_paper_cut")
        vbox_cut.addWidget(self._header_paper_cut)

        cut_form = QFormLayout()
        self.configure_form_layout(cut_form)
        cut_form.setContentsMargins(0, 0, 0, 0)
        cut_form.setVerticalSpacing(10)

        self.chk_auto_cut = QCheckBox()
        cut_form.addRow("", self.chk_auto_cut)
        # Tear-bar advice lives in a hint, not the checkbox text: "Disable for..." next to a box that
        # enables auto-cut read as "tick to disable" (#575).
        self.lbl_auto_cut_hint = QLabel()
        self.lbl_auto_cut_hint.setProperty("class", "muted")
        self.lbl_auto_cut_hint.setWordWrap(True)
        cut_form.addRow("", self.lbl_auto_cut_hint)

        self.combo_cut_type = QComboBox()
        self._lbl_cut_type = QLabel()
        cut_form.addRow(self._lbl_cut_type, self.combo_cut_type)

        self.spin_feed_lines = QSpinBox()
        self.spin_feed_lines.setRange(1, 8)
        self._lbl_feed_lines = QLabel()
        cut_form.addRow(self._lbl_feed_lines, self.spin_feed_lines)
        vbox_cut.addLayout(cut_form)

        # Section: Cash Drawer
        self._header_cash_drawer = self._make_section_header("settings.hardware.section_cash_drawer")
        vbox_cut.addWidget(self._header_cash_drawer)

        drawer_form = QFormLayout()
        self.configure_form_layout(drawer_form)
        drawer_form.setContentsMargins(0, 0, 0, 0)
        drawer_form.setVerticalSpacing(10)

        self.chk_drawer_cash_only = QCheckBox()
        drawer_form.addRow("", self.chk_drawer_cash_only)
        vbox_cut.addLayout(drawer_form)

        self.tabs.addTab(tab_cut, "")

        # --- Tab: Scale ---
        tab_scale, vbox_scale = self._build_vbox_tab()

        self._header_scale = self._make_section_header("settings.hardware.section_weighing_scale")
        vbox_scale.addWidget(self._header_scale)

        scale_form = QFormLayout()
        self.configure_form_layout(scale_form)
        scale_form.setContentsMargins(0, 0, 0, 0)
        scale_form.setVerticalSpacing(10)

        self.input_scale_prefix = QLineEdit()
        self.input_scale_prefix.setValidator(QIntValidator(0, 99, self))
        self.input_scale_prefix.setMaxLength(2)
        self.input_scale_prefix.setFixedWidth(80)
        self._lbl_barcode_prefix = QLabel()
        scale_form.addRow(self._lbl_barcode_prefix, self.input_scale_prefix)

        self.spin_decimal_places = QSpinBox()
        self.spin_decimal_places.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_decimal_places.setRange(0, 4)
        self.spin_decimal_places.setFixedWidth(80)
        self._lbl_decimal_places = QLabel()
        scale_form.addRow(self._lbl_decimal_places, self.spin_decimal_places)
        vbox_scale.addLayout(scale_form)

        self.tabs.addTab(tab_scale, "")

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def retranslate_ui(self) -> None:
        """Update all widget text and tab labels from the translation system."""
        self._page_title.setText(_t("settings.hardware.title"))
        self.btn_reset_defaults.setText(_t("settings.btn_reset_defaults"))
        self._page_subtitle.setText(_t("settings.hardware.subtitle"))
        self._retranslate_section_headers()

        self.tabs.setTabText(0, _t("settings.hardware.tab_printers"))
        self.tabs.setTabText(1, _t("settings.hardware.tab_cut_drawer"))
        self.tabs.setTabText(2, _t("settings.hardware.tab_weighing_scale"))

        # Printers tab
        self._lbl_printer_type.setText(_t("settings.hardware.connection_type"))
        for i, key in enumerate(("conn_win32", "conn_network", "conn_usb")):
            self.combo_printer_type.setItemText(i, _t(f"settings.hardware.{key}"))
        self._lbl_receipt_printer.setText(_t("settings.hardware.receipt_printer"))
        self.combo_receipt_printer.setItemText(0, self._receipt_printer_placeholder())
        self._lbl_printer_ip.setText(_t("settings.hardware.printer_ip"))
        self.input_printer_ip.setPlaceholderText(_t("settings.hardware.printer_ip_placeholder"))
        self._lbl_usb_id.setText(_t("settings.hardware.usb_id"))
        self.input_usb_id.setPlaceholderText(_t("settings.hardware.usb_id_placeholder"))
        self.lbl_usb_hint.setText(_t("settings.hardware.usb_hint"))
        self._lbl_a4_printer.setText(_t("settings.hardware.a4_printer"))
        self.btn_refresh_printers.setText(_t("settings.hardware.btn_refresh_printers"))
        self._lbl_paper_width.setText(_t("settings.hardware.paper_width"))
        self.chk_auto_print.setText(_t("settings.hardware.chk_auto_print"))
        self.chk_auto_print.setToolTip(_t("settings.hardware.tooltip_auto_print"))
        self._lbl_copies.setText(_t("settings.hardware.copies"))
        self.btn_test_print.setText(_t("settings.hardware.btn_test_print"))
        self.btn_open_drawer.setText(_t("settings.hardware.btn_open_drawer"))
        self._lbl_drawer_pin.setText(_t("settings.hardware.drawer_pin"))
        self.combo_drawer_pin.setToolTip(_t("settings.hardware.tooltip_drawer_pin"))

        # Cut & Drawer tab
        self.chk_auto_cut.setText(_t("settings.hardware.chk_auto_cut"))
        self.chk_auto_cut.setToolTip(_t("settings.hardware.tooltip_auto_cut"))
        self.lbl_auto_cut_hint.setText(_t("settings.hardware.hint_auto_cut"))

        self._lbl_cut_type.setText(_t("settings.hardware.cut_type"))
        # Re-populate cut type combo preserving selection
        current_cut_data = self.combo_cut_type.currentData()
        self.combo_cut_type.clear()
        self.combo_cut_type.addItem(_t("settings.hardware.cut_partial"), "partial")
        self.combo_cut_type.addItem(_t("settings.hardware.cut_full"), "full")
        if current_cut_data:
            idx = self.combo_cut_type.findData(current_cut_data)
            if idx >= 0:
                self.combo_cut_type.setCurrentIndex(idx)
        self.combo_cut_type.setToolTip(_t("settings.hardware.tooltip_cut_type"))

        self._lbl_feed_lines.setText(_t("settings.hardware.feed_lines"))
        self.spin_feed_lines.setToolTip(_t("settings.hardware.tooltip_feed_lines"))
        self.chk_drawer_cash_only.setText(_t("settings.hardware.chk_drawer_cash_only"))
        self.chk_drawer_cash_only.setToolTip(_t("settings.hardware.tooltip_drawer_cash_only"))

        # Scale tab
        self._lbl_barcode_prefix.setText(_t("settings.hardware.barcode_prefix"))
        self._lbl_decimal_places.setText(_t("settings.hardware.decimal_places"))
        self.equalize_form_labels()

    def _receipt_printer_placeholder(self) -> str:
        """Text of the receipt printer combo's empty first item."""
        if self.combo_receipt_printer.count() > 1:
            return _t("settings.hardware.choose_printer")
        return _t("settings.hardware.no_printers")

    def _fill_receipt_printer_combo(self, printers: list[str]) -> None:
        """Fill the Windows receipt printer combo: an empty "choose" item, then each printer by name."""
        self.combo_receipt_printer.clear()
        self.combo_receipt_printer.addItem("", "")
        for name in printers:
            self.combo_receipt_printer.addItem(name, name)
        self.combo_receipt_printer.setItemText(0, self._receipt_printer_placeholder())

    def _select_receipt_printer(self, name: str) -> None:
        """Select *name* in the receipt printer combo, adding it if Windows doesn't list it right now.

        A saved printer that is switched off or unplugged must not be
        silently replaced by another one on the next save.
        """
        if not name:
            self.combo_receipt_printer.setCurrentIndex(0)
            return
        idx = self.combo_receipt_printer.findData(name)
        if idx < 0:
            self.combo_receipt_printer.addItem(name, name)
            idx = self.combo_receipt_printer.count() - 1
        self.combo_receipt_printer.setCurrentIndex(idx)

    def _update_connection_fields(self) -> None:
        """Show only the field that belongs to the chosen connection type."""
        p_type = self.combo_printer_type.currentData()
        form = self._sel_form
        form.setRowVisible(self.combo_receipt_printer, p_type == PrinterType.WIN32)
        form.setRowVisible(self.input_printer_ip, p_type == PrinterType.NETWORK)
        form.setRowVisible(self.input_usb_id, p_type == PrinterType.USB)
        form.setRowVisible(self.lbl_usb_hint, p_type == PrinterType.USB)

    def current_printer_target(self) -> tuple[str, str]:
        """The receipt printer as currently shown on screen (saved or not).

        Returns:
            (printer_type, printer_path): a `PrinterType` and the matching
            Windows printer name / IP address / VID:PID. A Windows printer
            with nothing chosen is ("NONE", "").
        """
        p_type = self.combo_printer_type.currentData() or PrinterType.WIN32
        if p_type == PrinterType.NETWORK:
            return p_type, self.input_printer_ip.text().strip()
        if p_type == PrinterType.USB:
            return p_type, self.input_usb_id.text().strip()
        name = self.combo_receipt_printer.currentData() or ""
        return (PrinterType.WIN32, name) if name else (PrinterType.NONE, "")

    def _refresh_printer_list(self) -> None:
        """Re-scan for connected printers without needing an app restart.

        Preserves each combo's current selection when it's still present
        in the rescanned list.
        """
        current_receipt = self.combo_receipt_printer.currentData() or ""
        current_a4 = self.combo_a4_printer.currentText()

        system_printers = QPrinterInfo.availablePrinterNames()
        available_printers = system_printers or [_t("settings.hardware.no_printers")]

        self._fill_receipt_printer_combo(system_printers)
        idx = self.combo_receipt_printer.findData(current_receipt) if current_receipt else -1
        if idx >= 0:
            self.combo_receipt_printer.setCurrentIndex(idx)

        self.combo_a4_printer.clear()
        self.combo_a4_printer.addItems(available_printers)
        idx = self.combo_a4_printer.findText(current_a4)
        if idx >= 0:
            self.combo_a4_printer.setCurrentIndex(idx)

    def load(self, settings: dict):
        """Populate printer selection, print behavior, paper cut, drawer and scale fields from the settings dict."""
        p_type = settings.get("printer_type", PrinterType.NONE)
        p_path = settings.get("printer_path", "") or ""
        if p_type not in PrinterType.REAL:
            p_type, p_path = PrinterType.WIN32, ""
        self.combo_printer_type.setCurrentIndex(max(0, self.combo_printer_type.findData(p_type)))
        self._select_receipt_printer(p_path if p_type == PrinterType.WIN32 else "")
        self.input_printer_ip.setText(p_path if p_type == PrinterType.NETWORK else "")
        self.input_usb_id.setText(p_path if p_type == PrinterType.USB else "")

        a4_printer = settings.get("a4_printer_name", "")
        if a4_printer:
            idx = self.combo_a4_printer.findText(a4_printer)
            if idx >= 0:
                self.combo_a4_printer.setCurrentIndex(idx)

        paper_width = settings.get("paper_width", "80mm")
        idx = self.combo_paper_width.findText(paper_width)
        if idx >= 0:
            self.combo_paper_width.setCurrentIndex(idx)

        self.chk_auto_print.setChecked(settings.get("auto_print_receipt", True))
        self.spin_copies.setValue(settings.get("receipt_copies", 1))
        self.input_scale_prefix.setText(settings.get("scale_barcode_prefix", "20"))
        self.spin_decimal_places.setValue(settings.get("scale_decimal_places", 3))

        # Cut & Drawer
        self.chk_auto_cut.setChecked(settings.get("auto_cut_paper", True))
        cut_type = settings.get("cut_type", "partial")
        idx = self.combo_cut_type.findData(cut_type)
        if idx >= 0:
            self.combo_cut_type.setCurrentIndex(idx)
        self.spin_feed_lines.setValue(settings.get("feed_lines_before_cut", 3))
        self.chk_drawer_cash_only.setChecked(settings.get("drawer_on_cash_only", True))
        pin_idx = self.combo_drawer_pin.findData(settings.get("drawer_pin", DEFAULT_DRAWER_PIN))
        self.combo_drawer_pin.setCurrentIndex(max(0, pin_idx))

    def save(self) -> dict:
        """Return printer, print behavior, paper cut, drawer and scale fields as a settings dict.

        Raises:
            ValueError: If the scale barcode prefix is not exactly 2 digits.
        """
        prefix = self.input_scale_prefix.text()
        if len(prefix) != 2 or not prefix.isdigit():
            raise ValueError(_t("settings.hardware.scale_prefix_error"))

        p_type, p_path = self.current_printer_target()
        return {
            "printer_type": p_type,
            "printer_path": p_path,
            # Kept in step with the Windows printer so the legacy-name
            # migration in ConfigService never re-fires on it.
            "receipt_printer_name": p_path if p_type == PrinterType.WIN32 else "",
            "a4_printer_name": self.combo_a4_printer.currentText(),
            "paper_width": self.combo_paper_width.currentText(),
            "auto_print_receipt": self.chk_auto_print.isChecked(),
            "receipt_copies": self.spin_copies.value(),
            "scale_barcode_prefix": prefix,
            "scale_decimal_places": self.spin_decimal_places.value(),
            "auto_cut_paper": self.chk_auto_cut.isChecked(),
            "cut_type": self.combo_cut_type.currentData() or "partial",
            "feed_lines_before_cut": self.spin_feed_lines.value(),
            "drawer_on_cash_only": self.chk_drawer_cash_only.isChecked(),
            "drawer_pin": self.combo_drawer_pin.currentData() or DEFAULT_DRAWER_PIN,
        }

    def validate(self) -> None:
        """Reject a Network printer with no IP address or a malformed USB VID:PID.

        Raises:
            ValueError: With a translated message for the bad field.
        """
        from cbpos.infrastructure.hardware.escpos_driver import parse_usb_id

        p_type, p_path = self.current_printer_target()
        if p_type == PrinterType.NETWORK and not p_path:
            raise ValueError(_t("settings.hardware.ip_required"))
        if p_type == PrinterType.USB and parse_usb_id(p_path) is None:
            raise ValueError(_t("settings.hardware.usb_id_invalid"))

    def _test_print(self) -> None:
        """Send a test slip to the printer shown on screen (saved or not), off the UI thread."""
        from cbpos.ui.workers import PrinterTestWorker

        p_type, p_path = self.current_printer_target()
        self._start_hardware_test(PrinterTestWorker(p_type, p_path), self.btn_test_print)

    def _test_drawer(self) -> None:
        """Kick the drawer through the printer shown on screen, on the chosen pin, off the UI thread."""
        from cbpos.ui.workers import DrawerTestWorker

        p_type, p_path = self.current_printer_target()
        pin = self.combo_drawer_pin.currentData() or DEFAULT_DRAWER_PIN
        self._start_hardware_test(DrawerTestWorker(p_type, p_path, pin), self.btn_open_drawer)

    def _start_hardware_test(self, worker: QThread, button: QPushButton) -> None:
        """Run a printer/drawer test worker, showing progress until its result arrives.

        Args:
            worker: A PrinterTestWorker or DrawerTestWorker (deletes itself when done).
            button: The button that started it; disabled while the test runs.
        """
        from cbpos.ui.hardware_test_feedback import set_hardware_test_status

        self.btn_test_print.setEnabled(False)
        self.btn_open_drawer.setEnabled(False)
        set_hardware_test_status(self.lbl_test_result, _t("settings.hardware.testing"), "muted")
        self._hardware_test_worker = worker
        worker.result.connect(self._on_hardware_test_done)
        worker.start()

    def _on_hardware_test_done(self, result: HardwareTestResult) -> None:
        """Show the translated, styled outcome and re-enable the test buttons."""
        from cbpos.ui.hardware_test_feedback import show_hardware_test_result

        self.btn_test_print.setEnabled(True)
        self.btn_open_drawer.setEnabled(True)
        show_hardware_test_result(self.lbl_test_result, result)


__all__ = ["HardwarePage"]
