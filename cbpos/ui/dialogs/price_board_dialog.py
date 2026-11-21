"""Price Board Dialog for fast daily price updates (#931)."""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from PyQt6.QtCore import QEvent, QRegularExpression, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QColor, QKeyEvent, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QAbstractItemDelegate,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.price_board_service import (
    PriceBoardItem,
    PriceBoardService,
    StaleProductError,
)
from cbpos.core.services.theme_service import ThemeService
from cbpos.core.utils.formatters import format_currency
from cbpos.core.utils.money import round_money
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.styles.tokens import THEME_TOKENS
from cbpos.ui.utils.layout_helpers import protect_vertical_sizing
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.table_helpers import (
    NUMERIC_ALIGNMENT,
    align_numeric_headers,
    batch_table_update,
    configure_table_columns,
)
from cbpos.ui.widgets.wheel_guard import install_wheel_guard
from cbpos.ui.workers import start_background_job

logger = logging.getLogger(__name__)


class PriceBoardLoaderWorker(QThread):
    """Loads price board items in a background thread."""

    loaded = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, service: PriceBoardService | None = None) -> None:
        super().__init__()
        self.service = service or PriceBoardService()
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        """Fetch price board items and emit loaded signal."""
        try:
            items = self.service.get_price_board_items()
            self.loaded.emit(items)
        except Exception as e:
            logger.error("PriceBoardLoaderWorker failed: %s", e)
            self.error.emit(str(e))


class PriceBoardSaveWorker(QThread):
    """Saves price board updates in a background thread."""

    saved = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(
        self,
        updates: list[dict[str, Any]],
        acting_user_id: int,
        service: PriceBoardService | None = None,
    ) -> None:
        super().__init__()
        self.updates = updates
        self.acting_user_id = acting_user_id
        self.service = service or PriceBoardService()
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        """Persist price changes via service and emit result or error."""
        try:
            changed_ids = self.service.batch_update_prices(self.updates, self.acting_user_id)
            self.saved.emit(changed_ids)
        except StaleProductError as e:
            logger.warning("PriceBoardSaveWorker stale product: %s", e)
            self.error.emit(_t("price_board.stale_error"))
        except PermissionError as e:
            logger.warning("PriceBoardSaveWorker permission denied: %s", e)
            self.error.emit(_t("price_board.permission_denied"))
        except Exception as e:
            logger.error("PriceBoardSaveWorker failed: %s", e)
            self.error.emit(str(e))


class PriceBoardItemDelegate(QStyledItemDelegate):
    """Delegate providing formatted numeric editing with Tab/Enter auto-advance."""

    advance_requested = pyqtSignal(int)

    def createEditor(self, parent: QWidget, option, index) -> QLineEdit:
        """Create decimal line editor with regex validation requiring at least one digit."""
        editor = QLineEdit(parent)
        regex = QRegularExpression(r"^(?:\d{1,7}(\.\d{0,2})?|\d{0,7}\.\d{1,2})$")
        editor.setValidator(QRegularExpressionValidator(regex, editor))
        editor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        editor.setFrame(False)
        editor.setObjectName("PriceBoardPriceEditor")
        return editor

    def setEditorData(self, editor: QLineEdit, index) -> None:
        """Populate editor text from cell user role data."""
        raw_val = index.data(Qt.ItemDataRole.UserRole)
        if raw_val is not None and isinstance(raw_val, Decimal):
            text = str(raw_val)
        else:
            display_text = index.data(Qt.ItemDataRole.DisplayRole)
            text = str(display_text) if display_text is not None else ""
        editor.setText(text)
        editor.selectAll()

    def setModelData(self, editor: QLineEdit, model, index) -> None:
        """Parse editor text into Decimal and update model roles."""
        text = editor.text().strip()
        if not text:
            model.setData(index, None, Qt.ItemDataRole.UserRole)
            model.setData(index, "", Qt.ItemDataRole.DisplayRole)
            return

        if not editor.hasAcceptableInput():
            model.setData(index, None, Qt.ItemDataRole.UserRole)
            model.setData(index, text, Qt.ItemDataRole.DisplayRole)
            return

        try:
            val = round_money(Decimal(text))
            model.setData(index, val, Qt.ItemDataRole.UserRole)
            model.setData(index, format_currency(val), Qt.ItemDataRole.DisplayRole)
        except (InvalidOperation, ValueError):
            model.setData(index, None, Qt.ItemDataRole.UserRole)
            model.setData(index, text, Qt.ItemDataRole.DisplayRole)

    def eventFilter(self, editor: QLineEdit, event: QEvent) -> bool:
        """Intercept Return and Tab keys to commit and request advance."""
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                text = editor.text().strip()
                if not text or not editor.hasAcceptableInput():
                    return True
                try:
                    Decimal(text)
                except (InvalidOperation, ValueError):
                    return True
                self.commitData.emit(editor)
                self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
                # Determine current row and request advance
                parent_table = self.parent()
                if isinstance(parent_table, QTableWidget):
                    current_row = parent_table.currentRow()
                    self.advance_requested.emit(current_row)
                return True
        return super().eventFilter(editor, event)


class PriceBoardDialog(QDialog):
    """Fast daily price editing table for items flagged 'price changes often' (#931)."""

    def __init__(
        self,
        acting_user_id: int,
        parent: QWidget | None = None,
        initial_items: list[PriceBoardItem] | None = None,
    ) -> None:
        super().__init__(parent)
        self.acting_user_id = acting_user_id
        self.service = PriceBoardService()
        self.items: list[PriceBoardItem] = []
        self._print_labels_after_save = False
        self._is_saving = False

        self.setWindowTitle(_t("price_board.title"))
        self.setObjectName("PriceBoardDialog")
        self.setMinimumSize(800, 500)
        self.resize(920, 600)

        install_wheel_guard(self)
        self._init_ui()
        if initial_items is not None:
            self._on_data_loaded(initial_items)
        else:
            self._load_data()

    def reject(self) -> None:
        """Ignore reject while save is in progress."""
        if self._is_saving:
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ignore window close event while save is in progress."""
        if self._is_saving:
            event.ignore()
            return
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Ignore Escape key while save is in progress."""
        if self._is_saving and event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header Title & Subtitle
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        self.title_lbl = QLabel(_t("price_board.title"))
        self.title_lbl.setObjectName("PriceBoardTitle")
        self.title_lbl.setProperty("class", "dialog-title")

        self.subtitle_lbl = QLabel(_t("price_board.subtitle"))
        self.subtitle_lbl.setObjectName("PriceBoardSubtitle")
        self.subtitle_lbl.setProperty("class", "muted")

        header_layout.addWidget(self.title_lbl)
        header_layout.addWidget(self.subtitle_lbl)
        main_layout.addLayout(header_layout)

        # Stacked view: Loading, Empty, Table Content
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        # Page 0: Loading
        self.page_loading = QWidget()
        load_layout = QVBoxLayout(self.page_loading)
        load_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_loading = QLabel(_t("price_board.loading"))
        self.lbl_loading.setProperty("class", "muted")
        load_layout.addWidget(self.lbl_loading)
        self.stack.addWidget(self.page_loading)

        # Page 1: Empty State
        self.page_empty = QWidget()
        empty_layout = QVBoxLayout(self.page_empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(12)

        lbl_empty_icon = QLabel()
        lbl_empty_icon.setPixmap(Icons.get(Icons.INFO).pixmap(48, 48))
        lbl_empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(lbl_empty_icon)

        lbl_empty_title = QLabel(_t("price_board.empty_title"))
        lbl_empty_title.setProperty("class", "bold")
        lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(lbl_empty_title)

        lbl_empty_msg = QLabel(_t("price_board.empty_message"))
        lbl_empty_msg.setProperty("class", "muted")
        lbl_empty_msg.setWordWrap(True)
        lbl_empty_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_empty_msg.setMaximumWidth(500)
        empty_layout.addWidget(lbl_empty_msg)

        btn_empty_close = QPushButton(_t("price_board.close"))
        btn_empty_close.setProperty("class", "secondary")
        btn_empty_close.setFixedWidth(140)
        btn_empty_close.clicked.connect(self.reject)
        empty_layout.addWidget(btn_empty_close, alignment=Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.page_empty)

        # Page 2: Table Content
        self.page_content = QWidget()
        content_layout = QVBoxLayout(self.page_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        # Filter bar & summary
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("PriceBoardSearch")
        self.search_input.setPlaceholderText(_t("price_board.search_placeholder"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_table)
        filter_row.addWidget(self.search_input, 1)

        self.lbl_summary = QLabel()
        self.lbl_summary.setObjectName("PriceBoardSummary")
        self.lbl_summary.setProperty("class", "bold")
        filter_row.addWidget(self.lbl_summary, 0, Qt.AlignmentFlag.AlignVCenter)
        content_layout.addLayout(filter_row)

        # Table
        self.table = QTableWidget()
        self.table.setObjectName("PriceBoardTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            [
                _t("price_board.col_product"),
                _t("price_board.col_barcode"),
                _t("price_board.col_current_price"),
                _t("price_board.col_new_price"),
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
        self.table.setColumnWidth(3, 150)
        align_numeric_headers(self.table, (2, 3))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)

        self.delegate = PriceBoardItemDelegate(self.table)
        self.delegate.advance_requested.connect(self._advance_to_next_row)
        self.table.setItemDelegateForColumn(3, self.delegate)
        self.table.cellChanged.connect(self._on_cell_changed)

        content_layout.addWidget(self.table, 1)

        # Footer Actions
        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="price_board.btn_save",
            on_primary=self._on_save_clicked,
            cancel_key="price_board.btn_cancel",
            on_cancel=self.reject,
        )

        self.btn_save_and_print = QPushButton(_t("price_board.btn_save_and_print"))
        self.btn_save_and_print.setObjectName("BtnSaveAndPrint")
        self.btn_save_and_print.setProperty("class", "success")
        self.btn_save_and_print.setAutoDefault(False)
        self.btn_save_and_print.clicked.connect(self._on_save_and_print_clicked)

        # Insert Save & Print Labels before Cancel
        cancel_idx = footer_layout.indexOf(self.btn_cancel)
        footer_layout.insertWidget(cancel_idx, self.btn_save_and_print)

        content_layout.addLayout(footer_layout)
        self.stack.addWidget(self.page_content)

        protect_vertical_sizing(self)

    def _load_data(self) -> None:
        """Start background loader to fetch price board items."""
        self.stack.setCurrentIndex(0)
        worker = PriceBoardLoaderWorker(self.service)
        worker.loaded.connect(self._on_data_loaded)
        worker.error.connect(self._on_load_error)
        start_background_job(worker)

    def _on_data_loaded(self, items: list[PriceBoardItem]) -> None:
        self.items = items
        if not items:
            self.stack.setCurrentIndex(1)
            return

        self._populate_table()
        self.stack.setCurrentIndex(2)
        # Select first row's new price cell
        if self.table.rowCount() > 0:
            self.table.setCurrentCell(0, 3)
            self.table.edit(self.table.model().index(0, 3))

    def _on_load_error(self, error_msg: str) -> None:
        QMessageBox.critical(self, _t("price_board.error_title"), error_msg)
        self.reject()

    def _populate_table(self) -> None:
        """Populate table widget with loaded items."""
        with batch_table_update(self.table):
            self.table.setRowCount(0)
            no_edit = ~Qt.ItemFlag.ItemIsEditable
            num_align = NUMERIC_ALIGNMENT

            for row_idx, item in enumerate(self.items):
                self.table.insertRow(row_idx)
                self.table.setRowHeight(row_idx, 44)

                # Col 0: Product Name
                c0 = QTableWidgetItem(item.get_display_name())
                c0.setFlags(c0.flags() & no_edit)
                self.table.setItem(row_idx, 0, c0)

                # Col 1: Barcode
                c1 = QTableWidgetItem(item.barcode)
                c1.setFlags(c1.flags() & no_edit)
                self.table.setItem(row_idx, 1, c1)

                # Col 2: Current Price
                c2 = QTableWidgetItem(format_currency(item.current_price))
                c2.setTextAlignment(num_align)
                c2.setFlags(c2.flags() & no_edit)
                self.table.setItem(row_idx, 2, c2)

                # Col 3: New Price (editable)
                c3 = QTableWidgetItem(format_currency(item.current_price))
                c3.setTextAlignment(num_align)
                c3.setData(Qt.ItemDataRole.UserRole, item.current_price)
                self.table.setItem(row_idx, 3, c3)

        self._update_summary()

    def _filter_table(self, query: str) -> None:
        """Filter table rows by search query in product name or barcode."""
        q = query.strip().lower()
        for row in range(self.table.rowCount()):
            name = (self.table.item(row, 0).text() if self.table.item(row, 0) else "").lower()
            barcode = (self.table.item(row, 1).text() if self.table.item(row, 1) else "").lower()
            matches = (q in name) or (q in barcode) if q else True
            self.table.setRowHidden(row, not matches)

    def _on_cell_changed(self, row: int, col: int) -> None:
        """React to price cell modification."""
        if col != 3 or row >= len(self.items):
            return

        item = self.items[row]
        cell = self.table.item(row, 3)
        if not cell:
            return

        new_val = cell.data(Qt.ItemDataRole.UserRole)
        if new_val is not None and isinstance(new_val, Decimal):
            if new_val != item.current_price:
                theme = "Dark" if ThemeService.current_theme.lower() == "dark" else "Light"
                cell.setForeground(QColor(THEME_TOKENS[theme]["ACCENT"]))
                f = cell.font()
                f.setBold(True)
                cell.setFont(f)
            else:
                cell.setData(Qt.ItemDataRole.ForegroundRole, None)
                f = cell.font()
                f.setBold(False)
                cell.setFont(f)
        else:
            cell.setData(Qt.ItemDataRole.ForegroundRole, None)
            f = cell.font()
            f.setBold(False)
            cell.setFont(f)

        self._update_summary()

    def _update_summary(self) -> None:
        """Update header item count and changed count."""
        total = len(self.items)
        changed = 0
        for row in range(min(total, self.table.rowCount())):
            cell = self.table.item(row, 3)
            if cell:
                val = cell.data(Qt.ItemDataRole.UserRole)
                if val is not None and val != self.items[row].current_price:
                    changed += 1

        if changed > 0:
            self.lbl_summary.setText(
                f"{_t('price_board.items_count', count=total)} • {_t('price_board.changed_count', count=changed)}"
            )
        else:
            self.lbl_summary.setText(_t("price_board.items_count", count=total))

    def _advance_to_next_row(self, current_row: int) -> None:
        """Advance to next visible row's new price editor or to Save button."""
        next_row = -1
        for r in range(current_row + 1, self.table.rowCount()):
            if not self.table.isRowHidden(r):
                next_row = r
                break

        if next_row != -1:
            self.table.setCurrentCell(next_row, 3)
            self.table.edit(self.table.model().index(next_row, 3))
        else:
            self.btn_save.setFocus()

    def _collect_updates(self) -> tuple[list[dict[str, Any]], bool]:
        """Validate and collect pending updates from table.

        Returns:
            (updates_list, has_validation_error)
        """
        updates: list[dict[str, Any]] = []
        for row, item in enumerate(self.items):
            cell = self.table.item(row, 3)
            if not cell:
                continue
            val = cell.data(Qt.ItemDataRole.UserRole)
            if val is None or not isinstance(val, Decimal) or val < Decimal("0"):
                if self.table.isRowHidden(row):
                    self.search_input.clear()
                    self.table.setRowHidden(row, False)
                QMessageBox.warning(
                    self,
                    _t("price_board.error_title"),
                    _t("price_board.invalid_price", product=item.get_display_name()),
                )
                self.table.setCurrentCell(row, 3)
                self.table.edit(self.table.model().index(row, 3))
                return [], True

            updates.append(
                {
                    "product_id": item.id,
                    "expected_version_id": item.version_id,
                    "new_price": val,
                }
            )
        return updates, False

    def _on_save_clicked(self) -> None:
        self._print_labels_after_save = False
        self._execute_save()

    def _on_save_and_print_clicked(self) -> None:
        self._print_labels_after_save = True
        self._execute_save()

    def _execute_save(self) -> None:
        updates, has_error = self._collect_updates()
        if has_error:
            return

        # Check if there are any actual changes
        actual_changes = [
            up
            for up in updates
            if any(it.id == up["product_id"] and it.current_price != up["new_price"] for it in self.items)
        ]
        if not actual_changes:
            QMessageBox.information(self, _t("price_board.title"), _t("price_board.no_changes"))
            return

        self._set_saving(True)
        worker = PriceBoardSaveWorker(actual_changes, self.acting_user_id, self.service)
        worker.saved.connect(self._on_save_success)
        worker.error.connect(self._on_save_error)
        start_background_job(worker)

    def _set_saving(self, saving: bool) -> None:
        self._is_saving = saving
        self.btn_save.setEnabled(not saving)
        self.btn_save_and_print.setEnabled(not saving)
        self.btn_cancel.setEnabled(not saving)
        self.table.setEnabled(not saving)
        if saving:
            self.btn_save.setText(_t("price_board.saving"))
        else:
            self.btn_save.setText(_t("price_board.btn_save"))

    def _on_save_success(self, changed_ids: list[int]) -> None:
        self._set_saving(False)
        self.accept()

        if self._print_labels_after_save and changed_ids:
            from cbpos.ui.dialogs.label_print_dialog import LabelPrintDialog

            dlg = LabelPrintDialog(parent=self.parent(), preselected_product_ids=changed_ids)
            dlg.exec()

    def _on_save_error(self, error_msg: str) -> None:
        self._set_saving(False)
        if "was modified" in error_msg:
            display_msg = _t("price_board.stale_error")
        elif "Permission denied" in error_msg or "Permissions.PRICING_MANAGE" in error_msg:
            display_msg = _t("price_board.permission_denied")
        else:
            display_msg = error_msg
        QMessageBox.critical(self, _t("price_board.error_title"), display_msg)
