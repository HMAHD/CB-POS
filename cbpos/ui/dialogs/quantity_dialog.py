from decimal import Decimal, InvalidOperation

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence


class QuantityDialog(QDialog):
    """Prompt for quantity when adding a product to the cart."""

    def __init__(self, product, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter Quantity")
        self.setObjectName("QuantityDialog")
        self.setFixedSize(340, 180)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        # Product name
        self.lbl_product = QLabel(product.name_en)
        self.lbl_product.setObjectName("QtyProductName")
        self.lbl_product.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_product.setWordWrap(True)
        layout.addWidget(self.lbl_product)

        # Quantity input
        self.qty_input = QLineEdit("1")
        self.qty_input.setObjectName("QtyInput")
        self.qty_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        from PyQt6.QtGui import QDoubleValidator

        validator = QDoubleValidator(0.001, 999999.0, 3, self)
        self.qty_input.setValidator(validator)
        self.qty_input.selectAll()
        layout.addWidget(self.qty_input)

        # OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Own shortcuts bound to this dialog — takes priority over parent shortcuts
        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(self.accept)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self).activated.connect(self.accept)

        # Focus the input
        self.qty_input.setFocus()

        # Disable parent Enter shortcuts while this dialog is open
        self._disabled_shortcuts: list[QShortcut] = []
        if parent is not None:
            for attr_name in ("shortcut_enter", "shortcut_num_enter"):
                shortcut = getattr(parent, attr_name, None)
                if shortcut and shortcut.isEnabled():
                    shortcut.setEnabled(False)
                    self._disabled_shortcuts.append(shortcut)

    def done(self, result: int) -> None:
        """Re-enable parent shortcuts before closing."""
        for shortcut in self._disabled_shortcuts:
            shortcut.setEnabled(True)
        self._disabled_shortcuts.clear()
        super().done(result)

    def get_quantity(self) -> Decimal:
        """Return the entered quantity as Decimal."""
        text = self.qty_input.text().strip()
        try:
            qty = Decimal(text)
            if qty <= 0:
                return Decimal("1")
            return qty
        except (InvalidOperation, ValueError):
            return Decimal("1")
