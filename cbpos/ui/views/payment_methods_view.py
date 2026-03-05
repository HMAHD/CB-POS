"""
Payment Methods management view for Settings.
Full CRUD for payment methods with table display.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QDialog,
    QFormLayout,
    QLineEdit,
    QCheckBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from cbpos.core.services.payment_service import PaymentService

logger = logging.getLogger(__name__)


class PaymentMethodDialog(QDialog):
    """Dialog to add or edit a payment method."""

    def __init__(self, method=None, parent=None):
        super().__init__(parent)
        self.method = method
        self.setWindowTitle("Edit Payment Method" if method else "Add Payment Method")
        self.setMinimumWidth(400)
        self.setObjectName("PaymentMethodDialog")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("e.g. Cash, Card, PayHere")
        self.txt_name.setMaxLength(50)
        form.addRow("Name:", self.txt_name)

        self.txt_shortcut = QLineEdit()
        self.txt_shortcut.setPlaceholderText("e.g. F12 (optional)")
        self.txt_shortcut.setMaxLength(10)
        form.addRow("Shortcut Key:", self.txt_shortcut)

        self.chk_cash = QCheckBox("This is a cash-type method")
        form.addRow("Is Cash:", self.chk_cash)

        self.chk_drawer = QCheckBox("Open cash drawer on payment")
        form.addRow("Open Drawer:", self.chk_drawer)

        self.chk_active = QCheckBox("Method is active and available")
        self.chk_active.setChecked(True)
        form.addRow("Active:", self.chk_active)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("DialogCancelButton")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("DialogSaveButton")
        self.btn_save.setProperty("class", "primary")
        self.btn_save.clicked.connect(self._save)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

        # Load existing values
        if self.method:
            self.txt_name.setText(self.method.name)
            self.txt_shortcut.setText(self.method.shortcut or "")
            self.chk_cash.setChecked(self.method.is_cash)
            self.chk_drawer.setChecked(self.method.open_drawer)
            self.chk_active.setChecked(self.method.is_active)

    def _save(self) -> None:
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Payment method name is required.")
            self.txt_name.setFocus()
            return

        self.result_data = {
            "name": name,
            "shortcut": self.txt_shortcut.text().strip() or None,
            "is_cash": self.chk_cash.isChecked(),
            "open_drawer": self.chk_drawer.isChecked(),
            "is_active": self.chk_active.isChecked(),
        }
        self.accept()


class PaymentMethodsView(QWidget):
    """Payment Methods management — table with add/edit/toggle actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PaymentMethodsView")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        title = QLabel("Payment Methods")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        subtitle = QLabel("Manage payment methods available at checkout.")
        subtitle.setProperty("class", "muted")
        layout.addWidget(subtitle)

        # Action bar
        action_bar = QHBoxLayout()
        action_bar.addStretch()

        self.btn_add = QPushButton("Add Method")
        self.btn_add.setObjectName("PaymentMethodAddBtn")
        self.btn_add.setProperty("class", "primary")
        self.btn_add.clicked.connect(self._add_method)
        action_bar.addWidget(self.btn_add)

        layout.addLayout(action_bar)

        # Table
        self.table = QTableWidget()
        self.table.setObjectName("PaymentMethodsTable")
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Name", "Shortcut", "Cash", "Drawer", "Active", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        # Hint
        hint = QLabel("Cash method cannot be deleted. Deactivate methods to hide from checkout.")
        hint.setProperty("class", "muted")
        layout.addWidget(hint)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_methods()

    def _load_methods(self) -> None:
        """Reload all payment methods into the table."""
        methods = PaymentService.get_all_methods()
        self.table.setRowCount(len(methods))

        for row, method in enumerate(methods):
            self.table.setItem(row, 0, QTableWidgetItem(method.name))
            self.table.setItem(row, 1, QTableWidgetItem(method.shortcut or ""))

            cash_item = QTableWidgetItem("Yes" if method.is_cash else "")
            cash_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, cash_item)

            drawer_item = QTableWidgetItem("Yes" if method.open_drawer else "")
            drawer_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, drawer_item)

            active_item = QTableWidgetItem("Active" if method.is_active else "Inactive")
            active_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, active_item)

            # Action buttons
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(4)

            btn_edit = QPushButton("Edit")
            btn_edit.setObjectName("PaymentMethodEditBtn")
            btn_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_edit.clicked.connect(lambda _, m=method: self._edit_method(m))
            action_layout.addWidget(btn_edit)

            # Prevent deleting Cash method
            if not method.is_cash:
                btn_delete = QPushButton("Delete")
                btn_delete.setObjectName("PaymentMethodDeleteBtn")
                btn_delete.setProperty("class", "danger")
                btn_delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn_delete.clicked.connect(lambda _, m=method: self._delete_method(m))
                action_layout.addWidget(btn_delete)

            self.table.setCellWidget(row, 5, action_widget)

    def _add_method(self) -> None:
        dialog = PaymentMethodDialog(parent=self)
        if dialog.exec():
            data = dialog.result_data
            try:
                PaymentService.create_method(
                    name=data["name"],
                    is_cash=data["is_cash"],
                    open_drawer=data["open_drawer"],
                    shortcut=data["shortcut"],
                )
                self._load_methods()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create payment method: {e}")

    def _edit_method(self, method) -> None:
        dialog = PaymentMethodDialog(method=method, parent=self)
        if dialog.exec():
            data = dialog.result_data
            try:
                PaymentService.update_method(
                    method_id=method.id,
                    name=data["name"],
                    is_cash=data["is_cash"],
                    open_drawer=data["open_drawer"],
                    shortcut=data["shortcut"],
                    is_active=data["is_active"],
                )
                self._load_methods()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update payment method: {e}")

    def _delete_method(self, method) -> None:
        if method.is_cash:
            QMessageBox.warning(self, "Cannot Delete", "Cash payment method cannot be deleted.")
            return

        reply = QMessageBox.question(
            self,
            "Delete Payment Method",
            f'Are you sure you want to delete "{method.name}"?\n\n'
            "Tip: You can deactivate it instead to keep history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                PaymentService.delete_method(method.id)
                self._load_methods()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete payment method: {e}")
