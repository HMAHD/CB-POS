from decimal import Decimal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QGridLayout, QMessageBox, QWidget, QListWidget, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator
from cbpos.core.database import Database
from cbpos.core.models import Customer

class PaymentDialog(QDialog):
    def __init__(self, total_amount: Decimal, parent=None):
        super().__init__(parent)
        self.total_amount = total_amount
        self.payments = [] # List of {'method': str, 'amount': Decimal}
        self.customer_id = None
        
        self.setWindowTitle("Payment")
        self.setFixedSize(600, 700)
        self.setStyleSheet("background-color: #001F3F; color: white;")
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 1. Header Info
        header_layout = QHBoxLayout()
        
        lbl_total_title = QLabel("TOTAL DUE:")
        lbl_total_title.setStyleSheet("font-size: 18px; color: #AAAAAA;")
        self.lbl_total = QLabel(f"Rs. {self.total_amount:,.2f}")
        self.lbl_total.setStyleSheet("font-size: 32px; font-weight: bold; color: #39FF14;")
        
        header_layout.addWidget(lbl_total_title)
        header_layout.addWidget(self.lbl_total)
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # 2. Remaining Balance
        self.lbl_remaining = QLabel(f"Remaining: Rs. {self.total_amount:,.2f}")
        self.lbl_remaining.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_remaining.setStyleSheet("font-size: 24px; color: #FF4136; font-weight: bold; border: 1px solid #FF4136; padding: 10px;")
        layout.addWidget(self.lbl_remaining)

        # 3. Payment Entry
        entry_group = QWidget()
        entry_group.setStyleSheet("background-color: #003366; border-radius: 8px;")
        entry_layout = QGridLayout(entry_group)
        
        entry_layout.addWidget(QLabel("Method:"), 0, 0)
        self.cmb_method = QComboBox()
        self.cmb_method.addItems(["CASH", "CARD", "CREDIT"])
        self.cmb_method.setStyleSheet("font-size: 18px; padding: 5px; color: black; background-color: white;")
        self.cmb_method.currentTextChanged.connect(self.on_method_change)
        entry_layout.addWidget(self.cmb_method, 0, 1)
        
        entry_layout.addWidget(QLabel("Amount:"), 1, 0)
        self.txt_amount = QLineEdit()
        self.txt_amount.setPlaceholderText("Amount")
        self.txt_amount.setStyleSheet("font-size: 18px; padding: 5px; color: black; background-color: white;")
        self.txt_amount.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        self.txt_amount.returnPressed.connect(self.add_payment)
        entry_layout.addWidget(self.txt_amount, 1, 1)
        
        # Customer Selection (Hidden by default)
        self.lbl_customer = QLabel("Customer:")
        self.cmb_customer = QComboBox()
        self.cmb_customer.setStyleSheet("font-size: 18px; padding: 5px; color: black; background-color: white;")
        self.load_customers()
        
        self.lbl_customer.setVisible(False)
        self.cmb_customer.setVisible(False)
        
        entry_layout.addWidget(self.lbl_customer, 2, 0)
        entry_layout.addWidget(self.cmb_customer, 2, 1)
        
        btn_add = QPushButton("Add Payment")
        btn_add.setStyleSheet("background-color: #00BCEB; color: black; font-weight: bold; padding: 10px;")
        btn_add.clicked.connect(self.add_payment)
        entry_layout.addWidget(btn_add, 3, 0, 1, 2)
        
        layout.addWidget(entry_group)

        # 4. Payment List
        self.list_payments = QListWidget()
        self.list_payments.setStyleSheet("font-size: 16px; color: black; background-color: white;")
        layout.addWidget(self.list_payments)

        # 5. Bottom Actions
        action_layout = QHBoxLayout()
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #FF4136; color: white; padding: 15px;")
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_finish = QPushButton("FINISH SALE")
        self.btn_finish.setStyleSheet("background-color: #AAAAAA; color: black; padding: 15px; font-weight: bold;")
        self.btn_finish.setEnabled(False)
        self.btn_finish.clicked.connect(self.accept)
        
        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(self.btn_finish)
        
        layout.addLayout(action_layout)
        
        # Set initial amount
        self.txt_amount.setText(str(self.total_amount))
        self.txt_amount.setFocus()
        self.txt_amount.selectAll()

    def load_customers(self):
        db = Database()
        with db.get_session() as session:
            customers = session.query(Customer).all()
            self.customers_map = {c.name: c.id for c in customers}
            self.cmb_customer.addItems(list(self.customers_map.keys()))

    def on_method_change(self, method):
        is_credit = (method == "CREDIT")
        self.lbl_customer.setVisible(is_credit)
        self.cmb_customer.setVisible(is_credit)

    def add_payment(self):
        try:
            amount = Decimal(self.txt_amount.text())
        except:
            return

        if amount <= 0:
            return

        method = self.cmb_method.currentText()
        
        # If Credit, validate customer selected
        if method == "CREDIT":
            cust_name = self.cmb_customer.currentText()
            if not cust_name:
                QMessageBox.warning(self, "Error", "Please select a customer for Credit sale.")
                return
            self.customer_id = self.customers_map.get(cust_name)

        self.payments.append({'method': method, 'amount': amount})
        self.list_payments.addItem(f"{method}: Rs. {amount:,.2f}")
        
        self.update_balance()
        self.txt_amount.clear()
        self.txt_amount.setFocus()

    def update_balance(self):
        paid = sum(p['amount'] for p in self.payments)
        remaining = self.total_amount - paid
        
        if remaining > 0:
            self.lbl_remaining.setText(f"Remaining: Rs. {remaining:,.2f}")
            self.lbl_remaining.setStyleSheet("font-size: 24px; color: #FF4136; font-weight: bold; border: 1px solid #FF4136; padding: 10px;")
            self.btn_finish.setEnabled(False)
            self.btn_finish.setStyleSheet("background-color: #AAAAAA; color: black; padding: 15px; font-weight: bold;")
            self.txt_amount.setText(str(remaining))
        else:
            change = abs(remaining)
            self.lbl_remaining.setText(f"Change: Rs. {change:,.2f}")
            self.lbl_remaining.setStyleSheet("font-size: 24px; color: #39FF14; font-weight: bold; border: 1px solid #39FF14; padding: 10px;")
            self.btn_finish.setEnabled(True)
            self.btn_finish.setStyleSheet("background-color: #39FF14; color: black; padding: 15px; font-weight: bold;")
            self.btn_finish.setFocus()

    @property
    def payment_data(self):
        return self.payments, self.customer_id
