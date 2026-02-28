"""
Admin Tools view — embedded in Management stack.

Provides a tabbed interface for admin diagnostic tools:
- Database: file info, SQLite version, table row counts
- Error Logs: view/filter/export application warning & error logs
- Hardware: test receipt printer, cash drawer, barcode scanner
"""

import logging

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGroupBox,
    QFormLayout,
)
from PyQt6.QtCore import Qt

from cbpos.core.services.maintenance_service import MaintenanceService

logger = logging.getLogger(__name__)


class AdminToolsView(QWidget):
    """Tabbed view for database info, error logs, and hardware testing."""

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()

    def showEvent(self, event) -> None:
        """Refresh data when the view becomes visible."""
        super().showEvent(event)
        self._load_db_info()

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
        self.tab_logs_placeholder = QWidget()
        self.tabs.addTab(self.tab_logs_placeholder, "Error Logs")
        self.tab_hardware_placeholder = QWidget()
        self.tabs.addTab(self.tab_hardware_placeholder, "Hardware")
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
                rows_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.table_counts.setItem(row, 1, rows_item)
        except Exception as e:
            logger.warning("Could not load full DB info: %s", e)
