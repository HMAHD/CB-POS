import logging
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QTextEdit,
    QMessageBox,
    QGroupBox,
)
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.utils.formatters import format_currency
from cbpos.core.utils.permission_helper import check_permission_with_override

logger = logging.getLogger(__name__)


class RefundDialog(QDialog):
    """Dialog to search an original sale and process a full refund."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Process Refund")
        self.setMinimumSize(650, 500)
        self.setObjectName("RefundDialog")
        self.found_sale = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Search section
        search_layout = QHBoxLayout()
        lbl = QLabel("Receipt #:")
        lbl.setProperty("class", "bold")
        search_layout.addWidget(lbl)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter original receipt number...")
        self.search_input.returnPressed.connect(self.lookup_sale)
        search_layout.addWidget(self.search_input, 1)

        btn_lookup = QPushButton("Look Up")
        btn_lookup.setProperty("class", "primary")
        btn_lookup.clicked.connect(self.lookup_sale)
        search_layout.addWidget(btn_lookup)
        layout.addLayout(search_layout)

        # Sale details group
        self.details_group = QGroupBox("Original Sale Details")
        details_layout = QVBoxLayout(self.details_group)

        self.lbl_sale_info = QLabel("No sale loaded.")
        self.lbl_sale_info.setProperty("class", "transparent")
        details_layout.addWidget(self.lbl_sale_info)

        # Items table
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(4)
        self.items_table.setHorizontalHeaderLabels(["Product", "Qty", "Unit Price", "Subtotal"])
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.setAlternatingRowColors(True)
        details_layout.addWidget(self.items_table)

        layout.addWidget(self.details_group)

        # Reason
        lbl_reason = QLabel("Refund Reason (required):")
        lbl_reason.setProperty("class", "bold")
        layout.addWidget(lbl_reason)

        self.txt_reason = QTextEdit()
        self.txt_reason.setPlaceholderText("Enter reason for refund...")
        self.txt_reason.setMaximumHeight(80)
        layout.addWidget(self.txt_reason)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_refund = QPushButton("Process Refund")
        self.btn_refund.setProperty("class", "danger")
        self.btn_refund.setEnabled(False)
        self.btn_refund.clicked.connect(self.process_refund)
        btn_layout.addWidget(self.btn_refund)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def lookup_sale(self) -> None:
        """Look up original sale by document number."""
        search = self.search_input.text().strip()
        if not search:
            return

        from datetime import datetime, timedelta

        # Search in last 365 days
        to_dt = datetime.now()
        from_dt = to_dt - timedelta(days=365)

        results = TransactionService.get_sales_history(
            from_date=from_dt,
            to_date=to_dt,
            search_term=search,
            limit=1,
        )

        if not results:
            QMessageBox.warning(self, "Not Found", f"No sale found for '{search}'.")
            self.found_sale = None
            self.btn_refund.setEnabled(False)
            return

        sale = results[0]
        self.found_sale = sale

        # Display sale info
        customer_name = sale.customer.name if sale.customer else "Walk-in"
        date_str = sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "N/A"
        self.lbl_sale_info.setText(
            f"Receipt: {sale.document_number}  |  Date: {date_str}  |  "  # noqa: E222,E221
            f"Customer: {customer_name}  |  Total: {format_currency(sale.total_amount)}  |  "  # noqa: E222,E221
            f"Status: {sale.status}"
        )

        # Populate items table
        self.items_table.setRowCount(0)
        for item in sale.items:
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)

            product_name = item.product.name_en if item.product else "Unknown"
            self.items_table.setItem(row, 0, QTableWidgetItem(product_name))
            self.items_table.setItem(row, 1, QTableWidgetItem(str(item.qty)))
            self.items_table.setItem(row, 2, QTableWidgetItem(format_currency(item.unit_price)))
            self.items_table.setItem(row, 3, QTableWidgetItem(format_currency(item.subtotal)))

        # Enable refund button only for valid sales
        can_refund = sale.status not in ("VOID", "REFUNDED") and sale.payment_method != "REFUND"
        self.btn_refund.setEnabled(can_refund)

        if not can_refund:
            QMessageBox.warning(
                self,
                "Cannot Refund",
                f"This sale cannot be refunded (status: {sale.status}).",
            )

    def process_refund(self) -> None:
        """Process the refund after permission check."""
        if not self.found_sale:
            return

        reason = self.txt_reason.toPlainText().strip()
        if not reason:
            QMessageBox.warning(self, "Validation", "Please enter a reason for the refund.")
            return

        # Permission check
        from cbpos.core.constants.permissions import Permissions

        authorized_user = check_permission_with_override(Permissions.SALES_REFUND, self)
        if not authorized_user:
            return

        # Confirm
        reply = QMessageBox.question(
            self,
            "Confirm Refund",
            f"Refund {format_currency(self.found_sale.total_amount)} for "
            f"{self.found_sale.document_number}?\n\nReason: {reason}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_refund.setEnabled(False)
        self.btn_refund.setText("Processing...")
        try:
            success = TransactionService.process_refund(
                original_sale_id=self.found_sale.id,
                refund_reason=reason,
                user_id=authorized_user.id,
            )
            if success:
                QMessageBox.information(
                    self,
                    "Refund Processed",
                    f"Refund for {self.found_sale.document_number} processed successfully.",
                )
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Refund failed. Check logs for details.")
                self.btn_refund.setText("Process Refund")
                self.btn_refund.setEnabled(True)
        except ValueError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
            self.btn_refund.setText("Process Refund")
            self.btn_refund.setEnabled(True)
        except Exception as e:
            logger.error("Refund failed: %s", e)
            QMessageBox.critical(self, "Error", f"Refund failed: {e}")
            self.btn_refund.setText("Process Refund")
            self.btn_refund.setEnabled(True)
