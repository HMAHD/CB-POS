"""
Data Safety view — embedded in Settings view.

A thin page that puts the four Data Safety tabs side by side and wires
them together (#693). Each tab lives in its own module under
``cbpos/ui/views/data_safety/``:

- Backup: list, create, clean and delete backups; shop backup password
- Restore: verify and restore from an encrypted backup
- Maintenance: database info, VACUUM, integrity check
- Export: products, customers or sales to Excel/CSV

Uses QSS objectNames and class properties for theme compatibility.
No hardcoded colors — works with both dark and light themes.
"""

from PyQt6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from cbpos.i18n import _t, register_language_callback
from cbpos.ui.views.data_safety.backup_tab import BackupTabWidget
from cbpos.ui.views.data_safety.export_tab import ExportTabWidget
from cbpos.ui.views.data_safety.maintenance_tab import MaintenanceTabWidget
from cbpos.ui.views.data_safety.restore_tab import RestoreTabWidget
from cbpos.ui.widgets.loading_overlay import LoadingOverlay


class DataSafetyView(QWidget):
    """Tabbed view for backup, restore, maintenance, and export operations."""

    def __init__(self) -> None:
        """Build the Backup, Restore, Maintenance, and Export tabs."""
        super().__init__()
        self._overlay = LoadingOverlay(self)
        self._init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def showEvent(self, event) -> None:
        """Refresh data when the view becomes visible."""
        super().showEvent(event)
        self.backup_tab.refresh()
        self.restore_tab.refresh_password_hint()
        self.maintenance_tab.refresh()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Title
        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "dialog-title")
        layout.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel()
        self.lbl_subtitle.setProperty("class", "muted")
        layout.addWidget(self.lbl_subtitle)

        self.backup_tab = BackupTabWidget(self._overlay)
        self.restore_tab = RestoreTabWidget(self._overlay)
        self.maintenance_tab = MaintenanceTabWidget(self._overlay)
        self.export_tab = ExportTabWidget()

        # Tabs — let QSS handle tab styling
        self.tabs = QTabWidget()
        for tab in (self.backup_tab, self.restore_tab, self.maintenance_tab, self.export_tab):
            self.tabs.addTab(tab, "")
        layout.addWidget(self.tabs, 1)

        self.backup_tab.restore_requested.connect(self._open_restore)
        # Either tab can set the shop backup password; both show its state.
        self.backup_tab.password_changed.connect(self.restore_tab.refresh_password_hint)
        self.restore_tab.password_changed.connect(self.backup_tab.refresh_password_status)

    def _open_restore(self, path: str) -> None:
        """Switch to the Restore tab, ready to restore the backup at *path*."""
        self.tabs.setCurrentWidget(self.restore_tab)
        self.restore_tab.load_backup(path)

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self.lbl_title.setText(_t("data_safety.title"))
        self.lbl_subtitle.setText(_t("data_safety.subtitle"))
        for tab, title_key in (
            (self.backup_tab, "data_safety.tab_backup"),
            (self.restore_tab, "data_safety.tab_restore"),
            (self.maintenance_tab, "data_safety.tab_maintenance"),
            (self.export_tab, "data_safety.tab_export"),
        ):
            self.tabs.setTabText(self.tabs.indexOf(tab), _t(title_key))
            tab.retranslate_ui()
