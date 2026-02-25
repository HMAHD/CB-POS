from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDateEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QSplitter,
)
from PyQt6.QtCore import Qt, QDate
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.receipt_service import ReceiptService
from cbpos.core.services.auth_service import AuthService
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker


class HistoryView(QWidget):
    """
    Transaction History view with filtering, reprinting, and refund capabilities.
    """

    def __init__(self):
        super().__init__()
        self.current_sale = None
        self.init_ui()
        self.load_today()

    def init_ui(self):
        """Setup the UI layout"""
        layout = QVBoxLayout(self)

        # Filter Bar
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("From:"))
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate())
        filter_layout.addWidget(self.from_date)

        filter_layout.addWidget(QLabel("To:"))
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        filter_layout.addWidget(self.to_date)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by Receipt# or Customer...")
        filter_layout.addWidget(self.search_input, 1)

        filter_btn = QPushButton("Filter")
        filter_btn.clicked.connect(self.apply_filter)
        filter_layout.addWidget(filter_btn)

        layout.addLayout(filter_layout)

        # Main Content: Splitter with table and details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Transaction Table
        self.transaction_table = QTableWidget()
        self.transaction_table.setColumnCount(6)
        self.transaction_table.setHorizontalHeaderLabels(
            ["Date/Time", "Receipt#", "Cashier", "Total", "Method", "Status"]
        )
        self.transaction_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.transaction_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.transaction_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.transaction_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.transaction_table.itemSelectionChanged.connect(self.on_selection_changed)
        self.transaction_table.doubleClicked.connect(self.on_double_click)
        splitter.addWidget(self.transaction_table)

        # Details Panel
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)

        details_layout.addWidget(QLabel("<b>Transaction Details</b>"))

        self.details_label = QLabel("Select a transaction to view details")
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet("padding: 10px; background: #002244;")
        details_layout.addWidget(self.details_label)

        # Line Items Table
        details_layout.addWidget(QLabel("<b>Line Items:</b>"))
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(4)
        self.items_table.setHorizontalHeaderLabels(["Product", "Qty", "Unit Price", "Subtotal"])
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.verticalHeader().setVisible(False)
        details_layout.addWidget(self.items_table)

        # Action Buttons
        action_layout = QHBoxLayout()
        self.reprint_btn = QPushButton("Reprint Receipt")
        self.reprint_btn.clicked.connect(self.reprint_receipt)
        self.reprint_btn.setEnabled(False)
        action_layout.addWidget(self.reprint_btn)

        self.refund_btn = QPushButton("Process Refund")
        self.refund_btn.clicked.connect(self.process_refund)
        self.refund_btn.setEnabled(False)
        self.refund_btn.setStyleSheet("background-color: #FF4136; color: white;")
        action_layout.addWidget(self.refund_btn)

        details_layout.addLayout(action_layout)
        details_layout.addStretch()

        splitter.addWidget(details_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def load_today(self):
        """Load today's transactions"""
        self.apply_filter()

    def apply_filter(self):
        """Apply date range and search filters"""
        from_date = self.from_date.date().toPyDate()
        to_date = self.to_date.date().toPyDate()
        search_term = self.search_input.text().strip() or None

        sales = TransactionService.get_sales_history(
            from_date=datetime.combine(from_date, datetime.min.time()),
            to_date=datetime.combine(to_date, datetime.max.time()),
            search_term=search_term,
        )

        self.populate_table(sales)

    def populate_table(self, sales):
        """Populate transaction table with sales data"""
        self.transaction_table.setRowCount(0)

        for row, sale in enumerate(sales):
            self.transaction_table.insertRow(row)

            # Date/Time
            dt_item = QTableWidgetItem(sale.date.strftime("%Y-%m-%d %H:%M"))
            dt_item.setData(Qt.ItemDataRole.UserRole, sale.id)
            self.transaction_table.setItem(row, 0, dt_item)

            # Receipt#
            self.transaction_table.setItem(row, 1, QTableWidgetItem(sale.document_number))

            # Cashier
            cashier_name = sale.user.username if sale.user else "Unknown"
            self.transaction_table.setItem(row, 2, QTableWidgetItem(cashier_name))

            # Total
            total_item = QTableWidgetItem("Rs. {:.2f}".format(sale.total_amount))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.transaction_table.setItem(row, 3, total_item)

            # Method
            self.transaction_table.setItem(row, 4, QTableWidgetItem(sale.payment_method))

            # Status
            status_item = QTableWidgetItem(sale.status)
            if sale.status == "VOID":
                status_item.setForeground(Qt.GlobalColor.red)
            elif sale.payment_method == "REFUND":
                status_item.setForeground(Qt.GlobalColor.yellow)
                status_item.setText("REFUND")
            self.transaction_table.setItem(row, 5, status_item)

    def on_selection_changed(self):
        """Handle selection change in transaction table"""
        selected_rows = self.transaction_table.selectedItems()
        if not selected_rows:
            self.current_sale = None
            self.reprint_btn.setEnabled(False)
            self.refund_btn.setEnabled(False)
            return

        # Get sale ID from first column
        sale_id = self.transaction_table.item(selected_rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)

        # Load sale details
        sale = TransactionService.get_sale_details(sale_id)
        if sale:
            self.current_sale = sale
            self.display_details(sale)
            self.reprint_btn.setEnabled(True)
            # Enable refund only for completed non-refund sales
            self.refund_btn.setEnabled(sale.status == "COMPLETED" and sale.payment_method != "REFUND")

    def display_details(self, sale):
        """Display sale details in details panel"""
        details_text = f"""
        <b>Receipt:</b> {sale.document_number}<br>
        <b>Date:</b> {sale.date.strftime("%Y-%m-%d %H:%M:%S")}<br>
        <b>Cashier:</b> {sale.user.username if sale.user else 'Unknown'}<br>
        <b>Total:</b> Rs. {sale.total_amount:.2f}<br>
        <b>Payment:</b> {sale.payment_method}<br>
        <b>Status:</b> {sale.status}
        """

        if sale.refund_of_sale_id:
            details_text += f"<br><b>Refund of Sale:</b> #{sale.refund_of_sale_id}"  # noqa: E231

        self.details_label.setText(details_text)

        # Populate line items
        self.items_table.setRowCount(0)
        for row_idx, item in enumerate(sale.items):
            self.items_table.insertRow(row_idx)

            # Product name
            product_name = item.product.name_en if item.product else "Unknown"
            self.items_table.setItem(row_idx, 0, QTableWidgetItem(product_name))

            # Quantity
            qty_item = QTableWidgetItem("{:.3f}".format(item.qty))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row_idx, 1, qty_item)

            # Unit Price
            price_item = QTableWidgetItem("{:.2f}".format(item.unit_price))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row_idx, 2, price_item)

            # Subtotal
            subtotal_item = QTableWidgetItem("{:.2f}".format(item.subtotal))
            subtotal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(row_idx, 3, subtotal_item)

    def on_double_click(self):
        """Handle double-click to show full details"""
        if self.current_sale:
            self.reprint_receipt()

    def reprint_receipt(self):
        """Reprint the selected receipt"""
        if not self.current_sale:
            return

        try:
            # Build receipt
            from cbpos.core.services.config_service import ConfigService

            settings = ConfigService.get_all()
            language = settings.get("language", "en")

            worker = PrintWorker()

            if language == "en":
                receipt_text = ReceiptService.build_receipt_text(self.current_sale)
                worker.add_job("print_receipt", receipt_text)
            else:
                receipt_image = ReceiptService.build_receipt_image(self.current_sale)
                worker.add_job("print_image", receipt_image)

            QMessageBox.information(
                self,
                "Success",
                f"Receipt {self.current_sale.document_number} sent to printer.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reprint receipt: {e}")

    def process_refund(self):
        """Process a refund for the selected sale"""
        if not self.current_sale:
            return

        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            "Confirm Refund",
            f"<b>Refund Transaction?</b><br><br>"
            f"Receipt: {self.current_sale.document_number}<br>"
            f"Amount: Rs. {self.current_sale.total_amount:.2f}<br><br>"  # noqa: E231
            f"<b style='color: #FF4136'>Warning:</b> "  # noqa: E231
            f"Stock will be restored. "
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                current_user = AuthService.get_current_user()
                if not current_user:
                    QMessageBox.warning(self, "Error", "No user logged in.")
                    return

                success = TransactionService.process_refund(self.current_sale.id, "Customer Return", current_user.id)

                if success:
                    QMessageBox.information(self, "Success", "Refund processed successfully.")
                    self.apply_filter()  # Refresh list
                else:
                    QMessageBox.critical(self, "Error", "Failed to process refund. Check logs.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Refund failed: {e}")
