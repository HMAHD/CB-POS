import logging
from decimal import Decimal

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cbpos.config import Config
from cbpos.core.services.cart_service import CartService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.customer_service import CustomerService
from cbpos.core.services.logging_service import LoggingService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.scale_service import ScaleService
from cbpos.core.services.sound_service import SoundService
from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.formatters import format_currency
from cbpos.i18n import _t, register_language_callback
from cbpos.infrastructure.hardware.escpos_driver import printer_not_configured_message, receipt_printer_configured
from cbpos.ui.constants import CART_TABLE_ROW_HEIGHT, SEARCH_BAR_HEIGHT
from cbpos.ui.dialogs.advanced_search_dialog import AdvancedSearchDialog
from cbpos.ui.dialogs.customer_quick_add import CustomerQuickAddDialog
from cbpos.ui.dialogs.customer_selection_dialog import CustomerSelectionDialog
from cbpos.ui.dialogs.discount_dialog import DiscountDialog
from cbpos.ui.dialogs.payment_dialog import PaymentDialog
from cbpos.ui.dialogs.quantity_dialog import QuantityDialog
from cbpos.ui.dialogs.receipt_options_dialog import ReceiptOptionsDialog
from cbpos.ui.dialogs.set_item_price_dialog import SetItemPriceDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.utils.style_helpers import refresh_style
from cbpos.ui.widgets.action_panel import ActionPanel
from cbpos.ui.widgets.empty_state_widget import EmptyStateWidget
from cbpos.ui.widgets.order_bar import OrderBar
from cbpos.ui.widgets.side_menu import SideMenu

logger = logging.getLogger(__name__)


class SalesView(QWidget):
    """Main checkout screen: cart, barcode scanning, product search, and payment flow."""

    shift_closed = pyqtSignal()
    printer_setup_requested = pyqtSignal()  # "Set up printer" on the no-printer notice

    # The no-printer notice shows by itself once per app session (#623).
    _printer_notice_shown: bool = False

    def __init__(self):
        """Initialize services, build the UI, and wire up the side menu and print-error listener."""
        super().__init__()
        self.cart_service = CartService()
        self.product_service = ProductService()
        self.customer_service = CustomerService()
        self.customer = None
        self.current_search_mode = ConfigService.get("default_search_mode") or "ALL"
        self._undo_data = None
        self._processing: bool = False
        self._pending_proforma_id: int | None = None

        # Listen for print/drawer failures for the rest of the app's
        # lifetime. Covers open_cash_drawer() below, and also the
        # automatic post-sale receipt print (PrintWorkerPeripherals, used
        # when show_receipt_dialog is off for a frictionless checkout)
        # -- that path has no dialog of its
        # own to report a failure through, so without this the cashier
        # had no way to know a receipt silently failed to print.
        from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

        PrintWorker.instance().error_occurred.connect(self._on_print_error)

        self.init_ui()
        self.retranslate_ui()

        # Side Menu Overlay
        self.side_menu = SideMenu(self)
        self.side_menu.setVisible(False)

        # Animation
        self.menu_animation = QPropertyAnimation(self.side_menu, b"pos")
        self.menu_animation.setDuration(300)
        self.menu_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Install Event Filter for clicking outside
        self.installEventFilter(self)

        # Register for language changes
        register_language_callback(self.retranslate_ui, owner=self)

    def init_ui(self):
        """Build the header, cart/totals panel, action panel, and keyboard shortcuts."""
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

        # "No receipt printer" notice (#623) -- shown once per app session
        # by showEvent; non-blocking, so the cashier can keep selling.
        self.printer_notice = QFrame()
        self.printer_notice.setObjectName("PrinterNotice")
        notice_layout = QHBoxLayout(self.printer_notice)
        notice_layout.setContentsMargins(20, 6, 12, 6)
        self.printer_notice_label = QLabel()
        self.printer_notice_label.setObjectName("PrinterNoticeText")
        self.printer_notice_label.setWordWrap(True)
        notice_layout.addWidget(self.printer_notice_label, 1)
        self.printer_notice_setup = QPushButton()
        self.printer_notice_setup.setObjectName("PrinterNoticeSetupBtn")
        self.printer_notice_setup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.printer_notice_setup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.printer_notice_setup.clicked.connect(self._on_printer_setup_clicked)
        notice_layout.addWidget(self.printer_notice_setup)
        self.printer_notice_close = QToolButton()
        self.printer_notice_close.setObjectName("PrinterNoticeCloseBtn")
        self.printer_notice_close.setText("✕")
        self.printer_notice_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.printer_notice_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.printer_notice_close.clicked.connect(self.printer_notice.hide)
        notice_layout.addWidget(self.printer_notice_close)
        self.printer_notice.setVisible(False)
        # Only ever as tall as its text: QFrame and QSplitter are both
        # "Preferred" vertically, so without this (and the splitter's
        # stretch below) the main layout split the spare height between
        # them and the one-line notice ballooned to ~190px, squeezing the
        # cart and totals (#602).
        self.printer_notice.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        main_layout.addWidget(self.printer_notice)

        # 3. Content Area (Splitter) -- takes all remaining height
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(10)
        self.splitter.setChildrenCollapsible(False)
        main_layout.addWidget(self.splitter, 1)

        # ==========================
        # LEFT PANEL (Cart & Totals) - 75%
        # ==========================
        self.container_left = QWidget()
        self.container_left.setMinimumWidth(400)
        left_layout = QVBoxLayout(self.container_left)
        # Extra bottom margin: the totals row below can grow up to 4 lines
        # tall (item count/subtotal/discount/tax+exempt) plus the 48px
        # grand-total text, and a bare 10px left it sitting uncomfortably
        # close to the window's bottom edge on compact POS-hardware screens.
        left_layout.setContentsMargins(10, 10, 10, 16)
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

        # Icons instead of symbol labels (#213) -- "*", "||||", "#", "Tag" were
        # tested with non-technical shop owners and were not understood (a
        # magnifying glass, barcode, hashtag, and font glyph are self-evident
        # even without reading the tooltip, which requires a hover that
        # doesn't happen on a touch screen anyway).
        modes = [
            ("ALL", Icons.SEARCH),
            ("BARCODE", Icons.SEARCH_BARCODE),
            ("CODE", Icons.SEARCH_CODE),
            ("NAME", Icons.SEARCH_NAME),
        ]

        for mode_id, icon_name in modes:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setToolTip("")  # Set by retranslate_ui
            btn.setFixedSize(40, 40)
            btn.setIconSize(QSize(18, 18))
            btn.setProperty("mode", mode_id)
            btn.setProperty("iconName", icon_name)
            btn.setProperty("class", "SearchModeBtn")  # For styling
            btn.setObjectName("SearchModeBtn")  # For styling

            if mode_id == self.current_search_mode:
                btn.setChecked(True)

            self.mode_group.addButton(btn)
            search_layout.addWidget(btn)

        self._refresh_search_mode_icons()
        from cbpos.core.services.theme_service import ThemeService

        ThemeService.register_theme_callback(self._refresh_search_mode_icons)

        search_layout.addSpacing(10)

        # Search Input
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("")  # Set by retranslate_ui
        self.barcode_input.setFixedHeight(CART_TABLE_ROW_HEIGHT)

        self.barcode_input.returnPressed.connect(self.process_barcode)
        search_layout.addWidget(self.barcode_input)

        self.setup_autocomplete()
        left_layout.addWidget(search_container)

        # 2. Cart Table (Center)
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(5)
        self.cart_table.setHorizontalHeaderLabels(["", "", "", "", ""])  # Set by retranslate_ui

        # Optimized column sizing for better readability
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Item - flexible
        self.cart_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # Price - fixed
        self.cart_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # Qty - fixed
        self.cart_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # Disc - fixed
        self.cart_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)  # Total - fixed

        # Set fixed widths for numeric columns (better alignment)
        self.cart_table.setColumnWidth(1, 140)  # Price
        self.cart_table.setColumnWidth(2, 65)  # Qty
        self.cart_table.setColumnWidth(3, 65)  # Disc
        self.cart_table.setColumnWidth(4, 120)  # Total

        # Guard against columns truncating below readability on small/high-DPI
        # screens (the Item column, being Stretch-mode, always keeps whatever
        # width remains — this only bounds the Fixed-mode numeric columns).
        self.cart_table.horizontalHeader().setMinimumSectionSize(55)

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

        left_layout.addWidget(self.cart_table)

        # Empty Cart Placeholder -- an overlay centered over the table's own
        # row area (parented to its viewport), not a whole separate widget
        # swapped in for the table (#256). The header stays visible at all
        # times; only the "no rows yet" hint appears/disappears. Positioned
        # manually the same way the undo toast already is elsewhere in this
        # file, since a plain widget doesn't participate in viewport layout.
        # Uses the shared EmptyStateWidget (icon + text) instead of bare
        # text in a black rectangle -- the least-designed part of the
        # screen otherwise (#254/#257).
        self.empty_cart_label = EmptyStateWidget(Icons.SALES, self.cart_table.viewport())

        # Undo Toast (overlay at bottom of cart area)
        self.undo_toast = QLabel(self.container_left)
        self.undo_toast.setObjectName("UndoToast")
        self.undo_toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        # Subtotals (Left). With all 5 possible lines visible (item count,
        # subtotal, discount, tax, exempt) this column could grow tall
        # enough to sit uncomfortably close to the window's bottom edge on
        # a compact POS-hardware screen -- tighter spacing plus sharing the
        # tax/exempt line (they're the same breakdown anyway) keeps the
        # worst case to 4 lines instead of 5.
        subtotal_layout = QVBoxLayout()
        subtotal_layout.setSpacing(2)
        self.lbl_item_count = QLabel("")
        self.lbl_item_count.setObjectName("ItemCountLabel")
        self.lbl_subtotal = QLabel("")
        self.lbl_subtotal.setObjectName("SubtotalLabel")
        self.lbl_discount = QLabel("")
        self.lbl_discount.setObjectName("DiscountLabel")
        self.lbl_tax = QLabel("")
        self.lbl_tax.setObjectName("TaxLabel")
        self.lbl_exempt = QLabel("")
        self.lbl_exempt.setObjectName("ExemptLabel")
        self.lbl_exempt.setVisible(False)
        subtotal_layout.addWidget(self.lbl_item_count)
        subtotal_layout.addWidget(self.lbl_subtotal)
        subtotal_layout.addWidget(self.lbl_discount)

        tax_row = QHBoxLayout()
        tax_row.setSpacing(12)
        tax_row.addWidget(self.lbl_tax)
        tax_row.addWidget(self.lbl_exempt)
        tax_row.addStretch()
        subtotal_layout.addLayout(tax_row)

        total_layout.addLayout(subtotal_layout)

        total_layout.addStretch()

        # Grand Total (Right)
        grand_total_layout = QVBoxLayout()
        grand_total_layout.setSpacing(2)
        grand_total_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.lbl_grand_total_title = QLabel(_t("cart.header_total").upper())
        self.lbl_grand_total_title.setObjectName("GrandTotalCaption")
        self.lbl_grand_total_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.total_label = QLabel("0.00")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.total_label.setObjectName("TotalLabel")

        grand_total_layout.addWidget(self.lbl_grand_total_title)
        grand_total_layout.addWidget(self.total_label)
        total_layout.addLayout(grand_total_layout)

        self.total_widget = total_widget
        left_layout.addWidget(total_widget)

        # ==========================
        # RIGHT PANEL (Controls) - 25%
        # ==========================
        self.action_panel = ActionPanel()
        self.action_panel.setMinimumWidth(280)
        self.action_panel.setMaximumWidth(400)
        self.action_panel.setObjectName("ActionPanel")

        # Connect Action Panel Signals
        self.action_panel.customer_clicked.connect(self.select_customer)
        self.action_panel.customer_cleared.connect(self.clear_customer)
        self.action_panel.pay_clicked.connect(self.process_payment)

        self.action_panel.action_f2.connect(self.select_customer)
        self.action_panel.action_f3.connect(self.open_advanced_search)
        self.action_panel.action_f4.connect(self.change_line_quantity)
        self.action_panel.action_f6.connect(self.hold_bill)
        self.action_panel.action_f7.connect(self.recall_bill)
        self.action_panel.action_f8.connect(self.open_cash_drawer)
        self.action_panel.action_del.connect(self.void_bill)
        self.action_panel.action_ref.connect(self.open_refund)

        # Context Menu for Customer Button
        self.action_panel.btn_cust_select.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.action_panel.btn_cust_select.customContextMenuRequested.connect(self.show_customer_menu)
        self.btn_cust = self.action_panel.btn_cust_select  # Alias for existing code

        # Add panels to splitter
        self.splitter.addWidget(self.container_left)
        self.splitter.addWidget(self.action_panel)

        # Stretch: cart expands, action_panel fixed width
        self.splitter.setStretchFactor(0, 1)  # container_left — takes remaining space
        self.splitter.setStretchFactor(1, 0)  # action_panel — fixed width
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

        # Shortcuts
        self.setup_shortcuts()

        # Initialize Cart
        self.update_cart_ui()

    def retranslate_ui(self) -> None:
        """Update all widget text for current language."""
        self.printer_notice_label.setText(_t("sales.printer_notice"))
        self.printer_notice_setup.setText(_t("sales.printer_notice_setup"))
        self.printer_notice_close.setToolTip(_t("sales.printer_notice_dismiss"))

        # Search mode tooltips
        mode_tooltip_keys = {
            "ALL": "sales.search_mode_all",
            "BARCODE": "sales.search_mode_barcode",
            "CODE": "sales.search_mode_code",
            "NAME": "sales.search_mode_name",
        }
        for btn in self.mode_group.buttons():
            mode = btn.property("mode")
            key = mode_tooltip_keys.get(mode)
            if key:
                btn.setToolTip(_t(key))

        # Search input placeholder
        self._update_search_placeholder()

        # Cart table headers
        self.cart_table.setHorizontalHeaderLabels(
            [
                _t("cart.header_item"),
                _t("cart.header_price"),
                _t("cart.header_qty"),
                _t("cart.header_disc"),
                _t("cart.header_total"),
            ]
        )
        # Right-align the numeric column headers (Price/Qty/Disc/Total) to
        # match the right-aligned data beneath them -- ITEM (0) stays left.
        for col in (1, 2, 3, 4):
            header_item = self.cart_table.horizontalHeaderItem(col)
            if header_item:
                header_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Empty cart placeholder
        self.empty_cart_label.set_title(_t("sales.empty_cart"))

        # Totals — refresh display with current values
        self.lbl_grand_total_title.setText(_t("cart.header_total").upper())
        self.update_cart_display()

    def _update_search_placeholder(self) -> None:
        """Set the search placeholder text based on current search mode."""
        placeholder_keys = {
            "ALL": "sales.search_placeholder_all",
            "BARCODE": "sales.search_placeholder_barcode",
            "CODE": "sales.search_placeholder_code",
            "NAME": "sales.search_placeholder_name",
        }
        key = placeholder_keys.get(self.current_search_mode, "sales.search_placeholder_default")
        self.barcode_input.setPlaceholderText(_t(key))

    def update_logo(self):
        """Set the header logo and icons (also called on theme change)."""
        # The header is navy in *both* themes (#HeaderWidget in dark.qss and
        # light.qss), so it always needs the white-text logo -- the
        # theme-dependent ThemeService.get_logo_path() handed Light mode the
        # black-text one, nearly invisible on navy (#603).
        logo_path = Config.BASE_DIR / "cbpos" / "assets" / "logo" / "cover_white.png"

        if logo_path.exists():
            logo_pixmap = QPixmap(str(logo_path))
            self.lbl_logo.setPixmap(logo_pixmap.scaledToHeight(35, Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_logo.setText(_t("sales.logo_fallback"))  # Fallback
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
        """Register the POS keyboard shortcuts (F1-F12, Ctrl+D/Z, Delete, Page Up/Down, Enter)."""
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
        """Reposition the side menu, undo toast, and empty-cart hint; compact the total font on short windows."""
        super().resizeEvent(event)
        menu_width = self.side_menu.width()
        if self.side_menu.isVisible():
            self.side_menu.setGeometry(self.width() - menu_width, 0, menu_width, self.height())
        else:
            self.side_menu.setGeometry(self.width(), 0, menu_width, self.height())

        # Shrink the grand-total font on short windows (#202) — driven by a
        # QSS property selector, not an inline stylesheet, so it doesn't
        # fight the theme cascade the way #219 did.
        compact = self.height() < 900
        if self.total_label.property("compact") != compact:
            self.total_label.setProperty("compact", compact)
            refresh_style(self.total_label)

        # Keep the undo toast anchored correctly if the window is resized
        # while it's showing (#205) — it's positioned with absolute pixel
        # arithmetic, so it doesn't move on its own the way a layout would.
        if self.undo_toast.isVisible():
            self._position_undo_toast()

        if self.empty_cart_label.isVisible():
            self._position_empty_cart_label()

    def toggle_side_menu(self):
        """Slide the side menu open or closed over the action panel.

        The action panel stays where it is underneath the (opaque) menu.
        It used to be hidden while the menu was open, which let the
        splitter re-flow the cart to the full window width -- straight
        under the menu, hiding the Price/Qty/Disc/Total columns and the
        grand total (#602), and leaving the panel hidden for good if a
        resize raced the close animation (#206).
        """
        menu_width = self.side_menu.width()
        start_pos = self.side_menu.pos()

        if self.side_menu.isVisible():
            # Slide Out (Hide)
            end_pos = QPoint(self.width(), 0)
            self.menu_animation.setStartValue(start_pos)
            self.menu_animation.setEndValue(end_pos)

            def _on_hidden():
                self.side_menu.setVisible(False)
                self.menu_animation.finished.disconnect(_on_hidden)

            self.menu_animation.finished.connect(_on_hidden)
            self.menu_animation.start()
        else:
            self.side_menu.setVisible(True)
            self.side_menu.raise_()
            start_pos = QPoint(self.width(), 0)
            end_pos = QPoint(self.width() - menu_width, 0)
            self.side_menu.setGeometry(self.width(), 0, menu_width, self.height())

            self.menu_animation.setStartValue(start_pos)
            self.menu_animation.setEndValue(end_pos)
            self.menu_animation.start()

    def eventFilter(self, source, event):
        """Close the side menu when a click lands outside it."""
        if event.type() == event.Type.MouseButtonPress and self.side_menu.isVisible():
            # Check if click is outside menu
            if not self.side_menu.geometry().contains(event.pos()) and source is not self.menu_button:
                self.toggle_side_menu()
                return True
        return super().eventFilter(source, event)

    def showEvent(self, event):
        """Close a left-open side menu and refresh order tabs when returning to this view."""
        super().showEvent(event)
        if self.side_menu.isVisible():
            self.side_menu.setVisible(False)
            self.side_menu.clear_active()
        self._focus_search()
        self.order_bar.refresh_tabs()

        if not SalesView._printer_notice_shown and not receipt_printer_configured():
            SalesView._printer_notice_shown = True
            self._show_printer_notice()

    def _show_printer_notice(self) -> None:
        """Show the no-printer notice; the setup button only for users who can open Settings."""
        self.printer_notice_setup.setVisible(not self.side_menu.btn_settings.isHidden())
        self.printer_notice.setVisible(True)

    def _on_printer_setup_clicked(self) -> None:
        """Hide the notice and ask MainWindow to open Settings -> Hardware."""
        self.printer_notice.setVisible(False)
        self.printer_setup_requested.emit()

    def _focus_search(self) -> None:
        """Put the cursor back in the search box so the next scan or keystroke lands there (#535).

        Skipped while a dialog is open (e.g. Advanced Search stays up after a
        pick): the search box gets focus once that dialog's own caller closes it.
        """
        if QApplication.activeModalWidget() is None:
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

        # 1. Check for Loyalty Card. loyalty_card_code is free text (set in
        # CustomerEditor, no fixed prefix/length -- #488), so match it
        # directly rather than guessing at a shape first.
        customer = self.customer_service.find_by_loyalty_card(query)
        if customer:
            self.set_customer(customer)
            self.barcode_input.clear()
            self._focus_search()
            return

        if self._add_scale_item(query):
            return

        # Use product_service with current search mode
        products = self.product_service.search_products(query, mode=self.current_search_mode)

        # ALL mode matches barcodes with LIKE, so a full scan can also hit a
        # longer barcode that contains it. "Auto-Select on Barcode Match"
        # (Settings -> System) picks the exact barcode instead of opening
        # the multi-result search (#641).
        if len(products) > 1 and ConfigService.get("auto_select_barcode_match"):
            exact = [p for p in products if p.barcode == query]
            if len(exact) == 1:
                products = exact

        if len(products) == 1:
            SoundService.play("scan_success")
            dialog = QuantityDialog(products[0], self)
            if dialog.exec() and self._confirm_age_restriction(products[0]):
                self.cart_service.add_item(products[0], qty=dialog.get_quantity())
                self.update_cart_display()
            self.barcode_input.clear()
            self._focus_search()
        elif len(products) > 1:
            SoundService.play("scan_success")
            # Open advanced search with pre-filled query
            dialog = AdvancedSearchDialog(self)
            dialog.search_input.setText(query)
            dialog.perform_search()
            dialog.product_selected.connect(self.on_advanced_search_product_selected)
            dialog.exec()
            self.barcode_input.clear()
            self._focus_search()
        else:
            SoundService.play("scan_error")
            QMessageBox.warning(self, _t("sales.not_found_title"), _t("sales.not_found_message"))
            self._focus_search()

    def _add_scale_item(self, code: str) -> bool:
        """Add a weighing-scale label's item at its printed weight (#641).

        Reads the label with Settings -> Hardware -> Weighing Scale (prefix,
        decimal places); the 5-digit item code is the product's Item Code.
        A product whose own barcode is exactly ``code`` always wins.

        Returns:
            bool: True if ``code`` was a scale label for a known product (and was handled).
        """
        places = ConfigService.get("scale_decimal_places")
        parsed = ScaleService.parse_barcode(
            code,
            prefix=str(ConfigService.get("scale_barcode_prefix") or ""),
            decimal_places=None if places is None else int(places),
        )
        if not parsed or parsed["qty"] <= 0 or ProductService.get_by_barcode(code):
            return False
        matches = self.product_service.search_products(str(parsed["product_id"]), mode=ProductService.SEARCH_MODE_CODE)
        if not matches:
            return False

        product = matches[0]
        SoundService.play("scan_success")
        if self._confirm_age_restriction(product):
            self.cart_service.add_item(product, qty=parsed["qty"])
            self.update_cart_display()
        self.barcode_input.clear()
        self._focus_search()
        return True

    def update_cart_display(self):
        """Update cart display with visual indicators (Phase 6)."""
        from cbpos.core.services.theme_service import ThemeService

        is_dark = ThemeService.current_theme.lower() == "dark"
        text_color = QColor("#FFFFFF") if is_dark else QColor("#212529")
        text_brush = QBrush(text_color)

        self.cart_table.setRowCount(0)
        has_items = len(self.cart_service.items) > 0
        self.empty_cart_label.setVisible(not has_items)
        if not has_items:
            self._position_empty_cart_label()
        for row, item in enumerate(self.cart_service.items):
            self.cart_table.insertRow(row)
            self.cart_table.setRowHeight(row, CART_TABLE_ROW_HEIGHT)

            # Product Name (with note indicator)
            name = item["product"].name_en
            if item.get("note"):
                name = f"\U0001f4dd {name}"
            name_item = QTableWidgetItem(name)
            name_item.setToolTip(item["product"].name_en)
            name_item.setForeground(text_brush)

            # Whole-row highlight if discounted (theme-aware) -- computed
            # once so every cell on the line gets it, not just the name
            # cell. A single tinted cell in an otherwise plain row read as
            # half-finished rather than "this whole line is discounted" (#265).
            is_discounted = item.get("discount_type") != "NONE" or item.get("is_manual_price")
            row_bg_brush = None
            if is_discounted:
                bg_color = QColor(0, 50, 0) if is_dark else QColor(220, 255, 220)
                row_bg_brush = QBrush(bg_color)
                name_item.setBackground(row_bg_brush)

            # Price Display (Strikethrough if discounted/overridden)
            if item.get("original_price") and item["unit_price"] < item["original_price"]:
                lbl_price = QLabel()
                lbl_price.setText(
                    "<s>{}</s> <b>{}</b>".format(
                        format_currency(item["original_price"]), format_currency(item["unit_price"])
                    )
                )
                lbl_price.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                lbl_price.setProperty("class", "StrikethroughPrice")
                if row_bg_brush is not None:
                    lbl_price.setStyleSheet(f"background-color: {bg_color.name()};")
                self.cart_table.setCellWidget(row, 1, lbl_price)
            else:
                price_item = QTableWidgetItem(format_currency(item["unit_price"]))
                price_item.setForeground(text_brush)
                price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if row_bg_brush is not None:
                    price_item.setBackground(row_bg_brush)
                self.cart_table.setItem(row, 1, price_item)

            self.cart_table.setItem(row, 0, name_item)

            # Qty column — the raw Decimal always carries 3 decimal places
            # (e.g. "1.000"), which reads as a bug for whole-unit items like
            # bottled water. Format to the product's unit precision instead,
            # falling back to stripping trailing zeros if no unit is set (#224).
            product = item["product"]
            if product.unit is not None:
                dp = product.unit.decimal_places
                qty_str = f"{item['qty']:.{dp}f}"
            else:
                qty_str = f"{item['qty']:.3f}".rstrip("0").rstrip(".") or "0"
            qty_item = QTableWidgetItem(qty_str)
            qty_item.setForeground(text_brush)
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if row_bg_brush is not None:
                qty_item.setBackground(row_bg_brush)
            self.cart_table.setItem(row, 2, qty_item)

            # Disc column
            disc_val = item.get("discount_value", Decimal("0.00"))
            disc_type = item.get("discount_type", "NONE")
            if disc_val <= 0:
                disc_text = "-"
            elif disc_type == "FIXED":
                disc_text = format_currency(disc_val)
            else:
                disc_text = f"{disc_val}%"
            disc_item = QTableWidgetItem(disc_text)
            disc_item.setForeground(text_brush)
            disc_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if row_bg_brush is not None:
                disc_item.setBackground(row_bg_brush)
            self.cart_table.setItem(row, 3, disc_item)

            # Total column
            total_item = QTableWidgetItem(format_currency(item["total"]))
            total_item.setForeground(text_brush)
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if row_bg_brush is not None:
                total_item.setBackground(row_bg_brush)
            self.cart_table.setItem(row, 4, total_item)

        totals = self.cart_service.get_totals()
        final_total = totals.get("final_total", 0)
        subtotal = totals.get("subtotal", 0)
        cart_discount = totals.get("cart_discount", 0)
        item_count = totals.get("item_count", 0)

        from cbpos.core.services.config_service import ConfigService
        from cbpos.core.services.tax_service import TaxService

        tax_vat = totals.get("tax_vat", 0)
        tax_sscl = totals.get("tax_sscl", 0)
        tax_total = totals.get("tax", 0)
        exempt_amount = totals.get("exempt_amount", Decimal("0.00"))
        vat_active = TaxService.is_vat_active()

        self.total_label.setText(format_currency(final_total))
        self.lbl_subtotal.setText(_t("cart.subtotal", amount=format_currency(subtotal)))
        self.lbl_discount.setText(_t("cart.discount", amount=format_currency(cart_discount)))

        # Hide tax labels entirely when VAT is off
        if not vat_active:
            self.lbl_tax.setVisible(False)
            self.lbl_exempt.setVisible(False)
        else:
            self.lbl_tax.setVisible(True)
            if ConfigService.get("show_tax_breakdown") and tax_total > 0:
                self.lbl_tax.setText(
                    _t("cart.tax_breakdown", vat=format_currency(tax_vat), sscl=format_currency(tax_sscl))
                )
            else:
                self.lbl_tax.setText(_t("cart.tax", amount=format_currency(tax_total)))

            # Show exempt amount when applicable
            if exempt_amount > 0:
                self.lbl_exempt.setText(_t("cart.tax_exempt", amount=format_currency(exempt_amount)))
                self.lbl_exempt.setVisible(True)
            else:
                self.lbl_exempt.setVisible(False)

        self.lbl_item_count.setText(_t("cart.item_count", count=item_count))
        self.cart_table.scrollToBottom()

        # Brief highlight on last row to give visual feedback on item add.
        # A barcode scanner can add 2-5 items/second -- faster than the old
        # fixed 800ms QTimer.singleShot(), whose closure captured last_row by
        # value. A second scan before the first timer fired left two rows
        # highlighted at once, and once the table had been rebuilt again,
        # the stale closure's last_row could point at the wrong row
        # entirely (#222). A single cancellable timer, stopped and
        # restarted on every scan, means only the latest one ever fires.
        if not hasattr(self, "_highlight_timer"):
            self._highlight_timer = QTimer(self)
            self._highlight_timer.setSingleShot(True)

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

            self._highlight_timer.stop()
            try:
                self._highlight_timer.timeout.disconnect()
            except TypeError:
                pass  # nothing connected yet
            self._highlight_timer.timeout.connect(_clear_highlight)
            self._highlight_timer.start(600)

    def select_customer(self):
        """Open the customer selection dialog and apply the chosen customer (F2)."""
        dialog = CustomerSelectionDialog(self)
        if dialog.exec():
            self.set_customer(dialog.selected_customer)
        self._focus_search()

    def set_customer(self, customer):
        """Display the given customer and apply their pricing to the cart."""
        self.customer = customer
        self.action_panel.set_customer_info(self.customer.name, self.customer.phone, self.customer.loyalty_points)
        # CartService tracks its own customer for pricing (customer-specific
        # price lists), independently of this view's own display state --
        # without this, selecting a customer here never actually applied
        # their pricing to items added afterward.
        self.cart_service.set_customer(customer)

    def show_customer_menu(self, pos):
        """Show the customer button's context menu (quick add, view details, clear)."""
        menu = QMenu(self)

        quick_add = QAction(_t("customer_menu.quick_add_new"), self)
        quick_add.triggered.connect(self.quick_add_customer)
        menu.addAction(quick_add)

        if self.customer:
            details = QAction(_t("customer_menu.view_details"), self)
            menu.addAction(details)

            clear = QAction(_t("customer_menu.clear_customer"), self)
            clear.triggered.connect(self.clear_customer)
            menu.addAction(clear)

        menu.exec(self.btn_cust.mapToGlobal(pos))

    def quick_add_customer(self):
        """Open the quick-add customer dialog and select the newly created customer."""
        dialog = CustomerQuickAddDialog(self)
        if dialog.exec():
            self.set_customer(dialog.created_customer)
        self._focus_search()

    def clear_customer(self):
        """Reset the sale back to Walk-in Customer."""
        self.customer = None
        self.action_panel.clear_customer_info()
        self.cart_service.set_customer(None)
        self._focus_search()

    def process_payment(self):
        """Open the payment dialog and complete the sale on confirmation (F5/F10)."""
        if self._processing:
            return
        totals = self.cart_service.get_totals()
        if totals["subtotal"] <= 0:
            SoundService.play("scan_error")
            self._flash_pay_button_error()
            self._focus_search()
            return

        # A payment shortcut (F5/F10/F12) firing while the side menu is open
        # would otherwise open the dialog behind/under the menu overlay (#206).
        if self.side_menu.isVisible():
            self.toggle_side_menu()

        dialog = PaymentDialog(totals["final_total"], self, customer=self.customer)
        if dialog.exec():
            payments, dialog_customer_id = dialog.payment_data
            customer_id = dialog_customer_id or (self.customer.id if self.customer else None)
            redeemed_points = dialog.loyalty_points_redeemed

            self._processing = True
            try:
                sale = TransactionService.process_sale(
                    self.cart_service,
                    payments,
                    customer_id,
                    loyalty_points_redeemed=redeemed_points,
                )
                if sale:
                    # Mark proforma as converted if this was a proforma-to-sale conversion
                    proforma_id = self._pending_proforma_id
                    if proforma_id:
                        from cbpos.core.services.proforma_service import ProformaService

                        ProformaService.mark_converted(proforma_id, sale.id)
                        self._pending_proforma_id = None

                    self._finalize_sale(sale)
            except ValueError as e:
                QMessageBox.warning(self, _t("sales.validation_error"), str(e))
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), _t("sales.transaction_failed", error=str(e)))
            finally:
                self._processing = False
        self._focus_search()

    def hold_bill(self):
        """Suspend the current cart as a held bill and clear the view for a new one (F6)."""
        if not self.cart_service.items:
            return

        held_id = SuspendedTransactionService.hold_bill(self.cart_service)
        if held_id:
            self.cart_service.clear()
            # The held bill's own customer was already saved with it
            # (restored on recall) -- clear the display here so the next
            # cart starts on Walk-in Customer instead of visually keeping
            # whoever was selected for the bill just put away.
            self.clear_customer()
            self.update_cart_display()
            self.order_bar.refresh_tabs()
            QMessageBox.information(self, _t("orders.held_title"), _t("orders.held_message", id=held_id))
        else:
            QMessageBox.critical(self, _t("common.error"), _t("orders.held_error"))
        self._focus_search()

    def recall_bill(self):
        """Recall the most recently held bill back into the cart (F7)."""
        suspended = SuspendedTransactionService.get_latest_suspended()
        if not suspended:
            QMessageBox.information(self, _t("orders.empty_title"), _t("orders.empty_message"))
            self._focus_search()
            return

        if SuspendedTransactionService.recall_bill(suspended.id, self.cart_service):
            # recall_bill() already restored (or cleared) the customer on
            # cart_service itself -- sync this view's own display state
            # (the action panel, self.customer) to match.
            recalled_customer = self.cart_service.get_customer()
            if recalled_customer:
                self.set_customer(recalled_customer)
            else:
                self.clear_customer()

            self.order_bar.set_active_bill(suspended.id)
            self.update_cart_display()
            self.order_bar.refresh_tabs()
            QMessageBox.information(self, _t("orders.recalled_title"), _t("orders.recalled_message", id=suspended.id))
        else:
            QMessageBox.critical(self, _t("common.error"), _t("orders.recall_error"))
        self._focus_search()

    def void_bill(self):
        """Void the in-progress cart after permission check and confirmation (Delete)."""
        # If cart is empty, nothing to void
        if not self.cart_service.items:
            return

        # 1. Check Permission (with manager override)
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        authorized_user = check_permission_with_override(Permissions.SALES_VOID, self)
        if not authorized_user:
            return

        # 2. Confirm Void
        reply = QMessageBox.question(
            self,
            _t("orders.void_title"),
            _t("orders.void_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            item_count = len(self.cart_service.items)
            self.cart_service.clear()
            self.clear_customer()
            self.update_cart_display()
            LoggingService.log_action(
                user_id=authorized_user.id,
                action="VOID_BILL",
                event_type="TRANSACTION",
                details=f"Voided in-progress cart with {item_count} item(s)",
            )
        self._focus_search()

    # --- Phase 6: Advanced Search & Cart Enhancements ---

    def on_search_mode_changed(self, button):
        """Handle search mode change from segmented control."""
        mode = button.property("mode")
        self.current_search_mode = mode
        self._update_search_placeholder()
        self._refresh_search_mode_icons()
        self._focus_search()

    def _refresh_search_mode_icons(self) -> None:
        """Re-tint each search-mode icon for the current theme + checked
        state (#213). Checked/unchecked use opposite icon colors in both
        themes -- e.g. dark theme's checked state is a black icon on a
        cyan background -- so this can't be set once at construction."""
        from cbpos.core.services.theme_service import ThemeService

        is_dark = ThemeService.current_theme.lower() == "dark"
        for btn in self.mode_group.buttons():
            icon_name = btn.property("iconName")
            if not icon_name:
                continue
            if is_dark:
                color = "#000000" if btn.isChecked() else "#FFFFFF"
            else:
                color = "#FFFFFF" if btn.isChecked() else "#495057"
            btn.setIcon(Icons.get(icon_name, color=color))

    def set_search_mode(self, mode: str, icon: str):
        """Check the segmented-control button for the given search mode."""
        # Legacy support or external call
        # Find button with this mode and check it
        for btn in self.mode_group.buttons():
            if btn.property("mode") == mode:
                btn.setChecked(True)
                self.on_search_mode_changed(btn)
                break

    def setup_autocomplete(self):
        """Setup QCompleter for product names.

        Runs the product-name query in a background thread (#216) -- on a
        5,000+ product inventory this took 300-800ms run synchronously in
        __init__, causing a visible freeze at first launch and after every
        multi-user login switch. Bumped from top-100 to top-500 while at
        it, since a product outside the top 100 by sales count previously
        got no autocomplete suggestion even for an exact-name match.
        """
        from cbpos.ui.workers import AutocompleteLoadWorker

        self._autocomplete_worker = AutocompleteLoadWorker(self.product_service, limit=500)
        self._autocomplete_worker.result.connect(self._on_autocomplete_loaded)
        self._autocomplete_worker.start()

    def _on_autocomplete_loaded(self, names: list) -> None:
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
        icon_color = "#FFFFFF" if self._is_dark_theme() else "#212529"

        add_note_action = QAction(Icons.get(Icons.NOTE, icon_color), _t("cart.context_add_note"), self)
        add_note_action.triggered.connect(self.add_line_note)
        menu.addAction(add_note_action)

        # F4 is a real, already-existing global QShortcut for this exact
        # handler (see setup_shortcuts). Shown as a text hint via "\t" rather
        # than action.setShortcut("F4"): a second, separate F4 registration
        # on the same window risks Qt treating the key as ambiguous and
        # firing neither one, silently breaking the shortcut that already
        # works -- not something to risk without being able to verify it.
        change_qty_action = QAction(Icons.get(Icons.QTY, icon_color), _t("cart.context_change_qty") + "\tF4", self)
        change_qty_action.triggered.connect(self.change_line_quantity)
        menu.addAction(change_qty_action)

        discount_action = QAction(Icons.get(Icons.PERCENT, icon_color), _t("cart.context_line_discount"), self)
        discount_action.triggered.connect(self.apply_line_discount)
        menu.addAction(discount_action)

        price_action = QAction(Icons.get(Icons.EDIT, icon_color), _t("cart.context_change_price"), self)
        price_action.triggered.connect(self.change_line_price)
        menu.addAction(price_action)

        # Deliberately no Delete-key shortcut here: Delete is already bound
        # globally to void_bill() (voiding the *entire* sale) -- binding it
        # here too would make one keypress do two different destructive
        # things depending on focus, which is worse than no shortcut at all.
        remove_action = QAction(Icons.get(Icons.DELETE, "#FF4136"), _t("cart.context_remove_item"), self)
        remove_action.triggered.connect(self.remove_line_item)
        menu.addAction(remove_action)

        menu.exec(self.cart_table.viewport().mapToGlobal(position))

    def _is_dark_theme(self) -> bool:
        from cbpos.core.services.theme_service import ThemeService

        return ThemeService.current_theme.lower() == "dark"

    def _flash_pay_button_error(self) -> None:
        """Briefly flash PAY red when clicked on an empty cart (#209).

        Previously only a sound played -- silent to a cashier who has
        speakers muted, or just doesn't register a beep as "add items
        first" versus a hardware problem. Property+polish, not an inline
        stylesheet, matching the #219 pattern.
        """
        btn = self.action_panel.btn_pay
        btn.setProperty("state", "error")
        refresh_style(btn)

        def _clear_error() -> None:
            btn.setProperty("state", "")
            refresh_style(btn)

        # Owned by the button, so it dies with it instead of firing on a deleted widget.
        timer = QTimer(btn)
        timer.setSingleShot(True)
        timer.timeout.connect(_clear_error)
        timer.timeout.connect(timer.deleteLater)
        timer.start(400)

    def add_line_note(self):
        """Add note to selected cart line."""
        row = self.cart_table.currentRow()
        if row >= 0:
            note, ok = QInputDialog.getText(self, _t("cart.line_note_title"), _t("cart.line_note_prompt"))
            if ok and note:
                self.cart_service.items[row]["note"] = note
                self.update_cart_display()
        self._focus_search()

    def change_line_quantity(self):
        """Change quantity of selected cart line."""
        row = self.cart_table.currentRow()
        if row >= 0:
            item = self.cart_service.items[row]
            dialog = QuantityDialog(item["product"], parent=self, initial_qty=item["qty"])
            if dialog.exec():
                self.cart_service.update_quantity(row, dialog.get_quantity())
                self.update_cart_display()
        self._focus_search()

    def apply_line_discount(self):
        """Apply discount to selected cart line."""
        row = self.cart_table.currentRow()
        if row < 0:
            return

        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        authorized_user = check_permission_with_override(Permissions.SALES_DISCOUNT, self)
        if not authorized_user:
            return

        line_total = self.cart_service.items[row]["total"] if row < len(self.cart_service.items) else Decimal("0.00")
        dialog = DiscountDialog(self, original_amount=line_total)
        if dialog.exec():
            disc_type, disc_value = dialog.get_data()
            try:
                self.cart_service.apply_line_discount(row, disc_type, disc_value, user=authorized_user)
            except ValueError:
                QMessageBox.warning(
                    self,
                    _t("cart.discount_limit_title"),
                    _t("cart.discount_limit_message", value=str(disc_value)),
                )
                self._focus_search()
                return
            self.update_cart_display()
        self._focus_search()

    def change_line_price(self):
        """Override price of selected cart line (Manager Only)."""
        row = self.cart_table.currentRow()
        if row < 0:
            return

        # 1. Check Permission (with manager override)
        from cbpos.core.constants.permissions import Permissions
        from cbpos.core.utils.permission_helper import check_permission_with_override

        authorized_user = check_permission_with_override(Permissions.SALES_CHANGE_PRICE, self)
        if not authorized_user:
            return

        # 2. Get New Price
        item = self.cart_service.items[row]

        if not item["product"].price_change_allowed:
            QMessageBox.warning(self, _t("common.warning"), _t("cart.price_change_not_allowed"))
            self._focus_search()
            return

        current_price = item["unit_price"]
        dialog = SetItemPriceDialog(item["product"].name_en, current_price, parent=self)
        if dialog.exec():
            new_price = dialog.get_price()
            self.cart_service.override_price(row, new_price, authorized_user)
            self.update_cart_display()
        self._focus_search()

    def remove_line_item(self):
        """Remove selected item from cart with undo support."""
        row = self.cart_table.currentRow()
        if row >= 0:
            from cbpos.core.constants.permissions import Permissions
            from cbpos.core.utils.permission_helper import check_permission_with_override

            if not check_permission_with_override(Permissions.SALES_VOID, self):
                return

            removed_item = self.cart_service.items[row].copy()
            del self.cart_service.items[row]
            self.update_cart_display()

            self._undo_data = {"item": removed_item, "index": row}

            product_name = removed_item["product"].name_en
            self.undo_toast.setText(_t("cart.removed_undo", product=product_name))
            self.undo_toast.adjustSize()
            self._position_undo_toast()
            self.undo_toast.setVisible(True)
            self.undo_toast.raise_()

            QTimer.singleShot(4000, self._clear_undo)

    def _position_empty_cart_label(self) -> None:
        """Center the empty-cart hint over the table's row area (its viewport)."""
        viewport = self.cart_table.viewport()
        self.empty_cart_label.resize(viewport.size())

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
        self._focus_search()

    def on_advanced_search_product_selected(self, product):
        """Handle product selection from advanced search."""
        dialog = QuantityDialog(product, self)
        if dialog.exec() and self._confirm_age_restriction(product):
            self.cart_service.add_item(product, qty=dialog.get_quantity())
            self.update_cart_display()
        self._focus_search()

    def _confirm_age_restriction(self, product) -> bool:
        """Require cashier confirmation before adding an age-restricted product (#485)."""
        if not product.is_age_restricted:
            return True
        reply = QMessageBox.question(
            self,
            _t("sales.age_restriction_title"),
            _t("sales.age_restriction_confirm", product=product.name_en),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def switch_to_order(self, suspended_id):
        """
        Switch to a held order.
        1. Hold current order (if has items).
        2. Recall target order.
        """
        # 1. Hold Current (Auto-Hold)
        if self.cart_service.items:
            # We don't ask for note here for speed, or maybe use "Auto-Hold" note
            if not SuspendedTransactionService.hold_bill(self.cart_service, note="Auto-Switch"):
                QMessageBox.critical(self, _t("common.error"), _t("orders.switch_error"))
                self._focus_search()
                return
            self.cart_service.clear()

        # 2. Recall Target
        if SuspendedTransactionService.recall_bill(suspended_id, self.cart_service):
            self.order_bar.set_active_bill(suspended_id)
            self.update_cart_display()
            self.order_bar.refresh_tabs()
        else:
            QMessageBox.warning(self, _t("common.error"), _t("orders.recall_taken_error"))
            self.order_bar.refresh_tabs()
        self._focus_search()

    def create_new_order(self):
        """
        Start a new order.
        1. Hold current order (if has items).
        2. Clear cart.
        """
        if self.cart_service.items:
            if SuspendedTransactionService.hold_bill(self.cart_service, note="Auto-Switch"):
                self.cart_service.clear()
                self.update_cart_display()
                self.order_bar.set_active_bill(None)
                self.order_bar.refresh_tabs()
            else:
                QMessageBox.critical(self, _t("common.error"), _t("orders.held_error"))
        else:
            # Already empty, just refresh tabs to be sure
            self.order_bar.set_active_bill(None)
            self.order_bar.refresh_tabs()
        self._focus_search()

    def open_receive_payment(self) -> None:
        """Open Receive Payment dialog from POS (quick payment without sale)."""
        from cbpos.ui.dialogs.receive_payment_dialog import ReceivePaymentDialog

        dialog = ReceivePaymentDialog(parent=self)
        dialog.exec()
        self._focus_search()

    def open_reprint_receipt(self) -> None:
        """Open Receipt Reprint dialog to search and reprint past receipts."""
        from cbpos.ui.dialogs.receipt_reprint_dialog import ReceiptReprintDialog

        dialog = ReceiptReprintDialog(parent=self)
        dialog.exec()
        self._focus_search()

    def open_refund(self) -> None:
        """Open Refund dialog to process returns."""
        from cbpos.ui.dialogs.refund_dialog import RefundDialog

        dialog = RefundDialog(parent=self)
        dialog.exec()
        self._focus_search()

    def open_sale_history(self) -> None:
        """Open Sale History dialog for browsing sales, reprinting, and refunds."""
        from cbpos.ui.dialogs.sale_history_dialog import SaleHistoryDialog

        if self.side_menu.isVisible():
            self.toggle_side_menu()
        dialog = SaleHistoryDialog(parent=self)
        dialog.exec()
        self._focus_search()

    def open_shift_management(self) -> None:
        """Open the Shift dialog (X-read, Cash In/Out, End Shift) for the current user's open shift.

        Ending the shift there ends the cashier's session -- emits
        `shift_closed` so MainWindow can log out, forcing the next user to
        start a fresh shift on login.
        """
        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.shift_service import ShiftService
        from cbpos.ui.dialogs.shift_management_dialog import ShiftManagementDialog

        user = AuthService.get_current_user()
        shift = ShiftService().get_current_shift(user.id) if user else None
        if shift is None:
            QMessageBox.warning(self, _t("common.warning"), _t("shift_closing.no_open_shift"))
            return

        if self.side_menu.isVisible():
            self.toggle_side_menu()
        dialog = ShiftManagementDialog(shift.id, user.id, parent=self)
        dialog.exec()
        if dialog.shift_ended:
            self.shift_closed.emit()
        else:
            self._focus_search()

    def open_cash_drawer(self) -> None:
        """Open the cash drawer via PrintWorker (F8 / Ctrl+D)."""
        from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

        # error_occurred is already connected to _on_print_error once, for
        # the view's lifetime, in __init__ -- no per-call connect needed.
        PrintWorker.instance().add_job("kick_drawer")

    def _on_print_error(self, message: str) -> None:
        """Show printer error to user with context.

        "No printer set up" brings back the non-blocking notice instead --
        a modal after every sale would stall a shop that has no printer.
        """
        if message == printer_not_configured_message():
            self._show_printer_notice()
            return
        QMessageBox.warning(
            self,
            _t("sales.printer_error_title"),
            _t("sales.printer_error_message", message=message),
        )

    def _finalize_sale(self, sale) -> None:
        """Common post-sale cleanup: sound, clear cart, optionally show receipt dialog."""
        SoundService.play("payment_complete")
        self.cart_service.clear()
        self.update_cart_display()
        self._focus_search()
        self.customer = None
        self.action_panel.clear_customer_info()
        self.order_bar.set_active_bill(None)
        self.order_bar.refresh_tabs()

        # Show Receipt Options if configured (dialog handles printing)
        if ConfigService.get("show_receipt_dialog"):
            dlg = ReceiptOptionsDialog(sale, self)
            dlg.exec()
        self._focus_search()

    def quick_pay(self) -> None:
        """Quick close with full cash payment, skipping the payment dialog (F12)."""
        if self._processing:
            return
        # Check if quick pay is enabled in settings
        if not ConfigService.get("quick_pay_enabled"):
            QMessageBox.information(self, _t("sales.disabled"), _t("sales.quick_pay_disabled"))
            self._focus_search()
            return

        totals = self.cart_service.get_totals()
        if not self.cart_service.items or totals["subtotal"] <= 0:
            self._focus_search()
            return

        payments = [{"method": "CASH", "amount": totals["final_total"]}]
        customer_id = self.customer.id if self.customer else None

        self._processing = True
        try:
            sale = TransactionService.process_sale(self.cart_service, payments, customer_id)
            if sale:
                self._finalize_sale(sale)
        except ValueError as e:
            QMessageBox.warning(self, _t("sales.validation_error"), str(e))
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), _t("sales.transaction_failed", error=str(e)))
        finally:
            self._processing = False
        self._focus_search()

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
        self._focus_search()
