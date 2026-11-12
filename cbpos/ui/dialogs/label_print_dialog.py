"""Dialog for selecting products, configuring label formats, and printing barcode labels (#819).

Features:
- Compact format row for Language (en, si, ta, en+si, en+ta) and Size presets (50x30, 40x25, 58mm, custom).
- Custom width and height controls with validation against printer printable width.
- Live preview panel with real python-barcode rendering and fallback warning.
- Off-thread database loading and hardware print jobs.
"""

import logging
from typing import Any

from PyQt6.QtCore import QStringListModel, Qt
from PyQt6.QtGui import QIntValidator, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QFrame,
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

from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.label_service import (
    PRESET_DIMENSIONS,
    LabelOptions,
    LabelService,
)
from cbpos.core.services.product_service import ProductService
from cbpos.core.utils.destroy_hooks import call_on_destroyed
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.label_preview_dialog import LabelCard, LabelPreviewDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.layout_helpers import protect_vertical_sizing
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)
from cbpos.ui.workers import LabelProductLoaderWorker, start_background_job

logger = logging.getLogger(__name__)


class _QtyDelegate(QStyledItemDelegate):
    """Delegate that renders Qty cells as centered text and provides a validated QLineEdit editor."""

    def createEditor(self, parent: QWidget, option, index) -> QLineEdit:
        editor = QLineEdit(parent)
        editor.setValidator(QIntValidator(1, 999))
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setFrame(False)
        editor.setObjectName("TableQtyEditor")
        return editor

    def setEditorData(self, editor: QLineEdit, index) -> None:
        value = index.data(Qt.ItemDataRole.DisplayRole)
        editor.setText(value if value else "1")
        editor.selectAll()

    def setModelData(self, editor: QLineEdit, model, index) -> None:
        text = editor.text().strip()
        try:
            val = max(1, int(text)) if text else 1
        except ValueError:
            val = 1
        model.setData(index, str(val), Qt.ItemDataRole.EditRole)

    def displayText(self, value, locale) -> str:
        try:
            return str(max(1, int(value))) if value else "1"
        except (ValueError, TypeError):
            return "1"


class LabelPrintDialog(QDialog):
    """Dialog to search products, configure label layout, preview live, and print barcode labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("label_print.title"))
        self.setObjectName("LabelPrintDialog")
        self.setMinimumSize(920, 600)
        self.resize(980, 640)

        self.product_service = ProductService()
        self.label_items: list[dict[str, Any]] = []
        self.products_cache: dict[str, Any] = {}
        self._completer_activated = False
        self._print_job_id: str | None = None

        PrintWorker.instance().job_result.connect(self._on_print_job_result)
        call_on_destroyed(self, self._disconnect_print_worker)

        self._init_ui()
        self._load_products()
        self._update_validation()
        self._refresh_preview()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # ── Format Row: Language, Size, Custom WxH, Validation Error ──
        format_frame = QFrame()
        format_frame.setObjectName("LabelFormatCard")
        format_layout = QHBoxLayout(format_frame)
        format_layout.setContentsMargins(12, 10, 12, 10)
        format_layout.setSpacing(12)

        # Language selection
        lbl_lang = QLabel(_t("labels.language"))
        lbl_lang.setProperty("class", "bold")
        format_layout.addWidget(lbl_lang)

        self.combo_language = QComboBox()
        self.combo_language.setObjectName("ComboLabelLanguage")
        self.combo_language.setMinimumHeight(44)
        self.combo_language.addItem(_t("labels.lang_en"), "en")
        self.combo_language.addItem(_t("labels.lang_si"), "si")
        self.combo_language.addItem(_t("labels.lang_ta"), "ta")
        self.combo_language.addItem(_t("labels.lang_en_si"), "en+si")
        self.combo_language.addItem(_t("labels.lang_en_ta"), "en+ta")
        self.combo_language.currentIndexChanged.connect(self._on_format_changed)
        format_layout.addWidget(self.combo_language)

        format_layout.addSpacing(8)

        # Size preset selection
        lbl_size = QLabel(_t("labels.size"))
        lbl_size.setProperty("class", "bold")
        format_layout.addWidget(lbl_size)

        self.combo_size = QComboBox()
        self.combo_size.setObjectName("ComboLabelSize")
        self.combo_size.setMinimumHeight(44)
        self.combo_size.addItem(_t("labels.preset_50x30"), "50x30")
        self.combo_size.addItem(_t("labels.preset_40x25"), "40x25")
        self.combo_size.addItem(_t("labels.preset_58mm"), "58mm")
        self.combo_size.addItem(_t("labels.size_custom"), "custom")
        self.combo_size.currentIndexChanged.connect(self._on_size_preset_changed)
        format_layout.addWidget(self.combo_size)

        # Custom dimensions container (visible only when custom chosen)
        self.custom_dim_widget = QWidget()
        custom_lay = QHBoxLayout(self.custom_dim_widget)
        custom_lay.setContentsMargins(0, 0, 0, 0)
        custom_lay.setSpacing(6)

        lbl_w = QLabel(_t("labels.custom_width"))
        self.input_width = QLineEdit("50")
        self.input_width.setValidator(QIntValidator(10, 200))
        self.input_width.setFixedWidth(55)
        self.input_width.setMinimumHeight(44)
        self.input_width.textChanged.connect(self._on_custom_dim_changed)

        lbl_h = QLabel(_t("labels.custom_height"))
        self.input_height = QLineEdit("30")
        self.input_height.setValidator(QIntValidator(10, 200))
        self.input_height.setFixedWidth(55)
        self.input_height.setMinimumHeight(44)
        self.input_height.textChanged.connect(self._on_custom_dim_changed)

        custom_lay.addWidget(lbl_w)
        custom_lay.addWidget(self.input_width)
        custom_lay.addWidget(lbl_h)
        custom_lay.addWidget(self.input_height)
        self.custom_dim_widget.setVisible(False)
        format_layout.addWidget(self.custom_dim_widget)

        # Dimension validation error label
        self.lbl_dimension_error = QLabel()
        self.lbl_dimension_error.setProperty("class", "danger")
        self.lbl_dimension_error.setWordWrap(True)
        self.lbl_dimension_error.setVisible(False)
        format_layout.addWidget(self.lbl_dimension_error, 1)

        format_layout.addStretch()
        main_layout.addWidget(format_frame)

        # ── Main Area: Left (Queue & Search) + Right (Live Preview) ──
        body_layout = QHBoxLayout()
        body_layout.setSpacing(16)

        # ── Left Column: Search & Queue Table ──
        left_layout = QVBoxLayout()
        left_layout.setSpacing(10)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(_t("label_print.search_placeholder"))
        self.search_input.setMinimumHeight(44)

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
        btn_add.setMinimumHeight(44)
        btn_add.clicked.connect(self._add_product)
        search_layout.addWidget(btn_add)
        left_layout.addLayout(search_layout)

        # Table
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

        self._qty_delegate = _QtyDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self._qty_delegate)
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)

        left_layout.addWidget(self.table)

        # Under table row: totals and removal buttons
        queue_actions = QHBoxLayout()
        self.lbl_total = QLabel(_t("label_print.total_labels", count=0))
        self.lbl_total.setProperty("class", "bold")
        queue_actions.addWidget(self.lbl_total)

        queue_actions.addStretch()

        btn_remove = QPushButton(_t("label_print.remove_selected"))
        btn_remove.setProperty("class", "danger")
        btn_remove.setMinimumHeight(44)
        btn_remove.clicked.connect(self._remove_selected)
        queue_actions.addWidget(btn_remove)

        btn_clear = QPushButton(_t("label_print.clear_all"))
        btn_clear.setProperty("class", "danger")
        btn_clear.setMinimumHeight(44)
        btn_clear.clicked.connect(self._clear_all)
        queue_actions.addWidget(btn_clear)

        left_layout.addLayout(queue_actions)
        body_layout.addLayout(left_layout, 1)

        # ── Right Column: Live Preview Panel ──
        preview_container = QFrame()
        preview_container.setObjectName("LabelPreviewContainer")
        preview_container.setFixedWidth(320)
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(10)

        lbl_preview_title = QLabel(_t("labels.live_preview"))
        lbl_preview_title.setProperty("class", "bold")
        lbl_preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(lbl_preview_title)

        # Empty preview card state
        self.empty_preview_widget = QWidget()
        empty_lay = QVBoxLayout(self.empty_preview_widget)
        empty_lay.setContentsMargins(10, 40, 10, 40)
        lbl_empty_msg = QLabel(_t("labels.no_selection_preview"))
        lbl_empty_msg.setProperty("class", "secondary")
        lbl_empty_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_empty_msg.setWordWrap(True)
        empty_lay.addWidget(lbl_empty_msg)
        preview_layout.addWidget(self.empty_preview_widget)

        # The actual live label mockup card
        self.label_card = LabelCard(parent=self)
        self.label_card.setVisible(False)
        preview_layout.addWidget(self.label_card, alignment=Qt.AlignmentFlag.AlignCenter)

        # Info beneath preview
        self.lbl_barcode_info = QLabel()
        self.lbl_barcode_info.setProperty("class", "secondary")
        self.lbl_barcode_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.lbl_barcode_info)

        self.lbl_dimension_info = QLabel()
        self.lbl_dimension_info.setProperty("class", "secondary")
        self.lbl_dimension_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.lbl_dimension_info)

        # Fallback warning
        self.lbl_fallback_warning = QLabel(_t("labels.fallback_warning"))
        self.lbl_fallback_warning.setStyleSheet("color: #D97706; font-weight: bold;")
        self.lbl_fallback_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_fallback_warning.setWordWrap(True)
        self.lbl_fallback_warning.setVisible(False)
        preview_layout.addWidget(self.lbl_fallback_warning)

        # Receipt printer precision note
        lbl_receipt_note = QLabel(_t("labels.receipt_note"))
        lbl_receipt_note.setProperty("class", "secondary")
        lbl_receipt_note.setStyleSheet("font-size: 11px; color: #71717A;")
        lbl_receipt_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_receipt_note.setWordWrap(True)
        preview_layout.addWidget(lbl_receipt_note)

        preview_layout.addStretch()
        body_layout.addWidget(preview_container)

        main_layout.addLayout(body_layout)

        # ── Dialog Footer Row ──
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        btn_close = QPushButton(_t("common.close"))
        btn_close.setObjectName("BtnCancel")
        btn_close.setProperty("class", "secondary")
        btn_close.setMinimumHeight(44)
        btn_close.clicked.connect(self.reject)
        footer_layout.addWidget(btn_close)

        footer_layout.addStretch()

        self.btn_preview = QPushButton(_t("label_print.preview_label"))
        self.btn_preview.setProperty("class", "secondary")
        self.btn_preview.setMinimumHeight(44)
        self.btn_preview.clicked.connect(self._preview_label)
        footer_layout.addWidget(self.btn_preview)

        self.btn_print = QPushButton(_t("label_print.print_labels"))
        self.btn_print.setObjectName("BtnPrintLabels")
        self.btn_print.setProperty("class", "primary")
        self.btn_print.setMinimumHeight(44)
        self.btn_print.setShortcut(QKeySequence("Ctrl+P"))
        self.btn_print.clicked.connect(self._print_labels)
        footer_layout.addWidget(self.btn_print)

        main_layout.addLayout(footer_layout)
        protect_vertical_sizing(self)

    # ── Product loading & autocomplete ──

    def _disconnect_print_worker(self) -> None:
        try:
            PrintWorker.instance().job_result.disconnect(self._on_print_job_result)
        except Exception:
            pass

    def _load_products(self) -> None:
        """Load all active products into cache and completer off the UI thread."""
        self._loader_worker = LabelProductLoaderWorker(self.product_service)
        self._loader_worker.loaded.connect(self._on_products_loaded)
        start_background_job(self._loader_worker)

    def _on_products_loaded(self, products: list[Any]) -> None:
        """Populate product completer and cache from loaded products."""
        names: list[str] = []
        for p in products:
            key = f"{p.name_en} [{p.barcode}]"
            names.append(key)
            self.products_cache[key] = p
            self.products_cache[p.barcode] = p

        model = QStringListModel(names)
        self.product_completer.setModel(model)

    def _on_completer_activated(self, text: str) -> None:
        self._completer_activated = True
        self.search_input.setText(text)
        self._add_product()

    def _on_return_pressed(self) -> None:
        if self._completer_activated:
            self._completer_activated = False
            return
        self._add_product()

    # ── Options & Validation ──

    def _get_current_options(self) -> LabelOptions:
        lang = self.combo_language.currentData() or "en"
        preset = self.combo_size.currentData() or "50x30"

        if preset == "custom":
            try:
                w_mm = float(self.input_width.text().strip() or "50")
            except ValueError:
                w_mm = 50.0
            try:
                h_mm = float(self.input_height.text().strip() or "30")
            except ValueError:
                h_mm = 30.0
        else:
            w_mm, h_mm = PRESET_DIMENSIONS.get(preset, (50.0, 30.0))

        return LabelOptions(
            preset=preset,
            width_mm=w_mm,
            height_mm=h_mm,
            language=lang,
        )

    def _update_validation(self) -> bool:
        options = self._get_current_options()
        paper_w = ConfigService.get("paper_width") or "80mm"
        max_printable_w = 58.0 if paper_w == "58mm" else 80.0

        is_valid, err_key = LabelService.validate_dimensions(options.width_mm, options.height_mm, max_printable_w)

        if not is_valid:
            if err_key == "err_width_exceeds":
                self.lbl_dimension_error.setText(_t("labels.err_width_exceeds", max=int(max_printable_w)))
            else:
                self.lbl_dimension_error.setText(_t("labels.err_dimensions_min"))
            self.lbl_dimension_error.setVisible(True)
            self.btn_print.setEnabled(False)
            return False

        self.lbl_dimension_error.setVisible(False)
        has_items = len(self.label_items) > 0
        self.btn_print.setEnabled(has_items and self._print_job_id is None)
        return True

    def _on_format_changed(self) -> None:
        self._update_validation()
        self._refresh_preview()

    def _on_size_preset_changed(self) -> None:
        is_custom = self.combo_size.currentData() == "custom"
        self.custom_dim_widget.setVisible(is_custom)
        self._update_validation()
        self._refresh_preview()

    def _on_custom_dim_changed(self) -> None:
        self._update_validation()
        self._refresh_preview()

    # ── Table management & selection ──

    def _on_table_selection_changed(self) -> None:
        self._refresh_preview()

    def _refresh_table(self) -> None:
        with batch_table_update(self.table):
            self.table.setRowCount(0)
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
        self._update_validation()
        if self.label_items and self.table.currentRow() < 0:
            self.table.selectRow(0)
        self._refresh_preview()

    def _on_cell_changed(self, row: int, col: int) -> None:
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
        row = self.table.currentRow()
        if 0 <= row < len(self.label_items):
            del self.label_items[row]
            self._refresh_table()

    def _clear_all(self) -> None:
        self.label_items.clear()
        self._refresh_table()

    # ── Add / choose product ──

    def _add_product(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return

        product = self.products_cache.get(query)

        if not product:
            try:
                products = self.product_service.search_products(query, mode="ALL")
            except Exception as e:
                logger.error("Failed to search products: %s", e)
                products = []

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

        # Increment qty if already in queue
        for item in self.label_items:
            if getattr(item["product"], "id", None) == getattr(product, "id", None):
                item["quantity"] += 1
                self._refresh_table()
                self.search_input.clear()
                self.search_input.setFocus()
                return

        self.label_items.append({"product": product, "quantity": 1})
        self._refresh_table()
        self.search_input.clear()
        self.search_input.setFocus()

    def _choose_product(self, products: list[Any]) -> Any:
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

    # ── Live Preview & Print ──

    def _refresh_preview(self) -> None:
        if not self.label_items:
            self.label_card.setVisible(False)
            self.empty_preview_widget.setVisible(True)
            self.lbl_barcode_info.setText("")
            self.lbl_dimension_info.setText("")
            self.lbl_fallback_warning.setVisible(False)
            return

        row = self.table.currentRow()
        if row < 0 or row >= len(self.label_items):
            row = 0

        product = self.label_items[row]["product"]
        options = self._get_current_options()
        layout = LabelService.create_layout(product, options)

        self.empty_preview_widget.setVisible(False)
        self.label_card.setVisible(True)
        self.label_card.set_layout(layout)

        self.lbl_barcode_info.setText(
            _t("labels.barcode_symbology", type=f"{layout.barcode_symbology} ({layout.barcode_value})")
        )
        self.lbl_dimension_info.setText(
            _t("labels.barcode_dimensions", width=int(options.width_mm), height=int(options.height_mm))
        )

        if layout.is_fallback:
            self.lbl_fallback_warning.setText(_t("labels.fallback_warning"))
            self.lbl_fallback_warning.setVisible(True)
        else:
            self.lbl_fallback_warning.setVisible(False)

    def _preview_label(self) -> None:
        """Open popup preview dialog for selected product."""
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
        options = self._get_current_options()

        dlg = LabelPreviewDialog(product, options=options, parent=self)
        dlg.exec()

    def _print_labels(self) -> None:
        """Generate and send label print commands to PrintWorker."""
        if not self.label_items:
            QMessageBox.warning(
                self,
                _t("label_print.no_items_title"),
                _t("label_print.no_items_print_msg"),
            )
            return

        if not self._update_validation():
            return

        try:
            options = self._get_current_options()
            commands = LabelService.generate_batch_commands(self.label_items, options)
            self.btn_print.setEnabled(False)
            worker = PrintWorker.instance()
            self._print_job_id = worker.add_job("print_commands", commands)
        except Exception as e:
            logger.error("Label printing failed: %s", e)
            self._update_validation()
            QMessageBox.critical(self, _t("common.error"), _t("label_print.print_failed"))

    def _on_print_job_result(self, job_id: str, ok: bool, message: str) -> None:
        if self._print_job_id is None or job_id != self._print_job_id:
            return
        self._print_job_id = None
        self._update_validation()
        if ok:
            self._on_print_finished()
        else:
            self._on_print_error(message)

    def _on_print_finished(self) -> None:
        total = sum(item["quantity"] for item in self.label_items)
        QMessageBox.information(self, _t("label_print.printing_title"), _t("label_print.print_success", count=total))

    def _on_print_error(self, message: str) -> None:
        logger.error("Label printing failed: %s", message)
        QMessageBox.critical(self, _t("common.error"), _t("label_print.print_failed"))

    def keyPressEvent(self, event) -> None:
        """Handle escape key to close dialog."""
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
