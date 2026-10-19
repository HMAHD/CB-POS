import logging
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout

from cbpos.core.services.shift_service import ShiftService
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.widgets.denomination_widget import DenominationWidget

logger = logging.getLogger(__name__)


class StartShiftDialog(QDialog):
    """Mandatory, non-dismissable dialog collecting the opening cash float via blind count.

    Shown right after login whenever the user has no open shift. Cannot be
    closed or cancelled -- a shift must be started before reaching the Sales
    screen, so every shift has a known starting point for the closing
    variance report.
    """

    def __init__(self, user_id: int, parent=None):
        """Build the dialog for `user_id` and load the starting denomination widget."""
        super().__init__(parent)
        self.user_id = user_id
        self.starting_cash = Decimal(0)
        self.shift_service = ShiftService()

        self.setWindowTitle(_t("start_shift.title"))
        self.setMinimumSize(600, 550)
        self.resize(600, 550)
        # No close button -- starting a shift is mandatory, not optional.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        self.lbl_header = QLabel(_t("start_shift.header"))
        self.lbl_header.setProperty("class", "SectionHeader")
        self.lbl_header.setWordWrap(True)
        layout.addWidget(self.lbl_header)

        self.denomination_widget = DenominationWidget()
        self.denomination_widget.total_changed.connect(self._update_starting_cash)
        layout.addWidget(self.denomination_widget)

        self.btn_start = QPushButton(_t("start_shift.start_button"))
        self.btn_start.setProperty("class", "primary")
        self.btn_start.setMinimumHeight(44)
        self.btn_start.clicked.connect(self._start_shift)
        layout.addWidget(self.btn_start)

    def _update_starting_cash(self, total: Decimal):
        self.starting_cash = total

    def _start_shift(self):
        try:
            self.shift_service.start_shift(self.user_id, self.starting_cash)
            self.accept()
        except ValueError as e:
            logger.warning("Failed to start shift: %s", e, exc_info=True)
            QMessageBox.critical(self, _t("common.error"), translate_error(str(e)))
            self.accept()

    def closeEvent(self, event):
        """Ignore the window-close attempt -- starting a shift cannot be skipped."""
        event.ignore()

    def reject(self):
        """Ignore Escape/Alt+F4 -- starting a shift cannot be skipped."""
        return
