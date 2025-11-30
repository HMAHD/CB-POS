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
    QMenu,
    QToolButton,
    QInputDialog,
    QCompleter,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut, QAction, QBrush, QColor
from decimal import Decimal
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.ui.dialogs.payment_dialog import PaymentDialog
from cbpos.ui.dialogs.discount_dialog import DiscountDialog
from cbpos.ui.dialogs.receipt_options_dialog import ReceiptOptionsDialog
from cbpos.core.services.config_service import ConfigService
from cbpos.ui.dialogs.customer_selection_dialog import CustomerSelectionDialog
from cbpos.ui.dialogs.advanced_search_dialog import AdvancedSearchDialog
from cbpos.ui.views.visual_pos_view import VisualPosView
from cbpos.ui.widgets.order_bar import OrderBar
from cbpos.ui.resources.icons import Icons


class SalesView(QWidget):
    def __init__(self):
        super().__init__()
        self.cart_service = CartService()
        self.product_service = ProductService()
        self.customer = None
        self.current_search_mode = "ALL"
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
        self.cart_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cart_table.customContextMenuRequested.connect(self.show_cart_context_menu)

        # Order Bar (Multi-Tab)
        self.order_bar = OrderBar()
        self.order_bar.tab_switched.connect(self.switch_to_order)
        self.order_bar.new_tab_requested.connect(self.create_new_order)
        left_layout.addWidget(self.order_bar)

        left_layout.addWidget(self.cart_table)

        # --- RIGHT PANEL (Controls) ---
        right_panel = QWidget()
        right_panel.setFixedWidth(450)
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

        # --- MODE 0: Keyboard (Search + Numpad Actions) ---
        keyboard_widget = QWidget()
        kb_layout = QVBoxLayout(keyboard_widget)
        kb_layout.setContentsMargins(0, 0, 0, 0)

        # Search Mode Widget (Phase 6)
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)

        # Mode Selector Button
        self.search_mode_btn = QToolButton()
        self.search_mode_btn.setText("★")
        self.search_mode_btn.setToolTip("Search Mode")
        self.search_mode_btn.setFixedWidth(40)
        self.search_mode_btn.setStyleSheet("font-size: 18px;")
        self.search_mode_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        # Mode Menu
        mode_menu = QMenu(self)
        mode_menu.addAction("★ All Fields", lambda: self.set_search_mode("ALL", "★"))
        mode_menu.addAction(
            "▮ Barcode Only", lambda: self.set_search_mode("BARCODE", "▮")
        )
        mode_menu.addAction("# Code/ID", lambda: self.set_search_mode("CODE", "#"))
        mode_menu.addAction("⌂ Name Only", lambda: self.set_search_mode("NAME", "⌂"))
        self.search_mode_btn.setMenu(mode_menu)

        search_layout.addWidget(self.search_mode_btn)

        # Search Input
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan or type product...")
        self.barcode_input.setStyleSheet(
            "font-size: 20px; padding: 10px; border: 2px solid #00BCEB;"
        )
        self.barcode_input.returnPressed.connect(self.process_barcode)
        search_layout.addWidget(self.barcode_input)

        kb_layout.addWidget(search_container)
        self.setup_autocomplete()

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

        # F3 for Advanced Search (Phase 6)
        self.shortcut_f3 = QShortcut(QKeySequence("F3"), self)
        self.shortcut_f3.activated.connect(self.open_advanced_search)

        # Shortcuts for Enter Key (Decentralized Handling)
        self.shortcut_enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self.shortcut_enter.activated.connect(self.process_barcode)

        self.shortcut_num_enter = QShortcut(QKeySequence(Qt.Key.Key_Enter), self)
        self.shortcut_num_enter.activated.connect(self.process_barcode)

    def showEvent(self, event):
        super().showEvent(event)
        self.barcode_input.setFocus()
        self.order_bar.refresh_tabs()

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
        if self.stack_layout.currentIndex() == 1:
            self.toggle_view()

        self.barcode_input.setText(barcode)
        self.process_barcode()

    def process_barcode(self):
        """Process product search using current search mode (Phase 6)."""
        query = self.barcode_input.text().strip()
        if not query:
            return

        # Use product_service with current search mode
        products = self.product_service.search_products(
            query, mode=self.current_search_mode
        )

        if len(products) == 1:
            self.cart_service.add_item(products[0])
            self.update_cart_display()
            self.barcode_input.clear()
        elif len(products) > 1:
            # Open advanced search with pre-filled query
            dialog = AdvancedSearchDialog(self)
            dialog.search_input.setText(query)
            dialog.perform_search()
            dialog.product_selected.connect(self.on_advanced_search_product_selected)
            dialog.exec()
            self.barcode_input.clear()
        else:
            QMessageBox.warning(self, "Not Found", "Product not found.")

    def update_cart_display(self):
        """Update cart display with visual indicators (Phase 6)."""
        self.cart_table.setRowCount(0)
        for row, item in enumerate(self.cart_service.items):
            self.cart_table.insertRow(row)

            # Product Name (with note indicator)
            name = item["product"].name_en
            if item.get("note"):
                name = f"📝 {name}"
            name_item = QTableWidgetItem(name)

            # Price Display (Strikethrough if discounted/overridden)
            if (
                item.get("original_price")
                and item["unit_price"] < item["original_price"]
            ):
                # We can't easily do rich text in QTableWidgetItem without a delegate,
                # but we can show "Old -> New" or just New.
                # User requested Strikethrough.
                # Let's use a custom widget or just text for now if simple.
                # Actually, QTableWidgetItem doesn't support HTML directly easily for strikethrough without setFont.
                # Let's try to simulate it or just show "Old -> New" for clarity if strikethrough is hard.
                # Wait, user explicitly asked for Strikethrough.
                # I will use a QFont with setStrikeOut for the original price, but I need two prices.
                # So I will format it as: "~~100.00~~ 90.00"
                # Since I can't style parts of text in one item easily, I'll just show the final price
                # and maybe a tooltip or color indication, OR use a custom cell widget.
                # Given constraints, I'll use the "~~100.00~~ 90.00" string format which is not real strikethrough.
                # BETTER APPROACH: Use a cell widget (QLabel) that supports HTML.

                lbl_price = QLabel()
                lbl_price.setText(
                    "<s>{:.2f}</s> <b>{:.2f}</b>".format(
                        item["original_price"], item["unit_price"]
                    )
                )
                lbl_price.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                lbl_price.setStyleSheet("background-color: transparent;")
                self.cart_table.setCellWidget(row, 1, lbl_price)
            else:
                self.cart_table.setItem(
                    row, 1, QTableWidgetItem(f"{item['unit_price']:.2f}")  # noqa: E231
                )

            # Highlight if discounted
            if item.get("discount_type") != "NONE" or item.get("is_manual_price"):
                bg_color = QColor(220, 255, 220)  # Pale green
                brush = QBrush(bg_color)
                name_item.setBackground(brush)

            self.cart_table.setItem(row, 0, name_item)
            # If we didn't set a cell widget for price, we need to set the item
            if not self.cart_table.cellWidget(row, 1):
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
        self.total_label.setText(f"Rs. {totals['final_total']:.2f}")  # noqa: E231
        self.cart_table.scrollToBottom()

    def select_customer(self):
        dialog = CustomerSelectionDialog(self)
        if dialog.exec():
            self.customer = dialog.selected_customer
            cust_text = f"{self.customer.name} ({self.customer.phone})"
            self.lbl_customer.setText(cust_text)
            self.lbl_points.setText(f"Points: {self.customer.loyalty_points}")

    def process_payment(self):
        totals = self.cart_service.get_totals()
        if totals["subtotal"] <= 0:
            return

        dialog = PaymentDialog(totals["subtotal"], self)
        if dialog.exec():
            payments, _ = dialog.payment_data
            customer_id = self.customer.id if self.customer else None

            try:
                success = TransactionService.process_sale(
                    self.cart_service, payments, customer_id
                )
                if success:
                    QMessageBox.information(
                        self, "Success", "Sale processed successfully!"
                    )
                    self.cart_service.clear()
                    self.update_cart_display()
                    self.barcode_input.setFocus()
                    # Reset customer
                    self.customer = None
                    self.lbl_customer.setText("Walk-in Customer")
                    self.lbl_points.setText("")
                    self.lbl_customer.setText("Walk-in Customer")
                    self.lbl_points.setText("")
                    self.order_bar.refresh_tabs()

                    # Show Receipt Options if configured
                    settings = ConfigService.get_all()
                    if settings.get("show_receipt_dialog", "True") == "True":
                        # We need the sale object. TransactionService.process_sale returns bool.
                        # We might need to fetch the last sale or modify process_sale to return the sale object.
                        # For now, let's fetch the last sale for this user/terminal.
                        # Or better, let's just assume it worked and show options for "Last Sale".
                        # Ideally TransactionService returns the Sale ID.
                        # Let's assume we can get the last sale from DB.
                        from cbpos.core.database import Database
                        from cbpos.core.models import Sale

                        db = Database()
                        with db.get_session() as session:
                            last_sale = (
                                session.query(Sale).order_by(Sale.id.desc()).first()
                            )
                            if last_sale:
                                dlg = ReceiptOptionsDialog(last_sale, self)
                                dlg.exec()
            except ValueError as e:
                QMessageBox.warning(self, "Validation Error", str(e))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Transaction failed: {str(e)}")

    def hold_bill(self):
        if not self.cart_service.items:
            return

        if TransactionService.hold_bill(self.cart_service):
            self.cart_service.clear()
            self.update_cart_display()
            self.order_bar.refresh_tabs()
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
                return

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
            print(f"Cart Voided by {authorized_user.username}")

    # --- Phase 6: Advanced Search & Cart Enhancements ---

    def set_search_mode(self, mode: str, icon: str):
        """Update search mode and icon."""
        self.current_search_mode = mode
        self.search_mode_btn.setText(icon)
        self.barcode_input.setFocus()

    def setup_autocomplete(self):
        """Setup QCompleter for product names."""
        names = self.product_service.get_top_products(100)
        completer = QCompleter(names, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.barcode_input.setCompleter(completer)

    def show_cart_context_menu(self, position):
        """Display context menu for cart items."""
        if self.cart_table.rowCount() == 0:
            return

        menu = QMenu(self)

        add_note_action = QAction("Add Note", self)
        add_note_action.triggered.connect(self.add_line_note)
        menu.addAction(add_note_action)

        change_qty_action = QAction("Change Quantity", self)
        change_qty_action.triggered.connect(self.change_line_quantity)
        menu.addAction(change_qty_action)

        discount_action = QAction("Apply Line Discount", self)
        discount_action.triggered.connect(self.apply_line_discount)
        menu.addAction(discount_action)

        price_action = QAction("Change Price", self)
        price_action.triggered.connect(self.change_line_price)
        menu.addAction(price_action)

        remove_action = QAction("Remove Item", self)
        remove_action.triggered.connect(self.remove_line_item)
        menu.addAction(remove_action)

        menu.exec(self.cart_table.viewport().mapToGlobal(position))

    def add_line_note(self):
        """Add note to selected cart line."""
        row = self.cart_table.currentRow()
        if row >= 0:
            note, ok = QInputDialog.getText(
                self, "Line Note", "Enter note for this item:"
            )
            if ok and note:
                self.cart_service.items[row]["note"] = note
                self.update_cart_display()

    def change_line_quantity(self):
        """Change quantity of selected cart line."""
        row = self.cart_table.currentRow()
        if row >= 0:
            current_qty = self.cart_service.items[row]["qty"]
            qty, ok = QInputDialog.getDouble(
                self,
                "Change Quantity",
                "Enter new quantity:",
                value=float(current_qty),
                min=0.001,
                max=999999,
                decimals=3,
            )
            if ok:
                self.cart_service.items[row]["qty"] = Decimal(str(qty))
                self.cart_service.items[row]["total"] = (
                    Decimal(str(qty)) * self.cart_service.items[row]["unit_price"]
                )
                self.update_cart_display()

    def apply_line_discount(self):
        """Apply discount to selected cart line."""
        row = self.cart_table.currentRow()
        if row >= 0:
            dialog = DiscountDialog(self)
            if dialog.exec():
                disc_type, disc_value = dialog.get_data()
                self.cart_service.apply_line_discount(row, disc_type, disc_value)
                self.update_cart_display()

    def change_line_price(self):
        """Override price of selected cart line (Manager Only)."""
        row = self.cart_table.currentRow()
        if row < 0:
            return

        # 1. Check Permission
        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.permission_service import PermissionService
        from cbpos.ui.dialogs.manager_override_dialog import ManagerOverrideDialog

        current_user = AuthService.get_current_user()
        authorized_user = current_user

        if not PermissionService.user_has_permission(current_user, "change_price"):
            # Request Override
            dialog = ManagerOverrideDialog("change_price", self)
            if dialog.exec():
                authorized_user = dialog.authorized_user
            else:
                return

        # 2. Get New Price
        current_price = self.cart_service.items[row]["unit_price"]
        new_price, ok = QInputDialog.getDouble(
            self,
            "Change Price",
            "Enter new price:",
            value=float(current_price),
            min=0.01,
            max=999999,
            decimals=2,
        )

        if ok:
            self.cart_service.override_price(row, new_price, authorized_user)
            self.update_cart_display()

    def remove_line_item(self):
        """Remove selected item from cart."""
        row = self.cart_table.currentRow()
        if row >= 0:
            del self.cart_service.items[row]
            self.update_cart_display()

    def open_advanced_search(self):
        """Open advanced search dialog (F3)."""
        dialog = AdvancedSearchDialog(self)
        dialog.product_selected.connect(self.on_advanced_search_product_selected)
        dialog.exec()
        self.barcode_input.setFocus()

    def on_advanced_search_product_selected(self, product):
        """Handle product selection from advanced search."""
        self.cart_service.add_item(product)
        self.update_cart_display()
        self.barcode_input.setFocus()

    def switch_to_order(self, suspended_id):
        """
        Switch to a held order.
        1. Hold current order (if has items).
        2. Recall target order.
        """
        # 1. Hold Current (Auto-Hold)
        if self.cart_service.items:
            # We don't ask for note here for speed, or maybe use "Auto-Hold" note
            if not TransactionService.hold_bill(self.cart_service, note="Auto-Switch"):
                QMessageBox.critical(self, "Error", "Failed to hold current order.")
                return
            self.cart_service.clear()

        # 2. Recall Target
        if TransactionService.recall_bill(suspended_id, self.cart_service):
            self.update_cart_display()
            self.order_bar.refresh_tabs()
        else:
            QMessageBox.warning(
                self, "Error", "Could not recall order. It may have been taken."
            )
            self.order_bar.refresh_tabs()

    def create_new_order(self):
        """
        Start a new order.
        1. Hold current order (if has items).
        2. Clear cart.
        """
        if self.cart_service.items:
            if TransactionService.hold_bill(self.cart_service, note="Auto-Switch"):
                self.cart_service.clear()
                self.update_cart_display()
                self.order_bar.refresh_tabs()
            else:
                QMessageBox.critical(self, "Error", "Failed to hold current order.")
        else:
            # Already empty, just refresh tabs to be sure
            self.order_bar.refresh_tabs()
            self.barcode_input.setFocus()
