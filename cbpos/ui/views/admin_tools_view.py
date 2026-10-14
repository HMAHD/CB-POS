"""
Admin Tools view — embedded in Settings view.

Provides a tabbed interface for admin diagnostic tools:
- Database: file info, SQLite version, table row counts
- Error Logs: view/filter/export application warning & error logs
- Hardware: test receipt printer, cash drawer, barcode scanner
"""

import logging
import time
from datetime import datetime

from PyQt6 import sip
from PyQt6.QtCore import QDate, Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.config import Config
from cbpos.core.constants.hardware import DRAWER_PINS, PrinterType
from cbpos.core.services.error_log_service import ErrorLogService
from cbpos.core.services.hardware_test_service import HardwareTestResult, HardwareTestService
from cbpos.core.services.maintenance_service import MaintenanceService
from cbpos.core.utils.formatters import format_number
from cbpos.i18n import _t, register_language_callback
from cbpos.infrastructure.hardware.escpos_driver import drawer_pin_setting
from cbpos.ui.constants import SPACING_SM
from cbpos.ui.hardware_test_feedback import set_hardware_test_status, show_hardware_test_result
from cbpos.ui.resources.status_colors import DANGER, WARNING, status_color
from cbpos.ui.widgets.pagination_widget import PaginationWidget
from cbpos.ui.widgets.table_helpers import NUMERIC_ALIGNMENT, align_numeric_headers

logger = logging.getLogger(__name__)

_PRINTER_TYPE_KEYS = {
    PrinterType.WIN32: "printer.type_win32",
    PrinterType.NETWORK: "printer.type_network",
    PrinterType.USB: "printer.type_usb",
}

# Log level -> palette meaning. Only the Level cell is coloured: tinting
# whole rows made the log hard to read in both themes (#559).
_LEVEL_MEANINGS = {
    "WARNING": WARNING,
    "ERROR": DANGER,
    "CRITICAL": DANGER,
}


class AdminToolsView(QWidget):
    """Tabbed view for database info, error logs, and hardware testing."""

    def __init__(self) -> None:
        """Build the Database, Error Logs, and Hardware tabs."""
        super().__init__()
        self._current_log_entries: list = []
        self._init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def showEvent(self, event) -> None:
        """Refresh data when the view becomes visible."""
        super().showEvent(event)
        self._load_db_info()
        self._load_logs()
        self._load_printer_info()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "dialog-title")
        layout.addWidget(self.lbl_title)

        # Version + update check row
        version_layout = QHBoxLayout()
        version_layout.setSpacing(12)

        self.lbl_subtitle = QLabel()
        self.lbl_subtitle.setProperty("class", "muted")
        version_layout.addWidget(self.lbl_subtitle, 1)

        version_lbl = QLabel(f"v{Config.VERSION}")
        version_lbl.setProperty("class", "muted")
        version_layout.addWidget(version_lbl)

        self.btn_update = QPushButton()
        self.btn_update.setMinimumWidth(160)
        self.btn_update.clicked.connect(self._check_for_updates)
        version_layout.addWidget(self.btn_update)

        layout.addLayout(version_layout)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._make_scrollable(self._build_database_tab()), "")
        self.tabs.addTab(self._build_logs_tab(), "")
        self.tabs.addTab(self._make_scrollable(self._build_hardware_tab()), "")
        layout.addWidget(self.tabs, 1)

    @staticmethod
    def _make_scrollable(widget: QWidget) -> QScrollArea:
        """Wrap tab contents in a borderless scroll area for 1366x768 screens (#587)."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _check_for_updates(self) -> None:
        """Manually trigger an update check (non-silent — shows result either way)."""
        from cbpos.ui.dialogs.update_dialog import check_for_updates_async

        self._update_thread = check_for_updates_async(parent=self, silent=False)

    # ── Database Tab ─────────────────────────────────────────────────────

    def _build_database_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(12)

        # Database File group
        self.grp_file = QGroupBox()
        file_layout = QFormLayout(self.grp_file)
        file_layout.setVerticalSpacing(10)
        file_layout.setHorizontalSpacing(20)

        self.lbl_db_path = QLabel("--")
        self.lbl_db_path.setWordWrap(True)
        # QFormLayout can't compute a wrapped QLabel's sizeHint correctly
        # at layout time (chicken/egg: the wrap depends on the width it
        # hasn't been given yet), so without an explicit minimum only the
        # first fragment of a real path ever painted.
        self.lbl_db_path.setMinimumWidth(400)
        self.lbl_db_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_db_path_label = QLabel()
        file_layout.addRow(self.lbl_db_path_label, self.lbl_db_path)

        self.lbl_db_size = QLabel("--")
        self.lbl_db_size.setProperty("class", "bold")
        self.lbl_db_size.setMinimumHeight(self.fontMetrics().height() + 8)
        self.lbl_db_size_label = QLabel()
        file_layout.addRow(self.lbl_db_size_label, self.lbl_db_size)

        self.lbl_db_modified = QLabel("--")
        self.lbl_db_modified.setMinimumHeight(self.fontMetrics().height() + 8)
        self.lbl_db_modified_label = QLabel()
        file_layout.addRow(self.lbl_db_modified_label, self.lbl_db_modified)

        self.lbl_sqlite_version = QLabel("--")
        self.lbl_sqlite_version.setMinimumHeight(self.fontMetrics().height() + 8)
        self.lbl_sqlite_version_label = QLabel()
        file_layout.addRow(self.lbl_sqlite_version_label, self.lbl_sqlite_version)

        layout.addWidget(self.grp_file)

        # Table Row Counts group
        self.grp_tables = QGroupBox()
        tables_layout = QVBoxLayout(self.grp_tables)

        self.table_counts = QTableWidget()
        self.table_counts.setColumnCount(2)
        self.table_counts.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_counts.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_counts.setAlternatingRowColors(True)
        self.table_counts.verticalHeader().setVisible(False)

        header = self.table_counts.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tables_layout.addWidget(self.table_counts)

        layout.addWidget(self.grp_tables, 1)

        # Refresh / Integrity Check buttons
        btn_layout = QHBoxLayout()
        self.btn_db_refresh = QPushButton()
        self.btn_db_refresh.setProperty("class", "accent")
        self.btn_db_refresh.setMinimumWidth(120)
        self.btn_db_refresh.clicked.connect(self._load_db_info)
        btn_layout.addWidget(self.btn_db_refresh)

        self.btn_check_integrity = QPushButton()
        self.btn_check_integrity.setProperty("class", "accent")
        self.btn_check_integrity.setMinimumWidth(180)
        self.btn_check_integrity.clicked.connect(self._check_integrity)
        btn_layout.addWidget(self.btn_check_integrity)

        self.lbl_integrity_status = QLabel("")
        self.lbl_integrity_status.setWordWrap(True)
        btn_layout.addWidget(self.lbl_integrity_status, 1)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return tab

    def _load_db_info(self) -> None:
        """Load database information into the Database tab."""
        try:
            info = MaintenanceService.get_full_database_info()
            self.lbl_db_path.setText(info.get("path", "--"))
            self.lbl_db_size.setText(info.get("size", "--"))
            self.lbl_db_modified.setText(info.get("last_modified", "--"))
            self.lbl_sqlite_version.setText(info.get("sqlite_version", "--"))

            tables = info.get("tables", [])
            self.table_counts.setRowCount(len(tables))
            for row, t in enumerate(tables):
                self.table_counts.setItem(row, 0, QTableWidgetItem(t["name"]))
                rows_item = QTableWidgetItem(format_number(t["rows"], 0))
                rows_item.setTextAlignment(NUMERIC_ALIGNMENT)
                self.table_counts.setItem(row, 1, rows_item)
        except Exception as e:
            logger.warning("Could not load full DB info: %s", e)

    def _check_integrity(self) -> None:
        """Run PRAGMA integrity_check in a background thread.

        Reuses the same IntegrityCheckWorker already wired up on the
        Data Safety screen's Maintenance section, rather than
        duplicating it -- only the call site here was missing (#344).
        """
        self.btn_check_integrity.setEnabled(False)
        self.btn_check_integrity.setText(_t("admin_tools.db_integrity_checking"))
        self.lbl_integrity_status.setText("")

        from cbpos.ui.workers import IntegrityCheckWorker

        self._integrity_worker = IntegrityCheckWorker()
        self._integrity_worker.result.connect(self._on_integrity_check_finished)
        self._integrity_worker.start()

    def _on_integrity_check_finished(self, ok: bool, message: str) -> None:
        self.btn_check_integrity.setEnabled(True)
        self.btn_check_integrity.setText(_t("admin_tools.db_btn_check_integrity"))
        if ok:
            self.lbl_integrity_status.setProperty("class", "credit")
            self.lbl_integrity_status.setText(_t("admin_tools.db_integrity_passed"))
        else:
            self.lbl_integrity_status.setProperty("class", "debit")
            self.lbl_integrity_status.setText(_t("admin_tools.db_integrity_failed", message=message))
        self.lbl_integrity_status.style().unpolish(self.lbl_integrity_status)
        self.lbl_integrity_status.style().polish(self.lbl_integrity_status)

    # ── Error Logs Tab ───────────────────────────────────────────────────

    def _build_logs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(12)

        # Filter bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        self.lbl_level = QLabel()
        self.lbl_level.setProperty("class", "muted")
        filter_layout.addWidget(self.lbl_level)

        self.combo_log_level = QComboBox()
        self.combo_log_level.addItem(_t("admin_tools.logs_level_all"), "All")
        for level in ("WARNING", "ERROR", "CRITICAL"):
            self.combo_log_level.addItem(level, level)
        self.combo_log_level.setMinimumWidth(120)
        filter_layout.addWidget(self.combo_log_level)

        self.lbl_from = QLabel()
        self.lbl_from.setProperty("class", "muted")
        filter_layout.addWidget(self.lbl_from)

        self.date_log_from = QDateEdit()
        self.date_log_from.setCalendarPopup(True)
        self.date_log_from.setDate(QDate.currentDate().addDays(-30))
        self.date_log_from.setMinimumWidth(130)
        filter_layout.addWidget(self.date_log_from)

        self.lbl_to = QLabel()
        self.lbl_to.setProperty("class", "muted")
        filter_layout.addWidget(self.lbl_to)

        self.date_log_to = QDateEdit()
        self.date_log_to.setCalendarPopup(True)
        self.date_log_to.setDate(QDate.currentDate())
        self.date_log_to.setMinimumWidth(130)
        filter_layout.addWidget(self.date_log_to)

        self.input_log_search = QLineEdit()
        self.input_log_search.setMinimumWidth(160)
        self.input_log_search.returnPressed.connect(self._load_logs)
        filter_layout.addWidget(self.input_log_search)

        self.btn_apply = QPushButton()
        self.btn_apply.setProperty("class", "accent")
        self.btn_apply.setMinimumWidth(90)
        self.btn_apply.clicked.connect(self._load_logs)
        filter_layout.addWidget(self.btn_apply)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Stats label (spaced so it never crowds or overlaps dividers)
        self.lbl_log_stats = QLabel("")
        self.lbl_log_stats.setProperty("class", "muted")
        layout.addSpacing(SPACING_SM)
        layout.addWidget(self.lbl_log_stats)
        layout.addSpacing(SPACING_SM)

        # Log table
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(4)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.setAlternatingRowColors(True)
        self.log_table.verticalHeader().setVisible(False)

        log_header = self.log_table.horizontalHeader()
        log_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        log_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        log_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        log_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.log_table.setColumnWidth(0, 160)
        self.log_table.setColumnWidth(1, 80)
        self.log_table.setColumnWidth(2, 200)

        layout.addWidget(self.log_table, 1)

        # Pagination
        self.log_pagination = PaginationWidget()
        self.log_pagination.page_changed.connect(self._on_log_page_changed)
        layout.addWidget(self.log_pagination)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_export = QPushButton()
        self.btn_export.clicked.connect(self._export_logs)
        btn_layout.addWidget(self.btn_export)

        self.btn_clear = QPushButton()
        self.btn_clear.setProperty("class", "danger")
        self.btn_clear.clicked.connect(self._clear_logs)
        btn_layout.addWidget(self.btn_clear)

        self.btn_refresh_logs = QPushButton()
        self.btn_refresh_logs.clicked.connect(self._load_logs)
        btn_layout.addWidget(self.btn_refresh_logs)

        btn_layout.addStretch()

        self.lbl_log_count = QLabel("")
        self.lbl_log_count.setProperty("class", "muted")
        btn_layout.addWidget(self.lbl_log_count)

        layout.addLayout(btn_layout)

        return tab

    def _load_logs(self) -> None:
        """Load and display log entries based on current filters."""
        try:
            level = self.combo_log_level.currentData()
            if level == "All":
                level = None

            date_from = datetime(
                self.date_log_from.date().year(),
                self.date_log_from.date().month(),
                self.date_log_from.date().day(),
            )
            date_to = datetime(
                self.date_log_to.date().year(),
                self.date_log_to.date().month(),
                self.date_log_to.date().day(),
            )
            search = self.input_log_search.text().strip() or None

            entries = ErrorLogService.read_logs(level=level, date_from=date_from, date_to=date_to, search=search)
            self._current_log_entries = entries

            self.log_pagination.set_total(len(entries))
            self._populate_log_page()

            self.lbl_log_count.setText(_t("admin_tools.logs_entries_count", count=len(entries)))

            # Update stats
            stats = ErrorLogService.get_log_stats()
            log_size = ErrorLogService.get_total_log_size()
            self.lbl_log_stats.setText(
                _t(
                    "admin_tools.logs_stats",
                    warnings=stats["WARNING"],
                    errors=stats["ERROR"],
                    critical=stats["CRITICAL"],
                    size=log_size,
                )
            )
        except Exception as e:
            logger.warning("Could not load logs: %s", e)

    def _populate_log_page(self) -> None:
        """Populate the log table with entries for the current page."""
        entries = self._current_log_entries
        page_entries = self.log_pagination.get_page_slice(entries)

        self.log_table.setRowCount(len(page_entries))
        for row, entry in enumerate(page_entries):
            time_item = QTableWidgetItem(entry["timestamp"])
            level_item = QTableWidgetItem(entry["level"])
            source_item = QTableWidgetItem(entry["source"])
            msg_item = QTableWidgetItem(entry["message"])

            meaning = _LEVEL_MEANINGS.get(entry["level"])
            if meaning:
                level_item.setForeground(status_color(meaning))

            if entry["level"] == "CRITICAL":
                font = level_item.font()
                font.setBold(True)
                level_item.setFont(font)

            self.log_table.setItem(row, 0, time_item)
            self.log_table.setItem(row, 1, level_item)
            self.log_table.setItem(row, 2, source_item)
            self.log_table.setItem(row, 3, msg_item)

    def _on_log_page_changed(self, _page: int) -> None:
        self._populate_log_page()

    def _export_logs(self) -> None:
        """Export displayed log entries to a text file."""
        entries = getattr(self, "_current_log_entries", [])
        if not entries:
            QMessageBox.information(
                self,
                _t("admin_tools.logs_no_entries"),
                _t("admin_tools.logs_no_entries_msg"),
            )
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, _t("admin_tools.logs_export_title"), "cbpos_logs.txt", "Text Files (*.txt)"
        )
        if not filepath:
            return

        try:
            ErrorLogService.export_logs(filepath, entries)
            QMessageBox.information(
                self,
                _t("admin_tools.logs_export_complete"),
                _t("admin_tools.logs_export_complete_msg", count=len(entries), path=filepath),
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                _t("admin_tools.logs_export_failed"),
                _t("admin_tools.logs_export_failed_msg", error=e),
            )

    def _clear_logs(self) -> None:
        """Clear all log files after confirmation."""
        reply = QMessageBox.question(
            self,
            _t("admin_tools.logs_clear_title"),
            _t("admin_tools.logs_clear_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            ErrorLogService.clear_logs()
            self._load_logs()
        except Exception as e:
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("admin_tools.logs_clear_error", error=e),
            )

    # ── Hardware Tab ─────────────────────────────────────────────────────

    def _build_hardware_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(12)

        # Printer Configuration group
        self.grp_config = QGroupBox()
        config_layout = QFormLayout(self.grp_config)
        config_layout.setVerticalSpacing(10)
        config_layout.setHorizontalSpacing(20)

        self.lbl_hw_type = QLabel("--")
        self.lbl_hw_type.setMinimumHeight(self.fontMetrics().height() + 8)
        self.lbl_hw_type_label = QLabel()
        config_layout.addRow(self.lbl_hw_type_label, self.lbl_hw_type)

        self.lbl_hw_path = QLabel("--")
        self.lbl_hw_path.setMinimumHeight(self.fontMetrics().height() + 8)
        self.lbl_hw_path_label = QLabel()
        config_layout.addRow(self.lbl_hw_path_label, self.lbl_hw_path)

        self.lbl_hw_receipt = QLabel("--")
        self.lbl_hw_receipt.setMinimumHeight(self.fontMetrics().height() + 8)
        self.lbl_hw_receipt_label = QLabel()
        config_layout.addRow(self.lbl_hw_receipt_label, self.lbl_hw_receipt)

        self.lbl_hw_a4 = QLabel("--")
        self.lbl_hw_a4.setMinimumHeight(self.fontMetrics().height() + 8)
        self.lbl_hw_a4_label = QLabel()
        config_layout.addRow(self.lbl_hw_a4_label, self.lbl_hw_a4)

        self.lbl_hw_paper = QLabel("--")
        self.lbl_hw_paper.setMinimumHeight(self.fontMetrics().height() + 8)
        self.lbl_hw_paper_label = QLabel()
        config_layout.addRow(self.lbl_hw_paper_label, self.lbl_hw_paper)

        layout.addWidget(self.grp_config)

        # This tab only ever displays and tests hardware -- printer
        # selection and paper width can only actually be changed on the
        # main Hardware settings page, which isn't obvious from this
        # screen alone (#343).
        self.lbl_hw_config_hint = QLabel()
        self.lbl_hw_config_hint.setProperty("class", "muted")
        self.lbl_hw_config_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hw_config_hint)

        # Receipt Printer Test group
        self.grp_printer = QGroupBox()
        printer_layout = QVBoxLayout(self.grp_printer)
        printer_layout.setSpacing(8)

        self.lbl_printer_desc = QLabel()
        self.lbl_printer_desc.setProperty("class", "muted")
        self.lbl_printer_desc.setWordWrap(True)
        printer_layout.addWidget(self.lbl_printer_desc)

        printer_btn_row = QHBoxLayout()
        self.btn_test_printer = QPushButton()
        self.btn_test_printer.setProperty("class", "accent")
        self.btn_test_printer.setMinimumWidth(180)
        self.btn_test_printer.clicked.connect(self._test_printer)
        printer_btn_row.addWidget(self.btn_test_printer)

        self.lbl_printer_status = QLabel("")
        self.lbl_printer_status.setWordWrap(True)
        self.lbl_printer_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        printer_btn_row.addWidget(self.lbl_printer_status, 1)

        printer_layout.addLayout(printer_btn_row)
        layout.addWidget(self.grp_printer)

        # Cash Drawer Test group
        self.grp_drawer = QGroupBox()
        drawer_layout = QVBoxLayout(self.grp_drawer)
        drawer_layout.setSpacing(8)

        self.lbl_drawer_desc = QLabel()
        self.lbl_drawer_desc.setProperty("class", "muted")
        self.lbl_drawer_desc.setWordWrap(True)
        drawer_layout.addWidget(self.lbl_drawer_desc)

        drawer_btn_row = QHBoxLayout()
        self.btn_test_drawer = QPushButton()
        self.btn_test_drawer.setProperty("class", "accent")
        self.btn_test_drawer.setMinimumWidth(180)
        self.btn_test_drawer.clicked.connect(self._test_drawer)
        drawer_btn_row.addWidget(self.btn_test_drawer)

        # Drawer kick pin for this test (2 or 5, #624); starts on the saved one.
        self.lbl_drawer_pin = QLabel()
        drawer_btn_row.addWidget(self.lbl_drawer_pin)
        self.combo_drawer_pin = QComboBox()
        for pin in DRAWER_PINS:
            self.combo_drawer_pin.addItem(str(pin), pin)
        drawer_btn_row.addWidget(self.combo_drawer_pin)

        self.lbl_drawer_status = QLabel("")
        self.lbl_drawer_status.setWordWrap(True)
        self.lbl_drawer_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        drawer_btn_row.addWidget(self.lbl_drawer_status, 1)

        drawer_layout.addLayout(drawer_btn_row)
        layout.addWidget(self.grp_drawer)

        # Barcode Scanner Test group
        self.grp_scanner = QGroupBox()
        scanner_layout = QVBoxLayout(self.grp_scanner)
        scanner_layout.setSpacing(8)

        self.lbl_scanner_desc = QLabel()
        self.lbl_scanner_desc.setProperty("class", "muted")
        self.lbl_scanner_desc.setWordWrap(True)
        scanner_layout.addWidget(self.lbl_scanner_desc)

        scanner_row = QHBoxLayout()
        self.input_scanner_test = QLineEdit()
        self.input_scanner_test.textChanged.connect(self._on_scanner_input)
        self.input_scanner_test.returnPressed.connect(self._on_scanner_enter)
        scanner_row.addWidget(self.input_scanner_test, 1)

        self.btn_clear_scan = QPushButton()
        self.btn_clear_scan.setMinimumWidth(90)
        self.btn_clear_scan.clicked.connect(self._clear_scanner)
        scanner_row.addWidget(self.btn_clear_scan)

        scanner_layout.addLayout(scanner_row)

        self.lbl_scanner_status = QLabel("")
        self.lbl_scanner_status.setWordWrap(True)
        scanner_layout.addWidget(self.lbl_scanner_status)

        self.lbl_scanner_detection = QLabel("")
        self.lbl_scanner_detection.setWordWrap(True)
        self.lbl_scanner_detection.setProperty("class", "muted")
        scanner_layout.addWidget(self.lbl_scanner_detection)

        # Timing tracking for scanner detection
        self._scanner_keystroke_times: list[float] = []

        layout.addWidget(self.grp_scanner)

        layout.addStretch()

        return tab

    def _load_printer_info(self) -> None:
        """Load printer configuration into the Hardware tab."""
        try:
            info = HardwareTestService.get_printer_info()
            type_key = _PRINTER_TYPE_KEYS.get(info.get("type", ""), "printer.type_none")
            self.lbl_hw_type.setText(_t(type_key))
            not_set = _t("printer.not_set")
            self.lbl_hw_path.setText(info.get("path") or not_set)
            self.lbl_hw_receipt.setText(info.get("receipt_printer") or not_set)
            self.lbl_hw_a4.setText(info.get("a4_printer") or not_set)
            self.lbl_hw_paper.setText(info.get("paper_width", "--"))
            pin_idx = self.combo_drawer_pin.findData(drawer_pin_setting())
            self.combo_drawer_pin.setCurrentIndex(max(0, pin_idx))
        except Exception as e:
            logger.warning("Could not load printer info: %s", e)

    def _test_printer(self) -> None:
        """Test the receipt printer in a background thread."""
        self.btn_test_printer.setEnabled(False)
        self.btn_test_printer.setText(_t("admin_tools.hw_printer_testing"))
        self.lbl_printer_status.setText("")

        from cbpos.ui.workers import PrinterTestWorker

        self._printer_worker = PrinterTestWorker()
        self._printer_worker.result.connect(self._on_printer_test_done)
        self._printer_worker.start()
        QTimer.singleShot(15000, self._on_printer_test_timeout)

    def _on_printer_test_timeout(self) -> None:
        """Handle printer test timeout after 15 seconds."""
        worker = getattr(self, "_printer_worker", None)
        # The worker deletes itself via QThread.finished -> deleteLater (#632).
        if worker is not None and not sip.isdeleted(worker) and worker.isRunning():
            self.btn_test_printer.setEnabled(True)
            self.btn_test_printer.setText(_t("admin_tools.hw_btn_test_printer"))
            set_hardware_test_status(self.lbl_printer_status, _t("admin_tools.hw_printer_timeout"), "warning-hint")

    def _on_printer_test_done(self, result: HardwareTestResult) -> None:
        """Show the translated, styled test print outcome and re-enable the button."""
        self.btn_test_printer.setEnabled(True)
        self.btn_test_printer.setText(_t("admin_tools.hw_btn_test_printer"))
        show_hardware_test_result(self.lbl_printer_status, result)

    def _test_drawer(self) -> None:
        """Test the cash drawer in a background thread."""
        self.btn_test_drawer.setEnabled(False)
        self.btn_test_drawer.setText(_t("admin_tools.hw_drawer_testing"))
        self.lbl_drawer_status.setText("")

        from cbpos.ui.workers import DrawerTestWorker

        self._drawer_worker = DrawerTestWorker(pin=self.combo_drawer_pin.currentData())
        self._drawer_worker.result.connect(self._on_drawer_test_done)
        self._drawer_worker.start()
        QTimer.singleShot(15000, self._on_drawer_test_timeout)

    def _on_drawer_test_timeout(self) -> None:
        """Handle drawer test timeout after 15 seconds."""
        worker = getattr(self, "_drawer_worker", None)
        # The worker deletes itself via QThread.finished -> deleteLater (#632).
        if worker is not None and not sip.isdeleted(worker) and worker.isRunning():
            self.btn_test_drawer.setEnabled(True)
            self.btn_test_drawer.setText(_t("admin_tools.hw_btn_open_drawer"))
            set_hardware_test_status(self.lbl_drawer_status, _t("admin_tools.hw_drawer_timeout"), "warning-hint")

    def _on_drawer_test_done(self, result: HardwareTestResult) -> None:
        """Show the translated, styled drawer test outcome and re-enable the button."""
        self.btn_test_drawer.setEnabled(True)
        self.btn_test_drawer.setText(_t("admin_tools.hw_btn_open_drawer"))
        show_hardware_test_result(self.lbl_drawer_status, result)

    def _on_scanner_input(self, text: str) -> None:
        """Handle barcode scanner input and record keystroke timing."""
        self._scanner_keystroke_times.append(time.monotonic())

        if text.strip():
            self.lbl_scanner_status.setText(_t("admin_tools.hw_scanner_barcode_received", barcode=text.strip()))
            self.lbl_scanner_status.setProperty("class", "credit")
        else:
            self.lbl_scanner_status.setText("")
            self.lbl_scanner_status.setProperty("class", "")
            self._scanner_keystroke_times.clear()
            self.lbl_scanner_detection.setText("")
        self.lbl_scanner_status.style().unpolish(self.lbl_scanner_status)
        self.lbl_scanner_status.style().polish(self.lbl_scanner_status)

    def _on_scanner_enter(self) -> None:
        """Evaluate keystroke timing when Enter is pressed to detect scanner vs manual input."""
        self._evaluate_scanner_timing()

    def _evaluate_scanner_timing(self) -> None:
        """Check average time between keystrokes to determine input source."""
        times = self._scanner_keystroke_times
        if len(times) < 2:
            self.lbl_scanner_detection.setText("")
            return

        intervals = [times[i] - times[i - 1] for i in range(1, len(times))]
        avg_ms = (sum(intervals) / len(intervals)) * 1000

        if avg_ms < 50:
            detection_text = _t("admin_tools.hw_scanner_detected", ms=f"{avg_ms:.0f}")
            self.lbl_scanner_detection.setProperty("class", "credit")
        else:
            detection_text = _t("admin_tools.hw_scanner_manual", ms=f"{avg_ms:.0f}")
            self.lbl_scanner_detection.setProperty("class", "debit")

        self.lbl_scanner_detection.setText(detection_text)
        self.lbl_scanner_detection.style().unpolish(self.lbl_scanner_detection)
        self.lbl_scanner_detection.style().polish(self.lbl_scanner_detection)

    def _clear_scanner(self) -> None:
        """Clear the scanner test input."""
        self.input_scanner_test.clear()
        self.lbl_scanner_status.setText("")
        self.lbl_scanner_detection.setText("")
        self._scanner_keystroke_times.clear()
        self.input_scanner_test.setFocus()

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.lbl_title.setText(_t("admin_tools.title"))
        self.lbl_subtitle.setText(_t("admin_tools.subtitle"))
        self.btn_update.setText(_t("admin_tools.btn_check_updates"))

        # Tab titles
        self.tabs.setTabText(0, _t("admin_tools.tab_database"))
        self.tabs.setTabText(1, _t("admin_tools.tab_error_logs"))
        self.tabs.setTabText(2, _t("admin_tools.tab_hardware"))

        # Database tab
        self.grp_file.setTitle(_t("admin_tools.db_group_file"))
        self.lbl_db_path_label.setText(_t("admin_tools.db_path"))
        self.lbl_db_size_label.setText(_t("admin_tools.db_size"))
        self.lbl_db_modified_label.setText(_t("admin_tools.db_last_modified"))
        self.lbl_sqlite_version_label.setText(_t("admin_tools.db_sqlite_version"))
        self.btn_check_integrity.setText(_t("admin_tools.db_btn_check_integrity"))
        self.grp_tables.setTitle(_t("admin_tools.db_group_table_counts"))
        self.table_counts.setHorizontalHeaderLabels(
            [_t("admin_tools.db_header_table"), _t("admin_tools.db_header_rows")]
        )
        align_numeric_headers(self.table_counts, (1,))  # Rows
        self.btn_db_refresh.setText(_t("admin_tools.db_btn_refresh"))

        # Logs tab
        self.lbl_level.setText(_t("admin_tools.logs_level"))
        self.combo_log_level.setItemText(0, _t("admin_tools.logs_level_all"))
        self.lbl_from.setText(_t("admin_tools.logs_from"))
        self.lbl_to.setText(_t("admin_tools.logs_to"))
        self.input_log_search.setPlaceholderText(_t("admin_tools.logs_search_placeholder"))
        self.btn_apply.setText(_t("admin_tools.logs_btn_apply"))
        self.log_table.setHorizontalHeaderLabels(
            [
                _t("admin_tools.logs_header_time"),
                _t("admin_tools.logs_header_level"),
                _t("admin_tools.logs_header_source"),
                _t("admin_tools.logs_header_message"),
            ]
        )
        self.btn_export.setText(_t("admin_tools.logs_btn_export"))
        self.btn_clear.setText(_t("admin_tools.logs_btn_clear"))
        self.btn_refresh_logs.setText(_t("admin_tools.logs_btn_refresh"))

        # Hardware tab
        self.grp_config.setTitle(_t("admin_tools.hw_group_printer"))
        self.lbl_hw_type_label.setText(_t("admin_tools.hw_printer_type"))
        self.lbl_hw_path_label.setText(_t("admin_tools.hw_printer_path"))
        self.lbl_hw_receipt_label.setText(_t("admin_tools.hw_receipt_printer"))
        self.lbl_hw_a4_label.setText(_t("admin_tools.hw_a4_printer"))
        self.lbl_hw_paper_label.setText(_t("admin_tools.hw_paper_width"))
        self.lbl_hw_config_hint.setText(_t("admin_tools.hw_config_hint"))
        self.grp_printer.setTitle(_t("admin_tools.hw_group_receipt_test"))
        self.lbl_printer_desc.setText(_t("admin_tools.hw_receipt_desc"))
        self.btn_test_printer.setText(_t("admin_tools.hw_btn_test_printer"))
        self.grp_drawer.setTitle(_t("admin_tools.hw_group_drawer_test"))
        self.lbl_drawer_desc.setText(_t("admin_tools.hw_drawer_desc"))
        self.btn_test_drawer.setText(_t("admin_tools.hw_btn_open_drawer"))
        self.lbl_drawer_pin.setText(_t("settings.hardware.drawer_pin"))
        self.combo_drawer_pin.setToolTip(_t("settings.hardware.tooltip_drawer_pin"))
        self.grp_scanner.setTitle(_t("admin_tools.hw_group_scanner_test"))
        self.lbl_scanner_desc.setText(_t("admin_tools.hw_scanner_desc"))
        self.input_scanner_test.setPlaceholderText(_t("admin_tools.hw_scanner_placeholder"))
        self.btn_clear_scan.setText(_t("common.clear"))
