"""Notice card shown on Data Safety tabs when CB POS runs in network database mode."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from cbpos.core.services.backup_service import BackupService
from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons


class NetworkModeNoticeCard(QFrame):
    """Notice card explaining that backups and maintenance are handled on the server."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NetworkCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build_ui()
        self.retranslate_ui()
        ThemeService.register_theme_callback(self._update_icon, owner=self)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._icon_lbl = QLabel()
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self._update_icon()
        layout.addWidget(self._icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)

        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("CardTitle")
        text_layout.addWidget(self.lbl_title)

        self.lbl_body = QLabel()
        self.lbl_body.setProperty("class", "muted")
        self.lbl_body.setWordWrap(True)
        self.lbl_body.setStyleSheet("font-size: 13px; line-height: 1.4;")
        text_layout.addWidget(self.lbl_body)

        layout.addLayout(text_layout, 1)

    def _update_icon(self) -> None:
        color = ThemeService.get_accent_color()
        self._icon_lbl.setPixmap(Icons.get(Icons.INFO, color).pixmap(32, 32))

    def retranslate_ui(self) -> None:
        """Update translatable text with current language and server host."""
        host = BackupService.network_host()
        self.lbl_title.setText(_t("data_safety.network_mode_title"))
        self.lbl_body.setText(_t("data_safety.network_mode_body", host=host))
