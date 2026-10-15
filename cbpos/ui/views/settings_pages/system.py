"""System settings page (session security, POS behavior, features, backup)."""

from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
)

from cbpos.i18n import _t, register_language_callback
from cbpos.ui.views.settings_pages.base import SettingsPage


class SystemPage(SettingsPage):
    """System settings: session security, feature toggles, and behavior."""

    def init_ui(self):
        """Build the Security, POS Behavior, Features and Backup tabs."""
        _, self.tabs = self._create_page_layout("", "")

        # --- Tab 1: Security ---
        self._tab_sec, self._form_sec = self._build_form_tab()

        self.chk_timeout = QCheckBox()
        self.chk_timeout.toggled.connect(self._on_timeout_toggled)
        self._form_sec.addRow("", self.chk_timeout)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_timeout.setRange(1, 60)
        self.spin_timeout.setSuffix(" min")
        self.spin_timeout.setFixedWidth(260)
        self._lbl_timeout = QLabel()
        self._form_sec.addRow(self._lbl_timeout, self.spin_timeout)

        self.chk_void_reason = QCheckBox()
        self._form_sec.addRow("", self.chk_void_reason)

        self.spin_max_login = QSpinBox()
        self.spin_max_login.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_max_login.setRange(3, 20)
        self.spin_max_login.setFixedWidth(200)
        self._lbl_max_login = QLabel()
        self._form_sec.addRow(self._lbl_max_login, self.spin_max_login)

        self.spin_lockout = QSpinBox()
        self.spin_lockout.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_lockout.setRange(30, 3600)
        self.spin_lockout.setSuffix(" sec")
        self.spin_lockout.setFixedWidth(200)
        self._lbl_lockout = QLabel()
        self._form_sec.addRow(self._lbl_lockout, self.spin_lockout)

        self.tabs.addTab(self._tab_sec, "")

        # --- Tab 2: POS Behavior ---
        self._tab_pos, self._form_pos = self._build_form_tab()

        self.chk_quick_pay = QCheckBox()
        self._form_pos.addRow("", self.chk_quick_pay)

        self.chk_show_receipt_dialog = QCheckBox()
        self._form_pos.addRow("", self.chk_show_receipt_dialog)

        self.chk_auto_barcode_select = QCheckBox()
        self._form_pos.addRow("", self.chk_auto_barcode_select)

        self.chk_enable_sounds = QCheckBox()
        self._form_pos.addRow("", self.chk_enable_sounds)

        self.tabs.addTab(self._tab_pos, "")

        # --- Tab 3: Inventory ---
        self._tab_inv, self._form_inv = self._build_form_tab()

        self.chk_negative_stock = QCheckBox()
        self._form_inv.addRow("", self.chk_negative_stock)

        self.chk_auto_barcodes = QCheckBox()
        self._form_inv.addRow("", self.chk_auto_barcodes)

        self.chk_loyalty = QCheckBox()
        # Retained for legacy test compatibility (#754); not added to layout

        self.tabs.addTab(self._tab_inv, "")

        # --- Tab 4: Backup ---
        self._tab_backup, self._form_backup = self._build_form_tab()

        self.chk_auto_backup = QCheckBox()
        self._form_backup.addRow("", self.chk_auto_backup)

        self.spin_retention = QSpinBox()
        self.spin_retention.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_retention.setRange(1, 50)
        self.spin_retention.setSuffix(" backups")
        self._lbl_retention = QLabel()
        self._form_backup.addRow(self._lbl_retention, self.spin_retention)

        backup_dir_layout = QHBoxLayout()
        self.input_backup_dir = QLineEdit()
        self.input_backup_dir.setReadOnly(True)
        backup_dir_layout.addWidget(self.input_backup_dir, 1)

        self.btn_browse_backup = QPushButton()
        self.btn_browse_backup.setProperty("class", "secondary")
        self.btn_browse_backup.setFixedHeight(32)
        self.btn_browse_backup.clicked.connect(self._browse_backup_dir)
        backup_dir_layout.addWidget(self.btn_browse_backup)

        self._lbl_backup_folder = QLabel()
        self._form_backup.addRow(self._lbl_backup_folder, backup_dir_layout)

        self.tabs.addTab(self._tab_backup, "")

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def retranslate_ui(self) -> None:
        """Update all widget text and tab labels from the translation system."""
        self._page_title.setText(_t("settings.system.title"))
        self.btn_reset_defaults.setText(_t("settings.btn_reset_defaults"))
        self._page_subtitle.setText(_t("settings.system.subtitle"))

        self.tabs.setTabText(0, _t("settings.system.tab_security"))
        self.tabs.setTabText(1, _t("settings.system.tab_pos_behavior"))
        self.tabs.setTabText(2, _t("settings.system.tab_features"))
        self.tabs.setTabText(3, _t("settings.system.tab_backup"))

        # Security
        self.chk_timeout.setText(_t("settings.system.lock_on_idle"))
        self._lbl_timeout.setText(_t("settings.system.inactivity_timeout"))
        self.spin_timeout.setSuffix(_t("settings.system.suffix_min"))
        self.spin_timeout.setToolTip(_t("settings.system.tooltip_timeout"))
        self.chk_void_reason.setText(_t("settings.system.require_void_reason"))
        self.chk_void_reason.setToolTip(_t("settings.system.tooltip_void_reason"))
        self._lbl_max_login.setText(_t("settings.system.max_login_attempts"))
        self.spin_max_login.setToolTip(_t("settings.system.tooltip_max_login"))
        self._lbl_lockout.setText(_t("settings.system.lockout_duration"))
        self.spin_lockout.setSuffix(_t("settings.system.suffix_sec"))
        self.spin_lockout.setToolTip(_t("settings.system.tooltip_lockout"))

        # POS Behavior
        self.chk_quick_pay.setText(_t("settings.system.quick_pay"))
        self.chk_quick_pay.setToolTip(_t("settings.system.tooltip_quick_pay"))
        self.chk_show_receipt_dialog.setText(_t("settings.system.show_receipt_dialog"))
        self.chk_show_receipt_dialog.setToolTip(_t("settings.system.tooltip_receipt_dialog"))
        self.chk_auto_barcode_select.setText(_t("settings.system.auto_barcode_select"))
        self.chk_auto_barcode_select.setToolTip(_t("settings.system.tooltip_auto_barcode"))
        self.chk_enable_sounds.setText(_t("settings.system.enable_sounds"))
        self.chk_enable_sounds.setToolTip(_t("settings.system.tooltip_sounds"))

        # Features
        self.chk_negative_stock.setText(_t("settings.system.negative_stock"))
        self.chk_negative_stock.setToolTip(_t("settings.system.tooltip_negative_stock"))
        self.chk_auto_barcodes.setText(_t("settings.system.auto_barcodes"))
        self.chk_auto_barcodes.setToolTip(_t("settings.system.tooltip_auto_barcodes"))
        self.chk_loyalty.setText(_t("settings.system.loyalty_points"))
        self.chk_loyalty.setToolTip(_t("settings.system.tooltip_loyalty"))

        # Backup
        self.chk_auto_backup.setText(_t("settings.system.auto_backup"))
        self.chk_auto_backup.setToolTip(_t("settings.system.tooltip_auto_backup"))
        self._lbl_retention.setText(_t("settings.system.backup_retention"))
        self.spin_retention.setSuffix(_t("settings.system.suffix_backups"))
        self.spin_retention.setToolTip(_t("settings.system.tooltip_retention"))
        self._lbl_backup_folder.setText(_t("settings.system.backup_folder"))
        self.input_backup_dir.setPlaceholderText(_t("settings.system.backup_folder_placeholder"))
        self.btn_browse_backup.setText(_t("settings.system.btn_browse_backup"))
        self.equalize_form_labels()

    def _on_timeout_toggled(self, checked: bool) -> None:
        """Enable or disable inactivity timeout minutes input based on checkbox."""
        self.spin_timeout.setEnabled(checked)
        self._lbl_timeout.setEnabled(checked)

    def _browse_backup_dir(self) -> None:
        current = self.input_backup_dir.text() or ""
        chosen = QFileDialog.getExistingDirectory(self, _t("settings.system.choose_backup_folder"), current)
        if chosen:
            self.input_backup_dir.setText(chosen)

    def load(self, settings: dict):
        """Populate session security, POS behavior, feature toggle and backup fields from the settings dict."""
        timeout_val = int(settings.get("session_timeout_minutes", 0))
        if timeout_val > 0:
            self.chk_timeout.setChecked(True)
            self.spin_timeout.setValue(timeout_val)
            self.spin_timeout.setEnabled(True)
            self._lbl_timeout.setEnabled(True)
        else:
            self.chk_timeout.setChecked(False)
            self.spin_timeout.setValue(5)
            self.spin_timeout.setEnabled(False)
            self._lbl_timeout.setEnabled(False)
        self.chk_void_reason.setChecked(settings.get("require_void_reason", True))
        self.spin_max_login.setValue(int(settings.get("max_login_attempts", 5)))
        self.spin_lockout.setValue(int(settings.get("lockout_duration_seconds", 300)))
        self.chk_quick_pay.setChecked(settings.get("quick_pay_enabled", True))
        self.chk_show_receipt_dialog.setChecked(settings.get("show_receipt_dialog", True))
        self.chk_auto_barcode_select.setChecked(settings.get("auto_select_barcode_match", True))
        self.chk_enable_sounds.setChecked(settings.get("enable_sounds", True))
        self.chk_negative_stock.setChecked(settings.get("allow_negative_stock", False))
        self.chk_auto_barcodes.setChecked(settings.get("auto_generate_barcodes", True))
        self.chk_loyalty.setChecked(settings.get("enable_loyalty", True))
        self.chk_auto_backup.setChecked(settings.get("auto_backup_on_close", True))
        self.spin_retention.setValue(int(settings.get("backup_retention_count", 5)))
        self.input_backup_dir.setText(settings.get("backup_dir", ""))

    def save(self) -> dict:
        """Return session security, POS behavior, feature toggle and backup fields as a settings dict."""
        return {
            "session_timeout_minutes": self.spin_timeout.value() if self.chk_timeout.isChecked() else 0,
            "require_void_reason": self.chk_void_reason.isChecked(),
            "max_login_attempts": self.spin_max_login.value(),
            "lockout_duration_seconds": self.spin_lockout.value(),
            "quick_pay_enabled": self.chk_quick_pay.isChecked(),
            "show_receipt_dialog": self.chk_show_receipt_dialog.isChecked(),
            "auto_select_barcode_match": self.chk_auto_barcode_select.isChecked(),
            "enable_sounds": self.chk_enable_sounds.isChecked(),
            "allow_negative_stock": self.chk_negative_stock.isChecked(),
            "auto_generate_barcodes": self.chk_auto_barcodes.isChecked(),
            "auto_backup_on_close": self.chk_auto_backup.isChecked(),
            "backup_retention_count": self.spin_retention.value(),
            "backup_dir": self.input_backup_dir.text(),
        }


__all__ = ["SystemPage"]
