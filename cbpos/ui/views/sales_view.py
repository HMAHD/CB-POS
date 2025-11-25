from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLineEdit, QLabel, QPushButton, QGridLayout, QHeaderView, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.ui.dialogs.payment_dialog import PaymentDialog

class SalesView(QWidget):
    def __init__(self):
        super().__init__()
        self.cart_service = CartService()
        self.init_ui()
        
        # Focus Trap Timer
        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self.ensure_focus)
        self.focus_timer.start(2000) # Check every 2 seconds

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        
        # --- LEFT PANEL (Cart) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Cart Table
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(4)
        self.cart_table.setHorizontalHeaderLabels(["Item", "Price", "Qty", "Total"])
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.setStyleSheet("""
            QTableWidget {
                font-size: 16px;
                selection-background-color: #00BCEB;
                selection-color: #001F3F;
            }
            QHeaderView::section {
                background-color: #003366;
                color: white;
                font-weight: bold;
                padding: 5px;
            }
        """)
        left_layout.addWidget(self.cart_table)
        
        # --- RIGHT PANEL (Controls) ---
        right_panel = QWidget()
        right_panel.setFixedWidth(400)
        right_layout = QVBoxLayout(right_panel)
        
        # Barcode Input
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan Barcode...")
        self.barcode_input.setStyleSheet("font-size: 20px; padding: 10px; border: 2px solid #00BCEB;")
        self.barcode_input.returnPressed.connect(self.process_barcode)
        right_layout.addWidget(self.barcode_input)
        
        right_layout.addSpacing(20)
        
        # Buttons
        btn_layout = QGridLayout()
        
        self.btn_pay = QPushButton("PAY (F5)")
        self.btn_pay.setStyleSheet("background-color: #39FF14; color: black; font-weight: bold; padding: 20px;")
        self.btn_pay.clicked.connect(self.process_payment)
        btn_layout.addWidget(self.btn_pay, 0, 0, 1, 2)
        
        self.btn_hold = QPushButton("HOLD (F6)")
        self.btn_hold.setStyleSheet("background-color: #FFDC00; color: black;")
        self.btn_hold.clicked.connect(self.hold_bill)
        btn_layout.addWidget(self.btn_hold, 1, 0)
        
        self.btn_recall = QPushButton("RECALL (F7)")
        self.btn_recall.setStyleSheet("background-color: #0074D9; color: white;")
        self.btn_recall.clicked.connect(self.recall_bill)
        btn_layout.addWidget(self.btn_recall, 1, 1)
        
        self.btn_void = QPushButton("VOID (F4)")
        self.btn_void.setStyleSheet("background-color: #FF4136; color: white;")
        self.btn_void.clicked.connect(self.void_bill)
        btn_layout.addWidget(self.btn_void, 2, 0, 1, 2)
        
        # Temporary Inventory Button
        self.btn_inv = QPushButton("INVENTORY")
        self.btn_inv.setStyleSheet("background-color: #AAAAAA; color: black;")
        self.btn_inv.clicked.connect(self.open_inventory)
        btn_layout.addWidget(self.btn_inv, 3, 0, 1, 2)

        right_layout.addLayout(btn_layout)
        right_layout.addStretch()
        
        # Total Display
        self.total_label = QLabel("Rs. 0.00")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.total_label.setStyleSheet("font-size: 48px; font-weight: bold; color: #39FF14;")
        right_layout.addWidget(self.total_label)
        
        # Add panels
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

        # Shortcuts
        self.shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        self.shortcut_f5.activated.connect(self.process_payment)
        
        self.shortcut_f6 = QShortcut(QKeySequence("F6"), self)
        self.shortcut_f6.activated.connect(self.hold_bill)
        
        self.shortcut_f7 = QShortcut(QKeySequence("F7"), self)
        self.shortcut_f7.activated.connect(self.recall_bill)
        
        self.shortcut_f4 = QShortcut(QKeySequence("F4"), self)
        self.shortcut_f4.activated.connect(self.void_bill)

    def ensure_focus(self):
        """Force focus back to barcode input if window is active."""
        if self.window().isActiveWindow() and not self.barcode_input.hasFocus():
            # Only force focus if no dialog is open
            # This is a simple check, might need improvement
            self.barcode_input.setFocus()

    def process_barcode(self):
        barcode = self.barcode_input.text().strip()
        if not barcode:
            return
            
        product = ProductService.get_by_barcode(barcode)
        if product:
            self.cart_service.add_item(product)
            self.update_cart_display()
            self.barcode_input.clear()
        else:
            # Try search if not barcode
            products = ProductService.search(barcode)
            if len(products) == 1:
                self.cart_service.add_item(products[0])
                self.update_cart_display()
                self.barcode_input.clear()
            elif len(products) > 1:
                QMessageBox.information(self, "Multiple Found", "Multiple products found. Please refine search.")
            else:
                QMessageBox.warning(self, "Not Found", "Product not found.")

    def update_cart_display(self):
        self.cart_table.setRowCount(0)
        for row, item in enumerate(self.cart_service.items):
            self.cart_table.insertRow(row)
            self.cart_table.setItem(row, 0, QTableWidgetItem(item['product'].name_en))
            self.cart_table.setItem(row, 1, QTableWidgetItem(f"{item['unit_price']:.2f}"))
            self.cart_table.setItem(row, 2, QTableWidgetItem(f"{item['qty']:.3f}"))
            self.cart_table.setItem(row, 3, QTableWidgetItem(f"{item['total']:.2f}"))
        
        totals = self.cart_service.get_totals()
        self.total_label.setText(f"Rs. {totals['subtotal']:.2f}")
        self.cart_table.scrollToBottom()

    def process_payment(self):
        totals = self.cart_service.get_totals()
        if totals['subtotal'] <= 0:
            return

        dialog = PaymentDialog(totals['subtotal'], self)
        if dialog.exec():
            tendered = dialog.tendered_amount
            success = TransactionService.process_sale(self.cart_service, "CASH", tendered)
            if success:
                QMessageBox.information(self, "Success", "Sale processed successfully!")
                self.cart_service.clear()
                self.update_cart_display()
                self.barcode_input.setFocus()
            else:
                QMessageBox.critical(self, "Error", "Transaction failed!")

    def hold_bill(self):
        if not self.cart_service.items:
            return
        
        if TransactionService.hold_bill(self.cart_service):
            self.cart_service.clear()
            self.update_cart_display()
            QMessageBox.information(self, "Held", "Bill put on hold.")
        else:
            QMessageBox.critical(self, "Error", "Failed to hold bill.")

    def recall_bill(self):
        from cbpos.core.database import Database
        from cbpos.core.models import SuspendedTransaction
        
        db = Database()
        with db.get_session() as session:
            suspended = session.query(SuspendedTransaction).order_by(SuspendedTransaction.timestamp.desc()).first()
            if not suspended:
                QMessageBox.information(self, "Empty", "No held bills found.")
                return
            
            sus_id = suspended.id
            
        if TransactionService.recall_bill(sus_id, self.cart_service):
            self.update_cart_display()
            QMessageBox.information(self, "Recalled", "Bill recalled.")
        else:
            QMessageBox.critical(self, "Error", "Failed to recall bill.")

    def void_bill(self):
        reply = QMessageBox.question(self, "Void Bill", "Are you sure you want to clear the current bill?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self.ensure_focus)
        self.focus_timer.start(2000) # Check every 2 seconds

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        
        # --- LEFT PANEL (Cart) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Cart Table
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(4)
        self.cart_table.setHorizontalHeaderLabels(["Item", "Price", "Qty", "Total"])
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.setStyleSheet("""
            QTableWidget {
                font-size: 16px;
                selection-background-color: #00BCEB;
                selection-color: #001F3F;
            }
            QHeaderView::section {
                background-color: #003366;
                color: white;
                font-weight: bold;
                padding: 5px;
            }
        """)
        left_layout.addWidget(self.cart_table)
        
        # --- RIGHT PANEL (Controls) ---
        right_panel = QWidget()
        right_panel.setFixedWidth(400)
        right_layout = QVBoxLayout(right_panel)
        
        # Barcode Input
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan Barcode...")
        self.barcode_input.setStyleSheet("font-size: 20px; padding: 10px; border: 2px solid #00BCEB;")
        self.barcode_input.returnPressed.connect(self.process_barcode)
        right_layout.addWidget(self.barcode_input)
        
        right_layout.addSpacing(20)
        
        # Buttons
        btn_layout = QGridLayout()
        
        self.btn_pay = QPushButton("PAY (F5)")
        self.btn_pay.setStyleSheet("background-color: #39FF14; color: black; font-weight: bold; padding: 20px;")
        self.btn_pay.clicked.connect(self.process_payment)
        btn_layout.addWidget(self.btn_pay, 0, 0, 1, 2)
        
        self.btn_hold = QPushButton("HOLD (F6)")
        self.btn_hold.setStyleSheet("background-color: #FFDC00; color: black;")
        self.btn_hold.clicked.connect(self.hold_bill)
        btn_layout.addWidget(self.btn_hold, 1, 0)
        
        self.btn_recall = QPushButton("RECALL (F7)")
        self.btn_recall.setStyleSheet("background-color: #0074D9; color: white;")
        self.btn_recall.clicked.connect(self.recall_bill)
        btn_layout.addWidget(self.btn_recall, 1, 1)
        
        self.btn_void = QPushButton("VOID (F4)")
        self.btn_void.setStyleSheet("background-color: #FF4136; color: white;")
        self.btn_void.clicked.connect(self.void_bill)
        btn_layout.addWidget(self.btn_void, 2, 0, 1, 2)
        
        # Temporary Inventory Button
        self.btn_inv = QPushButton("INVENTORY")
        self.btn_inv.setStyleSheet("background-color: #AAAAAA; color: black;")
        self.btn_inv.clicked.connect(self.open_inventory)
        btn_layout.addWidget(self.btn_inv, 3, 0, 1, 2)

        right_layout.addLayout(btn_layout)
        right_layout.addStretch()
        
        # Total Display
        self.total_label = QLabel("Rs. 0.00")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.total_label.setStyleSheet("font-size: 48px; font-weight: bold; color: #39FF14;")
        right_layout.addWidget(self.total_label)
        
        # Add panels
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

        # Shortcuts
        self.shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        self.shortcut_f5.activated.connect(self.process_payment)
        
        self.shortcut_f6 = QShortcut(QKeySequence("F6"), self)
        self.shortcut_f6.activated.connect(self.hold_bill)
        
        self.shortcut_f7 = QShortcut(QKeySequence("F7"), self)
        self.shortcut_f7.activated.connect(self.recall_bill)
        
        self.shortcut_f4 = QShortcut(QKeySequence("F4"), self)
        self.shortcut_f4.activated.connect(self.void_bill)

    def ensure_focus(self):
        """Force focus back to barcode input if window is active."""
        if self.window().isActiveWindow() and not self.barcode_input.hasFocus():
            # Only force focus if no dialog is open
            # This is a simple check, might need improvement
            self.barcode_input.setFocus()

    def process_barcode(self):
        barcode = self.barcode_input.text().strip()
        if not barcode:
            return
            
        product = ProductService.get_by_barcode(barcode)
        if product:
            self.cart_service.add_item(product)
            self.update_cart_display()
            self.barcode_input.clear()
        else:
            # Try search if not barcode
            products = ProductService.search(barcode)
            if len(products) == 1:
                self.cart_service.add_item(products[0])
                self.update_cart_display()
                self.barcode_input.clear()
            elif len(products) > 1:
                QMessageBox.information(self, "Multiple Found", "Multiple products found. Please refine search.")
            else:
                QMessageBox.warning(self, "Not Found", "Product not found.")

    def update_cart_display(self):
        self.cart_table.setRowCount(0)
        for row, item in enumerate(self.cart_service.items):
            self.cart_table.insertRow(row)
            self.cart_table.setItem(row, 0, QTableWidgetItem(item['product'].name_en))
            self.cart_table.setItem(row, 1, QTableWidgetItem(f"{item['unit_price']:.2f}"))
            self.cart_table.setItem(row, 2, QTableWidgetItem(f"{item['qty']:.3f}"))
            self.cart_table.setItem(row, 3, QTableWidgetItem(f"{item['total']:.2f}"))
        
        totals = self.cart_service.get_totals()
        self.total_label.setText(f"Rs. {totals['subtotal']:.2f}")
        self.cart_table.scrollToBottom()

    def process_payment(self):
        totals = self.cart_service.get_totals()
        if totals['subtotal'] <= 0:
            return

        dialog = PaymentDialog(totals['subtotal'], self)
        if dialog.exec():
            tendered = dialog.tendered_amount
            success = TransactionService.process_sale(self.cart_service, "CASH", tendered)
            if success:
                QMessageBox.information(self, "Success", "Sale processed successfully!")
                self.cart_service.clear()
                self.update_cart_display()
                self.barcode_input.setFocus()
            else:
                QMessageBox.critical(self, "Error", "Transaction failed!")

    def hold_bill(self):
        if not self.cart_service.items:
            return
        
        if TransactionService.hold_bill(self.cart_service):
            self.cart_service.clear()
            self.update_cart_display()
            QMessageBox.information(self, "Held", "Bill put on hold.")
        else:
            QMessageBox.critical(self, "Error", "Failed to hold bill.")

    def recall_bill(self):
        from cbpos.core.database import Database
        from cbpos.core.models import SuspendedTransaction
        
        db = Database()
        with db.get_session() as session:
            suspended = session.query(SuspendedTransaction).order_by(SuspendedTransaction.timestamp.desc()).first()
            if not suspended:
                QMessageBox.information(self, "Empty", "No held bills found.")
                return
            
            sus_id = suspended.id
            
        if TransactionService.recall_bill(sus_id, self.cart_service):
            self.update_cart_display()
            QMessageBox.information(self, "Recalled", "Bill recalled.")
        else:
            QMessageBox.critical(self, "Error", "Failed to recall bill.")

    def void_bill(self):
        reply = QMessageBox.question(self, "Void Bill", "Are you sure you want to clear the current bill?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.cart_service.clear()
            self.update_cart_display()

    def open_inventory(self):
        # Temporary access to Inventory
        from cbpos.ui.views.inventory_master_view import InventoryMasterView
        self.inventory_window = InventoryMasterView()
        self.inventory_window.resize(1024, 768)
        self.inventory_window.show()
