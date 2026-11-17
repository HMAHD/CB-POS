"""Dialog to choose which cart item an extended warranty plan covers (#829)."""

from PyQt6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.ui.widgets.table_helpers import NUMERIC_ALIGNMENT, make_dialog_footer


class PlanCoveredItemChooserDialog(QDialog):
    """Chooser dialog shown when multiple eligible products exist in cart for an extended plan."""

    def __init__(self, plan_product, eligible_lines: list[dict], parent=None):
        super().__init__(parent)
        self.plan_product = plan_product
        self.eligible_lines = eligible_lines
        self._selected_line_id: str | None = None

        self.setWindowTitle(_t("cart.choose_covered_item_title", default="Select Covered Product"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        prompt_lbl = QLabel(
            _t(
                "cart.choose_covered_item_prompt",
                plan=getattr(self.plan_product, "name_en", ""),
                default=f"Select the covered product for '{getattr(self.plan_product, 'name_en', '')}':",
            )
        )
        prompt_lbl.setWordWrap(True)
        layout.addWidget(prompt_lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            [
                _t("cart.col_item", default="Item"),
                _t("cart.col_price", default="Price"),
                _t("cart.col_qty", default="Qty"),
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setRowCount(len(self.eligible_lines))
        for row, item in enumerate(self.eligible_lines):
            prod = item["product"]
            name_item = QTableWidgetItem(getattr(prod, "name_en", ""))
            self.table.setItem(row, 0, name_item)

            price_item = QTableWidgetItem(format_currency(item.get("unit_price", 0)))
            price_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table.setItem(row, 1, price_item)

            qty_val = item.get("qty", 1)
            qty_str = str(int(qty_val)) if qty_val % 1 == 0 else f"{qty_val:.3f}"
            qty_item = QTableWidgetItem(qty_str)
            qty_item.setTextAlignment(NUMERIC_ALIGNMENT)
            self.table.setItem(row, 2, qty_item)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.table)

        # Footer with OK / Cancel
        self.btn_ok = QPushButton(_t("common.ok", default="OK"))
        self.btn_ok.setProperty("class", "primary")
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self._on_ok)

        self.btn_cancel = QPushButton(_t("common.cancel", default="Cancel"))
        self.btn_cancel.clicked.connect(self.reject)

        footer = make_dialog_footer(self.btn_cancel, self.btn_ok)
        layout.addWidget(footer)

        # Select first row by default
        if self.eligible_lines:
            self.table.selectRow(0)

    def _on_selection_changed(self) -> None:
        has_sel = len(self.table.selectedItems()) > 0
        self.btn_ok.setEnabled(has_sel)

    def _on_double_clicked(self) -> None:
        if self.table.currentRow() >= 0:
            self._on_ok()

    def _on_ok(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.eligible_lines):
            self._selected_line_id = self.eligible_lines[row].get("line_id")
            self.accept()

    def get_selected_line_id(self) -> str | None:
        """Return the cart line_id of the selected covered item."""
        return self._selected_line_id
