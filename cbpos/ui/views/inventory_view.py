from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableView,
    QHeaderView,
    QMessageBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QColor, QBrush
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.services.import_service import ImportService
from cbpos.ui.dialogs.product_editor import ProductEditor
from cbpos.ui.workers import CsvImportWorker
from cbpos.ui.widgets.loading_overlay import LoadingOverlay


class InventoryModel(QAbstractTableModel):
    def __init__(self, products=None):
        super().__init__()
        self.products = products or []
        self.headers = ["Barcode", "Name", "Category", "Price", "Stock", "Unit"]

    def rowCount(self, parent=QModelIndex()):
        return len(self.products)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        product = self.products[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return product.barcode
            elif col == 1:
                return product.name_en
            elif col == 2:
                return product.category.name if product.category else "-"
            elif col == 3:
                return "{:.2f}".format(product.price)
            elif col == 4:
                return "{:.3f}".format(product.stock_qty)
            elif col == 5:
                if product.unit:
                    return product.unit.abbreviation
                return "kg" if product.is_weighted else "pcs"

        elif role == Qt.ItemDataRole.BackgroundRole:
            # Low stock warning - theme-aware colors via QSS alternate rows
            if product.stock_qty <= product.reorder_point:
                from cbpos.core.services.theme_service import ThemeService

                if ThemeService.current_theme.lower() == "light":
                    return QBrush(QColor(254, 226, 226))  # Very light red for light theme
                else:
                    return QBrush(QColor(60, 30, 30))  # Dark red tint for dark theme

        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def update_data(self, products):
        self.beginResetModel()
        self.products = products
        self.endResetModel()


class InventoryView(QWidget):
    def __init__(self):
        super().__init__()
        self.inventory_service = InventoryService()
        self.import_service = ImportService()
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Top Bar
        top_bar = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by Barcode or Name...")
        self.search_input.textChanged.connect(self.filter_data)

        self.add_btn = QPushButton("Add Product")
        self.add_btn.clicked.connect(self.open_add_dialog)

        self.import_btn = QPushButton("Import CSV")
        self.import_btn.clicked.connect(self.import_csv)

        self.cat_btn = QPushButton("Manage Categories")
        self.cat_btn.clicked.connect(self.open_category_dialog)

        self.unit_btn = QPushButton("Units")
        self.unit_btn.clicked.connect(self.open_unit_manager)

        self.label_btn = QPushButton("Print Labels")
        self.label_btn.clicked.connect(self.open_label_print)

        top_bar.addWidget(self.search_input)
        top_bar.addWidget(self.add_btn)
        top_bar.addWidget(self.import_btn)
        top_bar.addWidget(self.cat_btn)
        top_bar.addWidget(self.unit_btn)
        top_bar.addWidget(self.label_btn)

        layout.addLayout(top_bar)

        # Table
        self.table = QTableView()
        self.model = InventoryModel()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self.open_edit_dialog)

        # Context Menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)

        layout.addWidget(self.table)

        # Loading overlay
        self._overlay = LoadingOverlay(self)

    def load_data(self):
        self.all_products = self.inventory_service.get_all_products()
        self.model.update_data(self.all_products)

    def filter_data(self, text):
        if not text:
            self.model.update_data(self.all_products)
            return

        text = text.lower()
        filtered = [p for p in self.all_products if text in p.barcode.lower() or text in p.name_en.lower()]
        self.model.update_data(filtered)

    def open_add_dialog(self):
        dialog = ProductEditor(parent=self)
        if dialog.exec():
            self.load_data()

    def open_edit_dialog(self, index):
        product = self.model.products[index.row()]
        dialog = ProductEditor(product=product, parent=self)
        if dialog.exec():
            self.load_data()

    def open_category_dialog(self):
        from cbpos.ui.dialogs.category_manager import CategoryManagerDialog

        dialog = CategoryManagerDialog(parent=self)
        dialog.exec()
        self.load_data()

    def open_unit_manager(self):
        from cbpos.ui.dialogs.unit_manager import UnitManagerDialog

        dialog = UnitManagerDialog(parent=self)
        dialog.exec()

    def open_label_print(self):
        from cbpos.ui.dialogs.label_print_dialog import LabelPrintDialog

        dialog = LabelPrintDialog(parent=self)
        dialog.exec()

    def open_context_menu(self, position):
        from PyQt6.QtWidgets import QMenu
        from cbpos.ui.dialogs.stock_history_dialog import StockHistoryDialog

        index = self.table.indexAt(position)
        if not index.isValid():
            return

        menu = QMenu()
        history_action = menu.addAction("View Stock History")

        action = menu.exec(self.table.viewport().mapToGlobal(position))

        if action == history_action:
            product = self.model.products[index.row()]
            dialog = StockHistoryDialog(product, parent=self)
            dialog.exec()

    def import_csv(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Import CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return

        self.import_btn.setEnabled(False)
        self._overlay.show_loading("Importing products...")

        self._csv_worker = CsvImportWorker(self.import_service, file_path)
        self._csv_worker.progress.connect(self._on_csv_progress)
        self._csv_worker.finished.connect(self._on_csv_import_finished)
        self._csv_worker.error.connect(self._on_csv_import_error)
        self._csv_worker.start()

    def _on_csv_progress(self, current: int, total: int) -> None:
        self._overlay.set_text(f"Importing row {current} of {total}...")

    def _on_csv_import_finished(self, results: dict) -> None:
        self._overlay.hide_loading()
        self.import_btn.setEnabled(True)

        message = f"Success: {results['success']}\n" f"Failed: {results['failed']}\n" f"Skipped: {results['skipped']}"
        QMessageBox.information(self, "Import Results", message)
        self.load_data()

    def _on_csv_import_error(self, error_msg: str) -> None:
        self._overlay.hide_loading()
        self.import_btn.setEnabled(True)
        QMessageBox.critical(self, "Import Failed", f"CSV import failed: {error_msg}")
