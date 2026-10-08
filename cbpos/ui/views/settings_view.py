"""Top-level Settings screen with sidebar navigation to configuration pages."""

import contextlib
import json
import logging
import weakref

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.constants.permissions import Permissions
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.permission_service import PermissionService
from cbpos.i18n import _t, get_language, register_language_callback, translate_in, unregister_language_callback
from cbpos.ui.app_restart import restart_application
from cbpos.ui.views.settings_pages import (
    DocumentPage,
    HardwarePage,
    NetworkPage,
    ReceiptPage,
    SalesTaxPage,
    ShopInfoPage,
    SystemPage,
)
from cbpos.ui.widgets.collapsible_sidebar import CollapsibleSidebar

logger = logging.getLogger(__name__)


class SettingsView(QWidget):
    """Settings screen with a sidebar for config pages and operational tools (payments, data safety, admin)."""

    close_requested = pyqtSignal()
    logout_requested = pyqtSignal()
    request_pos_view = pyqtSignal()

    HARDWARE_PAGE = 3  # stack index of HardwarePage

    def __init__(self):
        """Build the UI, load current settings, and register the translation callback."""
        super().__init__()
        self._settings_dirty = False
        self._saved_snapshot: dict = {}
        self._page_snapshots: list[dict | None] = []
        self._dirty_pages: list[int] = []
        self.init_ui()
        self.load_settings()
        self._watch_page_edits()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        # weakref avoids a self -> destroyed-connection -> lambda -> self
        # reference cycle that only a full gc.collect() can break, which
        # can segfault mid-teardown (#392).
        self_ref = weakref.ref(self)

        def _unregister():
            view = self_ref()
            if view is not None:
                unregister_language_callback(view.retranslate_ui)

        self.destroyed.connect(_unregister)

    def init_ui(self):
        """Build the sidebar and, beside it, the stacked pages over one action bar."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar ---
        self.sidebar = CollapsibleSidebar()
        self.sidebar.nav_clicked.connect(self.switch_page)
        self.sidebar.pos_clicked.connect(self._on_pos_clicked)
        self.sidebar.logout_clicked.connect(self._on_logout_clicked)

        # Navigation buttons — config pages
        self.btn_shop_info = self.sidebar.add_nav_button("", "fa5s.store", 0)
        self.btn_sales_tax = self.sidebar.add_nav_button("", "fa5s.shopping-cart", 1)
        self.btn_documents = self.sidebar.add_nav_button("", "fa5s.file-invoice", 2)
        self.btn_hardware = self.sidebar.add_nav_button("", "fa5s.print", self.HARDWARE_PAGE)
        self.btn_receipt = self.sidebar.add_nav_button("", "fa5s.receipt", 4)
        self.btn_system = self.sidebar.add_nav_button("", "fa5s.cogs", 5)
        self.btn_network = self.sidebar.add_nav_button("", "fa5s.network-wired", 6)
        self.btn_payment_methods = self.sidebar.add_nav_button("", "fa5s.credit-card", 7)

        # Operational buttons
        self.btn_data_safety = self.sidebar.add_nav_button("", "fa5s.shield-alt", 8)
        self.btn_admin_tools = self.sidebar.add_nav_button("", "fa5s.toolbox", 9)

        self.sidebar.finalize()
        self.sidebar.highlight(0)
        main_layout.addWidget(self.sidebar)

        # --- Content Area ---
        self.stack = QStackedWidget()
        self.stack.setObjectName("SettingsContent")
        self.stack.currentChanged.connect(self.sidebar.highlight)

        # Config pages (participate in load/save)
        self.pages = [
            ShopInfoPage(),
            SalesTaxPage(),
            DocumentPage(),
            HardwarePage(),
            ReceiptPage(),
            SystemPage(),
            NetworkPage(),
        ]

        for page in self.pages:
            self.stack.addWidget(page)

        # Money spin boxes follow the currency symbol as it is typed (#555).
        self.pages[0].input_currency.textChanged.connect(self.pages[1].set_currency_symbol)

        # Operational views (self-contained, no load/save)
        from cbpos.ui.views.admin_tools_view import AdminToolsView
        from cbpos.ui.views.data_safety_view import DataSafetyView
        from cbpos.ui.views.payment_methods_view import PaymentMethodsView

        # Each sits in a scroll area: Admin Tools alone needs ~770px, which
        # pushed Settings past a 1366x768 screen and clipped POS/Logout (#591).
        self.payment_methods_view = PaymentMethodsView()
        self.stack.addWidget(self._scrollable(self.payment_methods_view))

        self.data_safety_view = DataSafetyView()
        self.stack.addWidget(self._scrollable(self.data_safety_view))

        self.admin_tools_view = AdminToolsView()
        self.stack.addWidget(self._scrollable(self.admin_tools_view))

        # --- Content column: pages over one Settings-wide action bar ---
        # The bar sits under the content only, never under the sidebar, so
        # the sidebar keeps its full height (#616, #591). It stays visible on
        # every page so no page's content area jumps in height (#317).
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.stack, 1)

        self.action_bar = QFrame()
        self.action_bar.setObjectName("SettingsActionBar")
        self.action_bar.setFixedHeight(52)
        bar_layout = QHBoxLayout(self.action_bar)
        bar_layout.setContentsMargins(20, 6, 20, 6)
        bar_layout.setSpacing(12)

        # Unsaved pages on config pages; "changes save automatically" on tool pages
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("SettingsSaveStatus")
        bar_layout.addWidget(self.lbl_status, 1)

        # Saves every config page at once -- kept apart from each page's own
        # Reset to Defaults (top of the page), which only resets that page.
        self.btn_save = QPushButton("")
        self.btn_save.setObjectName("BtnSave")
        self.btn_save.setMinimumWidth(170)
        self.btn_save.setFixedHeight(40)
        self.btn_save.clicked.connect(self.save_all)
        bar_layout.addWidget(self.btn_save)

        content_layout.addWidget(self.action_bar)
        main_layout.addWidget(content, 1)

        self.stack.currentChanged.connect(self._update_status_text)

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        """Wrap a tool page so a short screen scrolls it instead of growing Settings."""
        scroll = QScrollArea()
        scroll.setObjectName("SettingsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    def retranslate_ui(self) -> None:
        """Update all translatable text in the view."""
        self.setWindowTitle(_t("settings.title"))

        # Nav buttons
        self.btn_shop_info.setText(_t("settings.sidebar_shop_info"))
        self.btn_sales_tax.setText(_t("settings.sidebar_sales_tax"))
        self.btn_documents.setText(_t("settings.sidebar_documents"))
        self.btn_hardware.setText(_t("settings.sidebar_hardware"))
        self.btn_receipt.setText(_t("settings.sidebar_receipt"))
        self.btn_system.setText(_t("settings.sidebar_system"))
        self.btn_network.setText(_t("settings.sidebar_network"))
        self.btn_payment_methods.setText(_t("settings.sidebar_payments"))
        self.btn_data_safety.setText(_t("settings.sidebar_data_safety"))
        self.btn_admin_tools.setText(_t("settings.sidebar_admin_tools"))

        # Bottom sidebar buttons
        self.sidebar.retranslate_pos_logout()

        # Action bar
        self.btn_save.setText(_t("settings.btn_save_all"))
        self._refresh_unsaved_markers()

    # ------------------------------------------------------------------
    # Page switching
    # ------------------------------------------------------------------

    def _take_snapshot(self) -> dict:
        """Collect current values from all config pages for dirty comparison."""
        snapshot: dict = {}
        for page in self.pages:
            with contextlib.suppress(ValueError, Exception):
                snapshot.update(page.save())
        return snapshot

    def switch_page(self, index: int) -> None:
        """Switch the stacked widget to the given page index.

        Edits on other pages are kept (their sidebar items show the unsaved
        marker), so several pages can be edited and saved together.
        """
        self.stack.setCurrentIndex(index)

    # ------------------------------------------------------------------
    # Unsaved-changes markers
    # ------------------------------------------------------------------

    @staticmethod
    def _page_values(page) -> dict | None:
        """Return a config page's current values, or None if they can't be read yet."""
        try:
            return page.save()
        except Exception:
            return None

    def _watch_page_edits(self) -> None:
        """Re-check the unsaved markers whenever any input on a config page changes."""
        for page in self.pages:
            page.defaults_restored.connect(self._on_defaults_restored)
            for w in page.findChildren(QLineEdit):
                w.textChanged.connect(self._refresh_unsaved_markers)
            for w in page.findChildren(QTextEdit) + page.findChildren(QPlainTextEdit):
                w.textChanged.connect(self._refresh_unsaved_markers)
            for w in page.findChildren(QComboBox):
                w.currentIndexChanged.connect(self._refresh_unsaved_markers)
                w.editTextChanged.connect(self._refresh_unsaved_markers)
            for w in page.findChildren(QAbstractButton):
                if w.isCheckable():
                    w.toggled.connect(self._refresh_unsaved_markers)
            for w in page.findChildren(QSpinBox) + page.findChildren(QDoubleSpinBox) + page.findChildren(QSlider):
                w.valueChanged.connect(self._refresh_unsaved_markers)
            for w in page.findChildren(QDateTimeEdit):
                w.dateTimeChanged.connect(self._refresh_unsaved_markers)

    def _refresh_unsaved_markers(self, *_args) -> None:
        """Mark each sidebar item whose page differs from what's saved, and update the status text."""
        if len(self._page_snapshots) != len(self.pages):
            return
        tooltip = _t("settings.unsaved_marker_tooltip")
        self._dirty_pages = []
        for i, page in enumerate(self.pages):
            dirty = self._page_values(page) != self._page_snapshots[i]
            self.sidebar.nav_buttons[i].set_unsaved(dirty, tooltip)
            if dirty:
                self._dirty_pages.append(i)
        self._update_status_text()

    def _on_defaults_restored(self) -> None:
        """A page's Reset to Defaults saved its defaults: treat them as saved."""
        page = self.sender()
        if page in self.pages:
            values = self._page_values(page)
            self._page_snapshots[self.pages.index(page)] = values
            self._saved_snapshot.update(values or {})
        self._refresh_unsaved_markers()

    def _update_status_text(self, *_args) -> None:
        """Say what Save will do: which pages are unsaved, or that a tool page saves itself."""
        if self.stack.currentIndex() >= len(self.pages):
            text, state = _t("settings.auto_save_hint"), "auto"
        elif self._dirty_pages:
            # Button text escapes "&" as "&&" (mnemonics); show it plainly here
            names = ", ".join(self.sidebar.nav_buttons[i].text().replace("&&", "&") for i in self._dirty_pages)
            text, state = _t("settings.unsaved_pages", pages=names), "unsaved"
        else:
            text, state = _t("settings.all_saved"), "saved"
        self.lbl_status.setText(text)
        if self.lbl_status.property("state") != state:
            self.lbl_status.setProperty("state", state)
            self.lbl_status.style().unpolish(self.lbl_status)
            self.lbl_status.style().polish(self.lbl_status)

    def _check_discard_unsaved(self) -> bool:
        """Check for unsaved changes and prompt user. Returns True if safe to proceed."""
        if self._saved_snapshot and self._take_snapshot() != self._saved_snapshot:
            reply = QMessageBox.question(
                self,
                _t("settings.unsaved_title"),
                _t("settings.unsaved_message"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return False
            self.load_settings()
        return True

    def _on_pos_clicked(self) -> None:
        """Navigate to POS/Sales view, prompting for unsaved changes."""
        if self._check_discard_unsaved():
            self.request_pos_view.emit()

    def _on_logout_clicked(self) -> None:
        """Logout, prompting for unsaved changes."""
        if self._check_discard_unsaved():
            self.logout_requested.emit()

    # ------------------------------------------------------------------
    # User / permissions
    # ------------------------------------------------------------------

    def set_user(self, user) -> None:
        """Show/hide admin-only sidebar buttons based on user permissions."""
        is_admin = PermissionService.user_has_permission(user, Permissions.ADMIN_SETTINGS)
        self.btn_data_safety.setVisible(is_admin)
        self.btn_admin_tools.setVisible(is_admin)

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def load_settings(self):
        """Load current settings into every config page and snapshot the values for dirty-checking."""
        settings = ConfigService.get_all()
        for page in self.pages:
            page.load(settings)
        self._page_snapshots = [self._page_values(page) for page in self.pages]
        self._saved_snapshot = self._take_snapshot()
        self._refresh_unsaved_markers()

    def save_all(self):
        """Validate and save all config pages, then apply the changes live.

        Checks the ADMIN_SETTINGS permission, audits tax-rate changes to
        AuditLog, persists settings, restarts the scheduler timer if the
        auto-report toggle changed, and if theme, language, font size or
        terminal/db mode changed, asks to restart now or apply them at the
        next launch (they are never applied live, #581).
        """
        from cbpos.core.utils.permission_helper import check_permission_with_override

        if not check_permission_with_override(Permissions.ADMIN_SETTINGS, self):
            return

        current_config = ConfigService.get_all()
        current_lang = current_config.get("language", "en")
        current_theme = current_config.get("theme", "Dark")
        current_font_size = current_config.get("font_size", 12)

        all_settings = {}
        try:
            for page in self.pages:
                page.validate()
                all_settings.update(page.save())
        except ValueError as e:
            # Show the page holding the bad field so its inline error is visible
            self.stack.setCurrentWidget(page)
            QMessageBox.warning(self, _t("common.validation_error"), str(e))
            return

        warnings = [w for page in self.pages for w in getattr(page, "save_warnings", list)()]
        if warnings:
            reply = QMessageBox.warning(
                self,
                _t("common.warning"),
                "\n\n".join(warnings),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Audit log tax rate changes before saving
        tax_keys = [
            "tax_vat_rate",
            "tax_sscl_rate",
            "tax_sscl_turnover_pct",
            "vat_registered",
        ]
        tax_changes = {}
        for key in tax_keys:
            old_val = current_config.get(key)
            new_val = all_settings.get(key)
            if new_val is not None and str(old_val) != str(new_val):
                tax_changes[key] = {"old": old_val, "new": new_val}

        if tax_changes:
            from cbpos.core.database import Database
            from cbpos.core.models import AuditLog
            from cbpos.core.services.auth_service import AuthService

            user = AuthService.get_current_user()
            if user:
                db = Database()
                try:
                    terminal_id = ConfigService.get("terminal_id") or "TERM-01"
                    with db.get_session() as session:
                        log = AuditLog(
                            user_id=user.id,
                            action="TAX_RATE_CHANGE",
                            event_type="SECURITY",
                            terminal_id=terminal_id,
                            details=json.dumps(tax_changes),
                        )
                        session.add(log)
                except Exception as e:
                    logger.warning("Tax audit log failed: %s", e)

        ConfigService.update_all(all_settings)

        # Start/stop the auto-report scheduler timer live (#320) -- it used
        # to only be read once at process launch, so toggling this
        # checkbox had no effect until the next full app restart.
        if all_settings.get("auto_report_enabled") != current_config.get("auto_report_enabled"):
            from cbpos.core.services.scheduler_service import SchedulerService

            if all_settings.get("auto_report_enabled"):
                SchedulerService.start_timer()
            else:
                SchedulerService.stop_timer()

        new_theme = all_settings.get("theme", current_theme)
        new_lang = all_settings.get("language", current_lang)
        new_font_size = all_settings.get("font_size", current_font_size)

        # Theme/language/font size are only saved here, never applied live:
        # a live switch left screens whose retranslate_ui()/theme colors are
        # incomplete half-switched (#581). They apply at the next launch.
        restart_required = (
            new_theme != current_theme
            or new_lang != current_lang
            or new_font_size != current_font_size
            or all_settings.get("db_mode", "standalone") != current_config.get("db_mode", "standalone")
            or all_settings.get("terminal_mode", "standalone") != current_config.get("terminal_mode", "standalone")
        )

        self._page_snapshots = [self._page_values(page) for page in self.pages]
        self._saved_snapshot = self._take_snapshot()
        self._refresh_unsaved_markers()

        if restart_required:
            if self._prompt_restart(get_language(), new_lang):
                return
        else:
            QMessageBox.information(
                self,
                _t("settings.saved_title"),
                _t("settings.saved_message"),
            )

        self.close_requested.emit()

    def _sale_in_progress(self) -> bool:
        """Return True if the sales screen has items in its cart.

        A payment can only be in progress with items in the cart (the
        payment dialog is modal over Sales), so this covers both.
        """
        sales_view = getattr(self.window(), "sales_view", None)
        cart = getattr(sales_view, "cart_service", None)
        return bool(cart is not None and cart.items)

    def _prompt_restart(self, old_lang: str, new_lang: str) -> bool:
        """Ask to restart now or apply the saved settings at the next launch.

        Text is shown in the old language and, if it changed, the new one too.
        Restart now is never offered while a sale is in progress.

        Args:
            old_lang: The language the app is displayed in right now.
            new_lang: The language just saved.

        Returns:
            bool: True if the app is restarting.
        """

        def both(key: str, sep: str = "\n\n") -> str:
            text = translate_in(old_lang, key)
            other = translate_in(new_lang, key)
            return text if other == text else f"{text}{sep}{other}"

        if self._sale_in_progress():
            QMessageBox.information(
                self, translate_in(old_lang, "settings.saved_title"), both("settings.restart_prompt.busy_message")
            )
            return False

        if not self._ask_restart_now(
            translate_in(old_lang, "settings.restart_prompt.title"),
            both("settings.restart_prompt.message"),
            both("settings.restart_prompt.restart_now", " / "),
            both("settings.restart_prompt.later", " / "),
        ):
            return False
        return restart_application(self.window())

    def _ask_restart_now(self, title: str, text: str, restart_label: str, later_label: str) -> bool:
        """Show the Restart now / Apply next launch box; True if Restart now was chosen."""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Question)
        restart_btn = box.addButton(restart_label, QMessageBox.ButtonRole.AcceptRole)
        later_btn = box.addButton(later_label, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(restart_btn)
        box.setEscapeButton(later_btn)
        box.exec()
        return box.clickedButton() is restart_btn

    # ------------------------------------------------------------------
    # Responsive
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        """Auto-collapse sidebar on narrow screens."""
        super().resizeEvent(event)
        self.sidebar.handle_resize(event.size().width())
