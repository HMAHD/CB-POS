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
    def __init__(self, shift_id, parent=None):
        super().__init__(parent)
        self.shift_id = shift_id
        self.shift_service = ShiftService()
        self.counted_cash = Decimal(0)
        self.summary = None

        self.setWindowTitle("Close Shift")
        self.setFixedSize(800, 600)
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        self.lbl_step = QLabel("Step 1: Count Cash")
        self.lbl_step.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #00BCEB;"
        )
        layout.addWidget(self.lbl_step)

        # Stacked Widget (Wizard)
        self.stack = QStackedWidget()

        # --- Step 1: Cash Count ---
        self.page_count = QWidget()
        count_layout = QVBoxLayout(self.page_count)

        self.denomination_widget = DenominationWidget()
        self.denomination_widget.total_changed.connect(self.update_counted_cash)
        count_layout.addWidget(self.denomination_widget)

        self.stack.addWidget(self.page_count)

        # --- Step 2: Review ---
        self.page_review = QWidget()
        review_layout = QVBoxLayout(self.page_review)

        self.lbl_expected = QLabel("Expected: 0.00")
        self.lbl_actual = QLabel("Actual: 0.00")
        self.lbl_variance = QLabel("Variance: 0.00")

        style = "font-size: 20px; font-weight: bold;"
        self.lbl_expected.setStyleSheet(style)
        self.lbl_actual.setStyleSheet(style)
        self.lbl_variance.setStyleSheet(style)

        review_layout.addWidget(self.lbl_expected)
        review_layout.addWidget(self.lbl_actual)
        review_layout.addWidget(self.lbl_variance)

        review_layout.addWidget(QLabel("Reason for Variance (Required if not 0):"))
        self.txt_reason = QTextEdit()
        self.txt_reason.setPlaceholderText("Enter reason for discrepancy...")
        review_layout.addWidget(self.txt_reason)

        self.stack.addWidget(self.page_review)

        layout.addWidget(self.stack)

        # Footer Buttons
        btn_layout = QHBoxLayout()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_next = QPushButton("Next")
        self.btn_next.setStyleSheet(
            "background-color: #007ACC; color: white; font-weight: bold; padding: 10px;"
        )
        self.btn_next.clicked.connect(self.next_step)

        self.btn_back = QPushButton("Back")
        self.btn_back.setEnabled(False)
        self.btn_back.clicked.connect(self.prev_step)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_back)
        btn_layout.addWidget(self.btn_next)

        layout.addLayout(btn_layout)

    def load_data(self):
        try:
            self.summary = self.shift_service.get_shift_summary(self.shift_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.reject()

    def update_counted_cash(self, total):
        self.counted_cash = total

    def next_step(self):
        current = self.stack.currentIndex()

        if current == 0:
            # Move to Review
            self.stack.setCurrentIndex(1)
            self.btn_back.setEnabled(True)
            self.btn_next.setText("Close Shift & Print")
            self.btn_next.setStyleSheet(
                "background-color: #39FF14; color: black; font-weight: bold; padding: 10px;"
            )
            self.lbl_step.setText("Step 2: Review & Close")

            # Update Review Data
            expected = self.summary["expected_cash"]
            variance = self.counted_cash - expected

            self.lbl_expected.setText("Expected: {:,.2f}".format(expected))
            self.lbl_actual.setText("Actual: {:,.2f}".format(self.counted_cash))
            self.lbl_variance.setText("Variance: {:,.2f}".format(variance))

            if variance != 0:
                self.lbl_variance.setStyleSheet(
                    "font-size: 20px; font-weight: bold; color: #FF4136;"
                )
            else:
                self.lbl_variance.setStyleSheet(
                    "font-size: 20px; font-weight: bold; color: #39FF14;"
                )

        elif current == 1:
            # Close Shift
            self.close_shift()

    def prev_step(self):
        current = self.stack.currentIndex()
        if current == 1:
            self.stack.setCurrentIndex(0)
            self.btn_back.setEnabled(False)
            self.btn_next.setText("Next")
            self.btn_next.setStyleSheet(
                "background-color: #007ACC; color: white; font-weight: bold; padding: 10px;"
            )
            self.lbl_step.setText("Step 1: Count Cash")

    def close_shift(self):
        expected = self.summary["expected_cash"]
        variance = self.counted_cash - expected
        reason = self.txt_reason.toPlainText().strip()

        if variance != 0 and not reason:
            QMessageBox.warning(
                self, "Validation", "Please provide a reason for the variance."
            )
            return

        try:
            # Close Shift
            final_summary = self.shift_service.close_shift(
                self.shift_id, self.counted_cash, reason
            )

            # Print Z-Report
            report_text = ReceiptService.print_z_report(final_summary)
            # In a real app, we would send this to the printer
            # TransactionService.print_receipt(report_text) # Assuming this exists or similar
            print(report_text)  # For debug

            QMessageBox.information(self, "Success", "Shift Closed Successfully!")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to close shift: {str(e)}")
