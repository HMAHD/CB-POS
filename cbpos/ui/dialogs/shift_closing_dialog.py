from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.receipt_service import ReceiptService
from cbpos.core.services.shift_service import ShiftService
from cbpos.i18n import _t
from cbpos.ui.widgets.denomination_widget import DenominationWidget
from cbpos.ui.workers import BackupWorker


class ShiftClosingDialog(QDialog):
    """Wizard that guides the user through end-of-day cash reconciliation."""

    REASON_CATEGORIES = ["TILL_ERROR", "MISCOUNTED", "UNEXPLAINED_SHORTAGE", "OTHER"]

    def __init__(self, shift_id: int, parent=None):
        """Build the dialog and load the sales/cash summary for `shift_id`."""
        super().__init__(parent)
        self.shift_id = shift_id
        self.shift_service = ShiftService()
        self.counted_cash = Decimal(0)
        self.summary = None

        self.setWindowTitle(_t("shift_closing.title"))
        self.setFixedSize(800, 600)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        self.lbl_step = QLabel(_t("shift_closing.step1_count"))
        self.lbl_step.setObjectName("stepHeader")
        layout.addWidget(self.lbl_step)

        # Stacked wizard pages
        self.stack = QStackedWidget()
        # ---- Page 1 - cash count -----------------------------------------
        self.page_count = QWidget()
        count_layout = QVBoxLayout(self.page_count)
        self.denomination_widget = DenominationWidget()
        self.denomination_widget.total_changed.connect(self._update_counted_cash)
        count_layout.addWidget(self.denomination_widget)
        self.stack.addWidget(self.page_count)

        # ---- Page 2 - review ---------------------------------------------
        self.page_review = QWidget()
        review_layout = QVBoxLayout(self.page_review)

        self.lbl_expected = QLabel(_t("shift_closing.expected", amount="0.00"))
        self.lbl_actual = QLabel(_t("shift_closing.actual", amount="0.00"))
        self.lbl_variance = QLabel(_t("shift_closing.variance", amount="0.00"))
        for lbl in (self.lbl_expected, self.lbl_actual, self.lbl_variance):
            lbl.setObjectName("reviewLabel")
            review_layout.addWidget(lbl)

        review_layout.addWidget(QLabel(_t("shift_closing.variance_reason_label")))

        self.combo_reason_category = QComboBox()
        for category in self.REASON_CATEGORIES:
            self.combo_reason_category.addItem(_t(f"shift_closing.reason_category.{category.lower()}"), category)
        review_layout.addWidget(self.combo_reason_category)

        self.txt_reason = QTextEdit()
        self.txt_reason.setPlaceholderText(_t("shift_closing.reason_placeholder"))
        review_layout.addWidget(self.txt_reason)

        self.stack.addWidget(self.page_review)

        layout.addWidget(self.stack)

        # Footer buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton(_t("common.cancel"))
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_back = QPushButton(_t("common.back"))
        self.btn_back.setEnabled(False)
        self.btn_back.clicked.connect(self._prev_step)

        self.btn_next = QPushButton(_t("common.next"))
        self.btn_next.clicked.connect(self._next_step)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_back)
        btn_layout.addWidget(self.btn_next)

        layout.addLayout(btn_layout)

    def _load_data(self):
        try:
            self.summary = self.shift_service.get_shift_summary(self.shift_id)
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))
            self.reject()

    def _update_counted_cash(self, total: Decimal):
        self.counted_cash = total

    def _next_step(self):
        current = self.stack.currentIndex()
        if current == 0:  # move to review page
            self.stack.setCurrentIndex(1)
            self.btn_back.setEnabled(True)
            self.btn_next.setText(_t("shift_closing.close_and_print"))
            self.lbl_step.setText(_t("shift_closing.step2_review"))

            # ---- Populate review fields (safe .get()) --------------------
            expected = self.summary.get("expected_cash", Decimal(0))
            variance = self.counted_cash - expected

            self.lbl_expected.setText(_t("shift_closing.expected", amount=f"{expected:,.2f}"))
            self.lbl_actual.setText(_t("shift_closing.actual", amount=f"{self.counted_cash:,.2f}"))
            self.lbl_variance.setText(_t("shift_closing.variance", amount=f"{variance:,.2f}"))

            # colour handling via property (style sheet defined in theme.qss)
            self.lbl_variance.setProperty(
                "variance",
                "negative" if variance < 0 else "positive",
            )
            self.lbl_variance.style().unpolish(self.lbl_variance)
            self.lbl_variance.style().polish(self.lbl_variance)

        elif current == 1:  # close shift
            self._close_shift()

    def _prev_step(self):
        self.stack.setCurrentIndex(0)
        self.btn_back.setEnabled(False)
        self.btn_next.setText(_t("common.next"))
        self.lbl_step.setText(_t("shift_closing.step1_count"))

    def _close_shift(self):
        variance = self.counted_cash - self.summary.get("expected_cash", Decimal(0))
        reason = self.txt_reason.toPlainText().strip()

        if variance != 0 and not reason:
            QMessageBox.warning(
                self,
                _t("common.warning"),
                _t("shift_closing.reason_required"),
            )
            return

        reason_category = self.combo_reason_category.currentData() if variance != 0 else None

        try:
            final_summary = self.shift_service.close_shift(self.shift_id, self.counted_cash, reason, reason_category)
            # Generate Z-Report (printing is delegated to hardware layer)
            ReceiptService.print_z_report(final_summary)

            QMessageBox.information(self, _t("common.success"), _t("shift_closing.closed_success"))

            # Offer backup after successful shift close.
            # If user starts a backup, accept() is deferred until it finishes.
            if not self._offer_backup():
                self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), _t("shift_closing.close_failed", error=str(e)))

    def _offer_backup(self) -> bool:
        """Prompt user to create a backup after closing the shift.

        Returns:
            True if an async backup was started (caller should NOT call accept()),
            False if no backup is running (caller should call accept()).
        """
        reply = QMessageBox.question(
            self,
            _t("shift_closing.backup"),
            _t("shift_closing.backup_prompt"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False

        from PyQt6.QtWidgets import QFileDialog

        from cbpos.core.services.backup_service import BackupService
        from cbpos.ui.dialogs.backup_password_dialog import ensure_backup_password

        password = ensure_backup_password(self)
        if not password:
            return False

        default_dir = BackupService.get_default_backup_dir()
        chosen_dir = QFileDialog.getExistingDirectory(self, _t("shift_closing.choose_backup_location"), default_dir)
        if not chosen_dir:
            return False

        self.btn_cancel.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.btn_next.setText(_t("shift_closing.creating_backup"))
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))

        self._backup_worker = BackupWorker(chosen_dir, password)
        self._backup_worker.result.connect(self._on_backup_finished)
        self._backup_worker.error.connect(self._on_backup_error)
        self._backup_worker.start()
        return True

    def _on_backup_finished(self, backup_path: str) -> None:
        QApplication.restoreOverrideCursor()
        QMessageBox.information(
            self,
            _t("shift_closing.backup_complete"),
            _t("shift_closing.backup_saved", path=backup_path),
        )
        self.accept()

    def _on_backup_error(self, error_msg: str) -> None:
        QApplication.restoreOverrideCursor()
        QMessageBox.critical(self, _t("shift_closing.backup_failed"), _t("shift_closing.backup_error", error=error_msg))
        self.accept()
