"""
Payment Methods management view for Settings.
Full CRUD with inline toggle for active/inactive state.
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

# Row height must accommodate compact buttons comfortably
_ROW_HEIGHT = 44


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
        }
        self.accept()


class PaymentMethodsView(QWidget):
    """Payment Methods management — table with edit, toggle, delete actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PaymentMethodsView")
        self._methods = []
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

        self.btn_add = QPushButton("  Add Method  ")
        self.btn_add.setObjectName("PaymentMethodAddBtn")
        self.btn_add.setProperty("class", "primary")
        self.btn_add.clicked.connect(self._add_method)
        action_bar.addWidget(self.btn_add)

        layout.addLayout(action_bar)

        # Table — 6 columns: Name, Shortcut, Cash, Drawer, Status, Actions
        self.table = QTableWidget()
        self.table.setObjectName("PaymentMethodsTable")
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Name", "Shortcut", "Cash", "Drawer", "Status", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        # Fixed width for actions column to fit 3 buttons
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 260)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        # Hint
        hint = QLabel("Deactivate methods to hide from checkout. Cash method cannot be deleted.")
        hint.setProperty("class", "muted")
        layout.addWidget(hint)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_methods()

    def _make_action_btn(self, text: str, object_name: str, css_class: str = "") -> QPushButton:
        """Create a compact action button for table cells."""
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if css_class:
            btn.setProperty("class", css_class)
        return btn

    def _load_methods(self) -> None:
        """Reload all payment methods into the table."""
        self._methods = PaymentService.get_all_methods()
        self.table.setRowCount(len(self._methods))

        for row, method in enumerate(self._methods):
            self.table.setRowHeight(row, _ROW_HEIGHT)

            # Name
            name_item = QTableWidgetItem(method.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            # Shortcut
            shortcut_item = QTableWidgetItem(method.shortcut or "—")
            shortcut_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, shortcut_item)

            # Cash
            cash_item = QTableWidgetItem("Yes" if method.is_cash else "—")
            cash_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, cash_item)

            # Drawer
            drawer_item = QTableWidgetItem("Yes" if method.open_drawer else "—")
            drawer_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, drawer_item)

            # Status — styled text
            status_item = QTableWidgetItem("Active" if method.is_active else "Inactive")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, status_item)

            # Action buttons — Edit | Toggle | Delete
            action_widget = QWidget()
            action_widget.setObjectName("PaymentMethodActions")
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 4, 4, 4)
            action_layout.setSpacing(6)

            btn_edit = self._make_action_btn("Edit", "PMActionBtn")
            btn_edit.clicked.connect(lambda _, m=method: self._edit_method(m))
            action_layout.addWidget(btn_edit)

            # Toggle active/inactive
            toggle_text = "Deactivate" if method.is_active else "Activate"
            toggle_class = "warning" if method.is_active else "accent"
            btn_toggle = self._make_action_btn(toggle_text, "PMActionBtn", toggle_class)
            btn_toggle.clicked.connect(lambda _, m=method: self._toggle_method(m))
            action_layout.addWidget(btn_toggle)

            # Delete — not allowed for Cash method
            if not method.is_cash:
                btn_delete = self._make_action_btn("Delete", "PMActionBtn", "danger")
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
                )
                self._load_methods()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update payment method: {e}")

    def _toggle_method(self, method) -> None:
        """Toggle active/inactive state."""
        new_state = not method.is_active
        action = "activate" if new_state else "deactivate"
        try:
            PaymentService.update_method(method_id=method.id, is_active=new_state)
            self._load_methods()
            logger.info("Payment method '%s' %sd", method.name, action)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to {action} payment method: {e}")

    def _delete_method(self, method) -> None:
        if method.is_cash:
            QMessageBox.warning(self, "Cannot Delete", "Cash payment method cannot be deleted.")
            return

        reply = QMessageBox.question(
            self,
            "Delete Payment Method",
            f'Are you sure you want to delete "{method.name}"?\n\n'
            "Tip: You can deactivate it instead to keep transaction history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                PaymentService.delete_method(method.id)
                self._load_methods()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete payment method: {e}")
