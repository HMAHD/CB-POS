from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLineEdit,
    QHeaderView,
)

from cbpos.core.database import Database
from cbpos.core.models import Product
from cbpos.ui.dialogs.product_editor_dialog import ProductEditorDialog


class InventoryView(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by Name or Barcode...")
        self.search_input.textChanged.connect(self.refresh_data)

        btn_add = QPushButton("Add Product")
        btn_add.clicked.connect(self.add_product)

        btn_edit = QPushButton("Edit Selected")
        btn_edit.clicked.connect(self.edit_product)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh_data)

        toolbar.addWidget(self.search_input)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_refresh)
        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Barcode", "Name", "Price", "Stock"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_product)
        layout.addWidget(self.table)

    def refresh_data(self):
        query_text = self.search_input.text().strip()

        db = Database()
        with db.get_session() as session:
            query = session.query(Product)
            if query_text:
                query = query.filter(
                    (Product.name_en.ilike(f"%{query_text}%"))
                    | (Product.barcode.ilike(f"%{query_text}%"))
                )

            products = query.all()

            self.table.setRowCount(len(products))
            for i, p in enumerate(products):
                self.table.setItem(i, 0, QTableWidgetItem(str(p.id)))
                self.table.setItem(i, 1, QTableWidgetItem(p.barcode))
                self.table.setItem(i, 2, QTableWidgetItem(p.name_en))
                self.table.setItem(
                    i, 3, QTableWidgetItem(f"{p.price:.2f}")  # noqa: E231
                )
                self.table.setItem(
                    i, 4, QTableWidgetItem(f"{p.stock_qty:.3f}")  # noqa: E231
                )

    def add_product(self):
        dialog = ProductEditorDialog(parent=self)
        if dialog.exec():
            self.refresh_data()

    def edit_product(self):
        row = self.table.currentRow()
        if row < 0:
            return

        product_id = int(self.table.item(row, 0).text())

        db = Database()
        with db.get_session() as session:
            product = session.query(Product).get(product_id)
            if product:
                # Must detach or use new session in dialog, but dialog creates its own session.
                # We pass the detached object or just ID.
                # Ideally pass ID, but for simplicity passing object (detached automatically by session close?)
                # Actually, session closes at end of 'with', so 'product' is detached but valid.
                session.expunge(product)

        dialog = ProductEditorDialog(product, parent=self)
        if dialog.exec():
            self.refresh_data()
