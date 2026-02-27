"""
Dialog for managing units of measurement (CRUD).
"""

import logging
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QMessageBox,
    QFormLayout,
    QGroupBox,
)
from cbpos.core.services.unit_service import UnitService

logger = logging.getLogger(__name__)


class UnitManagerDialog(QDialog):
    """Dialog to view, add, edit, and delete units of measurement."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Units of Measurement")
        self.setMinimumSize(600, 450)
        self.setObjectName("UnitManagerDialog")
        self.selected_unit = None
        self._init_ui()
        self._load_units()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(15)

        # Left: table
        left = QVBoxLayout()

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Abbr.", "Decimals"])
        self.table.setColumnHidden(0, True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self.table)

        layout.addLayout(left, 2)

        # Right: form
        right = QVBoxLayout()

        form_group = QGroupBox("Unit Details")
        form_layout = QFormLayout(form_group)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g., Kilogram")
        form_layout.addRow("Name:", self.txt_name)

        self.txt_abbr = QLineEdit()
        self.txt_abbr.setPlaceholderText("e.g., kg")
        self.txt_abbr.setMaxLength(10)
        form_layout.addRow("Abbreviation:", self.txt_abbr)

        self.spin_decimals = QSpinBox()
        self.spin_decimals.setMinimum(0)
        self.spin_decimals.setMaximum(3)
        self.spin_decimals.setToolTip("Number of decimal places for quantities (0 = whole numbers only)")
        form_layout.addRow("Decimal Places:", self.spin_decimals)

        right.addWidget(form_group)

        # Buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        btn_add = QPushButton("Add New")
        btn_add.setStyleSheet("background-color: #39FF14; color: black; font-weight: bold; padding: 8px;")
        btn_add.clicked.connect(self._add_unit)
        btn_layout.addWidget(btn_add)

        btn_update = QPushButton("Update Selected")
        btn_update.setStyleSheet("background-color: #00BCEB; color: black; font-weight: bold; padding: 8px;")
        btn_update.clicked.connect(self._update_unit)
        btn_layout.addWidget(btn_update)

        btn_delete = QPushButton("Delete Selected")
        btn_delete.setStyleSheet("background-color: #FF4136; color: white; font-weight: bold; padding: 8px;")
        btn_delete.clicked.connect(self._delete_unit)
        btn_layout.addWidget(btn_delete)

        btn_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("padding: 8px;")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        right.addLayout(btn_layout)

        layout.addLayout(right, 1)

    def _load_units(self) -> None:
        """Load all units into the table."""
        units = UnitService.get_all(active_only=False)
        self.table.setRowCount(0)
        for unit in units:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(unit.id)))
            self.table.setItem(row, 1, QTableWidgetItem(unit.name))
            self.table.setItem(row, 2, QTableWidgetItem(unit.abbreviation))
            self.table.setItem(row, 3, QTableWidgetItem(str(unit.decimal_places)))

            if not unit.is_active:
                for col in range(4):
                    item = self.table.item(row, col)
                    if item:
                        item.setForeground(self.table.palette().color(self.table.palette().ColorRole.Mid))

    def _on_selection_changed(self) -> None:
        """Populate form when a unit is selected."""
        row = self.table.currentRow()
        if row < 0:
            return
        self.txt_name.setText(self.table.item(row, 1).text())
        self.txt_abbr.setText(self.table.item(row, 2).text())
        self.spin_decimals.setValue(int(self.table.item(row, 3).text()))

    def _validate(self) -> bool:
        """Validate form fields."""
        if not self.txt_name.text().strip():
            QMessageBox.warning(self, "Validation", "Name is required.")
            return False
        if not self.txt_abbr.text().strip():
            QMessageBox.warning(self, "Validation", "Abbreviation is required.")
            return False
        return True

    def _add_unit(self) -> None:
        """Add a new unit."""
        if not self._validate():
            return
        try:
            UnitService.create(
                name=self.txt_name.text().strip(),
                abbreviation=self.txt_abbr.text().strip(),
                decimal_places=self.spin_decimals.value(),
            )
            self._load_units()
            self._clear_form()
            QMessageBox.information(self, "Success", "Unit added.")
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def _update_unit(self) -> None:
        """Update selected unit."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Select a unit to update.")
            return
        if not self._validate():
            return

        unit_id = int(self.table.item(row, 0).text())
        try:
            UnitService.update(
                unit_id=unit_id,
                name=self.txt_name.text().strip(),
                abbreviation=self.txt_abbr.text().strip(),
                decimal_places=self.spin_decimals.value(),
            )
            self._load_units()
            QMessageBox.information(self, "Success", "Unit updated.")
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def _delete_unit(self) -> None:
        """Delete (deactivate) selected unit."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Select a unit to delete.")
            return

        unit_id = int(self.table.item(row, 0).text())
        unit_name = self.table.item(row, 1).text()

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete unit '{unit_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            UnitService.delete(unit_id)
            self._load_units()
            self._clear_form()
            QMessageBox.information(self, "Deleted", f"Unit '{unit_name}' deactivated.")
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def _clear_form(self) -> None:
        """Clear the form fields."""
        self.txt_name.clear()
        self.txt_abbr.clear()
        self.spin_decimals.setValue(0)
