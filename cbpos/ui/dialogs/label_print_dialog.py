"""
Dialog for selecting products and printing barcode labels.

Uses QStyledItemDelegate for the Qty column so that editing and rendering
go through Qt's model/view pipeline — QSS styling applies correctly.
"""

import contextlib
import logging

from PyQt6.QtCore import QStringListModel, Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QCompleter,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.label_service import LabelService
from cbpos.core.services.product_service import ProductService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.layout_helpers import protect_vertical_sizing
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)

logger = logging.getLogger(__name__)


class _QtyDelegate(QStyledItemDelegate):
    """Delegate that renders Qty cells as centered bold text and provides
    a validated QLineEdit editor accepting integers 1-999."""

    def createEditor(self, parent: QWidget, option, index) -> QLineEdit:
        """Return a centered, integer-validated (1-999) editor for the Qty cell."""
        editor = QLineEdit(parent)
        editor.setValidator(QIntValidator(1, 999))
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setFrame(False)

        # Delegate editors inside a globally-styled QTableWidget cannot
        editor.setObjectName("TableQtyEditor")
        return editor

    def setEditorData(self, editor: QLineEdit, index) -> None:
        """Populate the editor with the cell's current quantity, defaulting to 1."""
        value = index.data(Qt.ItemDataRole.DisplayRole)
        editor.setText(value if value else "1")
        editor.selectAll()

    def setModelData(self, editor: QLineEdit, model, index) -> None:
        """Write the edited quantity back to the model, clamped to at least 1."""
        text = editor.text().strip()
        try:
            val = max(1, int(text)) if text else 1
        except ValueError:
            val = 1
        model.setData(index, str(val), Qt.ItemDataRole.EditRole)

    def displayText(self, value, locale) -> str:
        """Render the stored value as a positive integer, defaulting to 1."""
        try:
            return str(max(1, int(value))) if value else "1"
        except (ValueError, TypeError):
            return "1"


class LabelPrintDialog(QDialog):
    """Dialog to search products, set quantities, and print barcode labels."""

    def __init__(self, parent=None):
        """Initialize the dialog and load the product cache for search/autocomplete."""
        super().__init__(parent)
        self.setWindowTitle(_t("label_print.title"))
        self.setMinimumSize(700, 500)
        self.setObjectName("LabelPrintDialog")
        self.product_service = ProductService()
        self.label_items: list[dict] = []
        self.products_cache: dict = {}
        self._completer_activated = False
        self._init_ui()
        self._load_products()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Search bar with autocomplete
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_t("label_print.search_placeholder"))

        self.product_completer = QCompleter()
        self.product_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.product_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.product_completer.setMaxVisibleItems(10)
        self.search_input.setCompleter(self.product_completer)

        self.product_completer.activated.connect(self._on_completer_activated)
        self.search_input.returnPressed.connect(self._on_return_pressed)
        search_layout.addWidget(self.search_input, 1)

        btn_add = QPushButton(_t("common.add"))
        btn_add.setProperty("class", "primary")
        btn_add.clicked.connect(self._add_product)
        search_layout.addWidget(btn_add)

        layout.addLayout(search_layout)

        # Label queue table
        self.table = QTableWidget()
        self.table.setObjectName("LabelQueueTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            [
                _t("label_print.col_product"),
                _t("label_print.col_barcode"),
                _t("label_print.col_price"),
                _t("label_print.col_qty"),
            ]
        )
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.Fixed,
            },
        )
        self.table.setColumnWidth(3, 100)
        align_numeric_headers(self.table, (2,))
        attach_table_empty_state(self.table, Icons.PRINT, "common.no_items")
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)

        # Qty column: editable via delegate; other columns: read-only
        self._qty_delegate = _QtyDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self._qty_delegate)
        self.table.cellChanged.connect(self._on_cell_changed)

        layout.addWidget(self.table)

        # Summary + actions
        btn_layout = QHBoxLayout()

        self.lbl_total = QLabel(_t("label_print.total_labels", count=0))
        self.lbl_total.setProperty("class", "bold")
        btn_layout.addWidget(self.lbl_total)

        btn_layout.addStretch()

        btn_remove = QPushButton(_t("label_print.remove_selected"))
        btn_remove.setProperty("class", "danger")
        btn_remove.clicked.connect(self._remove_selected)
        btn_layout.addWidget(btn_remove)

        btn_clear = QPushButton(_t("label_print.clear_all"))
        btn_clear.setProperty("class", "danger")
        btn_clear.clicked.connect(self._clear_all)
        btn_layout.addWidget(btn_clear)

        btn_preview = QPushButton(_t("label_print.preview_label"))
        btn_preview.setProperty("class", "secondary")
        btn_preview.clicked.connect(self._preview_label)
        btn_layout.addWidget(btn_preview)

        btn_print = QPushButton(_t("label_print.print_labels"))
        btn_print.setProperty("class", "primary")
        btn_print.clicked.connect(self._print_labels)
        btn_layout.addWidget(btn_print)

        layout.addLayout(btn_layout)
        protect_vertical_sizing(self)

    # ── Product loading & autocomplete ──

    def _load_products(self) -> None:
        """Load all active products into cache and completer."""
        products = self.product_service.get_all_products()
        names: list[str] = []
        for p in products:
            key = f"{p.name_en} [{p.barcode}]"
            names.append(key)
            self.products_cache[key] = p
            self.products_cache[p.barcode] = p

        model = QStringListModel(names)
        self.product_completer.setModel(model)

    def _on_completer_activated(self, text: str) -> None:
        """User picked from dropdown — add immediately."""
        self._completer_activated = True
        self.search_input.setText(text)
        self._add_product()

    def _on_return_pressed(self) -> None:
        """Handle Enter — skip if completer already handled it."""
        if self._completer_activated:
            self._completer_activated = False
            return
        self._add_product()

    # ── Add / choose product ──

    def _add_product(self) -> None:
        """Search for product and add to label queue."""
        query = self.search_input.text().strip()
        if not query:
            return

        product = self.products_cache.get(query)

        if not product:
            products = self.product_service.search_products(query, mode="ALL")
            if not products:
                QMessageBox.warning(
                    self,
                    _t("label_print.not_found_title"),
                    _t("label_print.not_found_msg", query=query),
                )
                return
            if len(products) == 1:
                product = products[0]
            else:
                product = self._choose_product(products)
                if product is None:
                    return

        # Already in list → increment qty
        for item in self.label_items:
            if item["product"].id == product.id:
                item["quantity"] += 1
                self._refresh_table()
                self.search_input.clear()
                self.search_input.setFocus()
                return

        self.label_items.append({"product": product, "quantity": 1})
        self._refresh_table()
        self.search_input.clear()
        self.search_input.setFocus()

    def _choose_product(self, products) -> object:
        """Show selection dialog when multiple products match."""
        dlg = QDialog(self)
        dlg.setWindowTitle(_t("label_print.select_product"))
        dlg.setMinimumSize(500, 300)
        lay = QVBoxLayout(dlg)

        tbl = QTableWidget()
        tbl.setColumnCount(3)
        tbl.setHorizontalHeaderLabels(
            [
                _t("common.name"),
                _t("label_print.col_barcode"),
                _t("label_print.col_price"),
            ]
        )
        configure_table_columns(
            tbl.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        align_numeric_headers(tbl, (2,))
        attach_table_empty_state(tbl, Icons.SEARCH, "common.no_items")
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setAlternatingRowColors(True)

        for p in products:
            row = tbl.rowCount()
            tbl.insertRow(row)
            tbl.setItem(row, 0, QTableWidgetItem(p.name_en))
            tbl.setItem(row, 1, QTableWidgetItem(p.barcode))
            price_item = QTableWidgetItem(format_currency(p.price))
            price_item.setTextAlignment(NUMERIC_ALIGNMENT)
            tbl.setItem(row, 2, price_item)

        tbl.doubleClicked.connect(dlg.accept)
        lay.addWidget(tbl)

        btn_lay = QHBoxLayout()
        btn_select = QPushButton(_t("label_print.select"))
        btn_select.setProperty("class", "primary")
        btn_select.clicked.connect(dlg.accept)
        btn_cancel = QPushButton(_t("common.cancel"))
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.setProperty("class", "secondary")
        btn_cancel.clicked.connect(dlg.reject)
        btn_lay.addStretch()
        btn_lay.addWidget(btn_select)
        btn_lay.addWidget(btn_cancel)
        lay.addLayout(btn_lay)

        if dlg.exec() and tbl.currentRow() >= 0:
            return products[tbl.currentRow()]
        return None

    # ── Table management ──

    def _refresh_table(self) -> None:
        """Rebuild table from label_items."""
        with batch_table_update(self.table):
            self.table.setRowCount(0)

            # Hoist LEGB locals
            table = self.table
            insert_row = table.insertRow
            set_row_height = table.setRowHeight
            set_item = table.setItem
            TableItem = QTableWidgetItem
            num_align = NUMERIC_ALIGNMENT
            align_center_vc = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            no_editable = ~Qt.ItemFlag.ItemIsEditable
            fmt_curr = format_currency

            for item in self.label_items:
                row = table.rowCount()
                insert_row(row)
                set_row_height(row, 44)

                prod = item["product"]
                c0 = TableItem(prod.name_en)
                c0.setFlags(c0.flags() & no_editable)
                set_item(row, 0, c0)

                c1 = TableItem(prod.barcode)
                c1.setFlags(c1.flags() & no_editable)
                set_item(row, 1, c1)

                c2 = TableItem(fmt_curr(prod.price))
                c2.setTextAlignment(num_align)
                c2.setFlags(c2.flags() & no_editable)
                set_item(row, 2, c2)

                qty_item = TableItem(str(item["quantity"]))
                qty_item.setTextAlignment(align_center_vc)
                set_item(row, 3, qty_item)

        self._update_total()

    def _on_cell_changed(self, row: int, col: int) -> None:
        """Sync edited Qty cell back to label_items."""
        if col != 3 or row >= len(self.label_items):
            return
        text = self.table.item(row, 3).text()
        try:
            value = max(1, int(text)) if text else 1
        except ValueError:
            value = 1
        self.label_items[row]["quantity"] = value
        self._update_total()

    def _update_total(self) -> None:
        total = sum(item["quantity"] for item in self.label_items)
        self.lbl_total.setText(_t("label_print.total_labels", count=total))

    def _remove_selected(self) -> None:
        """Remove selected product from label queue."""
        row = self.table.currentRow()
        if 0 <= row < len(self.label_items):
            del self.label_items[row]
            self._refresh_table()

    def _clear_all(self) -> None:
        """Clear all items from label queue."""
        self.label_items.clear()
        self._refresh_table()

    # ── Preview & Print ──

    def _preview_label(self) -> None:
        """Show a visual preview of a label for the selected product."""
        if not self.label_items:
            QMessageBox.warning(
                self,
                _t("label_print.no_items_title"),
                _t("label_print.no_items_preview_msg"),
            )
            return

        row = self.table.currentRow()
        if row < 0:
            row = 0
        product = self.label_items[row]["product"]

        from cbpos.ui.dialogs.label_preview_dialog import (
            LabelPreviewDialog,
        )

        dlg = LabelPreviewDialog(product, parent=self)
        dlg.exec()

    def _print_labels(self) -> None:
        """Generate and send label print commands."""
        if not self.label_items:
            QMessageBox.warning(
                self,
                _t("label_print.no_items_title"),
                _t("label_print.no_items_print_msg"),
            )
            return

        try:
            commands = LabelService.generate_batch_commands(self.label_items)
            worker = PrintWorker.instance()
            # PrintWorker.add_job() only queues the job -- the print itself
            # happens later, asynchronously, on the worker thread. Showing
            # "success" right after add_job() (the old behavior) meant the
            # user was told printing worked even when the printer wasn't
            # configured at all. Wait for the real outcome instead. Guard
            # against reconnecting on every call the same way
            # ReceiptOptionsDialog.print_thermal() does.
            try:
                worker.error_occurred.disconnect(self._on_print_error)
            except TypeError as e:
                logger.debug("Signal not connected yet: %s", e)
            with contextlib.suppress(TypeError):
                worker.job_completed.disconnect(self._on_print_finished)
            worker.error_occurred.connect(self._on_print_error)
            worker.job_completed.connect(self._on_print_finished)
            worker.add_job("print_commands", commands)
        except Exception as e:
            logger.error(f"Label printing failed: {e}")
            QMessageBox.critical(self, _t("common.error"), _t("label_print.print_failed"))

    def _on_print_finished(self) -> None:
        """Called once the queued print job actually completes."""
        total = sum(item["quantity"] for item in self.label_items)
        QMessageBox.information(self, _t("label_print.printing_title"), _t("label_print.print_success", count=total))

    def _on_print_error(self, message: str) -> None:
        """Called if the queued print job actually fails (e.g. no printer configured)."""
        logger.error("Label printing failed: %s", message)
        QMessageBox.critical(self, _t("common.error"), _t("label_print.print_failed"))
