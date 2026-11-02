"""Network database configuration settings page for multi-terminal setup."""

import logging
import socket

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontDatabase
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
    QToolTip,
    QVBoxLayout,
)
from sqlalchemy.engine import URL

from cbpos.config import Config
from cbpos.core.services.theme_service import ThemeService
from cbpos.core.utils.error_messages import translate_error
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
        self._network_schema_owner = False
        self._current_pg_url = None
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

        self.lbl_sslmode = QLabel()
        self.lbl_sslmode.setObjectName("FormLabel")
        self.cmb_sslmode = QComboBox()
        self.cmb_sslmode.setObjectName("InputNetwork")
        self.cmb_sslmode.addItems(["prefer", "require", "verify-ca", "verify-full", "disable"])
        grid_layout.addWidget(
            self.lbl_sslmode,
            5,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        grid_layout.addWidget(self.cmb_sslmode, 5, 1)

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

        # Step 2: Database Card
        self.database_card = QFrame()
        self.database_card.setObjectName("NetworkCard")
        self.database_card.setFrameShape(QFrame.Shape.StyledPanel)
        database_layout = QVBoxLayout(self.database_card)
        database_layout.setContentsMargins(25, 25, 25, 25)
        database_layout.setSpacing(14)

        self.lbl_database_step_title = QLabel()
        self.lbl_database_step_title.setObjectName("CardTitle")
        database_layout.addWidget(self.lbl_database_step_title)

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        self.lbl_db_state_icon = QLabel()
        self.lbl_db_state_icon.setObjectName("StatusIcon")
        self.lbl_db_state_desc = QLabel()
        self.lbl_db_state_desc.setWordWrap(True)
        status_row.addWidget(self.lbl_db_state_icon)
        status_row.addWidget(self.lbl_db_state_desc, 1)
        database_layout.addLayout(status_row)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        self.btn_copy_data = QPushButton()
        self.btn_copy_data.clicked.connect(self._on_copy_data_clicked)
        self.btn_copy_data.setVisible(False)

        self.btn_start_empty = QPushButton()
        self.btn_start_empty.clicked.connect(self._on_start_empty_clicked)
        self.btn_start_empty.setVisible(False)

        self.btn_make_main_update = QPushButton()
        self.btn_make_main_update.clicked.connect(self._on_make_main_update_clicked)
        self.btn_make_main_update.setVisible(False)

        actions_layout.addWidget(self.btn_copy_data)
        actions_layout.addWidget(self.btn_start_empty)
        actions_layout.addWidget(self.btn_make_main_update)
        actions_layout.addStretch()
        database_layout.addLayout(actions_layout)

        self.database_card.setEnabled(False)
        server_layout.addWidget(self.database_card)

        # Step 3: Confirm Card
        self.confirm_card = QFrame()
        self.confirm_card.setObjectName("NetworkCard")
        self.confirm_card.setFrameShape(QFrame.Shape.StyledPanel)
        confirm_layout = QVBoxLayout(self.confirm_card)
        confirm_layout.setContentsMargins(25, 25, 25, 25)
        confirm_layout.setSpacing(14)

        self.lbl_confirm_step_title = QLabel()
        self.lbl_confirm_step_title.setObjectName("CardTitle")
        confirm_layout.addWidget(self.lbl_confirm_step_title)

        self.lbl_confirm_summary = QLabel()
        self.lbl_confirm_summary.setWordWrap(True)
        confirm_layout.addWidget(self.lbl_confirm_summary)

        self.btn_switch = QPushButton()
        self.btn_switch.clicked.connect(self._on_switch_clicked)
        confirm_layout.addWidget(self.btn_switch)

        self.confirm_card.setEnabled(False)
        server_layout.addWidget(self.confirm_card)

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

        # Main PC Sync Code Card
        self.main_code_card = QFrame()
        self.main_code_card.setObjectName("SyncCodeBox")
        self.main_code_card.setStyleSheet(
            "QFrame#SyncCodeBox { background-color: rgba(0, 0, 0, 0.08); border: 1px solid rgba(128, 128, 128, 0.25); border-radius: 8px; padding: 12px; }"
        )
        main_code_layout = QVBoxLayout(self.main_code_card)
        main_code_layout.setContentsMargins(14, 12, 14, 12)
        main_code_layout.setSpacing(8)

        self.lbl_main_code_title = QLabel()
        self.lbl_main_code_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        main_code_layout.addWidget(self.lbl_main_code_title)

        self.lbl_main_code_desc = QLabel()
        self.lbl_main_code_desc.setObjectName("MigrationInfo")
        self.lbl_main_code_desc.setWordWrap(True)
        main_code_layout.addWidget(self.lbl_main_code_desc)

        code_box = QFrame()
        code_box.setStyleSheet(
            "background-color: rgba(0, 0, 0, 0.12); border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 6px; padding: 8px;"
        )
        code_box_layout = QHBoxLayout(code_box)
        code_box_layout.setContentsMargins(10, 8, 10, 8)

        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(10)

        self.lbl_main_code_fp = QLabel()
        self.lbl_main_code_fp.setFont(mono_font)
        self.lbl_main_code_fp.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        code_box_layout.addWidget(self.lbl_main_code_fp, 1)

        self.btn_copy_main_code = QPushButton()
        self.btn_copy_main_code.setObjectName("BtnTestNetwork")
        self.btn_copy_main_code.clicked.connect(self._copy_main_code)
        code_box_layout.addWidget(self.btn_copy_main_code, 0, Qt.AlignmentFlag.AlignTop)

        main_code_layout.addWidget(code_box)
        sync_card_layout.addWidget(self.main_code_card)

        # Terminal Pairing Card
        self.terminal_pairing_card = QFrame()
        self.terminal_pairing_card.setObjectName("SyncPairingBox")
        self.terminal_pairing_card.setStyleSheet(
            "QFrame#SyncPairingBox { background-color: rgba(0, 0, 0, 0.08); border: 1px solid rgba(128, 128, 128, 0.25); border-radius: 8px; padding: 12px; }"
        )
        tp_layout = QVBoxLayout(self.terminal_pairing_card)
        tp_layout.setContentsMargins(14, 12, 14, 12)
        tp_layout.setSpacing(8)

        self.lbl_tp_title = QLabel()
        self.lbl_tp_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        tp_layout.addWidget(self.lbl_tp_title)

        self.lbl_tp_status = QLabel()
        self.lbl_tp_status.setWordWrap(True)
        self.lbl_tp_status.setObjectName("MigrationInfo")
        tp_layout.addWidget(self.lbl_tp_status)

        tp_btn_layout = QHBoxLayout()
        self.btn_pair_action = QPushButton()
        self.btn_pair_action.setObjectName("BtnTestNetwork")
        self.btn_pair_action.clicked.connect(self._open_pairing_dialog)
        tp_btn_layout.addWidget(self.btn_pair_action)
        tp_btn_layout.addStretch()
        tp_layout.addLayout(tp_btn_layout)

        sync_card_layout.addWidget(self.terminal_pairing_card)

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

        # Server tab (3-step guided stepper)
        self.lbl_config_title.setText(_t("network_setup.step_connect"))
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
        self.lbl_sslmode.setText(_t("network_setup.sslmode"))
        self.btn_test.setText(_t("settings.network.btn_test_connection"))
        self.btn_test.setToolTip(_t("settings.network.tooltip_test_connection"))

        self.lbl_database_step_title.setText(_t("network_setup.step_database"))
        self.btn_copy_data.setText(_t("network_setup.copy_data"))
        self.btn_start_empty.setText(_t("network_setup.start_empty"))
        self.btn_make_main_update.setText(_t("network_setup.make_main_update"))

        self.lbl_confirm_step_title.setText(_t("network_setup.step_confirm"))
        self.btn_switch.setText(_t("network_setup.switch"))

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

        # Main PC Sync Code Card
        self.lbl_main_code_title.setText(_t("sync_pairing.this_computer_code"))
        self.lbl_main_code_desc.setText(_t("sync_pairing.main_help"))
        self.btn_copy_main_code.setText(_t("sync_pairing.copy_code"))

        # Terminal Pairing Card
        self.lbl_tp_title.setText(_t("sync_pairing.title"))
        self._update_terminal_pairing_card()

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
        self._network_schema_owner = bool(settings.get("network_schema_owner", False))
        sslmode = settings.get("network_db_sslmode", "prefer")
        ssl_idx = self.cmb_sslmode.findText(sslmode)
        if ssl_idx >= 0:
            self.cmb_sslmode.setCurrentIndex(ssl_idx)
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
            "network_db_sslmode": self.cmb_sslmode.currentText(),
            "network_schema_owner": self._network_schema_owner,
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
            self._on_connection_success(cfg)
            QMessageBox.information(
                self,
                _t("settings.network.connection_test_title"),
                _t("settings.network.connection_success_message").format(message=message),
            )
        else:
            self.connection_tested = False
            self.lbl_test_status.setText(_t("settings.network.failed"))
            self.btn_migrate.setEnabled(False)
            self.database_card.setEnabled(False)
            self.confirm_card.setEnabled(False)
            QMessageBox.critical(
                self,
                _t("settings.network.connection_test_title"),
                message,
            )

    def _on_connection_success(self, cfg: dict):
        """Construct PostgreSQL URL and inspect server schema state."""
        sslmode = self.cmb_sslmode.currentText()
        query = {"sslmode": sslmode} if sslmode and sslmode != "disable" else {}
        url_obj = URL.create(
            drivername="postgresql+psycopg2",
            username=cfg["user"],
            password=cfg["password"],
            host=cfg["host"],
            port=cfg["port"],
            database=cfg["dbname"],
            query=query,
        )
        self._current_pg_url = str(url_obj)
        self._inspect_and_update_database_step(self._current_pg_url)

    def _inspect_and_update_database_step(self, pg_url: str):
        """Inspect PostgreSQL database state and update Step 2 and Step 3 cards."""
        from cbpos.core.services.schema_migration_service import SchemaMigrationService

        try:
            rev = SchemaMigrationService.current_revision(pg_url)
            head = SchemaMigrationService.head_revision(pg_url)
            known = SchemaMigrationService.known_revisions(pg_url)
        except Exception as e:
            self.database_card.setEnabled(False)
            self.confirm_card.setEnabled(False)
            self.lbl_db_state_desc.setText(f"Error checking database schema: {e}")
            return

        self.database_card.setEnabled(True)

        if rev is None:
            # Check if tables exist
            from sqlalchemy import create_engine, inspect

            eng = create_engine(pg_url)
            try:
                tables = set(inspect(eng).get_table_names()) - {"alembic_version", "sqlite_sequence"}
            finally:
                eng.dispose()

            if not tables:
                # State: empty
                self.lbl_db_state_icon.setPixmap(Icons.get("fa5s.exclamation-triangle", "#ffc107").pixmap(24, 24))
                self.lbl_db_state_desc.setText(_t("network_setup.state_empty"))
                self.btn_copy_data.setVisible(True)
                self.btn_copy_data.setEnabled(True)
                self.btn_start_empty.setVisible(True)
                self.btn_start_empty.setEnabled(True)
                self.btn_make_main_update.setVisible(False)
                self.confirm_card.setEnabled(False)
                return

        if rev == head:
            # State: up to date
            self.lbl_db_state_icon.setPixmap(Icons.get("fa5s.check-circle", "#28a745").pixmap(24, 24))
            self.lbl_db_state_desc.setText(_t("network_setup.state_ok"))
            self.btn_copy_data.setVisible(False)
            self.btn_start_empty.setVisible(False)
            self.btn_make_main_update.setVisible(False)
            self.confirm_card.setEnabled(True)
            self._update_confirm_summary()
            return

        if rev in known and rev != head:
            # State: behind head
            self.lbl_db_state_icon.setPixmap(Icons.get("fa5s.exclamation-triangle", "#ffc107").pixmap(24, 24))
            self.lbl_db_state_desc.setText(_t("network_setup.state_behind"))
            self.btn_copy_data.setVisible(False)
            self.btn_start_empty.setVisible(False)
            self.btn_make_main_update.setVisible(True)
            self.btn_make_main_update.setEnabled(True)
            self.confirm_card.setEnabled(False)
            return

        # State: newer than this application
        self.lbl_db_state_icon.setPixmap(Icons.get("fa5s.times-circle", "#dc3545").pixmap(24, 24))
        self.lbl_db_state_desc.setText(_t("network_setup.state_newer"))
        self.btn_copy_data.setVisible(False)
        self.btn_start_empty.setVisible(False)
        self.btn_make_main_update.setVisible(False)
        self.confirm_card.setEnabled(False)

    def _on_copy_data_clicked(self):
        """Execute migration of SQLite data to PostgreSQL and update Step 2."""
        self._migrate_data()
        if self._current_pg_url:
            self._inspect_and_update_database_step(self._current_pg_url)

    def _on_start_empty_clicked(self):
        """Initialize empty database with default admin user on PostgreSQL."""
        import socket

        from sqlalchemy import create_engine

        from cbpos.core.models import Base
        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.database_setup_service import DatabaseSetupService
        from cbpos.core.services.schema_migration_service import SchemaMigrationService
        from cbpos.ui.dialogs.admin_pin_dialog import AdminPinDialog

        pin_dialog = AdminPinDialog(parent=self)
        if not pin_dialog.exec():
            return
        pin = pin_dialog.pin()
        user, role = AuthService.authenticate_pin(pin)
        if not user or not role or (role.access_level < 9 and role.name != "Admin"):
            QMessageBox.warning(
                self,
                _t("common.error"),
                _t("permission.admin_override_failed"),
            )
            return

        try:
            eng = create_engine(self._current_pg_url)
            Base.metadata.create_all(eng)
            eng.dispose()
            DatabaseSetupService.stamp_alembic_head(self._current_pg_url)
            self._network_schema_owner = True
            SchemaMigrationService.set_schema_owner_host(self._current_pg_url, socket.gethostname())
            QMessageBox.information(
                self,
                _t("network_setup.step_database"),
                _t("network_setup.database_ready"),
            )
            self._inspect_and_update_database_step(self._current_pg_url)
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))

    def _on_make_main_update_clicked(self):
        """Designate this machine as Main PC and run schema upgrade."""
        import socket

        from cbpos.core.services.auth_service import AuthService
        from cbpos.core.services.schema_migration_service import SchemaMigrationService
        from cbpos.ui.dialogs.admin_pin_dialog import AdminPinDialog

        pin_dialog = AdminPinDialog(parent=self)
        if not pin_dialog.exec():
            return
        pin = pin_dialog.pin()
        user, role = AuthService.authenticate_pin(pin)
        if not user or not role or (role.access_level < 9 and role.name != "Admin"):
            QMessageBox.warning(
                self,
                _t("common.error"),
                _t("permission.admin_override_failed"),
            )
            return

        try:
            SchemaMigrationService.upgrade_with_lock(self._current_pg_url, user_id=user.id)
            self._network_schema_owner = True
            SchemaMigrationService.set_schema_owner_host(self._current_pg_url, socket.gethostname())
            QMessageBox.information(
                self,
                _t("network_setup.step_database"),
                _t("network_setup.state_ok"),
            )
            self._inspect_and_update_database_step(self._current_pg_url)
        except Exception as e:
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("network_gate.update_failed", error=str(e)),
            )

    def _update_confirm_summary(self):
        """Update summary text in Step 3 card."""
        cfg = self._get_network_config()
        summary = (
            f"<b>{_t('network_setup.summary_host')}</b> {cfg['host']}:{cfg['port']}<br>"
            f"<b>{_t('network_setup.summary_database')}</b> {cfg['dbname']}<br>"
            f"<b>{_t('network_setup.summary_status')}</b> <span style='color:#28a745;'>{_t('network_setup.state_ok')}</span>"
        )
        self.lbl_confirm_summary.setText(summary)

    def _on_switch_clicked(self):
        """Save settings and restart application into network mode."""
        from cbpos.core.services.config_service import ConfigService
        from cbpos.ui.app_restart import restart_application

        cfg = self._get_network_config()
        ConfigService.set("db_mode", "network")
        ConfigService.set("network_db_host", cfg["host"])
        ConfigService.set("network_db_port", cfg["port"])
        ConfigService.set("network_db_name", cfg["dbname"])
        ConfigService.set("network_db_user", cfg["user"])
        ConfigService.set("network_db_password", cfg["password"])
        ConfigService.set("network_db_sslmode", self.cmb_sslmode.currentText())
        ConfigService.set("network_schema_owner", self._network_schema_owner)
        ConfigService.save_settings(self.save())

        win = self.window()
        restart_application(win)

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

        # Server address and sync code display for Main PC
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

            try:
                from cbpos.infrastructure import sync_tls

                cert_path, _ = sync_tls.get_or_create_certificate()
                with open(cert_path, encoding="ascii") as f:
                    pem = f.read()
                self._main_canonical_fp = sync_tls.cert_fingerprint(pem, multiline=False)
                self.lbl_main_code_fp.setText(sync_tls.cert_fingerprint(pem, multiline=True))
            except Exception as e:
                logger.warning("Could not load Main PC sync certificate: %s", e)
                self._main_canonical_fp = ""
                self.lbl_main_code_fp.setText("")

            self.main_code_card.setVisible(True)
            self.terminal_pairing_card.setVisible(False)
        elif is_terminal:
            self.lbl_server_address.setVisible(False)
            self.main_code_card.setVisible(False)
            self.terminal_pairing_card.setVisible(True)
            self._update_terminal_pairing_card()
        else:
            self.lbl_server_address.setVisible(False)
            self.main_code_card.setVisible(False)
            self.terminal_pairing_card.setVisible(False)

    def _update_terminal_pairing_card(self) -> None:
        """Update pairing status card on terminal."""
        from cbpos.core.services.config_service import ConfigService

        pinned_fp = ConfigService.get("sync_pinned_cert_fp") or ""

        if getattr(self, "_cert_mismatch", False):
            self.lbl_tp_status.setText(
                f"<span style='color: #F44336; font-weight: bold;'>● {_t('sync_pairing.changed')}</span>"
            )
            self.btn_pair_action.setText(_t("sync_pairing.review"))
            self.btn_pair_action.setEnabled(True)
        elif not pinned_fp:
            self.lbl_tp_status.setText(
                f"<span style='color: #FF9800; font-weight: bold;'>● {_t('sync_pairing.not_paired')}</span>"
            )
            self.btn_pair_action.setText(_t("sync_pairing.title"))
            self.btn_pair_action.setEnabled(True)
        else:
            truncated = pinned_fp[-23:] if len(pinned_fp) > 23 else pinned_fp
            self.lbl_tp_status.setText(
                f"<span style='color: #4CAF50; font-weight: bold;'>● {_t('sync_pairing.paired')}</span> (…{truncated})"
            )
            self.btn_pair_action.setText(_t("sync_pairing.change"))
            self.btn_pair_action.setEnabled(True)

    def _open_pairing_dialog(self) -> None:
        """Open SyncPairingDialog for pairing or reviewing code change."""
        address = self.input_main_pc_addr.text().strip()
        if not address:
            QMessageBox.warning(
                self,
                _t("settings.network.sync_validation_title"),
                _t("settings.network.sync_validation_message"),
            )
            return

        from urllib.parse import urlsplit

        if address.startswith("http://"):
            address = "https://" + address[len("http://") :]
        elif not address.startswith("https://"):
            address = f"https://{address}"

        parsed = urlsplit(address)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5555

        from cbpos.ui.dialogs.sync_pairing_dialog import SyncPairingDialog

        re_pair = getattr(self, "_cert_mismatch", False)
        dlg = SyncPairingDialog(host=host, port=port, re_pair=re_pair, parent=self)
        if dlg.exec():
            self._cert_mismatch = False
            self._update_terminal_pairing_card()
            win = self.window()
            if hasattr(win, "_sync_client") and win._sync_client:
                win._sync_client.reload_ssl_context()

    def _copy_main_code(self) -> None:
        """Copy the Main PC's TLS certificate fingerprint to clipboard."""
        if hasattr(self, "_main_canonical_fp") and self._main_canonical_fp:
            QApplication.clipboard().setText(self._main_canonical_fp)
            QToolTip.showText(
                self.btn_copy_main_code.mapToGlobal(self.btn_copy_main_code.rect().center()),
                _t("sync_pairing.code_copied"),
                self.btn_copy_main_code,
            )

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

        self.lbl_sync_test_status.setText(_t("settings.network.sync_test_testing"))
        self.btn_test_sync.setEnabled(False)
        QApplication.processEvents()

        from cbpos.ui.workers import SyncTestWorker

        worker = SyncTestWorker(address, self.input_sync_secret.text())
        self._sync_test_worker = worker
        worker.finished_result.connect(self._on_sync_test_finished)
        worker.start()

    def _on_sync_test_finished(self, success: bool, outcome: str, info: dict) -> None:
        """Handle outcome of the background sync server test."""
        self.btn_test_sync.setEnabled(True)
        if outcome == "ok":
            version = info.get("version", "?")
            terminals = info.get("terminals", 0)
            self.lbl_sync_test_status.setText(_t("settings.network.sync_test_connected"))
            QMessageBox.information(
                self,
                _t("settings.network.sync_success_title"),
                _t("settings.network.sync_success_message", version=version, terminals=terminals),
            )
        elif outcome == "unpaired":
            self.lbl_sync_test_status.setText(_t("sync_pairing.not_paired_short"))
            QMessageBox.information(
                self,
                _t("sync_pairing.title"),
                _t("sync_pairing.not_paired"),
            )
            self._update_terminal_pairing_card()
        elif outcome == "cert_mismatch":
            self._cert_mismatch = True
            self.lbl_sync_test_status.setText(_t("sync_pairing.changed"))
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("sync_pairing.changed"),
            )
            self._update_terminal_pairing_card()
        elif outcome == "unauthorized":
            self.lbl_sync_test_status.setText(_t("settings.network.sync_test_unauthorized"))
            QMessageBox.critical(
                self,
                _t("settings.network.sync_failed_title"),
                _t("settings.network.sync_failed_secret_message"),
            )
        elif outcome == "failed":
            self.lbl_sync_test_status.setText(_t("settings.network.sync_test_failed"))
            QMessageBox.critical(
                self,
                _t("settings.network.sync_failed_title"),
                _t(
                    "settings.network.sync_failed_message", address=info.get("address", ""), error=info.get("error", "")
                ),
            )
        elif outcome == "error":
            self.lbl_sync_test_status.setText(_t("settings.network.sync_test_error"))
            QMessageBox.critical(
                self,
                _t("settings.network.sync_error_title"),
                translate_error(str(info.get("error", ""))),
            )
        else:
            self.lbl_sync_test_status.setText(_t("settings.network.sync_test_unexpected"))

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
            ConfigService.set("sync_pinned_cert_pem", "")
            ConfigService.set("sync_pinned_cert_fp", "")
            self._cert_mismatch = False
            self._update_terminal_pairing_card()
            QMessageBox.information(
                self,
                _t("settings.network.btn_forget_main"),
                _t("settings.network.sync_forget_main_done_message"),
            )


__all__ = ["NetworkPage"]
