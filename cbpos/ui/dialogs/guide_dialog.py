"""
Reusable Guide Dialog Component.

Provides a structured, scrollable dialog for multi-step setup guides,
instructional walkthroughs, and consequential configuration help.
Guarantees responsive height capping (<= 85% of screen height) to prevent
content clipping on common POS displays (1366x768).
"""

from collections.abc import Sequence
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cbpos.i18n import _t


class GuideDialog(QDialog):
    """Reusable step-by-step guide dialog with scroll area, aligned step badges,

    and distinct warning card.
    """

    def __init__(
        self,
        title_key: str,
        steps: Sequence[tuple[str, str] | tuple[str | int, str, str] | dict[str, Any]],
        note_key: str | None = None,
        parent: QWidget | None = None,
        *,
        heading_key: str | None = None,
        close_key: str = "common.got_it",
        note_prefix_key: str | None = "common.important",
    ) -> None:
        super().__init__(parent)
        self.title_key = title_key
        self.heading_key = heading_key or title_key
        self.steps = steps
        self.note_key = note_key
        self.close_key = close_key
        self.note_prefix_key = note_prefix_key

        self.setWindowTitle(_t(self.title_key))
        self.setObjectName("GuideDialog")
        self._setup_geometry()
        self._init_ui()

    def _setup_geometry(self) -> None:
        """Cap dialog height to 85% of screen height and set responsive bounds."""
        parent_widget = self.parentWidget()
        screen = (
            parent_widget.screen()
            if parent_widget and hasattr(parent_widget, "screen") and parent_widget.screen()
            else None
        ) or QApplication.primaryScreen()

        if screen:
            geom = screen.availableGeometry()
            screen_h = geom.height()
            screen_w = geom.width()
        else:
            screen_h = 768
            screen_w = 1366

        # Cap height to at most 85% of available screen height
        max_h = max(360, min(650, int(screen_h * 0.85)))
        target_w = max(400, min(540, int(screen_w * 0.9)))

        self.setMinimumWidth(min(460, target_w))
        self.setMaximumWidth(max(target_w, 560))
        self.setMaximumHeight(max_h)
        self.resize(target_w, min(580, max_h))

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(14)

        # Dialog heading
        self.lbl_heading = QLabel(_t(self.heading_key))
        self.lbl_heading.setObjectName("GuideDialogTitle")
        self.lbl_heading.setProperty("class", "dialog-title")
        self.lbl_heading.setWordWrap(True)
        root_layout.addWidget(self.lbl_heading)

        # Scrollable container for steps and note
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setObjectName("GuideScrollArea")

        content_widget = QWidget()
        content_widget.setObjectName("GuideContentWidget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 2, 4, 2)
        content_layout.setSpacing(10)

        # Step cards
        self.step_frames: list[QFrame] = []
        for idx, step_item in enumerate(self.steps, start=1):
            frame = self._create_step_card(step_item, default_num=idx)
            self.step_frames.append(frame)
            content_layout.addWidget(frame)

        # Warning/Important Note (if provided)
        if self.note_key:
            self.note_card = self._create_note_card()
            content_layout.addWidget(self.note_card)
        else:
            self.note_card = None

        content_layout.addStretch()
        self.scroll_area.setWidget(content_widget)
        root_layout.addWidget(self.scroll_area, 1)

        # Pinned Footer (outside scroll area so button is always visible)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.addStretch()

        self.btn_close = QPushButton(_t(self.close_key))
        self.btn_close.setObjectName("BtnGuideClose")
        self.btn_close.setProperty("class", "primary")
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self.accept)
        footer_layout.addWidget(self.btn_close)

        root_layout.addLayout(footer_layout)

    def _create_step_card(
        self,
        step_item: tuple[str, str] | tuple[str | int, str, str] | dict[str, Any],
        default_num: int,
    ) -> QFrame:
        if isinstance(step_item, dict):
            num = str(step_item.get("number", default_num))
            heading_raw = step_item.get("title", step_item.get("heading", ""))
            detail_raw = step_item.get("detail", step_item.get("description", ""))
        elif isinstance(step_item, (tuple, list)):
            if len(step_item) == 2:
                num = str(default_num)
                heading_raw, detail_raw = step_item[0], step_item[1]
            elif len(step_item) >= 3:
                num = str(step_item[0])
                heading_raw, detail_raw = step_item[1], step_item[2]
            else:
                num = str(default_num)
                heading_raw = ""
                detail_raw = ""
        else:
            num = str(default_num)
            heading_raw = str(step_item)
            detail_raw = ""

        heading_text = _t(heading_raw) if isinstance(heading_raw, str) else str(heading_raw)
        detail_text = _t(detail_raw) if isinstance(detail_raw, str) else str(detail_raw)

        card = QFrame()
        card.setObjectName("GuideStep")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(12)

        # Badge: top-aligned with heading
        badge = QLabel(num)
        badge.setObjectName("GuideStepNum")
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

        # Text column: heading + description
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        lbl_head = QLabel(f"<b>{heading_text}</b>" if heading_text else "")
        lbl_head.setObjectName("GuideStepHeading")
        lbl_head.setProperty("class", "transparent")
        text_layout.addWidget(lbl_head)

        if detail_text:
            lbl_detail = QLabel(detail_text)
            lbl_detail.setObjectName("GuideStepDetail")
            lbl_detail.setWordWrap(True)
            lbl_detail.setProperty("class", "muted")
            text_layout.addWidget(lbl_detail)

        card_layout.addLayout(text_layout, 1)
        return card

    def _create_note_card(self) -> QLabel:
        note_body = _t(self.note_key) if self.note_key else ""
        if self.note_prefix_key:
            prefix = _t(self.note_prefix_key)
            text = f"<b>{prefix}:</b> {note_body}" if prefix else note_body
        else:
            text = note_body

        lbl_note = QLabel(text)
        lbl_note.setObjectName("GuideNote")
        lbl_note.setWordWrap(True)
        lbl_note.setProperty("class", "warning-hint")
        return lbl_note
