"""Base class for settings pages with standardized tab-based layout."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)

# Dynamic property holding a section header's i18n key (see _make_section_header).
_SECTION_TITLE_KEY = "i18n_key"


class SettingsPage(QWidget):
    """Base class for settings pages with standardized tab-based layout."""

    # Emitted after "Reset to Defaults" has written this page's defaults, so
    # the Settings view can treat them as saved (no stale unsaved marker).
    defaults_restored = pyqtSignal()

    def __init__(self):
        """Build the page UI by calling init_ui()."""
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize the UI. Override in subclasses."""

    def load(self, settings: dict):
        """Load settings into UI. Override in subclasses."""

    def save(self) -> dict:
        """Return a dictionary of settings to save. Override in subclasses."""
        return {}

    def validate(self) -> None:
        """Raise ValueError with a translated message if the page holds invalid input."""

    def save_warnings(self) -> list[str]:
        """Return non-blocking warnings to confirm before saving. Override in subclasses.

        Unlike a ValueError from validate(), these let the user choose to save anyway.
        save() itself must stay side-effect free -- it also backs the
        unsaved-changes snapshot and the per-page reset.
        """
        return []

    def _create_page_layout(self, title_text: str, subtitle_text: str) -> tuple[QVBoxLayout, QTabWidget]:
        """Creates the standard page layout: title + subtitle + tab widget.

        Returns:
            tuple: (main_layout, tab_widget)
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        self._page_title = QLabel(title_text)
        self._page_title.setProperty("class", "dialog-title")
        title_row.addWidget(self._page_title, 1)
        title_row.addWidget(self._make_reset_defaults_button())
        layout.addLayout(title_row)

        self._page_subtitle = QLabel(subtitle_text)
        self._page_subtitle.setProperty("class", "muted")
        layout.addWidget(self._page_subtitle)

        tabs = QTabWidget()
        # Native styles (e.g. Windows) elide tab labels with "..." once the
        # bar is narrower than its tabs' natural width -- ElideNone plus the
        # scroll buttons QTabBar already enables by default keeps every
        # label fully readable instead of silently truncating it (#321).
        tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        # A single tab (e.g. Documents -> "Numbering") implies hidden
        # content; auto-hide shows the bar only once a page has 2+ tabs,
        # and keeps tracking it as pages add their tabs after this (#571).
        tabs.setTabBarAutoHide(True)
        layout.addWidget(tabs, 1)

        return layout, tabs

    def _build_form_tab(self) -> tuple[QWidget, QFormLayout]:
        """Creates a tab widget with a scrollable form layout inside.

        Returns:
            tuple: (tab_widget, form_layout)
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("SettingsScrollArea")
        tab_layout.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("SettingsScrollInner")
        form = QFormLayout(inner)
        form.setContentsMargins(16, 20, 16, 20)
        form.setVerticalSpacing(15)
        form.setHorizontalSpacing(20)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        scroll.setWidget(inner)
        # Hover + wheel must scroll this form, not change a spin box/combo under the cursor (#598)
        install_wheel_guard(inner)

        return tab, form

    def _build_vbox_tab(self) -> tuple[QWidget, QVBoxLayout]:
        """Creates a tab widget with a scrollable vertical layout inside.

        Returns:
            tuple: (tab_widget, vbox_layout)
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("SettingsScrollArea")
        tab_layout.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("SettingsScrollInner")
        vbox = QVBoxLayout(inner)
        vbox.setContentsMargins(16, 20, 16, 20)
        vbox.setSpacing(16)
        vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(inner)
        install_wheel_guard(inner)  # see _build_form_tab (#598)

        return tab, vbox

    def configure_form_layout(self, form_layout: QFormLayout) -> None:
        """Applies standard configuration to a QFormLayout."""
        form_layout.setVerticalSpacing(15)
        form_layout.setHorizontalSpacing(20)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

    def _make_reset_defaults_button(self) -> QPushButton:
        """Create the per-page 'Reset to Defaults' button, wired to `_reset_to_defaults`."""
        self.btn_reset_defaults = QPushButton()
        self.btn_reset_defaults.setObjectName("BtnResetDefaults")
        self.btn_reset_defaults.setProperty("class", "secondary")
        self.btn_reset_defaults.clicked.connect(self._reset_to_defaults)
        return self.btn_reset_defaults

    def _reset_to_defaults(self) -> None:
        """Reset this page's own settings keys to their defaults, after confirmation.

        Scoped to only the keys this page's own `save()` returns -- resetting
        Hardware never touches Tax, resetting Tax never touches Shop Info, etc.
        (#425: per-section reset, not one all-or-nothing wipe).
        """
        from cbpos.core.services.config_service import ConfigService

        reply = QMessageBox.question(
            self,
            _t("settings.reset_defaults_title"),
            _t("settings.reset_defaults_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        page_keys = self.save().keys()
        defaults = {k: ConfigService.DEFAULTS[k] for k in page_keys if k in ConfigService.DEFAULTS}
        self.load(defaults)
        ConfigService.update_all(defaults)
        self.defaults_restored.emit()

        QMessageBox.information(self, _t("common.success"), _t("settings.reset_defaults_done"))

    @staticmethod
    def _make_section_header(title_key: str) -> QWidget:
        """Create a styled section header: the title with a full-width divider under it.

        Takes the i18n key, not translated text: the key is kept on the title
        label so ``_retranslate_section_headers`` can follow a live language
        switch (#739).
        The line sits below the title, not beside it -- on the same row it ran
        through the text's mid-height and read as a strike-through (#617).
        Use with ``form.addRow(header)`` (single-arg overload so it spans
        both columns).
        """
        container = QWidget()
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 10, 0, 2)
        col.setSpacing(4)

        lbl = QLabel(_t(title_key))
        lbl.setObjectName("SettingsSectionTitle")
        lbl.setProperty(_SECTION_TITLE_KEY, title_key)
        col.addWidget(lbl)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("SettingsSectionLine")
        col.addWidget(line)

        return container

    def _retranslate_section_headers(self) -> None:
        """Re-apply the current language to every section header on this page (#739)."""
        for lbl in self.findChildren(QLabel, "SettingsSectionTitle"):
            key = lbl.property(_SECTION_TITLE_KEY)
            if key:
                lbl.setText(_t(key))

    def equalize_form_labels(self, container: QWidget | None = None) -> None:
        """Ensure all QFormLayout label widgets in container (or this page) have identical width.

        Collects all non-empty QLabel widgets acting as row labels across all
        QFormLayouts, calculates the maximum intrinsic sizeHint width, and sets
        setFixedWidth(max_width) on each. This guarantees that all input fields
        start at the exact same X coordinate on the page regardless of how many
        sections or separate forms the page is composed of (#573).
        """
        target = container or self
        forms = target.findChildren(QFormLayout)
        if not forms:
            return

        labels: list[QLabel] = []
        for form in forms:
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                if item and item.widget() and isinstance(item.widget(), QLabel):
                    lbl = item.widget()
                    if lbl.text().strip():
                        labels.append(lbl)

        if not labels:
            return

        for lbl in labels:
            lbl.setMinimumWidth(0)
            lbl.setMaximumWidth(16777215)

        max_w = max(lbl.sizeHint().width() for lbl in labels)
        for lbl in labels:
            lbl.setFixedWidth(max_w)


__all__ = ["_SECTION_TITLE_KEY", "SettingsPage"]
