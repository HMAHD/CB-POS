"""Custom line edit for entering decimal monetary/numeric values."""

from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import QLocale
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QLineEdit


class DecimalLineEdit(QLineEdit):
    """A QLineEdit configured for decimal entry without float precision loss.

    Provides .value() and .setValue() for backwards-compatible test and widget
    interoperability, and .decimal_value() for lossless Decimal manipulation.
    """

    def __init__(
        self,
        bottom: float = 0.0,
        top: float = 100000.0,
        decimals: int = 2,
        parent=None,
    ):
        """Configure validator with standard decimal notation."""
        super().__init__(parent)
        validator = QDoubleValidator(bottom, top, decimals, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        validator.setLocale(QLocale.c())
        self.setValidator(validator)

    def value(self) -> float:
        """Return current value as float (for backward compatibility)."""
        text = self.text().strip()
        try:
            return float(text) if text else 0.0
        except ValueError:
            return 0.0

    def decimal_value(self) -> Decimal:
        """Return current value as an exact Decimal."""
        text = self.text().strip()
        try:
            return Decimal(text) if text else Decimal("0")
        except (InvalidOperation, ValueError):
            return Decimal("0")

    def setValue(self, val) -> None:
        """Set the display value from Decimal, float, int, or string."""
        if val is None:
            self.setText("")
        elif isinstance(val, Decimal):
            self.setText(str(val))
        elif isinstance(val, float):
            self.setText(f"{val:.2f}".rstrip("0").rstrip(".") if val.is_integer() else f"{val:.2f}")
        else:
            self.setText(str(val))
