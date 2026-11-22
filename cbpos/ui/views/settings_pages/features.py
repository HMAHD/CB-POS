"""Features management settings page for toggling optional shop capabilities (#942)."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.constants.features import IMPLEMENTED_FEATURES, Features
from cbpos.core.services.feature_flags import FeatureFlags
from cbpos.core.utils.destroy_hooks import call_on_destroyed
from cbpos.core.utils.error_messages import translate_error
from cbpos.core.utils.terminal_guard import catalog_is_read_only
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.widgets.read_only_banner import ReadOnlyBanner

logger = logging.getLogger(__name__)

# Fixed display order for implemented feature cards
FEATURE_ORDER = [
    Features.WARRANTY,
    Features.CREDIT_BOOK,
    Features.SERIAL_TRACKING,
    Features.CHEQUES,
    Features.POWER_CUT_AUTOSAVE,
    Features.PRICE_BOARD,
    Features.UNIT_CONVERSION,
]


class FeaturesPage(QWidget):
    """Card-based settings page for toggling implemented feature flags."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FeaturesPage")
        self._user = None
        self._switches: dict[str, QCheckBox] = {}
        self._card_labels: dict[str, tuple[QLabel, QLabel]] = {}
        self._init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)
        call_on_destroyed(self, unregister_language_callback, self.retranslate_ui)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Read-only banner on till terminals (#869)
        self.read_only_banner = ReadOnlyBanner()
        layout.addWidget(self.read_only_banner)

        # Header
        self._title = QLabel()
        self._title.setProperty("class", "dialog-title")
        layout.addWidget(self._title)

        self._subtitle = QLabel()
        self._subtitle.setProperty("class", "muted")
        layout.addWidget(self._subtitle)

        # Cards for implemented features
        for flag in FEATURE_ORDER:
            if flag not in IMPLEMENTED_FEATURES:
                continue

            card = QFrame()
            card.setObjectName("FeatureCard")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            card_layout.setSpacing(16)

            text_layout = QVBoxLayout()
            text_layout.setSpacing(4)

            lbl_name = QLabel()
            lbl_name.setObjectName("FeatureName")
            name_font = lbl_name.font()
            name_font.setBold(True)
            name_font.setPointSize(name_font.pointSize() + 1)
            lbl_name.setFont(name_font)

            lbl_desc = QLabel()
            lbl_desc.setObjectName("FeatureDesc")
            lbl_desc.setProperty("class", "muted")
            lbl_desc.setWordWrap(True)

            text_layout.addWidget(lbl_name)
            text_layout.addWidget(lbl_desc)
            card_layout.addLayout(text_layout, 1)

            chk = QCheckBox()
            chk.setObjectName(f"Toggle_{flag}")
            chk.setCursor(Qt.CursorShape.PointingHandCursor)
            chk.setChecked(FeatureFlags.is_on(flag))
            chk.toggled.connect(lambda checked, f=flag, c=chk: self._on_feature_toggled(f, checked, c))
            card_layout.addWidget(chk, 0, Qt.AlignmentFlag.AlignVCenter)

            self._switches[flag] = chk
            self._card_labels[flag] = (lbl_name, lbl_desc)
            layout.addWidget(card)

        layout.addStretch()
        self.refresh_states()

    def showEvent(self, event) -> None:
        """Refresh feature flag checkbox states when the page is shown."""
        super().showEvent(event)
        self.refresh_states()

    def set_user(self, user) -> None:
        """Record the active user for audit logging."""
        self._user = user

    def _get_acting_user_id(self) -> int | None:
        if self._user is not None and hasattr(self._user, "id"):
            return self._user.id
        from cbpos.core.services.auth_service import AuthService

        current = AuthService.get_current_user()
        if current is not None and hasattr(current, "id"):
            return current.id
        return None

    def refresh_states(self) -> None:
        """Reload all feature flag states from FeatureFlags service and update read-only status."""
        is_ro = catalog_is_read_only()
        self.read_only_banner.refresh_visibility()
        ro_tip = _t("catalog.read_only_tooltip") if is_ro else ""

        for flag, chk in self._switches.items():
            chk.blockSignals(True)
            chk.setChecked(FeatureFlags.is_on(flag))
            chk.setEnabled(not is_ro)
            chk.setToolTip(ro_tip)
            chk.blockSignals(False)

    def _on_feature_toggled(self, flag: str, checked: bool, chk: QCheckBox) -> None:
        """Save the updated feature flag state."""
        try:
            user_id = self._get_acting_user_id()
            FeatureFlags.set(flag, checked, acting_user_id=user_id)
            logger.info("Feature %s toggled to %s by user %s", flag, checked, user_id)
        except Exception as e:
            logger.error("Failed to toggle feature %s: %s", flag, e)
            chk.blockSignals(True)
            chk.setChecked(not checked)
            chk.blockSignals(False)
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))

    def retranslate_ui(self) -> None:
        """Update translatable texts on the page."""
        self._title.setText(_t("features.title"))
        self._subtitle.setText(_t("features.subtitle"))
        self.read_only_banner.retranslate_ui()

        for flag, (lbl_name, lbl_desc) in self._card_labels.items():
            lbl_name.setText(_t(f"features.name.{flag}"))
            lbl_desc.setText(_t(f"features.desc.{flag}"))

        if catalog_is_read_only():
            for chk in self._switches.values():
                chk.setToolTip(_t("catalog.read_only_tooltip"))
