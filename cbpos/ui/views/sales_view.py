from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLineEdit, QLabel, QPushButton, QGridLayout, QHeaderView, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIntValidator
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.cart_service import CartService

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
        
        # Numpad / Function Keys
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)
        
        # Example Function Keys
        f_keys = [
            ('F1\nHelp', 0, 0), ('F2\nQty', 0, 1), ('F3\nVoid', 0, 2),
            ('F4\nDisc', 1, 0), ('F5\nCust', 1, 1), ('F6\nHold', 1, 2)
        ]
        
        for text, r, c in f_keys:
            btn = QPushButton(text)
            btn.setFixedSize(100, 80)
            btn.setStyleSheet("background-color: #004d40; font-size: 14px;")
            grid_layout.addWidget(btn, r, c)
            
        right_layout.addLayout(grid_layout)
        right_layout.addStretch()
        
        # Total Display
        self.total_label = QLabel("Rs. 0.00")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.total_label.setStyleSheet("font-size: 48px; font-weight: bold; color: #39FF14;")
        right_layout.addWidget(self.total_label)
        
        # Add panels
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

    def ensure_focus(self):
        """Force focus back to barcode input if window is active."""
        if self.window().isActiveWindow() and not self.barcode_input.hasFocus():
            self.barcode_input.setFocus()

    def process_barcode(self):
        barcode = self.barcode_input.text().strip()
        if not barcode:
            return
            
        product = ProductService.get_by_barcode(barcode)
        if product:
            self.cart_service.add_item(product)
            self.refresh_cart()
            self.barcode_input.clear()
        else:
            # Try search if not exact match (optional, or show error)
            # For now, just show error
            QMessageBox.warning(self, "Product Not Found", f"No product found for '{barcode}'")
            self.barcode_input.selectAll()

    def refresh_cart(self):
        """Redraw the cart table."""
        self.cart_table.setRowCount(0)
        
        for item in self.cart_service.items:
            row = self.cart_table.rowCount()
            self.cart_table.insertRow(row)
            
            p = item['product']
            
            # Name
            name_item = QTableWidgetItem(p.name_en)
            self.cart_table.setItem(row, 0, name_item)
            
            # Price
            price_item = QTableWidgetItem(f"{p.price:,.2f}")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.cart_table.setItem(row, 1, price_item)
            
            # Qty
            qty_item = QTableWidgetItem(f"{item['qty']:.3f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cart_table.setItem(row, 2, qty_item)
            
            # Total
            total_item = QTableWidgetItem(f"{item['total']:,.2f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.cart_table.setItem(row, 3, total_item)
            
        # Scroll to bottom
        self.cart_table.scrollToBottom()
        
        # Update Total Label
        totals = self.cart_service.get_totals()
        self.total_label.setText(f"Rs. {totals['subtotal']:,.2f}")
