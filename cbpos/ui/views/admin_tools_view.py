"""
Admin Tools view — embedded in Management stack.

Provides a tabbed interface for admin diagnostic tools:
- Database: file info, SQLite version, table row counts
- Error Logs: view/filter/export application warning & error logs
- Hardware: test receipt printer, cash drawer, barcode scanner
"""

import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGroupBox,
    QFormLayout,
    QMessageBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor

from cbpos.core.services.maintenance_service import MaintenanceService
from cbpos.core.services.error_log_service import ErrorLogService
from cbpos.core.services.hardware_test_service import HardwareTestService

logger = logging.getLogger(__name__)

# Color coding for log levels
_LEVEL_COLORS = {
    "WARNING": QColor("#FFD700"),
    "ERROR": QColor("#FF4136"),
    "CRITICAL": QColor("#FF4136"),
}


class AdminToolsView(QWidget):
    """Tabbed view for database info, error logs, and hardware testing."""

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()

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

        title = QLabel("Admin Tools")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        subtitle = QLabel("Diagnostic tools for troubleshooting and system administration.")
        subtitle.setProperty("class", "muted")
        layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_database_tab(), "Database")
        self.tabs.addTab(self._build_logs_tab(), "Error Logs")
        self.tabs.addTab(self._build_hardware_tab(), "Hardware")
        layout.addWidget(self.tabs, 1)

    # ── Database Tab ─────────────────────────────────────────────────────

    def _build_database_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(12)

        # Database File group
        grp_file = QGroupBox("Database File")
        file_layout = QFormLayout(grp_file)
        file_layout.setVerticalSpacing(10)
        file_layout.setHorizontalSpacing(20)

        self.lbl_db_path = QLabel("--")
        self.lbl_db_path.setWordWrap(True)
        self.lbl_db_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        file_layout.addRow("Path:", self.lbl_db_path)

        self.lbl_db_size = QLabel("--")
        self.lbl_db_size.setProperty("class", "bold")
        file_layout.addRow("Size:", self.lbl_db_size)

        self.lbl_db_modified = QLabel("--")
        file_layout.addRow("Last Modified:", self.lbl_db_modified)

        self.lbl_sqlite_version = QLabel("--")
        file_layout.addRow("SQLite Version:", self.lbl_sqlite_version)

        layout.addWidget(grp_file)

        # Table Row Counts group
        grp_tables = QGroupBox("Table Row Counts")
        tables_layout = QVBoxLayout(grp_tables)

        self.table_counts = QTableWidget()
        self.table_counts.setColumnCount(2)
        self.table_counts.setHorizontalHeaderLabels(["Table", "Rows"])
        self.table_counts.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_counts.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_counts.setAlternatingRowColors(True)
        self.table_counts.verticalHeader().setVisible(False)

        header = self.table_counts.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tables_layout.addWidget(self.table_counts)

        layout.addWidget(grp_tables, 1)

        # Refresh button
        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "accent")
        btn_refresh.setFixedWidth(120)
        btn_refresh.clicked.connect(self._load_db_info)
        btn_layout.addWidget(btn_refresh)
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
                rows_item = QTableWidgetItem(str(t["rows"]))
                rows_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table_counts.setItem(row, 1, rows_item)
        except Exception as e:
            logger.warning("Could not load full DB info: %s", e)

    # ── Error Logs Tab ───────────────────────────────────────────────────

    def _build_logs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(12)

        # Filter bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        lbl_level = QLabel("Level:")
        lbl_level.setProperty("class", "muted")
        filter_layout.addWidget(lbl_level)

        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["All", "WARNING", "ERROR", "CRITICAL"])
        self.combo_log_level.setFixedWidth(120)
        filter_layout.addWidget(self.combo_log_level)

        lbl_from = QLabel("From:")
        lbl_from.setProperty("class", "muted")
        filter_layout.addWidget(lbl_from)

        self.date_log_from = QDateEdit()
        self.date_log_from.setCalendarPopup(True)
        self.date_log_from.setDate(QDate.currentDate().addDays(-30))
        self.date_log_from.setFixedWidth(130)
        filter_layout.addWidget(self.date_log_from)

        lbl_to = QLabel("To:")
        lbl_to.setProperty("class", "muted")
        filter_layout.addWidget(lbl_to)

        self.date_log_to = QDateEdit()
        self.date_log_to.setCalendarPopup(True)
        self.date_log_to.setDate(QDate.currentDate())
        self.date_log_to.setFixedWidth(130)
        filter_layout.addWidget(self.date_log_to)

        self.input_log_search = QLineEdit()
        self.input_log_search.setPlaceholderText("Search logs...")
        self.input_log_search.setFixedWidth(200)
        filter_layout.addWidget(self.input_log_search)

        btn_apply = QPushButton("Apply")
        btn_apply.setProperty("class", "accent")
        btn_apply.setFixedWidth(80)
        btn_apply.clicked.connect(self._load_logs)
        filter_layout.addWidget(btn_apply)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Stats label
        self.lbl_log_stats = QLabel("")
        self.lbl_log_stats.setProperty("class", "muted")
        layout.addWidget(self.lbl_log_stats)

        # Log table
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(4)
        self.log_table.setHorizontalHeaderLabels(["Time", "Level", "Source", "Message"])
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

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_export = QPushButton("Export Logs")
        btn_export.clicked.connect(self._export_logs)
        btn_layout.addWidget(btn_export)

        btn_clear = QPushButton("Clear Logs")
        btn_clear.setProperty("class", "danger")
        btn_clear.clicked.connect(self._clear_logs)
        btn_layout.addWidget(btn_clear)

        btn_refresh_logs = QPushButton("Refresh")
        btn_refresh_logs.clicked.connect(self._load_logs)
        btn_layout.addWidget(btn_refresh_logs)

        btn_layout.addStretch()

        self.lbl_log_count = QLabel("")
        self.lbl_log_count.setProperty("class", "muted")
        btn_layout.addWidget(self.lbl_log_count)

        layout.addLayout(btn_layout)

        return tab

    def _load_logs(self) -> None:
        """Load and display log entries based on current filters."""
        try:
            level = self.combo_log_level.currentText()
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

            self.log_table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                time_item = QTableWidgetItem(entry["timestamp"])
                level_item = QTableWidgetItem(entry["level"])
                source_item = QTableWidgetItem(entry["source"])
                msg_item = QTableWidgetItem(entry["message"])

                # Color coding
                color = _LEVEL_COLORS.get(entry["level"])
                if color:
                    for item in (time_item, level_item, source_item, msg_item):
                        item.setForeground(color)

                if entry["level"] == "CRITICAL":
                    font = level_item.font()
                    font.setBold(True)
                    level_item.setFont(font)

                self.log_table.setItem(row, 0, time_item)
                self.log_table.setItem(row, 1, level_item)
                self.log_table.setItem(row, 2, source_item)
                self.log_table.setItem(row, 3, msg_item)

            self.lbl_log_count.setText(f"{len(entries)} entries")

            # Update stats
            stats = ErrorLogService.get_log_stats()
            log_size = ErrorLogService.get_total_log_size()
            self.lbl_log_stats.setText(
                f"Warnings: {stats['WARNING']}  |  "
                f"Errors: {stats['ERROR']}  |  "
                f"Critical: {stats['CRITICAL']}  |  "
                f"Log size: {log_size}"
            )
        except Exception as e:
            logger.warning("Could not load logs: %s", e)

    def _export_logs(self) -> None:
        """Export displayed log entries to a text file."""
        entries = getattr(self, "_current_log_entries", [])
        if not entries:
            QMessageBox.information(self, "No Entries", "No log entries to export.")
            return

        filepath, _ = QFileDialog.getSaveFileName(self, "Export Logs", "cbpos_logs.txt", "Text Files (*.txt)")
        if not filepath:
            return

        try:
            ErrorLogService.export_logs(filepath, entries)
            QMessageBox.information(self, "Export Complete", f"Exported {len(entries)} entries to:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export logs:\n{e}")

    def _clear_logs(self) -> None:
        """Clear all log files after confirmation."""
        reply = QMessageBox.question(
            self,
            "Clear Logs",
            "This will delete all log entries.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            ErrorLogService.clear_logs()
            self._load_logs()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not clear logs:\n{e}")

    # ── Hardware Tab ─────────────────────────────────────────────────────

    def _build_hardware_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(12)

        # Printer Configuration group
        grp_config = QGroupBox("Printer Configuration")
        config_layout = QFormLayout(grp_config)
        config_layout.setVerticalSpacing(10)
        config_layout.setHorizontalSpacing(20)

        self.lbl_hw_type = QLabel("--")
        config_layout.addRow("Printer Type:", self.lbl_hw_type)

        self.lbl_hw_path = QLabel("--")
        config_layout.addRow("Printer Path:", self.lbl_hw_path)

        self.lbl_hw_receipt = QLabel("--")
        config_layout.addRow("Receipt Printer:", self.lbl_hw_receipt)

        self.lbl_hw_a4 = QLabel("--")
        config_layout.addRow("A4 Printer:", self.lbl_hw_a4)

        self.lbl_hw_paper = QLabel("--")
        config_layout.addRow("Paper Width:", self.lbl_hw_paper)

        layout.addWidget(grp_config)

        # Receipt Printer Test group
        grp_printer = QGroupBox("Receipt Printer Test")
        printer_layout = QVBoxLayout(grp_printer)
        printer_layout.setSpacing(8)

        lbl_printer_desc = QLabel("Send a test page to the configured receipt printer to verify connectivity.")
        lbl_printer_desc.setProperty("class", "muted")
        lbl_printer_desc.setWordWrap(True)
        printer_layout.addWidget(lbl_printer_desc)

        printer_btn_row = QHBoxLayout()
        self.btn_test_printer = QPushButton("Print Test Page")
        self.btn_test_printer.setProperty("class", "accent")
        self.btn_test_printer.setFixedWidth(160)
        self.btn_test_printer.clicked.connect(self._test_printer)
        printer_btn_row.addWidget(self.btn_test_printer)

        self.lbl_printer_status = QLabel("")
        self.lbl_printer_status.setWordWrap(True)
        printer_btn_row.addWidget(self.lbl_printer_status, 1)

        printer_layout.addLayout(printer_btn_row)
        layout.addWidget(grp_printer)

        # Cash Drawer Test group
        grp_drawer = QGroupBox("Cash Drawer Test")
        drawer_layout = QVBoxLayout(grp_drawer)
        drawer_layout.setSpacing(8)

        lbl_drawer_desc = QLabel("Send a kick signal to open the cash drawer via the receipt printer.")
        lbl_drawer_desc.setProperty("class", "muted")
        lbl_drawer_desc.setWordWrap(True)
        drawer_layout.addWidget(lbl_drawer_desc)

        drawer_btn_row = QHBoxLayout()
        self.btn_test_drawer = QPushButton("Open Drawer")
        self.btn_test_drawer.setProperty("class", "accent")
        self.btn_test_drawer.setFixedWidth(160)
        self.btn_test_drawer.clicked.connect(self._test_drawer)
        drawer_btn_row.addWidget(self.btn_test_drawer)

        self.lbl_drawer_status = QLabel("")
        self.lbl_drawer_status.setWordWrap(True)
        drawer_btn_row.addWidget(self.lbl_drawer_status, 1)

        drawer_layout.addLayout(drawer_btn_row)
        layout.addWidget(grp_drawer)

        # Barcode Scanner Test group
        grp_scanner = QGroupBox("Barcode Scanner Test")
        scanner_layout = QVBoxLayout(grp_scanner)
        scanner_layout.setSpacing(8)

        lbl_scanner_desc = QLabel("Click the input field below and scan a barcode to test your scanner.")
        lbl_scanner_desc.setProperty("class", "muted")
        lbl_scanner_desc.setWordWrap(True)
        scanner_layout.addWidget(lbl_scanner_desc)

        scanner_row = QHBoxLayout()
        self.input_scanner_test = QLineEdit()
        self.input_scanner_test.setPlaceholderText("Scan a barcode here...")
        self.input_scanner_test.textChanged.connect(self._on_scanner_input)
        scanner_row.addWidget(self.input_scanner_test, 1)

        btn_clear_scan = QPushButton("Clear")
        btn_clear_scan.setFixedWidth(80)
        btn_clear_scan.clicked.connect(self._clear_scanner)
        scanner_row.addWidget(btn_clear_scan)

        scanner_layout.addLayout(scanner_row)

        self.lbl_scanner_status = QLabel("")
        self.lbl_scanner_status.setWordWrap(True)
        scanner_layout.addWidget(self.lbl_scanner_status)

        layout.addWidget(grp_scanner)

        layout.addStretch()

        return tab

    def _load_printer_info(self) -> None:
        """Load printer configuration into the Hardware tab."""
        try:
            info = HardwareTestService.get_printer_info()
            self.lbl_hw_type.setText(info.get("type", "--"))
            self.lbl_hw_path.setText(info.get("path", "--"))
            self.lbl_hw_receipt.setText(info.get("receipt_printer", "--"))
            self.lbl_hw_a4.setText(info.get("a4_printer", "--"))
            self.lbl_hw_paper.setText(info.get("paper_width", "--"))
        except Exception as e:
            logger.warning("Could not load printer info: %s", e)

    def _test_printer(self) -> None:
        """Test the receipt printer in a background thread."""
        self.btn_test_printer.setEnabled(False)
        self.btn_test_printer.setText("Testing...")
        self.lbl_printer_status.setText("")

        from cbpos.ui.workers import PrinterTestWorker

        self._printer_worker = PrinterTestWorker()
        self._printer_worker.finished.connect(self._on_printer_test_done)
        self._printer_worker.start()

    def _on_printer_test_done(self, success: bool, message: str) -> None:
        self.btn_test_printer.setEnabled(True)
        self.btn_test_printer.setText("Print Test Page")
        self.lbl_printer_status.setText(message)
        self.lbl_printer_status.setProperty("class", "credit" if success else "debit")
        self.lbl_printer_status.style().unpolish(self.lbl_printer_status)
        self.lbl_printer_status.style().polish(self.lbl_printer_status)

    def _test_drawer(self) -> None:
        """Test the cash drawer in a background thread."""
        self.btn_test_drawer.setEnabled(False)
        self.btn_test_drawer.setText("Testing...")
        self.lbl_drawer_status.setText("")

        from cbpos.ui.workers import DrawerTestWorker

        self._drawer_worker = DrawerTestWorker()
        self._drawer_worker.finished.connect(self._on_drawer_test_done)
        self._drawer_worker.start()

    def _on_drawer_test_done(self, success: bool, message: str) -> None:
        self.btn_test_drawer.setEnabled(True)
        self.btn_test_drawer.setText("Open Drawer")
        self.lbl_drawer_status.setText(message)
        self.lbl_drawer_status.setProperty("class", "credit" if success else "debit")
        self.lbl_drawer_status.style().unpolish(self.lbl_drawer_status)
        self.lbl_drawer_status.style().polish(self.lbl_drawer_status)

    def _on_scanner_input(self, text: str) -> None:
        """Handle barcode scanner input."""
        if text.strip():
            self.lbl_scanner_status.setText(f"Barcode received: {text.strip()}")
            self.lbl_scanner_status.setProperty("class", "credit")
        else:
            self.lbl_scanner_status.setText("")
            self.lbl_scanner_status.setProperty("class", "")
        self.lbl_scanner_status.style().unpolish(self.lbl_scanner_status)
        self.lbl_scanner_status.style().polish(self.lbl_scanner_status)

    def _clear_scanner(self) -> None:
        """Clear the scanner test input."""
        self.input_scanner_test.clear()
        self.lbl_scanner_status.setText("")
        self.input_scanner_test.setFocus()
