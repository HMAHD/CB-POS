from decimal import Decimal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QGridLayout, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator

class PaymentDialog(QDialog):
    def __init__(self, total_amount: Decimal, parent=None):
        super().__init__(parent)
        self.total_amount = total_amount
        self.tendered_amount = Decimal("0.00")
        
        self.setWindowTitle("Payment")
        self.setFixedSize(500, 600)
        self.setStyleSheet("background-color: #001F3F; color: white;")
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # 1. Total Display
        total_title = QLabel("TOTAL TO PAY")
        total_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        total_title.setStyleSheet("color: #AAAAAA; font-size: 18px;")
        layout.addWidget(total_title)

        self.lbl_total = QLabel(f"Rs. {self.total_amount:,.2f}")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_total.setStyleSheet("font-size: 48px; font-weight: bold; color: #39FF14;")
        layout.addWidget(self.lbl_total)

        # 2. Tender Input
        self.txt_tender = QLineEdit()
        self.txt_tender.setPlaceholderText("Enter Amount")
        self.txt_tender.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_tender.setStyleSheet("""
            QLineEdit {
                font-size: 32px;
                padding: 10px;
                border: 2px solid #00BCEB;
                border-radius: 8px;
                background-color: #001226;
                color: white;
            }
            QLineEdit:focus {
                border-color: #39FF14;
            }
        """)
        # Validator to allow decimals
        self.txt_tender.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        self.txt_tender.textChanged.connect(self.calculate_change)
        self.txt_tender.returnPressed.connect(self.confirm_payment)
        layout.addWidget(self.txt_tender)

        # 3. Change Display
        self.lbl_change = QLabel("Change: Rs. 0.00")
        self.lbl_change.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_change.setStyleSheet("font-size: 24px; color: #00BCEB; font-weight: bold;")
        layout.addWidget(self.lbl_change)

        # 4. Quick Actions
        quick_layout = QGridLayout()
        quick_layout.setSpacing(10)
        
        btn_exact = QPushButton("Exact Cash (Space)")
        btn_exact.clicked.connect(self.set_exact_cash)
        btn_exact.setStyleSheet("background-color: #004d40;")
        quick_layout.addWidget(btn_exact, 0, 0, 1, 2)
        
        btn_1000 = QPushButton("Rs. 1000")
        btn_1000.clicked.connect(lambda: self.add_tender(1000))
        quick_layout.addWidget(btn_1000, 1, 0)
        
        btn_5000 = QPushButton("Rs. 5000")
        btn_5000.clicked.connect(lambda: self.add_tender(5000))
        quick_layout.addWidget(btn_5000, 1, 1)
        
        layout.addLayout(quick_layout)
        
        # 5. Bottom Buttons
        action_layout = QHBoxLayout()
        
        btn_cancel = QPushButton("Cancel (Esc)")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet("background-color: #FF4136; border: none;")
        
        btn_pay = QPushButton("PAY (Enter)")
        btn_pay.clicked.connect(self.confirm_payment)
        btn_pay.setStyleSheet("background-color: #39FF14; color: #001F3F; border: none;")
        
        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(btn_pay)
        
        layout.addLayout(action_layout)

    def calculate_change(self):
        text = self.txt_tender.text()
        try:
            tendered = Decimal(text) if text else Decimal("0.00")
        except:
            tendered = Decimal("0.00")
            
        self.tendered_amount = tendered
        change = tendered - self.total_amount
        
        if change >= 0:
            self.lbl_change.setText(f"Change: Rs. {change:,.2f}")
            self.lbl_change.setStyleSheet("font-size: 24px; color: #39FF14; font-weight: bold;")
        else:
            self.lbl_change.setText(f"Due: Rs. {abs(change):,.2f}")
            self.lbl_change.setStyleSheet("font-size: 24px; color: #FF4136; font-weight: bold;")

    def set_exact_cash(self):
        self.txt_tender.setText(str(self.total_amount))
        self.calculate_change()
        self.txt_tender.setFocus()

    def add_tender(self, amount):
        self.txt_tender.setText(str(amount))
        self.calculate_change()
        self.txt_tender.setFocus()

    def confirm_payment(self):
        if self.tendered_amount >= self.total_amount:
            self.accept()
        else:
            QMessageBox.warning(self, "Insufficient Payment", "Tendered amount is less than the total.")
            self.txt_tender.setFocus()
            self.txt_tender.selectAll()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.set_exact_cash()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
