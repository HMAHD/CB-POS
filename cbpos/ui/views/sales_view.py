import logging
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
    QStackedWidget,
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QSize, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut, QAction, QBrush, QColor, QPixmap
from decimal import Decimal
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.ui.dialogs.payment_dialog import PaymentDialog
from cbpos.ui.dialogs.discount_dialog import DiscountDialog
from cbpos.ui.dialogs.quantity_dialog import QuantityDialog
from cbpos.ui.dialogs.receipt_options_dialog import ReceiptOptionsDialog
from cbpos.core.services.config_service import ConfigService
from cbpos.ui.constants import SEARCH_BAR_HEIGHT, CART_TABLE_ROW_HEIGHT, PAYMENT_PANEL_WIDTH
from cbpos.ui.dialogs.customer_selection_dialog import CustomerSelectionDialog
from cbpos.ui.dialogs.advanced_search_dialog import AdvancedSearchDialog
from cbpos.ui.dialogs.customer_quick_add import CustomerQuickAddDialog
from cbpos.core.services.customer_service import CustomerService
from cbpos.ui.widgets.order_bar import OrderBar
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.side_menu import SideMenu
from cbpos.ui.widgets.action_panel import ActionPanel
from cbpos.core.utils.formatters import format_currency
from cbpos.core.services.sound_service import SoundService

logger = logging.getLogger(__name__)


class SalesView(QWidget):
    def __init__(self):
        super().__init__()
        self.cart_service = CartService()
        self.product_service = ProductService()
        self.customer_service = CustomerService()
        self.customer = None
        self.current_search_mode = ConfigService.get("default_search_mode") or "ALL"
        self._undo_data = None
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
        # 1. Main Layout (Vertical)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 2. Header (Top)
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(SEARCH_BAR_HEIGHT)
        self.header_widget.setObjectName("HeaderWidget")
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(20, 0, 20, 0)

        # Brand (Logo) - Store as instance variable for theme updates
        self.lbl_logo = QLabel()
        from cbpos.core.services.theme_service import ThemeService

        self.update_logo()  # Set initial logo

        self.lbl_logo.setObjectName("HeaderLogo")
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(self.lbl_logo)

        # Register callback to update logo when theme changes
        ThemeService.register_theme_callback(self.update_logo)

        header_layout.addStretch()

        # Menu Button (Hamburger)
        self.menu_button = QToolButton()
        self.menu_button.setObjectName("menu_button")
        self.menu_button.setIcon(Icons.get("fa5s.bars", "white"))
        self.menu_button.setIconSize(QSize(24, 24))
        self.menu_button.setFixedSize(42, 42)
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.clicked.connect(self.toggle_side_menu)
        header_layout.addWidget(self.menu_button)

        main_layout.addWidget(self.header_widget)

        # 3. Content Area (Splitter)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(10)
        self.splitter.setChildrenCollapsible(False)
        main_layout.addWidget(self.splitter)

        # ==========================
        # LEFT PANEL (Cart & Totals) - 75%
        # ==========================
        self.container_left = QWidget()
        left_layout = QVBoxLayout(self.container_left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(10)

        # 1. Search Bar (Top)
        search_container = QWidget()
        search_container.setObjectName("SearchWidget")
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
            btn.setObjectName("SearchModeBtn")  # For styling

            if mode_id == self.current_search_mode:
                btn.setChecked(True)

            self.mode_group.addButton(btn)
            search_layout.addWidget(btn)

        search_layout.addSpacing(10)

        # Search Input
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Scan or type product... (Enter)")
        self.barcode_input.setFixedHeight(CART_TABLE_ROW_HEIGHT)

        self.barcode_input.returnPressed.connect(self.process_barcode)
        search_layout.addWidget(self.barcode_input)

        self.setup_autocomplete()
        left_layout.addWidget(search_container)

        # 2. Cart Table (Center)
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(5)
        self.cart_table.setHorizontalHeaderLabels(["Item", "Price", "Qty", "Disc", "Total"])

        # Optimized column sizing for better readability
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Item - flexible
        self.cart_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # Price - fixed
        self.cart_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # Qty - fixed
        self.cart_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # Disc - fixed
        self.cart_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)  # Total - fixed

        # Set fixed widths for numeric columns (better alignment)
        self.cart_table.setColumnWidth(1, 100)  # Price
        self.cart_table.setColumnWidth(2, 80)  # Qty
        self.cart_table.setColumnWidth(3, 60)  # Disc
        self.cart_table.setColumnWidth(4, 120)  # Total

        # Set object name for CSS targeting
        self.cart_table.setObjectName("CartTable")
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setShowGrid(False)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cart_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cart_table.customContextMenuRequested.connect(self.show_cart_context_menu)
        self.cart_table.setAlternatingRowColors(True)

        # Empty Cart Placeholder
        self.empty_cart_label = QLabel("Scan or search to add items")
        self.empty_cart_label.setObjectName("EmptyCartLabel")
        self.empty_cart_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Stacked widget to swap between cart table and empty placeholder
        self.cart_stack = QStackedWidget()
        self.cart_stack.addWidget(self.empty_cart_label)  # index 0
        self.cart_stack.addWidget(self.cart_table)  # index 1
        self.cart_stack.setCurrentIndex(0)

        left_layout.addWidget(self.cart_stack)

        # Undo Toast (overlay at bottom of cart area)
        self.undo_toast = QLabel(self.container_left)
        self.undo_toast.setObjectName("UndoToast")
        self.undo_toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.undo_toast.setStyleSheet(
            "QLabel#UndoToast {"
            "  background-color: rgba(0, 31, 63, 0.92);"
            "  color: #00BCEB;"
            "  border: 1px solid #00BCEB;"
            "  border-radius: 6px;"
            "  padding: 8px 16px;"
            "  font-size: 13px;"
            "  font-weight: bold;"
            "}"
        )
        self.undo_toast.setVisible(False)

        # 3. Order Bar (Tabs)
        self.order_bar = OrderBar()
        self.order_bar.tab_switched.connect(self.switch_to_order)
        self.order_bar.new_tab_requested.connect(self.create_new_order)
        left_layout.addWidget(self.order_bar)

        # 4. Totals Widget (Bottom)
        total_widget = QFrame()
        total_widget.setObjectName("TotalWidget")

        total_layout = QHBoxLayout(total_widget)
        total_layout.setContentsMargins(20, 10, 20, 10)

        # Subtotals (Left)
        subtotal_layout = QVBoxLayout()
        self.lbl_item_count = QLabel("Items: 0")
        self.lbl_item_count.setObjectName("ItemCountLabel")
        self.lbl_subtotal = QLabel("Subtotal: 0.00")
        self.lbl_subtotal.setObjectName("SubtotalLabel")
        self.lbl_discount = QLabel("Disc: 0.00")
        self.lbl_discount.setObjectName("DiscountLabel")
        self.lbl_tax = QLabel("Tax: 0.00")
        self.lbl_tax.setObjectName("TaxLabel")
        subtotal_layout.addWidget(self.lbl_item_count)
        subtotal_layout.addWidget(self.lbl_subtotal)
        subtotal_layout.addWidget(self.lbl_discount)
        subtotal_layout.addWidget(self.lbl_tax)
        total_layout.addLayout(subtotal_layout)

        total_layout.addStretch()

        # Grand Total (Right)
        self.total_label = QLabel("0.00")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.total_label.setObjectName("TotalLabel")
        total_layout.addWidget(self.total_label)

        left_layout.addWidget(total_widget)

        # ==========================
        # RIGHT PANEL (Controls) - 25%
        # ==========================
        self.action_panel = ActionPanel()
        self.action_panel.setFixedWidth(PAYMENT_PANEL_WIDTH)
        self.action_panel.setObjectName("ActionPanel")

        # Connect Action Panel Signals
        self.action_panel.customer_clicked.connect(self.select_customer)
        self.action_panel.pay_clicked.connect(self.process_payment)

        self.action_panel.action_f2.connect(self.select_customer)
        self.action_panel.action_f3.connect(self.open_advanced_search)
        self.action_panel.action_f4.connect(self.change_line_quantity)
        self.action_panel.action_f6.connect(self.hold_bill)
        self.action_panel.action_f7.connect(self.recall_bill)
        self.action_panel.action_f8.connect(self.open_cash_drawer)
        self.action_panel.action_del.connect(self.void_bill)
        self.action_panel.action_ref.connect(self.open_refund)
        self.action_panel.action_more.connect(self.toggle_product_grid)

        # Context Menu for Customer Button
        self.action_panel.btn_cust_select.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.action_panel.btn_cust_select.customContextMenuRequested.connect(self.show_customer_menu)
        self.btn_cust = self.action_panel.btn_cust_select  # Alias for existing code

        # Product Grid Panel (Touch Mode) — hidden by default
        from cbpos.ui.widgets.product_grid_panel import ProductGridPanel

        self.product_grid = ProductGridPanel()
        self.product_grid.product_selected.connect(self.on_visual_item_clicked)
        self.product_grid.setVisible(False)

        # Add panels to splitter
        self.splitter.addWidget(self.container_left)
        self.splitter.addWidget(self.product_grid)
        self.splitter.addWidget(self.action_panel)

        # Stretch: cart expands, product_grid hidden initially, action_panel fixed width
        self.splitter.setStretchFactor(0, 1)  # container_left — takes remaining space
        self.splitter.setStretchFactor(1, 0)  # product_grid — hidden by default
        self.splitter.setStretchFactor(2, 0)  # action_panel — fixed width
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, True)  # product_grid can collapse
        self.splitter.setCollapsible(2, False)

        # Shortcuts
        self.setup_shortcuts()

        # Initialize Cart
        self.update_cart_ui()

    def update_logo(self):
        """Update logo based on current theme (called on theme change)."""
        from cbpos.core.services.theme_service import ThemeService
        from pathlib import Path

        logo_path = Path(ThemeService.get_logo_path())

        if logo_path.exists():
            logo_pixmap = QPixmap(str(logo_path))
            self.lbl_logo.setPixmap(logo_pixmap.scaledToHeight(35, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_logo.setText("CEYLON BYTE POS")  # Fallback
            self.lbl_logo.setObjectName("LogoLabel")

        # Update hamburger menu icon (if it exists) - always white
        if hasattr(self, "menu_button"):
            self.menu_button.setIcon(Icons.get("fa5s.bars", "white"))

        # Update side menu icons (if it exists)
        if hasattr(self, "side_menu"):
            self.side_menu.update_all_icons()

    def update_cart_ui(self):
        """Initial cart update (delegates to update_cart_display)."""
        self.update_cart_display()

    def setup_shortcuts(self):
        self.shortcut_f1 = QShortcut(QKeySequence("F1"), self)
        self.shortcut_f1.activated.connect(self.show_shortcuts_help)

        self.shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        self.shortcut_f5.activated.connect(self.process_payment)

        self.shortcut_f6 = QShortcut(QKeySequence("F6"), self)
        self.shortcut_f6.activated.connect(self.hold_bill)

        self.shortcut_f7 = QShortcut(QKeySequence("F7"), self)
        self.shortcut_f7.activated.connect(self.recall_bill)

        self.shortcut_f4 = QShortcut(QKeySequence("F4"), self)
        self.shortcut_f4.activated.connect(self.change_line_quantity)

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

        # F8 — Open Cash Drawer
        self.shortcut_f8 = QShortcut(QKeySequence("F8"), self)
        self.shortcut_f8.activated.connect(self.open_cash_drawer)

        # F10 — Open Payment (alias for F5)
        self.shortcut_f10 = QShortcut(QKeySequence("F10"), self)
        self.shortcut_f10.activated.connect(self.process_payment)

        # F12 — Quick Pay (cash)
        self.shortcut_f12 = QShortcut(QKeySequence("F12"), self)
        self.shortcut_f12.activated.connect(self.quick_pay)

        # Ctrl+D — Open Cash Drawer (alias for F8)
        self.shortcut_ctrl_d = QShortcut(QKeySequence("Ctrl+D"), self)
        self.shortcut_ctrl_d.activated.connect(self.open_cash_drawer)

        # Page Up — Select first item in cart
        self.shortcut_pgup = QShortcut(QKeySequence(Qt.Key.Key_PageUp), self)
        self.shortcut_pgup.activated.connect(self.select_first_cart_item)

        # Page Down — Select last item in cart
        self.shortcut_pgdn = QShortcut(QKeySequence(Qt.Key.Key_PageDown), self)
        self.shortcut_pgdn.activated.connect(self.select_last_cart_item)

        # Ctrl+Z — Undo last removed cart item
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self._undo_remove)

    def resizeEvent(self, event):
        super().resizeEvent(event)
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

            def _on_hidden():
                self.side_menu.setVisible(False)
                self.action_panel.setVisible(True)
                self.menu_animation.finished.disconnect(_on_hidden)

            self.menu_animation.finished.connect(_on_hidden)
            self.menu_animation.start()
        else:
            # Hide action panel so PAY button doesn't show behind menu
            self.action_panel.setVisible(False)
            self.side_menu.setVisible(True)
            self.side_menu.raise_()
            start_pos = QPoint(self.width(), 0)
            end_pos = QPoint(self.width() - menu_width, 0)
            self.side_menu.setGeometry(self.width(), 0, menu_width, self.height())

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
        # Restore action panel when returning to POS from other views
        if self.side_menu.isVisible():
            self.side_menu.setVisible(False)
            self.side_menu.clear_active()
        self.action_panel.setVisible(True)
        self.barcode_input.setFocus()
        self.order_bar.refresh_tabs()

    def on_visual_item_clicked(self, product):
        """Handle item click from Visual POS."""
        dialog = QuantityDialog(product, self)
        if dialog.exec():
            self.cart_service.add_item(product, qty=dialog.get_quantity())
            self.update_cart_display()
        self.barcode_input.setFocus()

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
            SoundService.play("scan_success")
            dialog = QuantityDialog(products[0], self)
            if dialog.exec():
                self.cart_service.add_item(products[0], qty=dialog.get_quantity())
                self.update_cart_display()
            self.barcode_input.clear()
            self.barcode_input.setFocus()
        elif len(products) > 1:
            SoundService.play("scan_success")
            # Open advanced search with pre-filled query
            dialog = AdvancedSearchDialog(self)
            dialog.search_input.setText(query)
            dialog.perform_search()
            dialog.product_selected.connect(self.on_advanced_search_product_selected)
            dialog.exec()
            self.barcode_input.clear()
            self.barcode_input.setFocus()
        else:
            SoundService.play("scan_error")
            QMessageBox.warning(self, "Not Found", "Product not found.")
            self.barcode_input.setFocus()

    def update_cart_display(self):
        """Update cart display with visual indicators (Phase 6)."""
        from cbpos.core.services.theme_service import ThemeService

        is_dark = ThemeService.current_theme.lower() == "dark"
        text_color = QColor("#FFFFFF") if is_dark else QColor("#212529")
        text_brush = QBrush(text_color)

        self.cart_table.setRowCount(0)
        has_items = len(self.cart_service.items) > 0
        self.cart_stack.setCurrentIndex(1 if has_items else 0)
        for row, item in enumerate(self.cart_service.items):
            self.cart_table.insertRow(row)
            self.cart_table.setRowHeight(row, CART_TABLE_ROW_HEIGHT)

            # Product Name (with note indicator)
            name = item["product"].name_en
            if item.get("note"):
                name = f"📝 {name}"
            name_item = QTableWidgetItem(name)
            name_item.setToolTip(item["product"].name_en)
            name_item.setForeground(text_brush)

            # Price Display (Strikethrough if discounted/overridden)
            if item.get("original_price") and item["unit_price"] < item["original_price"]:
                lbl_price = QLabel()
                lbl_price.setText("<s>{:.2f}</s> <b>{:.2f}</b>".format(item["original_price"], item["unit_price"]))
                lbl_price.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                lbl_price.setProperty("class", "StrikethroughPrice")
                self.cart_table.setCellWidget(row, 1, lbl_price)
            else:
                price_item = QTableWidgetItem(format_currency(item["unit_price"]))
                price_item.setForeground(text_brush)
                self.cart_table.setItem(row, 1, price_item)

            # Highlight if discounted (theme-aware)
            if item.get("discount_type") != "NONE" or item.get("is_manual_price"):
                bg_color = QColor(0, 50, 0) if is_dark else QColor(220, 255, 220)
                name_item.setBackground(QBrush(bg_color))

            self.cart_table.setItem(row, 0, name_item)

            # Qty column
            qty_item = QTableWidgetItem(str(item["qty"]))
            qty_item.setForeground(text_brush)
            self.cart_table.setItem(row, 2, qty_item)

            # Disc column
            disc_val = item.get("discount_value", Decimal("0.00"))
            disc_text = f"{disc_val}%" if disc_val > 0 else "-"
            disc_item = QTableWidgetItem(disc_text)
            disc_item.setForeground(text_brush)
            self.cart_table.setItem(row, 3, disc_item)

            # Total column
            total_item = QTableWidgetItem(format_currency(item["total"]))
            total_item.setForeground(text_brush)
            self.cart_table.setItem(row, 4, total_item)

        totals = self.cart_service.get_totals()
        final_total = totals.get("final_total", 0)
        subtotal = totals.get("subtotal", 0)
        cart_discount = totals.get("cart_discount", 0)
        item_count = totals.get("item_count", 0)

        from cbpos.core.services.config_service import ConfigService

        tax_vat = totals.get("tax_vat", 0)
        tax_sscl = totals.get("tax_sscl", 0)
        tax_total = totals.get("tax", 0)

        self.total_label.setText(format_currency(final_total))
        self.lbl_subtotal.setText(f"Subtotal: {format_currency(subtotal)}")
        self.lbl_discount.setText(f"Disc: {format_currency(cart_discount)}")
        if ConfigService.get("show_tax_breakdown") and tax_total > 0:
            self.lbl_tax.setText(f"VAT: {format_currency(tax_vat)}  SSCL: {format_currency(tax_sscl)}")
        else:
            self.lbl_tax.setText(f"Tax: {format_currency(tax_total)}")
        self.lbl_item_count.setText(f"Items: {item_count}")
        self.cart_table.scrollToBottom()

        # Brief highlight on last row to give visual feedback on item add
        if has_items:
            last_row = self.cart_table.rowCount() - 1
            highlight_color = QColor("#00BCEB") if is_dark else QColor("#B3ECFF")
            highlight_brush = QBrush(highlight_color)
            for col in range(self.cart_table.columnCount()):
                cell = self.cart_table.item(last_row, col)
                if cell:
                    cell.setBackground(highlight_brush)

            def _clear_highlight() -> None:
                for col in range(self.cart_table.columnCount()):
                    cell = self.cart_table.item(last_row, col)
                    if cell:
                        cell.setBackground(QBrush())

            QTimer.singleShot(800, _clear_highlight)

    def select_customer(self):
        dialog = CustomerSelectionDialog(self)
        if dialog.exec():
            self.set_customer(dialog.selected_customer)
        self.barcode_input.setFocus()

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
            menu.addAction(details)

            clear = QAction("Clear Customer", self)
            clear.triggered.connect(self.clear_customer)
            menu.addAction(clear)

        menu.exec(self.btn_cust.mapToGlobal(pos))

    def quick_add_customer(self):
        dialog = CustomerQuickAddDialog(self)
        if dialog.exec():
            self.set_customer(dialog.created_customer)
        self.barcode_input.setFocus()

    def clear_customer(self):
        self.customer = None
        self.action_panel.clear_customer_info()

    def process_payment(self):
        if getattr(self, "_processing", False):
            return
        totals = self.cart_service.get_totals()
        if totals["subtotal"] <= 0:
            SoundService.play("scan_error")
            return

        dialog = PaymentDialog(totals["subtotal"], self)
        if dialog.exec():
            payments, _ = dialog.payment_data
            customer_id = self.customer.id if self.customer else None

            self._processing = True
            try:
                sale = TransactionService.process_sale(self.cart_service, payments, customer_id)
                if sale:
                    # Mark proforma as converted if this was a proforma-to-sale conversion
                    proforma_id = getattr(self, "_pending_proforma_id", None)
                    if proforma_id:
                        from cbpos.core.services.proforma_service import ProformaService

                        ProformaService.mark_converted(proforma_id, sale.id)
                        self._pending_proforma_id = None

                    self._finalize_sale(sale)
            except ValueError as e:
                QMessageBox.warning(self, "Validation Error", str(e))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Transaction failed: {str(e)}")
            finally:
                self._processing = False
        self.barcode_input.setFocus()

    def hold_bill(self):
        if not self.cart_service.items:
            return

        held_id = TransactionService.hold_bill(self.cart_service)
        if held_id:
            self.cart_service.clear()
            self.update_cart_display()
            self.order_bar.refresh_tabs()
            QMessageBox.information(self, "Held", f"Held #{held_id}")
        else:
            QMessageBox.critical(self, "Error", "Failed to hold bill.")
        self.barcode_input.setFocus()

    def recall_bill(self):
        suspended = TransactionService.get_latest_suspended()
        if not suspended:
            QMessageBox.information(self, "Empty", "No held bills found.")
            self.barcode_input.setFocus()
            return

        if TransactionService.recall_bill(suspended.id, self.cart_service):
            self.order_bar.set_active_bill(suspended.id)
            self.update_cart_display()
            self.order_bar.refresh_tabs()
            QMessageBox.information(self, "Recalled", f"Bill #{suspended.id} recalled.")
        else:
            QMessageBox.critical(self, "Error", "Failed to recall bill.")
        self.barcode_input.setFocus()

    def void_bill(self):
        # If cart is empty, nothing to void
        if not self.cart_service.items:
            return

        # 1. Check Permission (with manager override)
        from cbpos.core.utils.permission_helper import check_permission_with_override

        from cbpos.core.constants.permissions import Permissions

        authorized_user = check_permission_with_override(Permissions.SALES_VOID, self)  # noqa: F841
        if not authorized_user:
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
        self.barcode_input.setFocus()

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

        # Select the row under the cursor before showing the menu
        row = self.cart_table.indexAt(position).row()
        if row < 0:
            return
        self.cart_table.selectRow(row)

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
        self.barcode_input.setFocus()

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
        self.barcode_input.setFocus()

    def apply_line_discount(self):
        """Apply discount to selected cart line."""
        row = self.cart_table.currentRow()
        if row < 0:
            return

        from cbpos.core.utils.permission_helper import check_permission_with_override
        from cbpos.core.constants.permissions import Permissions

        authorized_user = check_permission_with_override(Permissions.SALES_DISCOUNT, self)
        if not authorized_user:
            return

        line_total = self.cart_service.items[row]["total"] if row < len(self.cart_service.items) else Decimal("0.00")
        dialog = DiscountDialog(self, original_amount=line_total)
        if dialog.exec():
            disc_type, disc_value = dialog.get_data()
            try:
                self.cart_service.apply_line_discount(row, disc_type, disc_value)
            except ValueError:
                QMessageBox.warning(self, "Discount Limit", str(disc_value) + "% exceeds the allowed discount limit.")
                self.barcode_input.setFocus()
                return
            self.update_cart_display()
        self.barcode_input.setFocus()

    def change_line_price(self):
        """Override price of selected cart line (Manager Only)."""
        row = self.cart_table.currentRow()
        if row < 0:
            return

        # 1. Check Permission (with manager override)
        from cbpos.core.utils.permission_helper import check_permission_with_override

        from cbpos.core.constants.permissions import Permissions

        authorized_user = check_permission_with_override(Permissions.SALES_CHANGE_PRICE, self)
        if not authorized_user:
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
        self.barcode_input.setFocus()

    def remove_line_item(self):
        """Remove selected item from cart with undo support."""
        row = self.cart_table.currentRow()
        if row >= 0:
            removed_item = self.cart_service.items[row].copy()
            del self.cart_service.items[row]
            self.update_cart_display()

            self._undo_data = {"item": removed_item, "index": row}

            product_name = removed_item["product"].name_en
            self.undo_toast.setText(f"Removed: {product_name} — Ctrl+Z to undo")
            self.undo_toast.adjustSize()
            self._position_undo_toast()
            self.undo_toast.setVisible(True)
            self.undo_toast.raise_()

            QTimer.singleShot(4000, self._clear_undo)

    def _position_undo_toast(self) -> None:
        """Position the undo toast at the bottom-center of the cart area."""
        parent_w = self.container_left.width()
        toast_w = min(self.undo_toast.sizeHint().width() + 32, parent_w - 40)
        toast_h = self.undo_toast.sizeHint().height()
        x = (parent_w - toast_w) // 2
        y = self.container_left.height() - toast_h - 60
        self.undo_toast.setGeometry(x, y, toast_w, toast_h)

    def _clear_undo(self) -> None:
        """Clear undo state and hide toast."""
        self._undo_data = None
        self.undo_toast.setVisible(False)

    def _undo_remove(self) -> None:
        """Re-insert the last removed cart item at its original position."""
        if self._undo_data is None:
            return

        item = self._undo_data["item"]
        index = self._undo_data["index"]

        index = min(index, len(self.cart_service.items))
        self.cart_service.items.insert(index, item)
        self.update_cart_display()

        self._undo_data = None
        self.undo_toast.setVisible(False)

    def open_advanced_search(self):
        """Open advanced search dialog (F3)."""
        dialog = AdvancedSearchDialog(self)
        dialog.product_selected.connect(self.on_advanced_search_product_selected)
        dialog.exec()
        self.barcode_input.setFocus()

    def on_advanced_search_product_selected(self, product):
        """Handle product selection from advanced search."""
        dialog = QuantityDialog(product, self)
        if dialog.exec():
            self.cart_service.add_item(product, qty=dialog.get_quantity())
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
            self.order_bar.set_active_bill(suspended_id)
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
                self.order_bar.set_active_bill(None)
                self.order_bar.refresh_tabs()
            else:
                QMessageBox.critical(self, "Error", "Failed to hold current order.")
        else:
            # Already empty, just refresh tabs to be sure
            self.order_bar.set_active_bill(None)
            self.order_bar.refresh_tabs()
            self.barcode_input.setFocus()

    def toggle_product_grid(self) -> None:
        """Toggle the visual product grid panel on/off."""
        is_visible = self.product_grid.isVisible()
        self.product_grid.setVisible(not is_visible)
        if not is_visible:
            # Set splitter sizes: cart gets remaining, grid 350px, action panel keeps fixed width
            total = self.splitter.width()
            action_w = PAYMENT_PANEL_WIDTH
            grid_w = 420
            cart_w = total - grid_w - action_w
            self.splitter.setSizes([max(cart_w, 200), grid_w, action_w])

    def open_receive_payment(self) -> None:
        """Open Receive Payment dialog from POS (quick payment without sale)."""
        from cbpos.ui.dialogs.receive_payment_dialog import ReceivePaymentDialog

        dialog = ReceivePaymentDialog(parent=self)
        dialog.exec()
        self.barcode_input.setFocus()

    def open_reprint_receipt(self) -> None:
        """Open Receipt Reprint dialog to search and reprint past receipts."""
        from cbpos.ui.dialogs.receipt_reprint_dialog import ReceiptReprintDialog

        dialog = ReceiptReprintDialog(parent=self)
        dialog.exec()
        self.barcode_input.setFocus()

    def open_refund(self) -> None:
        """Open Refund dialog to process returns."""
        from cbpos.ui.dialogs.refund_dialog import RefundDialog

        dialog = RefundDialog(parent=self)
        dialog.exec()
        self.barcode_input.setFocus()

    def open_cash_drawer(self) -> None:
        """Open the cash drawer via PrintWorker (F8 / Ctrl+D)."""
        from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

        worker = PrintWorker()
        worker.error_occurred.connect(self._on_print_error)
        worker.add_job("kick_drawer")
        self._drawer_worker = worker  # prevent GC

    def _on_print_error(self, message: str) -> None:
        """Show printer error to user with context."""
        QMessageBox.warning(
            self,
            "Printer Error",
            f"Receipt print failed: {message}\n\n"
            "Check printer connection and verify settings "
            "under Settings > Hardware.",
        )

    def _finalize_sale(self, sale) -> None:
        """Common post-sale cleanup: sound, clear cart, optionally show receipt dialog."""
        SoundService.play("payment_complete")
        self.cart_service.clear()
        self.update_cart_display()
        self.barcode_input.setFocus()
        self.customer = None
        self.action_panel.clear_customer_info()
        self.order_bar.set_active_bill(None)
        self.order_bar.refresh_tabs()

        # Show Receipt Options if configured (dialog handles printing)
        if ConfigService.get("show_receipt_dialog"):
            dlg = ReceiptOptionsDialog(sale, self)
            dlg.exec()
        self.barcode_input.setFocus()

    def quick_pay(self) -> None:
        """Quick close with full cash payment, skipping the payment dialog (F12)."""
        if getattr(self, "_processing", False):
            return
        # Check if quick pay is enabled in settings
        if not ConfigService.get("quick_pay_enabled"):
            QMessageBox.information(self, "Disabled", "Quick Pay is disabled in settings.")
            return

        if not self.cart_service.items:
            return

        totals = self.cart_service.get_totals()
        if totals["subtotal"] <= 0:
            return

        payments = [{"method": "CASH", "amount": totals["final_total"]}]
        customer_id = self.customer.id if self.customer else None

        self._processing = True
        try:
            sale = TransactionService.process_sale(self.cart_service, payments, customer_id)
            if sale:
                self._finalize_sale(sale)
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Transaction failed: {str(e)}")
        finally:
            self._processing = False
        self.barcode_input.setFocus()

    def select_first_cart_item(self) -> None:
        """Select the first item in the cart table (Page Up)."""
        if self.cart_table.rowCount() > 0:
            self.cart_table.selectRow(0)

    def select_last_cart_item(self) -> None:
        """Select the last item in the cart table (Page Down)."""
        count = self.cart_table.rowCount()
        if count > 0:
            self.cart_table.selectRow(count - 1)

    def show_shortcuts_help(self):
        """Show keyboard shortcuts help dialog (F1)."""
        from cbpos.ui.dialogs.shortcuts_help_dialog import ShortcutsHelpDialog

        dialog = ShortcutsHelpDialog(self)
        dialog.exec()
        self.barcode_input.setFocus()
