"""Network database configuration settings page for multi-terminal setup."""

import logging
import socket

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from sqlalchemy.engine import URL

from cbpos.config import Config
from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.dialogs.guide_dialog import GuideDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.views.settings_pages.base import SettingsPage
from cbpos.ui.widgets.help_icon_button import HelpIconButton

logger = logging.getLogger(__name__)


class NetworkPage(SettingsPage):
    """Network database configuration for multi-terminal setup."""

    def __init__(self):
        """Reset the connection-tested flag, then build the page UI."""
        self.connection_tested = False
        super().__init__()

    def init_ui(self):
        """Build the Mode, Server Configuration, Migration and LAN Sync tabs."""
        _, self.tabs = self._create_page_layout("", "")

        # --- Tab 1: Mode ---
        tab_mode, mode_layout = self._build_vbox_tab()

        # One-line framing so this tab doesn't read as a duplicate of
        # LAN Sync (#334) -- Mode/Server/Migration configure switching the
        # whole app to one *shared* PostgreSQL database; LAN Sync instead
        # keeps *separate* SQLite databases synced between terminals. Two
        # genuinely different multi-terminal strategies with nothing on
        # either tab explaining which is which.
        self.lbl_mode_explainer = QLabel()
        self.lbl_mode_explainer.setWordWrap(True)
        self.lbl_mode_explainer.setProperty("class", "muted")
        mode_layout.addWidget(self.lbl_mode_explainer)

        # Status Card
        self.status_card = QFrame()
        self.status_card.setObjectName("StatusCard")
        self.status_card.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(self.status_card)
        status_layout.setContentsMargins(20, 20, 20, 20)
        status_layout.setSpacing(15)

        self.lbl_mode_icon = QLabel()
        self.lbl_mode_icon.setObjectName("StatusIcon")
        self.lbl_mode_icon.setPixmap(Icons.get("fa5s.desktop", ThemeService.get_accent_color()).pixmap(32, 32))

        status_text_layout = QVBoxLayout()
        self.lbl_status_title = QLabel()
        self.lbl_status_title.setObjectName("StatusTitle")
        self.lbl_status_subtitle = QLabel()
        self.lbl_status_subtitle.setObjectName("StatusSubtitle")
        status_text_layout.addWidget(self.lbl_status_title)
        status_text_layout.addWidget(self.lbl_status_subtitle)

        mode_selector_layout = QVBoxLayout()
        mode_header_row = QHBoxLayout()
        self.lbl_db_mode = QLabel()
        self.lbl_db_mode.setObjectName("StatusModeLabel")
        mode_header_row.addWidget(self.lbl_db_mode)
        self.btn_db_mode_help = HelpIconButton(on_click=self._show_db_mode_guide)
        mode_header_row.addWidget(self.btn_db_mode_help)
        mode_header_row.addStretch()

        self.cmb_db_mode = QComboBox()
        self.cmb_db_mode.setObjectName("StatusModeSelector")
        self.cmb_db_mode.currentTextChanged.connect(self._on_mode_changed)

        self.lbl_db_mode_hint = QLabel()
        self.lbl_db_mode_hint.setProperty("class", "muted")
        self.lbl_db_mode_hint.setWordWrap(True)

        mode_selector_layout.addLayout(mode_header_row)
        mode_selector_layout.addWidget(self.cmb_db_mode)
        mode_selector_layout.addWidget(self.lbl_db_mode_hint)

        status_layout.addWidget(self.lbl_mode_icon)
        status_layout.addLayout(status_text_layout, 1)
        status_layout.addLayout(mode_selector_layout)

        mode_layout.addWidget(self.status_card)

        self.lbl_warning = QLabel()
        self.lbl_warning.setObjectName("NetworkWarning")
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.setProperty("class", "warning-hint")
        self.lbl_warning.setVisible(False)
        mode_layout.addWidget(self.lbl_warning)

        self.tabs.addTab(tab_mode, "")

        # --- Tab 2: Server Configuration ---
        tab_server, server_layout = self._build_vbox_tab()

        self.config_card = QFrame()
        self.config_card.setObjectName("NetworkCard")
        self.config_card.setFrameShape(QFrame.Shape.StyledPanel)
        config_layout = QVBoxLayout(self.config_card)
        config_layout.setContentsMargins(25, 25, 25, 25)
        config_layout.setSpacing(18)

        self.lbl_config_title = QLabel()
        self.lbl_config_title.setObjectName("CardTitle")
        config_layout.addWidget(self.lbl_config_title)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "127.0.0.1"
        self._local_ip = local_ip

        self.lbl_local_ip = QLabel()
        self.lbl_local_ip.setObjectName("IPHelper")
        config_layout.addWidget(self.lbl_local_ip)

        grid_layout = QGridLayout()
        grid_layout.setVerticalSpacing(12)
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setColumnStretch(0, 0)
        grid_layout.setColumnStretch(1, 1)

        self.lbl_host = QLabel()
        self.lbl_host.setObjectName("FormLabel")
        self.input_host = QLineEdit()
        self.input_host.setObjectName("InputNetwork")
        grid_layout.addWidget(
            self.lbl_host,
            0,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_host, 0, 1)

        self.lbl_port = QLabel()
        self.lbl_port.setObjectName("FormLabel")
        self.input_port = QSpinBox()
        self.input_port.setObjectName("InputNetwork")
        self.input_port.setFixedHeight(38)
        self.input_port.setRange(1, 65535)
        self.input_port.setValue(5432)
        grid_layout.addWidget(
            self.lbl_port,
            1,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_port, 1, 1)

        self.lbl_dbname = QLabel()
        self.lbl_dbname.setObjectName("FormLabel")
        self.input_dbname = QLineEdit()
        self.input_dbname.setObjectName("InputNetwork")
        grid_layout.addWidget(
            self.lbl_dbname,
            2,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_dbname, 2, 1)

        self.lbl_user = QLabel()
        self.lbl_user.setObjectName("FormLabel")
        self.input_user = QLineEdit()
        self.input_user.setObjectName("InputNetwork")
        grid_layout.addWidget(
            self.lbl_user,
            3,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_user, 3, 1)

        self.lbl_password = QLabel()
        self.lbl_password.setObjectName("FormLabel")
        self.input_password = QLineEdit()
        self.input_password.setObjectName("InputNetwork")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        grid_layout.addWidget(
            self.lbl_password,
            4,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.input_password, 4, 1)

        config_layout.addLayout(grid_layout)

        test_btn_layout = QHBoxLayout()
        self.btn_test = QPushButton()
        self.btn_test.setObjectName("BtnTestNetwork")
        self.btn_test.clicked.connect(self._test_connection)
        self.lbl_test_status = QLabel("")
        self.lbl_test_status.setObjectName("TestStatus")
        test_btn_layout.addWidget(self.btn_test)
        test_btn_layout.addWidget(self.lbl_test_status, 1)
        config_layout.addLayout(test_btn_layout)

        server_layout.addWidget(self.config_card)

        self.tabs.addTab(tab_server, "")

        # --- Tab 3: Migration ---
        tab_migrate, migrate_layout = self._build_vbox_tab()

        self.migration_card = QFrame()
        self.migration_card.setObjectName("MigrationCard")
        self.migration_card.setFrameShape(QFrame.Shape.StyledPanel)
        migration_layout = QVBoxLayout(self.migration_card)
        migration_layout.setContentsMargins(25, 25, 25, 25)
        migration_layout.setSpacing(18)

        self.lbl_migration_title = QLabel()
        self.lbl_migration_title.setObjectName("CardTitle")
        migration_layout.addWidget(self.lbl_migration_title)

        self.lbl_migration_info = QLabel()
        self.lbl_migration_info.setWordWrap(True)
        self.lbl_migration_info.setObjectName("MigrationInfo")
        migration_layout.addWidget(self.lbl_migration_info)

        self.btn_migrate = QPushButton()
        self.btn_migrate.setObjectName("BtnMigrate")
        self.btn_migrate.setEnabled(False)
        self.btn_migrate.clicked.connect(self._migrate_data)
        migration_layout.addWidget(self.btn_migrate)

        migrate_layout.addWidget(self.migration_card)

        self.tabs.addTab(tab_migrate, "")

        # --- Tab 4: LAN Sync (Multi-Terminal) ---
        tab_sync, sync_layout = self._build_vbox_tab()

        self.sync_card = QFrame()
        self.sync_card.setObjectName("NetworkCard")
        self.sync_card.setFrameShape(QFrame.Shape.StyledPanel)
        sync_card_layout = QVBoxLayout(self.sync_card)
        sync_card_layout.setContentsMargins(25, 25, 25, 25)
        sync_card_layout.setSpacing(18)

        self.lbl_sync_title = QLabel()
        self.lbl_sync_title.setObjectName("CardTitle")
        sync_card_layout.addWidget(self.lbl_sync_title)

        self.lbl_sync_desc = QLabel()
        self.lbl_sync_desc.setWordWrap(True)
        self.lbl_sync_desc.setObjectName("MigrationInfo")
        sync_card_layout.addWidget(self.lbl_sync_desc)

        sync_grid = QGridLayout()
        sync_grid.setVerticalSpacing(12)
        sync_grid.setHorizontalSpacing(10)
        sync_grid.setColumnStretch(0, 0)
        sync_grid.setColumnStretch(1, 1)

        # Terminal Mode selector
        tm_label_layout = QHBoxLayout()
        tm_label_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_terminal_mode = QLabel()
        self.lbl_terminal_mode.setObjectName("FormLabel")
        tm_label_layout.addWidget(self.lbl_terminal_mode)
        self.btn_terminal_mode_help = HelpIconButton(on_click=self._show_terminal_mode_guide)
        tm_label_layout.addWidget(self.btn_terminal_mode_help)
        tm_label_layout.addStretch()
        sync_grid.addLayout(tm_label_layout, 0, 0, Qt.AlignmentFlag.AlignLeft)

        tm_widget_col = QVBoxLayout()
        tm_widget_col.setContentsMargins(0, 0, 0, 0)
        tm_widget_col.setSpacing(4)
        self.cmb_terminal_mode = QComboBox()
        self.cmb_terminal_mode.addItem("", "standalone")
        self.cmb_terminal_mode.addItem("", "main")
        self.cmb_terminal_mode.addItem("", "terminal")
        self.cmb_terminal_mode.currentIndexChanged.connect(self._on_terminal_mode_changed)
        tm_widget_col.addWidget(self.cmb_terminal_mode)

        self.lbl_terminal_mode_hint = QLabel()
        self.lbl_terminal_mode_hint.setProperty("class", "muted")
        self.lbl_terminal_mode_hint.setWordWrap(True)
        tm_widget_col.addWidget(self.lbl_terminal_mode_hint)
        sync_grid.addLayout(tm_widget_col, 0, 1)

        # Terminal ID
        self.lbl_sync_terminal_id = QLabel()
        self.lbl_sync_terminal_id.setObjectName("FormLabel")
        self.input_terminal_id = QLineEdit()
        self.input_terminal_id.setObjectName("InputNetwork")
        sync_grid.addWidget(self.lbl_sync_terminal_id, 1, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.input_terminal_id, 1, 1)

        # Sync server port (Main PC mode)
        self.lbl_sync_port = QLabel()
        self.lbl_sync_port.setObjectName("FormLabel")
        sync_grid.addWidget(self.lbl_sync_port, 2, 0, Qt.AlignmentFlag.AlignLeft)

        sync_port_col = QVBoxLayout()
        sync_port_col.setContentsMargins(0, 0, 0, 0)
        sync_port_col.setSpacing(4)
        self.spin_sync_port = QSpinBox()
        self.spin_sync_port.setObjectName("InputNetwork")
        self.spin_sync_port.setFixedHeight(38)
        self.spin_sync_port.setRange(1024, 65535)
        self.spin_sync_port.setValue(5555)
        sync_port_col.addWidget(self.spin_sync_port)

        self.lbl_sync_port_hint = QLabel()
        self.lbl_sync_port_hint.setProperty("class", "muted")
        self.lbl_sync_port_hint.setWordWrap(True)
        sync_port_col.addWidget(self.lbl_sync_port_hint)
        sync_grid.addLayout(sync_port_col, 2, 1)

        # Main PC address (Terminal mode)
        self.lbl_main_pc_addr = QLabel()
        self.lbl_main_pc_addr.setObjectName("FormLabel")
        self.input_main_pc_addr = QLineEdit()
        self.input_main_pc_addr.setObjectName("InputNetwork")
        sync_grid.addWidget(self.lbl_main_pc_addr, 3, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.input_main_pc_addr, 3, 1)

        # Sync interval
        self.lbl_sync_interval = QLabel()
        self.lbl_sync_interval.setObjectName("FormLabel")
        self.spin_sync_interval = QSpinBox()
        self.spin_sync_interval.setObjectName("InputNetwork")
        self.spin_sync_interval.setFixedHeight(38)
        self.spin_sync_interval.setRange(1, 60)
        self.spin_sync_interval.setValue(3)
        sync_grid.addWidget(self.lbl_sync_interval, 4, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.spin_sync_interval, 4, 1)

        # Shared secret — required on both Main PC and every Terminal
        self.lbl_sync_secret = QLabel()
        self.lbl_sync_secret.setObjectName("FormLabel")
        self.input_sync_secret = QLineEdit()
        self.input_sync_secret.setObjectName("InputNetwork")
        self.input_sync_secret.setEchoMode(QLineEdit.EchoMode.Password)
        sync_grid.addWidget(self.lbl_sync_secret, 5, 0, Qt.AlignmentFlag.AlignLeft)
        sync_grid.addWidget(self.input_sync_secret, 5, 1)

        sync_card_layout.addLayout(sync_grid)

        # Test LAN Sync Connection button
        sync_test_layout = QHBoxLayout()
        self.btn_test_sync = QPushButton()
        self.btn_test_sync.setObjectName("BtnTestNetwork")
        self.btn_test_sync.clicked.connect(self._test_sync_connection)
        self.lbl_sync_test_status = QLabel("")
        self.lbl_sync_test_status.setObjectName("TestStatus")
        sync_test_layout.addWidget(self.btn_test_sync)
        sync_test_layout.addWidget(self.lbl_sync_test_status, 1)
        sync_card_layout.addLayout(sync_test_layout)

        # Forget Trusted Main PC — recovery path after intentionally
        # replacing the Main PC (see SyncClient._check_main_identity)
        self.btn_forget_main = QPushButton()
        self.btn_forget_main.setObjectName("BtnTestNetwork")
        self.btn_forget_main.clicked.connect(self._forget_trusted_main_pc)
        sync_card_layout.addWidget(self.btn_forget_main)

        # Server address display (Main PC mode)
        self.lbl_server_address = QLabel("")
        self.lbl_server_address.setObjectName("IPHelper")
        self.lbl_server_address.setWordWrap(True)
        sync_card_layout.addWidget(self.lbl_server_address)

        sync_layout.addWidget(self.sync_card)
        self.tabs.addTab(tab_sync, "")

        self._on_mode_changed("Standalone")
        self._on_terminal_mode_changed(0)

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

        # The first style polish on show() re-expands these spinboxes past
        # their #InputNetwork height (a pre-existing QSS specificity clash
        # with "QWidget#SettingsContent QSpinBox"), so pin the height again
        # one event-loop tick after the initial polish has already happened.
        def _fix_spinbox_heights():
            try:
                for spinbox in (self.input_port, self.spin_sync_port, self.spin_sync_interval):
                    spinbox.setFixedHeight(38)
            except RuntimeError:
                pass

        QTimer.singleShot(0, _fix_spinbox_heights)

    def _show_db_mode_guide(self) -> None:
        """Show guide dialog explaining standalone vs network database modes."""
        steps = [
            ("settings.network.guide_db_mode_step1_title", "settings.network.guide_db_mode_step1_detail"),
            ("settings.network.guide_db_mode_step2_title", "settings.network.guide_db_mode_step2_detail"),
            ("settings.network.guide_db_mode_step3_title", "settings.network.guide_db_mode_step3_detail"),
        ]
        dlg = GuideDialog(
            title_key="settings.network.guide_db_mode_title",
            steps=steps,
            note_key="settings.network.guide_db_mode_note",
            parent=self,
        )
        dlg.exec()

    def _show_terminal_mode_guide(self) -> None:
        """Show guide dialog explaining LAN Sync terminal roles and setup."""
        steps = [
            (
                "settings.network.guide_terminal_mode_step1_title",
                "settings.network.guide_terminal_mode_step1_detail",
            ),
            (
                "settings.network.guide_terminal_mode_step2_title",
                "settings.network.guide_terminal_mode_step2_detail",
            ),
            (
                "settings.network.guide_terminal_mode_step3_title",
                "settings.network.guide_terminal_mode_step3_detail",
            ),
        ]
        dlg = GuideDialog(
            title_key="settings.network.guide_terminal_mode_title",
            steps=steps,
            note_key="settings.network.guide_terminal_mode_note",
            parent=self,
        )
        dlg.exec()

    def retranslate_ui(self) -> None:
        """Update all widget text and tab labels from the translation system."""
        self._page_title.setText(_t("settings.network.title"))
        self.btn_reset_defaults.setText(_t("settings.btn_reset_defaults"))
        self._page_subtitle.setText(_t("settings.network.subtitle"))

        self.tabs.setTabText(0, _t("settings.network.tab_mode"))
        self.tabs.setTabText(1, _t("settings.network.tab_server"))
        self.tabs.setTabText(2, _t("settings.network.tab_migration"))
        self.tabs.setTabText(3, _t("settings.network.tab_lan_sync"))

        # Mode tab
        self.lbl_mode_explainer.setText(_t("settings.network.mode_explainer"))
        self.lbl_db_mode.setText(_t("settings.network.database_mode"))
        self.cmb_db_mode.setToolTip(_t("settings.network.tooltip_db_mode"))
        self.btn_db_mode_help.setToolTip(_t("settings.network.tooltip_db_mode"))
        self.lbl_db_mode_hint.setText(_t("settings.network.hint_db_mode"))

        # Re-populate db mode combo preserving selection
        current_data = self.cmb_db_mode.currentData()
        self.cmb_db_mode.blockSignals(True)
        self.cmb_db_mode.clear()
        self.cmb_db_mode.addItem(_t("settings.network.mode_standalone"), "Standalone")
        self.cmb_db_mode.addItem(_t("settings.network.mode_network"), "Network")
        if current_data:
            idx = self.cmb_db_mode.findData(current_data)
            if idx >= 0:
                self.cmb_db_mode.setCurrentIndex(idx)
        self.cmb_db_mode.blockSignals(False)

        # Update status text based on current mode
        is_network = self.cmb_db_mode.currentData() == "Network"
        if is_network:
            self.lbl_status_title.setText(_t("settings.network.network_mode_title"))
            self.lbl_status_subtitle.setText(_t("settings.network.network_mode_subtitle"))
        else:
            self.lbl_status_title.setText(_t("settings.network.single_mode_title"))
            self.lbl_status_subtitle.setText(_t("settings.network.single_mode_subtitle"))

        self.lbl_warning.setText(_t("settings.network.mode_change_warning"))

        # Server tab
        self.lbl_config_title.setText(_t("settings.network.server_config_title"))
        self.lbl_local_ip.setText(_t("settings.network.local_ip").format(ip=self._local_ip))
        self.lbl_host.setText(_t("settings.network.host_ip"))
        self.input_host.setPlaceholderText(_t("settings.network.host_placeholder"))
        self.input_host.setToolTip(_t("settings.network.tooltip_host"))
        self.lbl_port.setText(_t("settings.network.port"))
        self.input_port.setToolTip(_t("settings.network.tooltip_port"))
        self.lbl_dbname.setText(_t("settings.network.database_name"))
        self.input_dbname.setPlaceholderText(_t("settings.network.database_name_placeholder"))
        self.input_dbname.setToolTip(_t("settings.network.tooltip_dbname"))
        self.lbl_user.setText(_t("settings.network.username"))
        self.input_user.setPlaceholderText(_t("settings.network.username_placeholder"))
        self.input_user.setToolTip(_t("settings.network.tooltip_user"))
        self.lbl_password.setText(_t("settings.network.password"))
        self.input_password.setPlaceholderText(_t("settings.network.password_placeholder"))
        self.input_password.setToolTip(_t("settings.network.tooltip_password"))
        self.btn_test.setText(_t("settings.network.btn_test_connection"))
        self.btn_test.setToolTip(_t("settings.network.tooltip_test_connection"))

        # Migration tab
        self.lbl_migration_title.setText(_t("settings.network.migration_title"))
        self.lbl_migration_info.setText(_t("settings.network.migration_info"))
        self.btn_migrate.setText(_t("settings.network.btn_upload"))
        self.btn_migrate.setToolTip(_t("settings.network.tooltip_migrate"))

        # LAN Sync tab
        self.lbl_sync_title.setText(_t("settings.network.sync_title"))
        self.lbl_sync_desc.setText(_t("settings.network.sync_desc"))

        self.lbl_terminal_mode.setText(_t("settings.network.terminal_mode"))
        self.btn_terminal_mode_help.setToolTip(_t("settings.network.tooltip_terminal_mode"))
        self.lbl_terminal_mode_hint.setText(_t("settings.network.hint_terminal_mode"))
        current_terminal_mode = self.cmb_terminal_mode.currentData()
        self.cmb_terminal_mode.blockSignals(True)
        self.cmb_terminal_mode.clear()
        self.cmb_terminal_mode.addItem(_t("settings.network.terminal_mode_standalone"), "standalone")
        self.cmb_terminal_mode.addItem(_t("settings.network.terminal_mode_main"), "main")
        self.cmb_terminal_mode.addItem(_t("settings.network.terminal_mode_terminal"), "terminal")
        if current_terminal_mode:
            tm_idx = self.cmb_terminal_mode.findData(current_terminal_mode)
            if tm_idx >= 0:
                self.cmb_terminal_mode.setCurrentIndex(tm_idx)
        self.cmb_terminal_mode.blockSignals(False)
        self.cmb_terminal_mode.setToolTip(_t("settings.network.tooltip_terminal_mode"))

        self.lbl_sync_terminal_id.setText(_t("settings.network.sync_terminal_id"))
        self.input_terminal_id.setPlaceholderText(_t("settings.network.sync_terminal_id_placeholder"))
        self.input_terminal_id.setToolTip(_t("settings.network.tooltip_terminal_id"))

        self.lbl_sync_port.setText(_t("settings.network.sync_port"))
        self.spin_sync_port.setToolTip(_t("settings.network.tooltip_sync_port"))
        self.lbl_sync_port_hint.setText(_t("settings.network.hint_sync_port"))

        self.lbl_main_pc_addr.setText(_t("settings.network.main_pc_address"))
        self.input_main_pc_addr.setPlaceholderText(_t("settings.network.main_pc_address_placeholder"))
        self.input_main_pc_addr.setToolTip(_t("settings.network.tooltip_main_pc_address"))

        self.lbl_sync_interval.setText(_t("settings.network.sync_interval"))
        self.spin_sync_interval.setSuffix(_t("settings.network.sync_interval_suffix"))
        self.spin_sync_interval.setToolTip(_t("settings.network.tooltip_sync_interval"))

        self.lbl_sync_secret.setText(_t("settings.network.sync_secret"))
        self.input_sync_secret.setPlaceholderText(_t("settings.network.sync_secret_placeholder"))
        self.input_sync_secret.setToolTip(_t("settings.network.tooltip_sync_secret"))

        self.btn_test_sync.setText(_t("settings.network.btn_test_sync"))
        self.btn_test_sync.setToolTip(_t("settings.network.tooltip_test_sync"))

        self.btn_forget_main.setText(_t("settings.network.btn_forget_main"))
        self.btn_forget_main.setToolTip(_t("settings.network.tooltip_forget_main"))
        self.equalize_form_labels()

    def load(self, settings: dict):
        """Populate database mode, server connection and LAN sync fields from the settings dict."""
        db_mode = settings.get("db_mode", "standalone")
        mode_data = "Standalone" if db_mode == "standalone" else "Network"
        idx = self.cmb_db_mode.findData(mode_data)
        if idx >= 0:
            self.cmb_db_mode.setCurrentIndex(idx)
        self.input_host.setText(settings.get("network_db_host", "localhost"))
        self.input_port.setValue(settings.get("network_db_port", 5432))
        self.input_dbname.setText(settings.get("network_db_name", "cbpos"))
        self.input_user.setText(settings.get("network_db_user", "postgres"))
        self.input_password.setText(settings.get("network_db_password", ""))
        self._original_mode = self.cmb_db_mode.currentData()
        self._on_mode_changed(self.cmb_db_mode.currentData() or "Standalone")

        # LAN Sync settings
        terminal_mode = settings.get("terminal_mode", "standalone")
        tm_idx = self.cmb_terminal_mode.findData(terminal_mode)
        if tm_idx >= 0:
            self.cmb_terminal_mode.setCurrentIndex(tm_idx)
        self.input_terminal_id.setText(settings.get("terminal_id", "TERM-01"))
        self.spin_sync_port.setValue(int(settings.get("sync_server_port", 5555)))
        self.input_main_pc_addr.setText(settings.get("main_pc_address", ""))
        self.spin_sync_interval.setValue(int(settings.get("sync_interval_seconds", 3)))
        self.input_sync_secret.setText(settings.get("sync_shared_secret", ""))

    def save(self) -> dict:
        """Return database mode, server connection and LAN sync fields as a settings dict."""
        mode_data = self.cmb_db_mode.currentData() or "Standalone"
        db_mode = "standalone" if mode_data == "Standalone" else "network"
        return {
            "db_mode": db_mode,
            "network_db_host": self.input_host.text().strip(),
            "network_db_port": self.input_port.value(),
            "network_db_name": self.input_dbname.text().strip(),
            "network_db_user": self.input_user.text().strip(),
            "network_db_password": self.input_password.text(),
            # LAN Sync
            "terminal_mode": self.cmb_terminal_mode.currentData() or "standalone",
            "terminal_id": self.input_terminal_id.text().strip() or "TERM-01",
            "sync_server_port": self.spin_sync_port.value(),
            "main_pc_address": self.input_main_pc_addr.text().strip(),
            "sync_interval_seconds": self.spin_sync_interval.value(),
            "sync_shared_secret": self.input_sync_secret.text(),
        }

    def _on_mode_changed(self, mode: str):
        is_network = mode == "Network"
        icon_color = ThemeService.get_accent_color()
        if is_network:
            self.lbl_mode_icon.setPixmap(Icons.get("fa5s.network-wired", icon_color).pixmap(32, 32))
            self.lbl_status_title.setText(_t("settings.network.network_mode_title"))
            self.lbl_status_subtitle.setText(_t("settings.network.network_mode_subtitle"))
        else:
            self.lbl_mode_icon.setPixmap(Icons.get("fa5s.desktop", icon_color).pixmap(32, 32))
            self.lbl_status_title.setText(_t("settings.network.single_mode_title"))
            self.lbl_status_subtitle.setText(_t("settings.network.single_mode_subtitle"))
        self.connection_tested = False
        self.btn_migrate.setEnabled(False)
        self.lbl_test_status.setText("")
        if hasattr(self, "_original_mode"):
            self.lbl_warning.setVisible(mode != self._original_mode)

    def _get_network_config(self):
        return {
            "host": self.input_host.text().strip(),
            "port": self.input_port.value(),
            "dbname": self.input_dbname.text().strip(),
            "user": self.input_user.text().strip(),
            "password": self.input_password.text(),
        }

    def _test_connection(self):
        from cbpos.core.database import Database

        cfg = self._get_network_config()
        if not all([cfg["host"], cfg["dbname"], cfg["user"]]):
            QMessageBox.warning(
                self,
                _t("common.validation_error"),
                _t("settings.network.validation_required_fields"),
            )
            return

        self.lbl_test_status.setText(_t("settings.network.testing"))
        self.btn_test.setEnabled(False)
        QApplication.processEvents()

        success, message = Database.test_connection(
            mode="network",
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["dbname"],
            user=cfg["user"],
            password=cfg["password"],
        )
        self.btn_test.setEnabled(True)

        if success:
            self.connection_tested = True
            self.lbl_test_status.setText(_t("settings.network.connected"))
            self.btn_migrate.setEnabled(True)
            QMessageBox.information(
                self,
                _t("settings.network.connection_test_title"),
                _t("settings.network.connection_success_message").format(message=message),
            )
        else:
            self.connection_tested = False
            self.lbl_test_status.setText(_t("settings.network.failed"))
            self.btn_migrate.setEnabled(False)
            QMessageBox.critical(
                self,
                _t("settings.network.connection_test_title"),
                message,
            )

    def _migrate_data(self):
        from cbpos.core.services.migration_service import MigrationService

        cfg = self._get_network_config()
        if not all([cfg["host"], cfg["dbname"], cfg["user"]]):
            QMessageBox.warning(
                self,
                _t("common.validation_error"),
                _t("settings.network.validation_before_migrate"),
            )
            return

        confirm = QMessageBox.question(
            self,
            _t("settings.network.confirm_migration_title"),
            _t("settings.network.confirm_migration_message").format(
                host=cfg["host"],
                port=cfg["port"],
                dbname=cfg["dbname"],
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        sqlite_url = Config.DB_URI
        url_obj = URL.create(
            drivername="postgresql+psycopg2",
            username=cfg["user"],
            password=cfg["password"],
            host=cfg["host"],
            port=cfg["port"],
            database=cfg["dbname"],
        )
        postgres_url = url_obj

        progress = QProgressDialog(
            _t("settings.network.migrating_progress"),
            None,
            0,
            0,
            self,
        )
        progress.setWindowTitle(_t("settings.network.migration_progress_title"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        try:
            success, message = MigrationService.migrate_sqlite_to_postgres(sqlite_url, postgres_url)
            progress.close()
            if success:
                QMessageBox.information(
                    self,
                    _t("settings.network.migration_success_title"),
                    _t("settings.network.migration_success_message").format(message=message),
                )
            else:
                QMessageBox.critical(
                    self,
                    _t("settings.network.migration_failed_title"),
                    _t("settings.network.migration_failed_message").format(message=message),
                )
        except Exception as e:
            progress.close()
            import logging

            logging.getLogger(__name__).exception("Data migration failed: %s", e)
            QMessageBox.critical(
                self,
                _t("settings.network.migration_error_title"),
                _t("settings.network.migration_error_message"),
            )

    def _on_terminal_mode_changed(self, index: int) -> None:
        """Show/hide fields based on selected terminal mode."""
        mode = self.cmb_terminal_mode.currentData() or "standalone"

        is_main = mode == "main"
        is_terminal = mode == "terminal"
        is_sync = is_main or is_terminal

        # Terminal ID always visible when sync enabled
        self.lbl_sync_terminal_id.setVisible(is_sync)
        self.input_terminal_id.setVisible(is_sync)

        # Sync port only for Main PC
        self.lbl_sync_port.setVisible(is_main)
        self.spin_sync_port.setVisible(is_main)

        # Main PC address only for Terminal
        self.lbl_main_pc_addr.setVisible(is_terminal)
        self.input_main_pc_addr.setVisible(is_terminal)

        # Sync interval for both
        self.lbl_sync_interval.setVisible(is_sync)
        self.spin_sync_interval.setVisible(is_sync)

        # Shared secret for both
        self.lbl_sync_secret.setVisible(is_sync)
        self.input_sync_secret.setVisible(is_sync)

        # Test button only for Terminal mode
        self.btn_test_sync.setVisible(is_terminal)
        self.lbl_sync_test_status.setVisible(is_terminal)
        self.btn_forget_main.setVisible(is_terminal)

        # Server address display for Main PC
        if is_main:
            try:
                import socket

                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.1)
                s.connect(("10.255.255.255", 1))
                ip = s.getsockname()[0]
                s.close()
            except Exception:
                ip = "127.0.0.1"
            port = self.spin_sync_port.value()
            self.lbl_server_address.setText(_t("settings.network.sync_server_address_display", ip=ip, port=port))
            self.lbl_server_address.setVisible(True)
        else:
            self.lbl_server_address.setVisible(False)

    def _test_sync_connection(self) -> None:
        """Test the connection to the Main PC sync server."""
        address = self.input_main_pc_addr.text().strip()
        if not address:
            QMessageBox.warning(
                self,
                _t("settings.network.sync_validation_title"),
                _t("settings.network.sync_validation_message"),
            )
            return

        if address.startswith("http://"):
            address = "https://" + address[len("http://") :]
        elif not address.startswith("https://"):
            address = f"https://{address}"

        self.lbl_sync_test_status.setText(_t("settings.network.sync_test_testing"))
        self.btn_test_sync.setEnabled(False)
        QApplication.processEvents()

        try:
            import json
            import urllib.error
            import urllib.request

            from cbpos.infrastructure.sync_tls import build_client_ssl_context

            url = f"{address}/sync/heartbeat"
            req = urllib.request.Request(url, method="GET", headers={"X-Sync-Token": self.input_sync_secret.text()})
            with urllib.request.urlopen(req, timeout=5, context=build_client_ssl_context()) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("status") == "ok":
                version = data.get("protocol_version", "?")
                terminals = data.get("terminals_connected", 0)
                self.lbl_sync_test_status.setText(_t("settings.network.sync_test_connected"))
                QMessageBox.information(
                    self,
                    _t("settings.network.sync_success_title"),
                    _t("settings.network.sync_success_message", version=version, terminals=terminals),
                )
            else:
                self.lbl_sync_test_status.setText(_t("settings.network.sync_test_unexpected"))

        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.lbl_sync_test_status.setText(_t("settings.network.sync_test_unauthorized"))
                QMessageBox.critical(
                    self,
                    _t("settings.network.sync_failed_title"),
                    _t("settings.network.sync_failed_secret_message"),
                )
            else:
                self.lbl_sync_test_status.setText(_t("settings.network.sync_test_failed"))
                QMessageBox.critical(
                    self,
                    _t("settings.network.sync_failed_title"),
                    _t("settings.network.sync_failed_message", address=address, error=e),
                )
        except urllib.error.URLError as e:
            self.lbl_sync_test_status.setText(_t("settings.network.sync_test_failed"))
            QMessageBox.critical(
                self,
                _t("settings.network.sync_failed_title"),
                _t("settings.network.sync_failed_message", address=address, error=e),
            )
        except Exception as e:
            self.lbl_sync_test_status.setText(_t("settings.network.sync_test_error"))
            QMessageBox.critical(self, _t("settings.network.sync_error_title"), str(e))
        finally:
            self.btn_test_sync.setEnabled(True)

    def _forget_trusted_main_pc(self) -> None:
        """Clear the pinned Main PC identity so this Terminal will trust
        whichever machine answers at the configured address next time.

        Needed after intentionally replacing the Main PC — otherwise
        SyncClient refuses to sync against a different instance_id than
        the one it first connected to.
        """
        from cbpos.core.services.config_service import ConfigService

        reply = QMessageBox.question(
            self,
            _t("settings.network.btn_forget_main"),
            _t("settings.network.sync_forget_main_confirm_message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ConfigService.set("sync_known_main_instance_id", "")
            QMessageBox.information(
                self,
                _t("settings.network.btn_forget_main"),
                _t("settings.network.sync_forget_main_done_message"),
            )


__all__ = ["NetworkPage"]
