import logging

from PyQt6.QtCore import QEvent, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.permission_service import PermissionService
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.resources.icons import Icons
from cbpos.ui.views.credit_book_view import CreditBookView
from cbpos.ui.views.dashboard_view import DashboardView
from cbpos.ui.views.document_view import DocumentBrowserView
from cbpos.ui.views.inventory_view import InventoryView
from cbpos.ui.views.pricelist_view import PriceListView
from cbpos.ui.views.promotion_view import PromotionView
from cbpos.ui.views.purchase_view import PurchaseView
from cbpos.ui.views.reorder_view import ReorderView
from cbpos.ui.views.reports.report_viewer import ReportViewer
from cbpos.ui.views.user_view import UserView
from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar

logger = logging.getLogger(__name__)


class ManagementView(QWidget):
    """Sidebar-navigated shell for inventory, purchasing, reports, and admin screens.

    Individual tab views are created lazily on first visit via
    `switch_tab()` rather than all up front.
    """

    logout_requested = pyqtSignal()
    request_pos_view = pyqtSignal()
    convert_proforma_to_sale = pyqtSignal(dict)

    def __init__(self):
        """Build the sidebar and content stack, then show the Dashboard tab."""
        super().__init__()
        self.init_ui()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

        # Views are now built lazily by switch_tab() (#227), so the stack
        # starts with zero widgets and nothing to show. Before that change,
        # all 10 views were built eagerly and QStackedWidget defaulted to
        # showing the first one added (Dashboard); land on it explicitly
        # here so entering Management isn't blank until a sidebar click (#275).
        self.switch_tab(0)

    def init_ui(self):
        """Build the collapsible sidebar and the (initially empty) content stack."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar ---
        self.sidebar = CollapsibleSidebar()
        self.sidebar.nav_clicked.connect(self.switch_tab)
        self.sidebar.pos_clicked.connect(self.request_pos_view.emit)
        self.sidebar.logout_clicked.connect(self.logout_requested.emit)

        self.btn_dashboard = self.sidebar.add_nav_button("", Icons.DASHBOARD, 0)
        self.btn_inventory = self.sidebar.add_nav_button("", Icons.INVENTORY, 1)
        self.btn_purchasing = self.sidebar.add_nav_button("", Icons.PURCHASE, 2)
        self.btn_customers = self.sidebar.add_nav_button("", Icons.CREDIT_BOOK, 3)

        # Section break: day-to-day operational screens above, management
        # and admin screens below -- a resting point instead of one flat,
        # undifferentiated 10-item list (#315).
        self.lbl_sidebar_section_management = self.sidebar.add_section_label("")

        self.btn_reports = self.sidebar.add_nav_button("", Icons.REPORTS, 4)
        self.btn_documents = self.sidebar.add_nav_button("", Icons.DOCUMENTS, 5)
        self.btn_users = self.sidebar.add_nav_button("", Icons.USERS, 6)
        self.btn_pricelists = self.sidebar.add_nav_button("", Icons.PRICE_LIST, 7)
        self.btn_promotions = self.sidebar.add_nav_button("", Icons.PROMOTION, 8)
        self.btn_stock_take = self.sidebar.add_nav_button("", Icons.STOCK_TAKE, 9)
        self.btn_reorder = self.sidebar.add_nav_button("", Icons.REORDER, 10)

        self.sidebar.finalize()
        main_layout.addWidget(self.sidebar)

        # Tab name (key of MANAGEMENT_TAB_PERMISSIONS) -> its sidebar button, for set_user()
        self._tab_buttons = {
            "dashboard": self.btn_dashboard,
            "inventory": self.btn_inventory,
            "purchasing": self.btn_purchasing,
            "credit_book": self.btn_customers,
            "reports": self.btn_reports,
            "documents": self.btn_documents,
            "users": self.btn_users,
            "pricelists": self.btn_pricelists,
            "promotions": self.btn_promotions,
            "stock_take": self.btn_stock_take,
            "reorder": self.btn_reorder,
        }

        # --- Content Area ---
        content_area = QWidget()
        content_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(self.stack)

        main_layout.addWidget(content_area, 1)

        # Views are created lazily by switch_tab(), not all 10 up front here
        # (#227) -- see _get_or_create_view(). The nav-index -> attribute
        # name mapping lets set_user() and switch_tab() find an
        # already-created view without a long if/elif chain.
        self._view_widgets: dict = {}
        self._view_attr_names = {
            0: "dashboard_view",
            1: "inventory_view",
            2: "purchase_view",
            3: "credit_book_view",
            4: "reports_view",
            5: "document_view",
            6: "user_view",
            7: "pricelist_view",
            8: "promotion_view",
            9: "stock_take_view",
            10: "reorder_view",
        }

    def retranslate_ui(self) -> None:
        """Update all translatable text in the view."""
        # Logo fallback
        if self.sidebar.lbl_logo.pixmap() is None or self.sidebar.lbl_logo.pixmap().isNull():
            self.sidebar.lbl_logo.setText(_t("management.logo_fallback"))

        # Nav buttons
        self.btn_dashboard.setText(_t("management.sidebar_dashboard"))
        self.btn_inventory.setText(_t("management.sidebar_inventory"))
        self.btn_purchasing.setText(_t("management.sidebar_purchasing"))
        self.btn_customers.setText(_t("management.sidebar_credit_book"))
        self.lbl_sidebar_section_management.setText(_t("management.sidebar_section_management").upper())
        self.btn_reports.setText(_t("management.sidebar_reports"))
        self.btn_documents.setText(_t("management.sidebar_documents"))
        self.btn_users.setText(_t("management.sidebar_users"))
        self.btn_pricelists.setText(_t("management.sidebar_price_lists"))
        self.btn_promotions.setText(_t("management.sidebar_promotions"))
        self.btn_stock_take.setText(_t("management.sidebar_stock_take"))
        self.btn_reorder.setText(_t("management.sidebar_reorder"))

        # Bottom buttons
        self.sidebar.retranslate_pos_logout()

    def switch_tab(self, index: int) -> None:
        """Show the view at the given sidebar nav index, creating it on first use."""
        widget = self._get_or_create_view(index)
        self.stack.setCurrentWidget(widget)
        self.sidebar.highlight(index)

    def process_barcode_external(self, barcode: str) -> None:
        """Forward a global scan to the current tab if it handles scans (#547)."""
        current = self.stack.currentWidget()
        if hasattr(current, "process_barcode_external"):
            current.process_barcode_external(barcode)

    def _create_view(self, index: int):
        """Factory for the view at a given nav index. StockTakeView keeps
        its existing deferred import here rather than moving it to module
        level, since that's the pre-existing pattern this file used."""
        if index == 0:
            return DashboardView()
        if index == 1:
            return InventoryView()
        if index == 2:
            return PurchaseView()
        if index == 3:
            return CreditBookView()
        if index == 4:
            return ReportViewer()
        if index == 5:
            view = DocumentBrowserView()
            view.convert_to_sale_requested.connect(self.convert_proforma_to_sale.emit)
            return view
        if index == 6:
            return UserView()
        if index == 7:
            return PriceListView()
        if index == 8:
            return PromotionView()
        if index == 9:
            from cbpos.ui.views.stock_take_view import StockTakeView

            return StockTakeView()
        if index == 10:
            view = ReorderView()
            view.navigate_to_purchase.connect(self._handle_reorder_navigation)
            return view
        raise ValueError(f"No view factory for nav index {index}")

    def _handle_reorder_navigation(self, items: list, purchase_order_id: int) -> None:
        """Switch to the Purchase tab and pre-fill a new GRN from the Purchase Order just created."""
        purchase_view = self._get_or_create_view(2)
        purchase_view.prefill_grn_items(items, purchase_order_id=purchase_order_id)
        self.stack.setCurrentWidget(purchase_view)
        self.sidebar.highlight(2)

    def _get_or_create_view(self, index: int):
        if index not in self._view_widgets:
            widget = self._create_view(index)
            self._view_widgets[index] = widget
            setattr(self, self._view_attr_names[index], widget)
            self.stack.addWidget(widget)

            # These views need the current user as soon as they're
            # created, not just on the next login (set_user() already
            # re-applies to existing views below).
            if index in (2, 9, 10):
                user = getattr(self, "user", None)
                if user is not None:
                    widget.set_user(user)
        return self._view_widgets[index]

    def set_user(self, user) -> None:
        """Store the logged-in user, apply admin-only nav visibility, and propagate to created views."""
        self.user = user

        # Same definition the side menu uses to offer Management (#728)
        visible = PermissionService.management_tabs(user)
        for tab, button in self._tab_buttons.items():
            button.setVisible(tab in visible)

        if hasattr(self, "purchase_view"):
            self.purchase_view.set_user(user)
        if hasattr(self, "stock_take_view"):
            self.stock_take_view.set_user(user)
        if hasattr(self, "reorder_view"):
            self.reorder_view.set_user(user)

    def resizeEvent(self, event) -> None:
        """Auto-collapse sidebar on narrow screens and recompute layout."""
        super().resizeEvent(event)
        self.sidebar.handle_resize(event.size().width())
        if self.layout() is not None:
            self.layout().activate()

    def changeEvent(self, event) -> None:
        """Handle window state changes (e.g. restore from minimized)."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            win = self.window()
            if win is not None and not win.isMinimized():
                w = self.width()
                if w > 0:
                    self.sidebar.handle_resize(w)
                if self.layout() is not None:
                    self.layout().activate()
                current = self.stack.currentWidget()
                if current is not None and current.layout() is not None:
                    current.layout().activate()

    def showEvent(self, event) -> None:
        """Recompute layout when switching back to this view."""
        super().showEvent(event)
        w = self.width()
        if w > 0:
            self.sidebar.handle_resize(w)
        if self.layout() is not None:
            self.layout().activate()
        current = self.stack.currentWidget()
        if current is not None and current.layout() is not None:
            current.layout().activate()
