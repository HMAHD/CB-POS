"""About, Help, Feedback and Legal Dialog for CB POS."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cbpos.config import Config
from cbpos.core.constants.links import (
    get_docs_url,
    get_report_bug_url,
    get_source_url,
    get_suggest_feature_url,
    get_website_url,
    open_external_url,
)
from cbpos.core.services.theme_service import ThemeService
from cbpos.i18n import _t
from cbpos.ui.dialogs.text_viewer_dialog import TextViewerDialog
from cbpos.ui.dialogs.update_dialog import check_for_updates_async
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.dialog_footer import make_close_footer

logger = logging.getLogger(__name__)


class AboutDialog(QDialog):
    """About dialog providing branding, documentation, feedback, updates, and legal notices."""

    MIN_TOUCH_TARGET = 44

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AboutDialog")
        self.setWindowTitle(_t("about.title"))
        self.setMinimumSize(480, 560)
        self.resize(520, 680)

        self._init_ui()
        self._setup_tab_order()

    def _init_ui(self) -> None:
        """Construct the dialog layout with scrollable content and fixed close footer."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Scroll Area for small-screen safety (1024x768 and expanded text)
        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("AboutScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("AboutContainer")
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(24, 24, 24, 20)
        content_layout.setSpacing(16)

        # ── 1. Centred Logo & Branding ───────────────────────────
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.setSpacing(8)

        self.lbl_logo = QLabel()
        self.lbl_logo.setObjectName("AboutLogo")
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = ThemeService.get_logo_path()
        if Path(logo_path).exists():
            pix = QPixmap(logo_path)
            # Scale logo preserving aspect ratio
            scaled_pix = pix.scaledToWidth(180, Qt.TransformationMode.SmoothTransformation)
            self.lbl_logo.setPixmap(scaled_pix)
        header_layout.addWidget(self.lbl_logo)

        self.lbl_app_name = QLabel(Config.APP_NAME)
        self.lbl_app_name.setObjectName("AboutAppName")
        self.lbl_app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_app_name.setProperty("class", "dialog-title")
        header_layout.addWidget(self.lbl_app_name)

        # Build date / version
        date_display = Config.BUILD_DATE if Config.BUILD_DATE else _t("about.dev_build")
        version_text = _t("about.version", version=Config.VERSION, date=date_display)
        self.lbl_version = QLabel(version_text)
        self.lbl_version.setObjectName("AboutVersion")
        self.lbl_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_version.setProperty("class", "muted")
        header_layout.addWidget(self.lbl_version)

        # Clickable company link
        self.btn_company = QPushButton("Ceylon Byte (Pvt) Ltd · ceybyte.com")
        self.btn_company.setObjectName("AboutCompanyBtn")
        self.btn_company.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_company.setFlat(True)
        self.btn_company.clicked.connect(self._on_open_website)
        header_layout.addWidget(self.btn_company)

        content_layout.addLayout(header_layout)

        # ── 2. Get Help Section ───────────────────────────────────
        content_layout.addWidget(self._make_section_title(_t("about.help_section")))

        help_layout = QVBoxLayout()
        help_layout.setSpacing(10)

        # Row 1: User Guide & Check for Updates
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.btn_user_guide = self._make_action_button(
            text=_t("about.user_guide"),
            icon_name="fa5s.book-open",
            primary=True,
            on_click=self._on_open_user_guide,
        )
        self.btn_check_updates = self._make_action_button(
            text=_t("about.check_updates"),
            icon_name="fa5s.sync-alt",
            primary=True,
            on_click=self._on_check_updates,
        )
        row1.addWidget(self.btn_user_guide)
        row1.addWidget(self.btn_check_updates)
        help_layout.addLayout(row1)

        # Row 2: Report a Problem & Suggest a Feature
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.btn_report_problem = self._make_action_button(
            text=_t("about.report_problem"),
            icon_name="fa5s.bug",
            primary=False,
            on_click=self._on_open_report_problem,
        )
        self.btn_suggest_feature = self._make_action_button(
            text=_t("about.suggest_feature"),
            icon_name="fa5s.lightbulb",
            primary=False,
            on_click=self._on_open_suggest_feature,
        )
        row2.addWidget(self.btn_report_problem)
        row2.addWidget(self.btn_suggest_feature)
        help_layout.addLayout(row2)

        content_layout.addLayout(help_layout)

        # Helper text regarding feedback privacy
        self.lbl_feedback_helper = QLabel(_t("about.feedback_helper"))
        self.lbl_feedback_helper.setObjectName("AboutFeedbackHelper")
        self.lbl_feedback_helper.setWordWrap(True)
        self.lbl_feedback_helper.setProperty("class", "muted")
        content_layout.addWidget(self.lbl_feedback_helper)

        # ── 3. Legal Section ──────────────────────────────────────
        content_layout.addWidget(self._make_section_title(_t("about.legal_section")))

        legal_layout = QVBoxLayout()
        legal_layout.setSpacing(10)

        # Row 1: Licence & Privacy Notice
        legal_row1 = QHBoxLayout()
        legal_row1.setSpacing(10)
        self.btn_licence = self._make_action_button(
            text=_t("about.licence"),
            icon_name="fa5s.balance-scale",
            primary=False,
            on_click=self._on_open_licence,
        )
        self.btn_privacy = self._make_action_button(
            text=_t("about.privacy"),
            icon_name="fa5s.user-shield",
            primary=False,
            on_click=self._on_open_privacy,
        )
        legal_row1.addWidget(self.btn_licence)
        legal_row1.addWidget(self.btn_privacy)
        legal_layout.addLayout(legal_row1)

        # Row 2: Third-Party Notices & View Source Code
        legal_row2 = QHBoxLayout()
        legal_row2.setSpacing(10)
        self.btn_third_party = self._make_action_button(
            text=_t("about.third_party_notices"),
            icon_name="fa5s.file-alt",
            primary=False,
            on_click=self._on_open_third_party,
        )
        self.btn_view_source = self._make_action_button(
            text=_t("about.view_source"),
            icon_name="fa5b.github",
            primary=False,
            on_click=self._on_view_source,
        )
        legal_row2.addWidget(self.btn_third_party)
        legal_row2.addWidget(self.btn_view_source)
        legal_layout.addLayout(legal_row2)

        content_layout.addLayout(legal_layout)

        content_layout.addStretch(1)
        scroll_area.setWidget(container)
        root_layout.addWidget(scroll_area, 1)

        # ── 4. Standard Close Footer ──────────────────────────────
        footer_widget = QWidget()
        footer_widget.setObjectName("AboutFooter")
        footer_box = QVBoxLayout(footer_widget)
        footer_box.setContentsMargins(20, 10, 20, 14)
        footer_layout, self.btn_close = make_close_footer(on_close=self.accept)
        self.btn_close.setMinimumHeight(self.MIN_TOUCH_TARGET)
        footer_box.addLayout(footer_layout)
        root_layout.addWidget(footer_widget)

    def _setup_tab_order(self) -> None:
        """Establish clean keyboard Tab order from top to bottom."""
        widgets = [
            self.btn_company,
            self.btn_user_guide,
            self.btn_check_updates,
            self.btn_report_problem,
            self.btn_suggest_feature,
            self.btn_licence,
            self.btn_privacy,
            self.btn_third_party,
            self.btn_view_source,
            self.btn_close,
        ]
        for i in range(len(widgets) - 1):
            self.setTabOrder(widgets[i], widgets[i + 1])

    def _make_section_title(self, text: str) -> QLabel:
        """Create a styled section heading label."""
        lbl = QLabel(text)
        lbl.setProperty("class", "section-header")
        lbl.setContentsMargins(0, 8, 0, 2)
        return lbl

    def _make_action_button(
        self,
        text: str,
        icon_name: str,
        primary: bool,
        on_click,
    ) -> QPushButton:
        """Create a touch-friendly interactive button with icon."""
        btn = QPushButton(text)
        btn.setMinimumHeight(self.MIN_TOUCH_TARGET)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        icon_color = "#00BCEB" if primary else ThemeService.get_icon_color()
        btn.setIcon(Icons.get(icon_name, icon_color))
        btn.setIconSize(QSize(18, 18))

        if primary:
            btn.setProperty("class", "primary")
        else:
            btn.setProperty("class", "secondary")

        btn.clicked.connect(on_click)
        return btn

    # ── Action Handlers ───────────────────────────────────────────

    def _on_open_website(self) -> None:
        open_external_url(get_website_url(), parent=self)

    def _on_open_user_guide(self) -> None:
        open_external_url(get_docs_url(), parent=self)

    def _on_open_report_problem(self) -> None:
        open_external_url(get_report_bug_url(), parent=self)

    def _on_open_suggest_feature(self) -> None:
        open_external_url(get_suggest_feature_url(), parent=self)

    def _on_check_updates(self) -> None:
        check_for_updates_async(parent=self, silent=False, button=self.btn_check_updates)

    def _on_open_licence(self) -> None:
        TextViewerDialog.show_document(
            title=_t("about.licence"),
            filename="LICENSE",
            parent=self,
        )

    def _on_open_privacy(self) -> None:
        TextViewerDialog.show_document(
            title=_t("about.privacy"),
            filename="PRIVACY.md",
            parent=self,
        )

    def _on_open_third_party(self) -> None:
        TextViewerDialog.show_document(
            title=_t("about.third_party_notices"),
            filename="THIRD_PARTY_NOTICES.txt",
            parent=self,
        )

    def _on_view_source(self) -> None:
        open_external_url(get_source_url(), parent=self)
