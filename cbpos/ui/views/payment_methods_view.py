"""
Payment Methods management view for Settings.
Card-based list with inline toggle, edit, and delete actions.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QDialog,
    QFormLayout,
    QLineEdit,
    QCheckBox,
    QMessageBox,
    QScrollArea,
    QFrame,
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


class _MethodCard(QFrame):
    """A single payment method row card."""

    def __init__(self, method, parent_view: "PaymentMethodsView", parent=None):
        super().__init__(parent)
        self.method = method
        self._parent_view = parent_view
        self.setObjectName("PMCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # --- Left: Name + tags ---
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        name_label = QLabel(self.method.name)
        name_label.setObjectName("PMCardName")
        info_layout.addWidget(name_label)

        # Tags line: properties as small text
        tags = []
        if self.method.is_cash:
            tags.append("Cash")
        if self.method.open_drawer:
            tags.append("Opens Drawer")
        if self.method.shortcut:
            tags.append(self.method.shortcut)

        if tags:
            tag_label = QLabel(" \u00b7 ".join(tags))
            tag_label.setObjectName("PMCardTags")
            info_layout.addWidget(tag_label)

        layout.addLayout(info_layout, 1)

        # --- Center: Status badge ---
        status_text = "Active" if self.method.is_active else "Inactive"
        status_class = "pm-active" if self.method.is_active else "pm-inactive"
        status_label = QLabel(status_text)
        status_label.setObjectName("PMCardStatus")
        status_label.setProperty("class", status_class)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setFixedWidth(80)
        layout.addWidget(status_label)

        # --- Right: Action buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_edit = QPushButton("Edit")
        btn_edit.setObjectName("PMCardBtn")
        btn_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_edit.clicked.connect(lambda: self._parent_view._edit_method(self.method))
        btn_layout.addWidget(btn_edit)

        toggle_text = "Deactivate" if self.method.is_active else "Activate"
        toggle_class = "warning" if self.method.is_active else "accent"
        btn_toggle = QPushButton(toggle_text)
        btn_toggle.setObjectName("PMCardBtn")
        btn_toggle.setProperty("class", toggle_class)
        btn_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_toggle.clicked.connect(lambda: self._parent_view._toggle_method(self.method))
        btn_layout.addWidget(btn_toggle)

        if not self.method.is_cash:
            btn_delete = QPushButton("Delete")
            btn_delete.setObjectName("PMCardBtn")
            btn_delete.setProperty("class", "danger")
            btn_delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_delete.clicked.connect(lambda: self._parent_view._delete_method(self.method))
            btn_layout.addWidget(btn_delete)

        layout.addLayout(btn_layout)


class PaymentMethodsView(QWidget):
    """Payment Methods management — card-based list with actions."""

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

        # Scrollable card list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setObjectName("PMCardScroll")

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()

        self.scroll.setWidget(self._list_container)
        layout.addWidget(self.scroll, 1)

        # Hint
        hint = QLabel("Deactivate methods to hide from checkout. Cash method cannot be deleted.")
        hint.setProperty("class", "muted")
        layout.addWidget(hint)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_methods()

    def _load_methods(self) -> None:
        """Rebuild the card list from database."""
        self._methods = PaymentService.get_all_methods()

        # Clear existing cards
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add cards
        for i, method in enumerate(self._methods):
            card = _MethodCard(method, parent_view=self)
            self._list_layout.insertWidget(i, card)

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
