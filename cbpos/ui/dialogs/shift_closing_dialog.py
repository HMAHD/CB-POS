from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QWidget,
    QTextEdit,
    QMessageBox,
)
from decimal import Decimal
from cbpos.ui.widgets.denomination_widget import DenominationWidget
from cbpos.core.services.shift_service import ShiftService
from cbpos.core.services.receipt_service import ReceiptService


class ShiftClosingDialog(QDialog):
    """Wizard that guides the user through end-of-day cash reconciliation."""

    def __init__(self, shift_id: int, parent=None):
        super().__init__(parent)
        self.shift_id = shift_id
        self.shift_service = ShiftService()
        self.counted_cash = Decimal(0)
        self.summary = None

        self.setWindowTitle("Close Shift")
        self.setFixedSize(800, 600)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        self.lbl_step = QLabel("Step 1: Count Cash")
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

        self.lbl_expected = QLabel("Expected: 0.00")
        self.lbl_actual = QLabel("Actual: 0.00")
        self.lbl_variance = QLabel("Variance: 0.00")
        for lbl in (self.lbl_expected, self.lbl_actual, self.lbl_variance):
            lbl.setObjectName("reviewLabel")
            review_layout.addWidget(lbl)

        review_layout.addWidget(QLabel("Reason for Variance (required if not 0):"))
        self.txt_reason = QTextEdit()
        self.txt_reason.setPlaceholderText("Enter reason for discrepancy...")
        review_layout.addWidget(self.txt_reason)

        self.stack.addWidget(self.page_review)

        layout.addWidget(self.stack)

        # Footer buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_back = QPushButton("Back")
        self.btn_back.setEnabled(False)
        self.btn_back.clicked.connect(self._prev_step)

        self.btn_next = QPushButton("Next")
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
            QMessageBox.critical(self, "Error", str(e))
            self.reject()

    def _update_counted_cash(self, total: Decimal):
        self.counted_cash = total

    def _next_step(self):
        current = self.stack.currentIndex()
        if current == 0:  # move to review page
            self.stack.setCurrentIndex(1)
            self.btn_back.setEnabled(True)
            self.btn_next.setText("Close Shift & Print")
            self.lbl_step.setText("Step 2: Review & Close")

            # ---- Populate review fields (safe .get()) --------------------
            expected = self.summary.get("expected_cash", Decimal(0))
            variance = self.counted_cash - expected

            self.lbl_expected.setText("Expected: {:,.2f}".format(expected))
            self.lbl_actual.setText("Actual: {:,.2f}".format(self.counted_cash))
            self.lbl_variance.setText("Variance: {:,.2f}".format(variance))

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
        self.btn_next.setText("Next")
        self.lbl_step.setText("Step 1: Count Cash")

    def _close_shift(self):
        variance = self.counted_cash - self.summary.get("expected_cash", Decimal(0))
        reason = self.txt_reason.toPlainText().strip()

        if variance != 0 and not reason:
            QMessageBox.warning(
                self,
                "Validation",
                "Please provide a reason for the variance.",
            )
            return

        try:
            final_summary = self.shift_service.close_shift(self.shift_id, self.counted_cash, reason)
            # Generate Z-Report (printing is delegated to hardware layer)
            ReceiptService.print_z_report(final_summary)

            QMessageBox.information(self, "Success", "Shift closed and Z-Report generated.")

            # Offer backup after successful shift close
            self._offer_backup()

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to close shift: {e}")

    def _offer_backup(self) -> None:
        """Prompt user to create a backup after closing the shift."""
        reply = QMessageBox.question(
            self,
            "Backup",
            "Would you like to create a backup of the database?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from cbpos.core.services.backup_service import BackupService
        from PyQt6.QtWidgets import QFileDialog

        default_dir = BackupService.get_default_backup_dir()
        chosen_dir = QFileDialog.getExistingDirectory(self, "Choose Backup Location", default_dir)
        if not chosen_dir:
            return

        try:
            backup_path = BackupService.create_backup(chosen_dir)
            QMessageBox.information(self, "Backup Complete", f"Backup saved to:\n{backup_path}")
        except Exception as e:
            QMessageBox.critical(self, "Backup Failed", f"Backup failed: {e}")
