from decimal import Decimal, InvalidOperation

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer


class SetItemPriceDialog(QDialog):
    """Prompt for a price-list item's price.

    QInputDialog.getDouble() renders the value in a native spin box whose
    up/down stepper arrows don't pick up the app's QSS theme, so this
    mirrors QuantityDialog's QLineEdit + QDoubleValidator pattern instead.
    """

    def __init__(self, product_name: str, current_price: Decimal, parent=None):
        """Build the price prompt for `product_name`, pre-filled with `current_price`."""
        super().__init__(parent)
        self.setWindowTitle(_t("pricelist.set_price_title"))
        self.setObjectName("SetItemPriceDialog")
        self.setFixedWidth(340)
        self.setMinimumHeight(200)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        lbl_prompt = QLabel(_t("pricelist.set_price_prompt", product_name=product_name))
        lbl_prompt.setObjectName("SetPricePrompt")
        lbl_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_prompt.setWordWrap(True)
        layout.addWidget(lbl_prompt)

        self.price_input = QLineEdit(f"{current_price:.2f}")
        self.price_input.setObjectName("SetPriceInput")
        self.price_input.setMinimumHeight(44)
        self.price_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.price_input.setValidator(QDoubleValidator(0.01, 999999.0, 2, self))
        self.price_input.selectAll()
        layout.addWidget(self.price_input)

        footer_layout, self.btn_ok, self.btn_cancel = make_dialog_footer(
            primary_key="common.ok",
            on_primary=self.accept,
            on_cancel=self.reject,
            primary_object_name="BtnOk",
        )
        layout.addLayout(footer_layout)

        QShortcut(QKeySequence(Qt.Key.Key_Return), self).activated.connect(self.accept)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self).activated.connect(self.accept)

        self.price_input.setFocus()

    def _parsed_price(self):
        """Return the entered price as Decimal, or None if not a positive number."""
        text = self.price_input.text().strip()
        try:
            price = Decimal(text)
        except InvalidOperation:
            return None
        return price if price > 0 else None

    def accept(self):
        """Reject the input with a warning if the price isn't a positive number, else accept."""
        if self._parsed_price() is None:
            QMessageBox.warning(
                self,
                _t("pricelist.set_price_invalid_title"),
                _t("pricelist.set_price_invalid_message"),
            )
            return
        super().accept()

    def get_price(self) -> Decimal:
        """Return the entered price as Decimal, falling back to 0.01 if invalid.

        Only meaningful after accept() -- callers read this from an
        accepted (exec() returned True) dialog, so the value is already
        known to be a positive number.
        """
        return self._parsed_price() or Decimal("0.01")
