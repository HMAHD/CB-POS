"""Read-only catalog notice banner shown on till terminals (#869)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

from cbpos.core.utils.terminal_guard import catalog_is_read_only
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons


class ReadOnlyBanner(QFrame):
    """Callout banner informing users that catalog edits belong on the Main PC."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ReadOnlyCatalogBanner")
        self._init_ui()
        self.refresh_visibility()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(Icons.get(Icons.INFO, "#00BCEB").pixmap(20, 20))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.icon_label)

        self.text_label = QLabel()
        self.text_label.setObjectName("ReadOnlyCatalogBannerText")
        self.text_label.setWordWrap(True)
        self.text_label.setText(_t("catalog.read_only_banner"))
        layout.addWidget(self.text_label, 1)

    def retranslate_ui(self) -> None:
        """Update banner text with current language."""
        self.text_label.setText(_t("catalog.read_only_banner"))

    def refresh_visibility(self) -> bool:
        """Update visibility based on catalog_is_read_only(). Returns True if read-only."""
        is_ro = catalog_is_read_only()
        self.setVisible(is_ro)
        return is_ro
