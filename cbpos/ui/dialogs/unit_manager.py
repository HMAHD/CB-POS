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
    QFrame,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.unit_service import UnitService

logger = logging.getLogger(__name__)


class UnitManagerDialog(QDialog):
    """Dialog to view, add, edit, and delete units of measurement."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Units of Measurement")
        self.setMinimumSize(620, 460)
        self.setObjectName("UnitManagerDialog")
        self._editing_id = None
        self._init_ui()
        self._load_units()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Left: Table ──
        left = QVBoxLayout()
        left.setSpacing(8)

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

        # ── Right: Form + Actions ──
        right = QVBoxLayout()
        right.setSpacing(10)

        # Form
        form_group = QGroupBox("Unit Details")
        form_layout = QFormLayout(form_group)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setSpacing(10)

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
        self.spin_decimals.setToolTip("Decimal places for quantities (0 = whole numbers)")
        form_layout.addRow("Decimal Places:", self.spin_decimals)

        right.addWidget(form_group)

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_save = QPushButton("Save New")
        self.btn_save.setProperty("class", "primary")
        self.btn_save.clicked.connect(self._save_unit)
        btn_layout.addWidget(self.btn_save)

        self.btn_delete = QPushButton("Delete Selected")
        self.btn_delete.setProperty("class", "danger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_unit)
        btn_layout.addWidget(self.btn_delete)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        btn_layout.addWidget(sep)

        self.btn_clear = QPushButton("Clear / New")
        self.btn_clear.clicked.connect(self._clear_form)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()

        btn_close = QPushButton("Close")
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
            self._editing_id = None
            self.btn_delete.setEnabled(False)
            return

        self._editing_id = int(self.table.item(row, 0).text())
        self.txt_name.setText(self.table.item(row, 1).text())
        self.txt_abbr.setText(self.table.item(row, 2).text())
        self.spin_decimals.setValue(int(self.table.item(row, 3).text()))
        self.btn_save.setText("Update")
        self.btn_delete.setEnabled(True)

    def _validate(self) -> bool:
        """Validate form fields."""
        if not self.txt_name.text().strip():
            QMessageBox.warning(self, "Validation", "Name is required.")
            self.txt_name.setFocus()
            return False
        if not self.txt_abbr.text().strip():
            QMessageBox.warning(self, "Validation", "Abbreviation is required.")
            self.txt_abbr.setFocus()
            return False
        return True

    def _save_unit(self) -> None:
        """Add or update a unit based on current editing state."""
        if not self._validate():
            return

        name = self.txt_name.text().strip()
        abbr = self.txt_abbr.text().strip()
        decimals = self.spin_decimals.value()

        try:
            if self._editing_id:
                UnitService.update(
                    unit_id=self._editing_id,
                    name=name,
                    abbreviation=abbr,
                    decimal_places=decimals,
                )
                QMessageBox.information(self, "Success", f"Unit '{name}' updated.")
            else:
                UnitService.create(name=name, abbreviation=abbr, decimal_places=decimals)
                QMessageBox.information(self, "Success", f"Unit '{name}' added.")
            self._load_units()
            self._clear_form()
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def _delete_unit(self) -> None:
        """Delete (deactivate) selected unit."""
        row = self.table.currentRow()
        if row < 0:
            return

        unit_id = int(self.table.item(row, 0).text())
        unit_name = self.table.item(row, 1).text()

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete unit '{unit_name}'?\n\nThis will deactivate it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            UnitService.delete(unit_id)
            self._load_units()
            self._clear_form()
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))

    def _clear_form(self) -> None:
        """Clear form and reset to 'add new' mode."""
        self._editing_id = None
        self.txt_name.clear()
        self.txt_abbr.clear()
        self.spin_decimals.setValue(0)
        self.btn_save.setText("Save New")
        self.btn_delete.setEnabled(False)
        self.table.clearSelection()
        self.txt_name.setFocus()
