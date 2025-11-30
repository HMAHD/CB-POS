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
    QMenu,
    QToolButton,
    QInputDialog,
    QCompleter,
    QFrame,
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
from cbpos.ui.widgets.order_bar import OrderBar
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.side_menu import SideMenu


class SalesView(QWidget):
    def __init__(self):
        super().__init__()
        self.cart_service = CartService()
        self.product_service = ProductService()
        self.customer = None
        self.current_search_mode = "ALL"
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
        header_widget.setStyleSheet(
            "background-color: #001226; border-bottom: 1px solid #003366;"
        )
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 0, 20, 0)

        # Brand (Logo)
        lbl_logo = QLabel()
        logo_pixmap = QPixmap("assets/logo/cover_black.png")
        if not logo_pixmap.isNull():
            lbl_logo.setPixmap(
                logo_pixmap.scaledToHeight(
                    30, Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            lbl_logo.setText("CEYLON BYTE POS")  # Fallback
            lbl_logo.setStyleSheet(
                "color: #00BCEB; font-weight: bold; font-size: 16px;"
            )
        lbl_logo.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
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

        # --- CONTENT AREA (Split Screen) ---
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

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

        # Mode Selector Button
        self.search_mode_btn = QToolButton()
        self.search_mode_btn.setText("★")
        self.search_mode_btn.setToolTip("Search Mode")
        self.search_mode_btn.setFixedWidth(40)
        self.search_mode_btn.setFixedHeight(40)
        self.search_mode_btn.setStyleSheet(
            "font-size: 18px; background-color: #333; border: 1px solid #555;"
        )
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
        self.barcode_input.setPlaceholderText("Scan or type product... (Enter)")
        self.barcode_input.setFixedHeight(40)
        self.barcode_input.setStyleSheet(
            "font-size: 16px; padding: 5px; border: 1px solid #555; background-color: #222; color: white;"
        )
        self.barcode_input.returnPressed.connect(self.process_barcode)
        search_layout.addWidget(self.barcode_input)

        self.setup_autocomplete()
        left_layout.addWidget(search_container)

        # 2. Cart Table (Center)
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(4)
        self.cart_table.setHorizontalHeaderLabels(["Item", "Price", "Qty", "Total"])
        self.cart_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
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
        # Styling handled in theme.qss, but setting object name for specificity if needed
        self.cart_table.setObjectName("CartTable")

        left_layout.addWidget(self.cart_table)

        # 3. Order Bar (Tabs)
        self.order_bar = OrderBar()
        self.order_bar.tab_switched.connect(self.switch_to_order)
        self.order_bar.new_tab_requested.connect(self.create_new_order)
        left_layout.addWidget(self.order_bar)

        # 4. Totals Widget (Bottom)
        total_widget = QFrame()
        total_widget.setStyleSheet(
            "background-color: #252526; border-top: 2px solid #3E3E42; border-radius: 5px;"
        )
        total_layout = QHBoxLayout(total_widget)
        total_layout.setContentsMargins(20, 10, 20, 10)

        # Subtotals (Left)
        subtotal_layout = QVBoxLayout()
        self.lbl_subtotal = QLabel("Subtotal: 0.00")
        self.lbl_tax = QLabel("Tax: 0.00")
        self.lbl_subtotal.setStyleSheet("color: #AAAAAA; font-size: 14px;")
        self.lbl_tax.setStyleSheet("color: #AAAAAA; font-size: 14px;")
        subtotal_layout.addWidget(self.lbl_subtotal)
        subtotal_layout.addWidget(self.lbl_tax)
        total_layout.addLayout(subtotal_layout)

        total_layout.addStretch()

        # Grand Total (Right)
        self.total_label = QLabel("0.00")
        self.total_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.total_label.setStyleSheet(
            "font-size: 48px; font-weight: bold; color: #39FF14;"
        )
        total_layout.addWidget(self.total_label)

        left_layout.addWidget(total_widget)

        # ==========================
        # RIGHT PANEL (Controls) - 25%
        # ==========================
        right_panel = QWidget()
        right_panel.setFixedWidth(350)  # Fixed width for control panel
        right_panel.setStyleSheet(
            "background-color: #1E1E1E; border-left: 1px solid #3E3E42;"
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(10)

        # 1. Customer Header
        customer_frame = QFrame()
        customer_frame.setStyleSheet(
            "background-color: #2D2D30; border-radius: 5px; padding: 5px;"
        )
        cust_layout = QHBoxLayout(customer_frame)
        cust_layout.setContentsMargins(5, 5, 5, 5)

        self.lbl_customer = QLabel("Walk-in Customer")
        self.lbl_customer.setStyleSheet(
            "font-weight: bold; font-size: 14px; color: white;"
        )

        btn_cust = QPushButton("Select")
        btn_cust.setFixedWidth(70)
        btn_cust.setStyleSheet(
            "background-color: #007ACC; color: white; border: none; padding: 5px;"
        )
        btn_cust.clicked.connect(self.select_customer)

        cust_layout.addWidget(self.lbl_customer)
        cust_layout.addStretch()
        cust_layout.addWidget(btn_cust)

        right_layout.addWidget(customer_frame)

        self.lbl_points = QLabel("")
        self.lbl_points.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_points.setStyleSheet(
            "color: #FFDC00; font-weight: bold; font-size: 12px;"
        )
        right_layout.addWidget(self.lbl_points)

        # 2. Action Grid (Command Console)
        # Using a Grid Layout for square buttons
        action_grid = QGridLayout()
        action_grid.setSpacing(10)

        # Helper to create styled action buttons
        def create_action_btn(text, icon, slot, row, col, color=None):
            btn = QPushButton(text)
            btn.setFixedSize(100, 80)  # Square-ish
            # btn.setIcon(Icons.get(icon)) # Icons need to be handled carefully with text
            # For now, just text or we can add icon later.
            # The user requested "Icon + Text below".
            # Standard QPushButton doesn't support Text Under Icon easily without QToolButton or stylesheet hacks.
            # Let's use QToolButton for better control or just styled QPushButton.
            # Going with styled QPushButton for simplicity and robustness first.

            style = """
                QPushButton {
                    background-color: #2D2D30;
                    border: 1px solid #3E3E42;
                    color: white;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    border: 1px solid #00BCEB;
                    background-color: #3E3E42;
                }
                QPushButton:pressed {
                    background-color: #00BCEB;
                    color: black;
                }
            """
            if color:
                style += "QPushButton {{ color: {}; }}".format(color)

            btn.setStyleSheet(style)
            btn.clicked.connect(slot)
            action_grid.addWidget(btn, row, col)
            return btn

        # Row 0
        create_action_btn("F2\nCustomer", "", self.select_customer, 0, 0)
        create_action_btn("F3\nSearch", "", self.open_advanced_search, 0, 1)
        create_action_btn("F4\nQty", "", self.change_line_quantity, 0, 2)

        # Row 1
        create_action_btn("F6\nHold", "", self.hold_bill, 1, 0, "#FFDC00")
        create_action_btn("F7\nRecall", "", self.recall_bill, 1, 1)
        create_action_btn(
            "F8\nDrawer", "", lambda: print("Drawer"), 1, 2
        )  # Placeholder

        # Row 2
        create_action_btn("Del\nVoid", "", self.void_bill, 2, 0, "#FF4136")
        create_action_btn("Ref\nRefund", "", lambda: print("Refund"), 2, 1, "#FF4136")
        create_action_btn("...\nMore", "", lambda: print("More"), 2, 2)

        right_layout.addLayout(action_grid)
        right_layout.addStretch()

        # 3. Pay Button (Bottom)
        self.btn_pay = QPushButton("PAY (F5)")
        self.btn_pay.setFixedHeight(80)
        self.btn_pay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pay.setStyleSheet(
            """
            QPushButton {
                background-color: #39FF14;
                color: #001F3F;
                font-size: 24px;
                font-weight: bold;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #32E012;
            }
            QPushButton:pressed {
                background-color: #28B40E;
            }
        """
        )
        self.btn_pay.clicked.connect(self.process_payment)
        right_layout.addWidget(self.btn_pay)

        # Add panels to content layout
        content_layout.addWidget(left_panel, stretch=75)
        content_layout.addWidget(right_panel, stretch=25)

        main_layout.addWidget(content_widget)

        # Shortcuts
        self.setup_shortcuts()

    def setup_shortcuts(self):
        self.shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        self.shortcut_f5.activated.connect(self.process_payment)

        self.shortcut_f6 = QShortcut(QKeySequence("F6"), self)
        self.shortcut_f6.activated.connect(self.hold_bill)

        self.shortcut_f7 = QShortcut(QKeySequence("F7"), self)
        self.shortcut_f7.activated.connect(self.recall_bill)

        self.shortcut_f4 = QShortcut(QKeySequence("F4"), self)
        self.shortcut_f4.activated.connect(
            self.change_line_quantity
        )  # Changed to Qty as per grid

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
            self.side_menu.setGeometry(
                self.width() - menu_width, 0, menu_width, self.height()
            )
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
            self.menu_animation.finished.connect(
                lambda: self.side_menu.setVisible(False)
            )
            self.menu_animation.finished.connect(
                self.menu_animation.finished.disconnect
            )  # Disconnect after run
            self.menu_animation.start()
        else:
            # Slide In (Show)
            self.side_menu.setVisible(True)
            self.side_menu.raise_()
            start_pos = QPoint(self.width(), 0)
            end_pos = QPoint(self.width() - menu_width, 0)
            self.side_menu.setGeometry(
                self.width(), 0, menu_width, self.height()
            )  # Ensure start pos

            self.menu_animation.setStartValue(start_pos)
            self.menu_animation.setEndValue(end_pos)
            self.menu_animation.start()

    def eventFilter(self, source, event):
        if event.type() == event.Type.MouseButtonPress and self.side_menu.isVisible():
            # Check if click is outside menu
            if (
                not self.side_menu.geometry().contains(event.pos())
                and source is not self.menu_button
            ):
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
                lbl_price = QLabel()
                lbl_price.setText(
                    "<s>{:.2f}</s> <b>{:.2f}</b>".format(
                        item["original_price"], item["unit_price"]
                    )
                )
                lbl_price.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                lbl_price.setStyleSheet("background-color: transparent; color: white;")
                self.cart_table.setCellWidget(row, 1, lbl_price)
            else:
                self.cart_table.setItem(
                    row, 1, QTableWidgetItem(f"{item['unit_price']:.2f}")  # noqa: E231
                )

            # Highlight if discounted
            if item.get("discount_type") != "NONE" or item.get("is_manual_price"):
                bg_color = QColor(0, 50, 0)  # Dark Green for dark mode
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
        self.total_label.setText(f"{totals['final_total']:.2f}")  # noqa: E231
        self.lbl_subtotal.setText(f"Subtotal: {totals['subtotal']:.2f}")  # noqa: E231
        self.lbl_tax.setText(f"Tax: {totals['tax']:.2f}")  # noqa: E231
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
                    self.order_bar.refresh_tabs()

                    # Show Receipt Options if configured
                    settings = ConfigService.get_all()
                    if settings.get("show_receipt_dialog", "True") == "True":
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
