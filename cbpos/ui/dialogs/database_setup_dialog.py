import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from cbpos.i18n import _t

logger = logging.getLogger(__name__)


class DatabaseSetupDialog(QDialog):
    """First-run dialog to choose between empty or demo database."""

    CHOICE_EMPTY = "empty"
    CHOICE_DEMO = "demo"

    def __init__(self, parent=None):
        """Initialize the dialog with the empty-database and demo-database option cards."""
        super().__init__(parent)
        self.setWindowTitle(_t("db_setup.title"))
        self.setMinimumSize(520, 380)
        self.resize(520, 380)
        self.setObjectName("DatabaseSetupDialog")
        self.choice = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(15)

        # Title
        lbl_title = QLabel(_t("db_setup.heading"))
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setObjectName("WizardTitle")
        layout.addWidget(lbl_title)

        # Description
        lbl_desc = QLabel(_t("db_setup.description"))
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        lbl_desc.setProperty("class", "muted")
        layout.addWidget(lbl_desc)

        layout.addSpacing(10)

        # Two option cards side by side
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)

        # --- Empty Database Card ---
        empty_card = QFrame()
        empty_card.setObjectName("SetupCard")
        empty_layout = QVBoxLayout(empty_card)
        empty_layout.setContentsMargins(15, 15, 15, 15)
        empty_layout.setSpacing(8)

        lbl_empty_icon = QLabel(_t("db_setup.empty_icon"))
        lbl_empty_icon.setObjectName("SetupCardIcon")
        lbl_empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(lbl_empty_icon)

        lbl_empty_title = QLabel(_t("db_setup.empty_title"))
        lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_empty_title.setProperty("class", "bold")
        empty_layout.addWidget(lbl_empty_title)

        lbl_empty_desc = QLabel(_t("db_setup.empty_desc"))
        lbl_empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_empty_desc.setWordWrap(True)
        lbl_empty_desc.setProperty("class", "muted")
        empty_layout.addWidget(lbl_empty_desc)

        empty_layout.addStretch()

        btn_empty = QPushButton(_t("db_setup.btn_empty"))
        btn_empty.setObjectName("BtnSave")
        btn_empty.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_empty.clicked.connect(self._choose_empty)
        empty_layout.addWidget(btn_empty)

        cards_layout.addWidget(empty_card)

        # --- Demo Database Card ---
        demo_card = QFrame()
        demo_card.setObjectName("SetupCard")
        demo_layout = QVBoxLayout(demo_card)
        demo_layout.setContentsMargins(15, 15, 15, 15)
        demo_layout.setSpacing(8)

        lbl_demo_icon = QLabel(_t("db_setup.demo_icon"))
        lbl_demo_icon.setObjectName("SetupCardIcon")
        lbl_demo_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        demo_layout.addWidget(lbl_demo_icon)

        lbl_demo_title = QLabel(_t("db_setup.demo_title"))
        lbl_demo_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_demo_title.setProperty("class", "bold")
        demo_layout.addWidget(lbl_demo_title)

        lbl_demo_desc = QLabel(_t("db_setup.demo_desc"))
        lbl_demo_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_demo_desc.setWordWrap(True)
        lbl_demo_desc.setProperty("class", "muted")
        demo_layout.addWidget(lbl_demo_desc)

        demo_layout.addStretch()

        btn_demo = QPushButton(_t("db_setup.btn_demo"))
        btn_demo.setObjectName("BtnSave")
        btn_demo.setProperty("class", "accent")
        btn_demo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_demo.clicked.connect(self._choose_demo)
        demo_layout.addWidget(btn_demo)

        cards_layout.addWidget(demo_card)

        layout.addLayout(cards_layout)
        layout.addStretch()

    def _choose_empty(self) -> None:
        """User chose Start Fresh."""
        self.choice = self.CHOICE_EMPTY
        self.accept()

    def _choose_demo(self) -> None:
        """User chose Demo Data."""
        self.choice = self.CHOICE_DEMO
        self.accept()

    def _set_loading(self, text: str) -> None:
        """Show loading state."""
        self.setEnabled(False)
        self.setWindowTitle(text)
        QApplication.processEvents()
