from datetime import datetime
from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QInputDialog,
    QMessageBox,
    QSplitter,
    QDateEdit,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QLineEdit,
)
from PyQt6.QtCore import Qt, QDate
from cbpos.core.services.price_list_service import PriceListService
from cbpos.core.services.product_service import ProductService


class PriceListView(QWidget):
    def __init__(self):
        super().__init__()
        self.price_list_service = PriceListService()
        self.product_service = ProductService()
        self.current_list = None
        self.init_ui()
        self.load_lists()

    def init_ui(self):
        layout = QHBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel: List of Price Lists
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        lbl_lists = QLabel("Price Lists")
        lbl_lists.setStyleSheet("font-weight: bold; font-size: 16px;")
        left_layout.addWidget(lbl_lists)

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self.on_list_selected)
        left_layout.addWidget(self.list_widget)

        btn_add = QPushButton("Add Price List")
        btn_add.clicked.connect(self.add_price_list)
        left_layout.addWidget(btn_add)

        splitter.addWidget(left_panel)

        # Right Panel: Details and Items
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Header Info
        self.lbl_list_name = QLabel("Select a Price List")
        self.lbl_list_name.setStyleSheet("font-weight: bold; font-size: 18px; color: #00BCEB;")
        right_layout.addWidget(self.lbl_list_name)

        self.lbl_dates = QLabel("")
        right_layout.addWidget(self.lbl_dates)

        # Grid
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["ID", "Product", "Base Price", "List Price"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_item_price)
        right_layout.addWidget(self.table)

        splitter.addWidget(right_panel)
        splitter.setSizes([300, 700])

        layout.addWidget(splitter)

    def load_lists(self):
        self.list_widget.clear()
        lists = self.price_list_service.get_all_lists()
        for pl in lists:
            item = QListWidgetItem(pl.name)
            item.setData(Qt.ItemDataRole.UserRole, pl)
            self.list_widget.addItem(item)

    def on_list_selected(self, item):
        self.current_list = item.data(Qt.ItemDataRole.UserRole)
        self.lbl_list_name.setText(self.current_list.name)

        start = self.current_list.start_date.strftime("%Y-%m-%d") if self.current_list.start_date else "N/A"
        end = self.current_list.end_date.strftime("%Y-%m-%d") if self.current_list.end_date else "N/A"
        self.lbl_dates.setText(f"Valid: {start} to {end}")

        self.load_items()

    def load_items(self):
        if not self.current_list:
            return

        # Get all products
        products = self.product_service.get_all_products()
        # Get existing price list items
        list_items = self.price_list_service.get_items(self.current_list.id)
        price_map = {item.product_id: item.price for item in list_items}

        self.table.setRowCount(0)
        for p in products:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(str(p.id)))
            self.table.setItem(row, 1, QTableWidgetItem(p.name_en))
            self.table.setItem(row, 2, QTableWidgetItem("{:.2f}".format(p.price)))

            list_price = price_map.get(p.id)
            price_display = "{:.2f}".format(list_price) if list_price is not None else "-"

            price_item = QTableWidgetItem(price_display)
            if list_price is not None:
                price_item.setForeground(Qt.GlobalColor.green)

            self.table.setItem(row, 3, price_item)

    def add_price_list(self):
        dialog = PriceListDialog(self)
        if dialog.exec():
            name, start, end = dialog.get_data()
            try:
                self.price_list_service.create_price_list(name, start, end)
                self.load_lists()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def edit_item_price(self, index):
        if not self.current_list:
            return

        row = index.row()
        product_id = int(self.table.item(row, 0).text())
        product_name = self.table.item(row, 1).text()
        base_price = Decimal(self.table.item(row, 2).text())

        current_val_str = self.table.item(row, 3).text()
        current_val = float(current_val_str) if current_val_str != "-" else float(base_price)

        new_price, ok = QInputDialog.getDouble(
            self,
            "Set List Price",
            f"Enter price for {product_name}: ",
            value=current_val,
            min=0.01,
            decimals=2,
        )

        if ok:
            try:
                self.price_list_service.set_item_price(self.current_list.id, product_id, Decimal(str(new_price)))
                self.load_items()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))


class PriceListDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Price List")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit()
        self.start_date = QDateEdit()
        self.start_date.setDate(QDate.currentDate())
        self.start_date.setCalendarPopup(True)

        self.end_date = QDateEdit()
        self.end_date.setDate(QDate.currentDate().addYears(1))
        self.end_date.setCalendarPopup(True)

        form.addRow("Name:", self.name_input)
        form.addRow("Start Date:", self.start_date)
        form.addRow("End Date:", self.end_date)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        start = datetime.combine(self.start_date.date().toPyDate(), datetime.min.time())
        end = datetime.combine(self.end_date.date().toPyDate(), datetime.max.time())
        return self.name_input.text(), start, end
