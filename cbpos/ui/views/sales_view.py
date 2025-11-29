from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QLabel,
    QPushButton,
    QGridLayout,
    QHeaderView,
    QMessageBox,
    QStackedLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.ui.dialogs.payment_dialog import PaymentDialog
from cbpos.ui.dialogs.customer_selection_dialog import (  # noqa: F401
    CustomerSelectionDialog,
)
from cbpos.ui.views.visual_pos_view import VisualPosView
from cbpos.ui.resources.icons import Icons


class SalesView(QWidget):
    def __init__(self):
        super().__init__()
        self.cart_service = CartService()
        self.customer = None
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- LEFT PANEL (Cart) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # Cart Table
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(4)
        self.cart_table.setHorizontalHeaderLabels(["Item", "Price", "Qty", "Total"])
        self.cart_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setShowGrid(False)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        left_layout.addWidget(self.cart_table)

        # --- RIGHT PANEL (Controls) ---
        right_panel = QWidget()
        right_panel.setFixedWidth(450)  # Slightly wider for visual grid
        right_layout = QVBoxLayout(right_panel)

        # 1. Header (Customer + Toggle)
        header_layout = QHBoxLayout()

        self.lbl_customer = QLabel("Walk-in Customer")
        self.lbl_customer.setStyleSheet("font-weight: bold; font-size: 14px;")

        btn_cust = QPushButton("Select")
        btn_cust.setFixedWidth(80)
        btn_cust.clicked.connect(self.select_customer)

        self.btn_toggle_view = QPushButton()
        self.btn_toggle_view.setIcon(Icons.get("fa5s.th"))
        self.btn_toggle_view.setToolTip("Toggle Visual Mode")
        self.btn_toggle_view.setCheckable(True)
        self.btn_toggle_view.setFixedWidth(40)
        self.btn_toggle_view.clicked.connect(self.toggle_view)

        header_layout.addWidget(self.lbl_customer)
        header_layout.addWidget(btn_cust)
        header_layout.addWidget(self.btn_toggle_view)

        right_layout.addLayout(header_layout)

        self.lbl_points = QLabel("")
        self.lbl_points.setStyleSheet("color: #FFDC00; font-weight: bold;")
        right_layout.addWidget(self.lbl_points)

        right_layout.addSpacing(10)

        # 2. Stacked Content (Keyboard vs Visual)
        self.stack_layout = QStackedLayout()

        # --- MODE 0: Keyboard (Barcode + Numpad Actions) ---
        keyboard_widget = QWidget()
        kb_layout = QVBoxLayout(keyboard_widget)
        kb_layout.setContentsMargins(0, 0, 0, 0)

        # Barcode Input
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan Barcode...")
        self.barcode_input.setStyleSheet(
            "font-size: 20px; padding: 10px; border: 2px solid #00BCEB;"
        )
        self.barcode_input.returnPressed.connect(self.process_barcode)
        kb_layout.addWidget(self.barcode_input)

        kb_layout.addSpacing(20)

        # Action Buttons
        btn_layout = QGridLayout()

        self.btn_pay = QPushButton("PAY (F5)")
        self.btn_pay.setStyleSheet(
            "background-color: #39FF14; color: black; font-weight: bold; padding: 20px;"
        )
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

        kb_layout.addLayout(btn_layout)
        kb_layout.addStretch()

        # --- MODE 1: Visual POS ---
        self.visual_pos = VisualPosView()
        self.visual_pos.item_clicked.connect(self.on_visual_item_clicked)

        # Add to stack
        self.stack_layout.addWidget(keyboard_widget)
        self.stack_layout.addWidget(self.visual_pos)

        right_layout.addLayout(self.stack_layout)

        # Total Display (Always Visible)
        self.total_label = QLabel("Rs. 0.00")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.total_label.setStyleSheet(
            "font-size: 64px; font-weight: bold; color: #39FF14; margin-top: 20px;"
        )
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

        # Shortcuts for Enter Key (Decentralized Handling)
        self.shortcut_enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self.shortcut_enter.activated.connect(self.process_barcode)

        self.shortcut_num_enter = QShortcut(QKeySequence(Qt.Key.Key_Enter), self)
        self.shortcut_num_enter.activated.connect(self.process_barcode)

    def showEvent(self, event):
        super().showEvent(event)
        self.barcode_input.setFocus()

    def toggle_view(self):
        """Toggle between Keyboard and Visual modes."""
        if self.stack_layout.currentIndex() == 0:
            self.stack_layout.setCurrentIndex(1)
            self.btn_toggle_view.setChecked(True)
        else:
            self.stack_layout.setCurrentIndex(0)
            self.btn_toggle_view.setChecked(False)
            self.barcode_input.setFocus()

    def on_visual_item_clicked(self, product):
        """Handle item click from Visual POS."""
        self.cart_service.add_item(product)
        self.update_cart_display()

    def process_barcode_external(self, barcode):
        """Handle barcode from global scanner hook."""
        # Ensure we are in keyboard mode or just process it?
        # Ideally, scanner should work in both modes.
        # If in visual mode, we might want to just add item directly without input field focus
        # But for now, let's switch to keyboard mode to show feedback
        if self.stack_layout.currentIndex() == 1:
            self.toggle_view()

        self.barcode_input.setText(barcode)
        self.process_barcode()

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
                QMessageBox.information(
                    self,
                    "Multiple Found",
                    "Multiple products found. Please refine search.",
                )
            else:
                QMessageBox.warning(self, "Not Found", "Product not found.")

    def update_cart_display(self):
        self.cart_table.setRowCount(0)
        for row, item in enumerate(self.cart_service.items):
            self.cart_table.insertRow(row)
            self.cart_table.setItem(row, 0, QTableWidgetItem(item["product"].name_en))
            self.cart_table.setItem(
                row, 1, QTableWidgetItem(f"{item['unit_price']:.2f}")  # noqa: E231
            )
            self.cart_table.setItem(
                row, 2, QTableWidgetItem(f"{item['qty']:.3f}")  # noqa: E231
            )
            self.cart_table.setItem(
                row, 3, QTableWidgetItem(f"{item['total']:.2f}")  # noqa: E231
            )

        totals = self.cart_service.get_totals()
        self.total_label.setText(f"Rs. {totals['subtotal']:.2f}")  # noqa: E231
        self.cart_table.scrollToBottom()

    def select_customer(self):
        dialog = CustomerSelectionDialog(self)
        if dialog.exec():
            self.customer = dialog.selected_customer
            cust_text = f"{self.customer.name} ({self.customer.phone})"
            self.lbl_customer.setText(cust_text)
            self.lbl_points.setText(f"Points: {self.customer.loyalty_points}")
        else:
            # Keep previous customer selection on cancel
            pass

    def process_payment(self):
        totals = self.cart_service.get_totals()
        if totals["subtotal"] <= 0:
            return

        dialog = PaymentDialog(totals["subtotal"], self)
        if dialog.exec():
            payments, _ = dialog.payment_data
            # Use selected customer ID if available
            customer_id = self.customer.id if self.customer else None

            success = TransactionService.process_sale(
                self.cart_service, payments, customer_id
            )
            if success:
                QMessageBox.information(self, "Success", "Sale processed successfully!")
                self.cart_service.clear()
                self.update_cart_display()
                self.barcode_input.setFocus()
                # Reset customer
                self.customer = None
                self.lbl_customer.setText("Walk-in Customer")
                self.lbl_points.setText("")
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
            suspended = (
                session.query(SuspendedTransaction)
                .order_by(SuspendedTransaction.timestamp.desc())
                .first()
            )
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
        # 1. Check Permission
        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.permission_service import PermissionService
        from cbpos.ui.dialogs.manager_override_dialog import ManagerOverrideDialog

        current_user = AuthService.get_current_user()
        authorized_user = current_user

        if not PermissionService.user_has_permission(current_user, "can_void_sale"):
            # Request Override
            dialog = ManagerOverrideDialog("can_void_sale", self)
            if dialog.exec():
                authorized_user = dialog.authorized_user
            else:
                return  # Cancelled

        # 2. Confirm Void
        reply = QMessageBox.question(
            self,
            "Void Bill",
            "Are you sure you want to clear the current bill?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.cart_service.clear()
            self.update_cart_display()

            # Log the action (Optional)
            print(f"Cart Voided by {authorized_user.username}")
