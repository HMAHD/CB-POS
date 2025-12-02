from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QLabel,
    QHeaderView,
    QMessageBox,
    QMenu,
    QToolButton,
    QInputDialog,
    QCompleter,
    QFrame,
    QSplitter,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtGui import QKeySequence, QShortcut, QAction, QBrush, QColor, QPixmap
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
from cbpos.ui.dialogs.customer_quick_add import CustomerQuickAddDialog
from cbpos.core.services.customer_service import CustomerService
from cbpos.ui.widgets.order_bar import OrderBar
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.side_menu import SideMenu
from pathlib import Path
from cbpos.ui.widgets.action_panel import ActionPanel
from cbpos.core.utils.formatters import format_currency


class SalesView(QWidget):
    def __init__(self):
        super().__init__()
        self.cart_service = CartService()
        self.product_service = ProductService()
        self.customer_service = CustomerService()
        self.customer = None
        self.current_search_mode = ConfigService.get("default_search_mode") or "ALL"
        self.init_ui()

        # Side Menu Overlay
        self.side_menu = SideMenu(self)
        self.side_menu.setVisible(False)

        # Animation
        self.menu_animation = QPropertyAnimation(self.side_menu, b"pos")
        self.menu_animation.setDuration(300)
        self.menu_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Install Event Filter for clicking outside
        self.installEventFilter(self)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- HEADER ---
        header_widget = QWidget()
        header_widget.setFixedHeight(50)
        header_widget.setStyleSheet("background-color: #001226; border-bottom: 1px solid #003366;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 0, 20, 0)

        # Brand (Logo)
        lbl_logo = QLabel()
        logo_path = Path("assets/logo/cover_black.png")

        if logo_path.exists():
            logo_pixmap = QPixmap(str(logo_path))
            lbl_logo.setPixmap(logo_pixmap.scaledToHeight(35, Qt.TransformationMode.SmoothTransformation))
        else:
            lbl_logo.setText("CEYLON BYTE POS")  # Fallback
            lbl_logo.setStyleSheet("color: #00BCEB; font-weight: bold; font-size: 16px;")
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(lbl_logo)

        header_layout.addStretch()

        # Menu Button
        self.menu_button = QToolButton()
        self.menu_button.setObjectName("menu_button")
        self.menu_button.setIcon(Icons.get("fa5s.ellipsis-v"))
        self.menu_button.setStyleSheet("border: none; background: transparent;")
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.clicked.connect(self.toggle_side_menu)
        header_layout.addWidget(self.menu_button)

        main_layout.addWidget(header_widget)

        # --- BODY (Splitter) ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(10)  # For styling
        self.splitter.setChildrenCollapsible(False)

        main_layout.addWidget(self.splitter)

        # ==========================
        # LEFT PANEL (Cart & Totals) - 75%
        # ==========================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(10)

        # 1. Search Bar (Top)
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)

        # Mode Selector (Segmented Control)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.buttonClicked.connect(self.on_search_mode_changed)

        modes = [
            ("ALL", "*", "All"),
            ("BARCODE", "||||", "Barcode"),
            ("CODE", "#", "Code"),
            ("NAME", "Tag", "Name"),
        ]

        for mode_id, text, tooltip in modes:
            btn = QToolButton()
            btn.setText(text)
            btn.setCheckable(True)
            btn.setToolTip(tooltip)
            btn.setFixedSize(40, 40)
            btn.setProperty("mode", mode_id)
            btn.setProperty("class", "SearchModeBtn")  # For styling

            if mode_id == self.current_search_mode:
                btn.setChecked(True)

            self.mode_group.addButton(btn)
            search_layout.addWidget(btn)

        search_layout.addSpacing(10)

        # Search Input
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan or type product... (Enter)")
        self.barcode_input.setFixedHeight(40)
        self.barcode_input.setStyleSheet(
            "font-size: 16px; padding: 5px; border: 1px solid #555; " "background-color: #222; color: white;"
        )
        self.barcode_input.returnPressed.connect(self.process_barcode)
        search_layout.addWidget(self.barcode_input)

        self.setup_autocomplete()
        left_layout.addWidget(search_container)

        # 2. Cart Table (Center)
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(4)
        self.cart_table.setHorizontalHeaderLabels(["Item", "Price", "Qty", "Total"])
        self.cart_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cart_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )  # Item name flexible
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setShowGrid(False)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cart_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cart_table.customContextMenuRequested.connect(self.show_cart_context_menu)
        self.cart_table.setAlternatingRowColors(True)
        # Styling handled in theme.qss, but setting object name for specificity
        # if needed
        self.cart_table.setObjectName("CartTable")

        left_layout.addWidget(self.cart_table)

        # 3. Order Bar (Tabs)
        self.order_bar = OrderBar()
        self.order_bar.tab_switched.connect(self.switch_to_order)
        self.order_bar.new_tab_requested.connect(self.create_new_order)
        left_layout.addWidget(self.order_bar)

        # 4. Totals Widget (Bottom)
        total_widget = QFrame()
        total_widget.setStyleSheet("background-color: #252526; border-top: 2px solid #3E3E42; border-radius: 5px;")
        total_layout = QHBoxLayout(total_widget)
        total_layout.setContentsMargins(20, 10, 20, 10)

        # Subtotals (Left)
        subtotal_layout = QVBoxLayout()
        self.lbl_item_count = QLabel("Items: 0")
        self.lbl_subtotal = QLabel("Subtotal: 0.00")
        self.lbl_discount = QLabel("Disc: 0.00")
        self.lbl_tax = QLabel("Tax: 0.00")

        # Styling for small labels
        small_label_style = "color: #AAAAAA; font-size: 14px;"
        self.lbl_item_count.setStyleSheet(small_label_style)
        self.lbl_subtotal.setStyleSheet(small_label_style)
        self.lbl_discount.setStyleSheet(small_label_style)
        self.lbl_tax.setStyleSheet(small_label_style)

        subtotal_layout.addWidget(self.lbl_item_count)
        subtotal_layout.addWidget(self.lbl_subtotal)
        subtotal_layout.addWidget(self.lbl_discount)
        subtotal_layout.addWidget(self.lbl_tax)
        total_layout.addLayout(subtotal_layout)

        total_layout.addStretch()

        # Grand Total (Right)
        self.lbl_total = QLabel("0.00")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_total.setStyleSheet("font-size: 48px; font-weight: bold; color: #39FF14;")
        total_layout.addWidget(self.lbl_total)

        left_layout.addWidget(total_widget)

        # ==========================
        # RIGHT PANEL (Controls) - 25%
        # ==========================
        self.action_panel = ActionPanel()
        self.action_panel.setFixedWidth(350)
        self.action_panel.setStyleSheet("background-color: #1E1E1E; border-left: 1px solid #3E3E42;")

        # Connect Action Panel Signals
        self.action_panel.customer_clicked.connect(self.select_customer)
        self.action_panel.pay_clicked.connect(self.process_payment)

        self.action_panel.action_f2.connect(self.select_customer)
        self.action_panel.action_f3.connect(self.open_advanced_search)
        self.action_panel.action_f4.connect(self.change_line_quantity)
        self.action_panel.action_f6.connect(self.hold_bill)
        self.action_panel.action_f7.connect(self.recall_bill)
        self.action_panel.action_f8.connect(lambda: print("Drawer"))  # Placeholder
        self.action_panel.action_del.connect(self.void_bill)
        self.action_panel.action_ref.connect(lambda: print("Refund"))  # Placeholder
        self.action_panel.action_more.connect(lambda: print("More"))  # Placeholder

        # Context Menu for Customer Button (Access via internal button if needed,
        # or just keep simple for now)
        self.action_panel.btn_cust_select.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.action_panel.btn_cust_select.customContextMenuRequested.connect(self.show_customer_menu)
        self.btn_cust = self.action_panel.btn_cust_select  # Alias for existing code

        # Add panels to splitter
        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(self.action_panel)

        # Set Stretch Factors (75% / 25%)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

        # Shortcuts
        self.setup_shortcuts()

        # Initialize Cart
        self.update_cart_ui()

    def update_cart_ui(self):
        self.cart_table.setRowCount(0)
        for row, item in enumerate(self.cart_service.items):
            self.cart_table.insertRow(row)

            product = item["product"]
            qty = item["qty"]
            price = item["price"]
            discount = item["discount"]
            total = item["total"]

            self.cart_table.setItem(row, 0, QTableWidgetItem(product.name_en))
            self.cart_table.setItem(row, 1, QTableWidgetItem(format_currency(price)))
            self.cart_table.setItem(row, 2, QTableWidgetItem(str(qty)))

            disc_text = f"{discount}%" if discount > 0 else "-"
            self.cart_table.setItem(row, 3, QTableWidgetItem(disc_text))

            self.cart_table.setItem(row, 4, QTableWidgetItem(format_currency(total)))

        totals = self.cart_service.get_totals()

        # Extract values
        final_total = totals.get("final_total", 0)
        subtotal = totals.get("subtotal", 0)
        cart_discount = totals.get("cart_discount", 0)
        # Tax is not explicitly in get_totals() top level, but it's calculated in TaxService.
        # Wait, get_totals() returns subtotal, discount, final_total.
        # Tax is usually included in the price (MRP).
        # If we want to show tax breakdown, we might need to calculate it or get it from somewhere.
        # For now, let's assume TaxService.calculate_taxes(final_total) is needed or just show 0 if not available.
        # Actually, TaxService.calculate_taxes(total_amount) was used in process_sale.
        # Let's calculate it here for display.
        from cbpos.core.services.tax_service import TaxService

        tax_info = TaxService.calculate_taxes(final_total)
        tax_amount = tax_info["vat"] + tax_info["sscl"]

        item_count = totals.get("item_count", 0)  # Sum of quantities
        # or totals.get("count", 0) # Number of lines
        # User asked for "Items: {count}" which usually means item count.
        # Let's use item_count (qty sum) as it's more useful for retail.

        self.lbl_total.setText(format_currency(final_total))
        self.lbl_subtotal.setText(f"Subtotal: {format_currency(subtotal)}")
        self.lbl_discount.setText(f"Disc: {format_currency(cart_discount)}")
        self.lbl_tax.setText(f"Tax: {format_currency(tax_amount)}")
        self.lbl_item_count.setText(f"Items: {item_count}")

        self.cart_table.scrollToBottom()

    def setup_shortcuts(self):
        self.shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        self.shortcut_f5.activated.connect(self.process_payment)

        self.shortcut_f6 = QShortcut(QKeySequence("F6"), self)
        self.shortcut_f6.activated.connect(self.hold_bill)

        self.shortcut_f7 = QShortcut(QKeySequence("F7"), self)
        self.shortcut_f7.activated.connect(self.recall_bill)

        self.shortcut_f4 = QShortcut(QKeySequence("F4"), self)
        self.shortcut_f4.activated.connect(self.change_line_quantity)  # Changed to Qty as per grid

        self.shortcut_f3 = QShortcut(QKeySequence("F3"), self)
        self.shortcut_f3.activated.connect(self.open_advanced_search)

        self.shortcut_f2 = QShortcut(QKeySequence("F2"), self)
        self.shortcut_f2.activated.connect(self.select_customer)

        self.shortcut_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self.shortcut_del.activated.connect(self.void_bill)

        # Shortcuts for Enter Key (Decentralized Handling)
        self.shortcut_enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self.shortcut_enter.activated.connect(self.process_barcode)

        self.shortcut_num_enter = QShortcut(QKeySequence(Qt.Key.Key_Enter), self)
        self.shortcut_num_enter.activated.connect(self.process_barcode)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position menu at right edge
        menu_width = self.side_menu.width()
        if self.side_menu.isVisible():
            self.side_menu.setGeometry(self.width() - menu_width, 0, menu_width, self.height())
        else:
            self.side_menu.setGeometry(self.width(), 0, menu_width, self.height())

    def toggle_side_menu(self):
        menu_width = self.side_menu.width()
        start_pos = self.side_menu.pos()

        if self.side_menu.isVisible():
            # Slide Out (Hide)
            end_pos = QPoint(self.width(), 0)
            self.menu_animation.setStartValue(start_pos)
            self.menu_animation.setEndValue(end_pos)
            self.menu_animation.finished.connect(lambda: self.side_menu.setVisible(False))
            self.menu_animation.finished.connect(self.menu_animation.finished.disconnect)  # Disconnect after run
            self.menu_animation.start()
        else:
            # Slide In (Show)
            self.side_menu.setVisible(True)
            self.side_menu.raise_()
            start_pos = QPoint(self.width(), 0)
            end_pos = QPoint(self.width() - menu_width, 0)
            self.side_menu.setGeometry(self.width(), 0, menu_width, self.height())  # Ensure start pos

            self.menu_animation.setStartValue(start_pos)
            self.menu_animation.setEndValue(end_pos)
            self.menu_animation.start()

    def eventFilter(self, source, event):
        if event.type() == event.Type.MouseButtonPress and self.side_menu.isVisible():
            # Check if click is outside menu
            if not self.side_menu.geometry().contains(event.pos()) and source is not self.menu_button:
                self.toggle_side_menu()
                return True
        return super().eventFilter(source, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.barcode_input.setFocus()
        self.order_bar.refresh_tabs()

    def on_visual_item_clicked(self, product):
        """Handle item click from Visual POS."""
        self.cart_service.add_item(product)
        self.update_cart_display()

    def process_barcode_external(self, barcode):
        """Handle barcode from global scanner hook."""
        self.barcode_input.setText(barcode)
        self.process_barcode()

    def process_barcode(self):
        """Process product search using current search mode (Phase 6)."""
        query = self.barcode_input.text().strip()
        if not query:
            return

        # 1. Check for Loyalty Card (e.g. Starts with L- or specific length)
        # Assuming L- prefix for now as per request
        if query.startswith("L-") or (len(query) == 12 and query.isdigit()):
            customer = self.customer_service.find_by_loyalty_card(query)
            if customer:
                self.set_customer(customer)
                self.barcode_input.clear()
                return

        # Use product_service with current search mode
        products = self.product_service.search_products(query, mode=self.current_search_mode)

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
            if item.get("original_price") and item["unit_price"] < item["original_price"]:
                lbl_price = QLabel()
                lbl_price.setText("<s>{:.2f}</s> <b>{:.2f}</b>".format(item["original_price"], item["unit_price"]))
                lbl_price.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                lbl_price.setStyleSheet("background-color: transparent; color: white;")
                self.cart_table.setCellWidget(row, 1, lbl_price)
            else:
                self.cart_table.setItem(row, 1, QTableWidgetItem(f"{item['unit_price']:.2f}"))  # noqa: E231

            # Highlight if discounted
            if item.get("discount_type") != "NONE" or item.get("is_manual_price"):
                bg_color = QColor(0, 50, 0)  # Dark Green for dark mode
                brush = QBrush(bg_color)
                name_item.setBackground(brush)

            self.cart_table.setItem(row, 0, name_item)
            # If we didn't set a cell widget for price, we need to set the item
            if not self.cart_table.cellWidget(row, 1):
                self.cart_table.setItem(row, 1, QTableWidgetItem(f"{item['unit_price']:.2f}"))  # noqa: E231

            self.cart_table.setItem(row, 2, QTableWidgetItem(f"{item['qty']:.3f}"))  # noqa: E231
            self.cart_table.setItem(row, 3, QTableWidgetItem(f"{item['total']:.2f}"))  # noqa: E231

        totals = self.cart_service.get_totals()
        self.total_label.setText(f"{totals['final_total']:.2f}")  # noqa: E231
        self.lbl_subtotal.setText(f"Subtotal: {totals['subtotal']:.2f}")  # noqa: E231
        self.lbl_tax.setText(f"Tax: {totals['tax']:.2f}")  # noqa: E231
        self.cart_table.scrollToBottom()

    def select_customer(self):
        dialog = CustomerSelectionDialog(self)
        if dialog.exec():
            self.set_customer(dialog.selected_customer)

    def set_customer(self, customer):
        self.customer = customer
        self.action_panel.set_customer_info(self.customer.name, self.customer.phone, self.customer.loyalty_points)

        # Trigger price recalculation if needed (Phase 2)
        # self.cart_service.recalculate_prices(customer.price_list_id)

    def show_customer_menu(self, pos):
        menu = QMenu(self)

        quick_add = QAction("Quick Add New", self)
        quick_add.triggered.connect(self.quick_add_customer)
        menu.addAction(quick_add)

        if self.customer:
            details = QAction("View Details", self)
            # details.triggered.connect(self.view_customer_details) # TODO
            menu.addAction(details)

            clear = QAction("Clear Customer", self)
            clear.triggered.connect(self.clear_customer)
            menu.addAction(clear)

        menu.exec(self.btn_cust.mapToGlobal(pos))

    def quick_add_customer(self):
        dialog = CustomerQuickAddDialog(self)
        if dialog.exec():
            self.set_customer(dialog.created_customer)

    def clear_customer(self):
        self.customer = None
        self.action_panel.clear_customer_info()

    def process_payment(self):
        totals = self.cart_service.get_totals()
        if totals["subtotal"] <= 0:
            return

        dialog = PaymentDialog(totals["subtotal"], self)
        if dialog.exec():
            payments, _ = dialog.payment_data
            customer_id = self.customer.id if self.customer else None

            try:
                success = TransactionService.process_sale(self.cart_service, payments, customer_id)
                if success:
                    QMessageBox.information(self, "Success", "Sale processed successfully!")
                    self.cart_service.clear()
                    self.update_cart_display()
                    self.barcode_input.setFocus()
                    # Reset customer
                    self.customer = None
                    self.action_panel.clear_customer_info()
                    self.order_bar.refresh_tabs()

                    # Show Receipt Options if configured
                    settings = ConfigService.get_all()
                    if settings.get("show_receipt_dialog", "True") == "True":
                        from cbpos.core.database import Database
                        from cbpos.core.models import Sale

                        db = Database()
                        with db.get_session() as session:
                            last_sale = session.query(Sale).order_by(Sale.id.desc()).first()
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
        # 1. Check Permission
        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.permission_service import PermissionService
        from cbpos.ui.dialogs.manager_override_dialog import ManagerOverrideDialog

        current_user = AuthService.get_current_user()
        authorized_user = current_user

        # If cart is empty, nothing to void
        if not self.cart_service.items:
            return

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

    def on_search_mode_changed(self, button):
        """Handle search mode change from segmented control."""
        mode = button.property("mode")
        self.current_search_mode = mode

        placeholders = {
            "ALL": "Scan or type product... (Enter)",
            "BARCODE": "Scan barcode...",
            "CODE": "Enter product code...",
            "NAME": "Type product name...",
        }
        self.barcode_input.setPlaceholderText(placeholders.get(mode, "Search..."))
        self.barcode_input.setFocus()

    def set_search_mode(self, mode: str, icon: str):
        # Legacy support or external call
        # Find button with this mode and check it
        for btn in self.mode_group.buttons():
            if btn.property("mode") == mode:
                btn.setChecked(True)
                self.on_search_mode_changed(btn)
                break

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
            note, ok = QInputDialog.getText(self, "Line Note", "Enter note for this item:")
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
                self.cart_service.items[row]["total"] = Decimal(str(qty)) * self.cart_service.items[row]["unit_price"]
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
            QMessageBox.warning(self, "Error", "Could not recall order. It may have been taken.")
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
