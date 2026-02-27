import logging
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDateEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QSplitter,
    QComboBox,
    QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QColor

from cbpos.core.services.document_browser_service import DocumentBrowserService
from cbpos.core.services.proforma_service import ProformaService
from cbpos.core.services.receipt_service import ReceiptService
from cbpos.core.services.transaction_service import TransactionService
from cbpos.core.services.auth_service import AuthService
from cbpos.core.constants.status import DocumentStatus
from cbpos.core.utils.formatters import format_currency
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker

logger = logging.getLogger(__name__)


class DocumentBrowserView(QWidget):
    """
    Unified document browser that consolidates Sales, Purchases,
    Proformas, and other document types into a single searchable view.
    """

    convert_to_sale_requested = pyqtSignal(dict)

    # Status color map
    STATUS_COLORS = {
        "COMPLETED": QColor("#39FF14"),
        "VOID": QColor("#FF4136"),
        "QUOTE": QColor("#00BCEB"),
        "EXPIRED": QColor("#888888"),
        "CONVERTED": QColor("#FF851B"),
        "DRAFT": QColor("#FFDC00"),
        "SUSPENDED": QColor("#FFDC00"),
    }

    def __init__(self) -> None:
        super().__init__()
        self.current_doc: dict | None = None
        self.current_page = 1
        self.total_docs = 0
        self.init_ui()
        try:
            self.load_documents()
        except Exception as e:
            logger.error("Failed to load documents on init: %s", e)

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title
        title = QLabel("Document Browser")
        title.setObjectName("ViewTitle")
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        # Filter Bar
        filter_frame = QFrame()
        filter_frame.setObjectName("FilterBar")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(8, 8, 8, 8)
        filter_layout.setSpacing(8)

        # Document Type
        lbl_type = QLabel("Type:")
        lbl_type.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_type)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["All", "Sales", "Purchases", "Proforma"])
        self.type_combo.setMinimumWidth(110)
        filter_layout.addWidget(self.type_combo)

        # Status
        lbl_status = QLabel("Status:")
        lbl_status.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_status)
        self.status_combo = QComboBox()
        self.status_combo.addItems(["All", "Completed", "Void", "Draft", "Quote", "Expired", "Converted"])
        self.status_combo.setMinimumWidth(110)
        filter_layout.addWidget(self.status_combo)

        # Date Range
        lbl_from = QLabel("From:")
        lbl_from.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_from)
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addWidget(self.from_date)

        lbl_to = QLabel("To:")
        lbl_to.setProperty("class", "transparent")
        filter_layout.addWidget(lbl_to)
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())
        filter_layout.addWidget(self.to_date)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search document number...")
        self.search_input.returnPressed.connect(self.apply_filter)
        filter_layout.addWidget(self.search_input, 1)

        # Buttons
        filter_btn = QPushButton("Filter")
        filter_btn.clicked.connect(self.apply_filter)
        filter_layout.addWidget(filter_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_filter)
        filter_layout.addWidget(clear_btn)

        # New Proforma button
        new_proforma_btn = QPushButton("+ New Quotation")
        new_proforma_btn.setObjectName("BtnSuccess")
        new_proforma_btn.setProperty("class", "accent")
        new_proforma_btn.clicked.connect(self.open_proforma_dialog)
        filter_layout.addWidget(new_proforma_btn)

        layout.addWidget(filter_frame)

        # Main Content: Splitter with table and details — stretch=1 so it fills remaining space
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Document Table
        self.doc_table = QTableWidget()
        self.doc_table.setColumnCount(7)
        self.doc_table.setHorizontalHeaderLabels(
            ["Date", "Doc #", "Type", "Customer/Supplier", "Total", "Status", "User"]
        )
        self.doc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.doc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.doc_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.doc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.doc_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.doc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.doc_table.verticalHeader().setVisible(False)
        self.doc_table.setAlternatingRowColors(True)
        self.doc_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.doc_table.itemSelectionChanged.connect(self.on_selection_changed)
        splitter.addWidget(self.doc_table)

        # Details Panel
        details_widget = QFrame()
        details_widget.setObjectName("DocDetailsPanel")
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(8)

        lbl_details_title = QLabel("<b>Document Details</b>")
        lbl_details_title.setProperty("class", "transparent")
        details_layout.addWidget(lbl_details_title)

        self.details_label = QLabel("Select a document to view details")
        self.details_label.setWordWrap(True)
        self.details_label.setProperty("class", "transparent")
        details_layout.addWidget(self.details_label)

        # Line Items
        lbl_items_title = QLabel("<b>Line Items:</b>")
        lbl_items_title.setProperty("class", "transparent")
        details_layout.addWidget(lbl_items_title)
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(5)
        self.items_table.setHorizontalHeaderLabels(["Product", "Qty", "Unit Price", "Discount", "Total"])
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        details_layout.addWidget(self.items_table, 1)  # stretch so items table fills details panel

        # Payment Info
        self.payment_label = QLabel("")
        self.payment_label.setWordWrap(True)
        self.payment_label.setProperty("class", "transparent")
        details_layout.addWidget(self.payment_label)

        # Action Buttons
        action_layout = QHBoxLayout()

        self.reprint_btn = QPushButton("Reprint")
        self.reprint_btn.clicked.connect(self.reprint_document)
        self.reprint_btn.setEnabled(False)
        action_layout.addWidget(self.reprint_btn)

        self.refund_btn = QPushButton("Refund")
        self.refund_btn.clicked.connect(self.process_refund)
        self.refund_btn.setEnabled(False)
        self.refund_btn.setProperty("class", "danger")
        action_layout.addWidget(self.refund_btn)

        self.convert_btn = QPushButton("Convert to Sale")
        self.convert_btn.clicked.connect(self.convert_proforma)
        self.convert_btn.setEnabled(False)
        self.convert_btn.setProperty("class", "primary")
        action_layout.addWidget(self.convert_btn)

        self.void_btn = QPushButton("Void")
        self.void_btn.clicked.connect(self.void_document)
        self.void_btn.setEnabled(False)
        self.void_btn.setProperty("class", "danger")
        action_layout.addWidget(self.void_btn)

        details_layout.addLayout(action_layout)

        splitter.addWidget(details_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)  # stretch=1 so splitter fills all remaining vertical space

        # Pagination
        page_layout = QHBoxLayout()
        page_layout.addStretch()
        self.page_label = QLabel("Page 1")
        self.page_label.setProperty("class", "transparent")
        page_layout.addWidget(self.page_label)

        self.prev_btn = QPushButton("< Previous")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        page_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next >")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        page_layout.addWidget(self.next_btn)

        layout.addLayout(page_layout)

    def apply_filter(self) -> None:
        """Apply filters and reload documents."""
        self.current_page = 1
        self.load_documents()

    def clear_filter(self) -> None:
        """Reset all filters to defaults."""
        self.type_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.to_date.setDate(QDate.currentDate())
        self.search_input.clear()
        self.current_page = 1
        self.load_documents()

    def load_documents(self) -> None:
        """Load documents from service with current filters."""
        # Map combo selections to service params
        type_map = {"All": None, "Sales": "SALE", "Purchases": "PURCHASE", "Proforma": "PROFORMA"}
        status_map = {
            "All": None,
            "Completed": "COMPLETED",
            "Void": "VOID",
            "Draft": "DRAFT",
            "Quote": "QUOTE",
            "Expired": "EXPIRED",
            "Converted": "CONVERTED",
        }

        doc_type = type_map.get(self.type_combo.currentText())
        status = status_map.get(self.status_combo.currentText())

        from_date = self.from_date.date().toPyDate()
        to_date = self.to_date.date().toPyDate()

        search = self.search_input.text().strip() or None

        result = DocumentBrowserService.search_documents(
            doc_type=doc_type,
            status=status,
            date_from=datetime.combine(from_date, datetime.min.time()),
            date_to=datetime.combine(to_date, datetime.max.time()),
            search_term=search,
            page=self.current_page,
            per_page=50,
        )

        self.total_docs = result["total"]
        self.populate_table(result["documents"])
        self.update_pagination()

    def populate_table(self, documents: list) -> None:
        """Populate the document table."""
        self.doc_table.setRowCount(0)
        self.current_doc = None
        self.reset_action_buttons()

        for row, doc in enumerate(documents):
            self.doc_table.insertRow(row)

            # Date
            dt_item = QTableWidgetItem(doc["date"].strftime("%Y-%m-%d %H:%M") if doc["date"] else "")
            dt_item.setData(Qt.ItemDataRole.UserRole, doc["id"])
            dt_item.setData(Qt.ItemDataRole.UserRole + 1, doc["type"])
            self.doc_table.setItem(row, 0, dt_item)

            # Doc #
            self.doc_table.setItem(row, 1, QTableWidgetItem(doc["document_number"]))

            # Type
            type_display = {
                "SALE": "Sale",
                "PURCHASE": "Purchase",
                "PROFORMA": "Quotation",
            }
            self.doc_table.setItem(row, 2, QTableWidgetItem(type_display.get(doc["type"], doc["type"])))

            # Customer/Supplier
            self.doc_table.setItem(row, 3, QTableWidgetItem(doc.get("entity_name", "")))

            # Total
            total = doc.get("total_amount")
            total_text = format_currency(total) if total is not None else ""
            total_item = QTableWidgetItem(total_text)
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.doc_table.setItem(row, 4, total_item)

            # Status (color-coded)
            status_item = QTableWidgetItem(doc["status"])
            color = self.STATUS_COLORS.get(doc["status"])
            if color:
                status_item.setForeground(color)
            self.doc_table.setItem(row, 5, status_item)

            # User
            self.doc_table.setItem(row, 6, QTableWidgetItem(doc.get("username", "")))

    def on_selection_changed(self) -> None:
        """Handle row selection — load full details."""
        selected = self.doc_table.selectedItems()
        if not selected:
            self.current_doc = None
            self.reset_action_buttons()
            return

        row = selected[0].row()
        first_item = self.doc_table.item(row, 0)
        doc_id = first_item.data(Qt.ItemDataRole.UserRole)
        doc_type = first_item.data(Qt.ItemDataRole.UserRole + 1)

        details = DocumentBrowserService.get_document_details(doc_id, doc_type)
        if details:
            self.current_doc = details
            self.display_details(details)
            self.update_action_buttons(details)

    def display_details(self, doc: dict) -> None:
        """Display document details in the details panel."""
        type_labels = {"sale": "Sale", "purchase": "Purchase", "proforma": "Quotation"}

        html = f"""
        <b>Document:</b> {doc['document_number']}<br>
        <b>Type:</b> {type_labels.get(doc['type'], doc['type'])}<br>
        <b>Date:</b> {doc['date'].strftime('%Y-%m-%d %H:%M:%S') if doc['date'] else 'N/A'}<br>
        <b>Status:</b> {doc['status']}<br>
        <b>User:</b> {doc.get('username', '')}<br>
        """

        entity = doc.get("entity_name", "")
        if entity:
            label = "Supplier" if doc["type"] == "purchase" else "Customer"
            html += f"<b>{label}:</b> {entity}<br>"

        total = doc.get("total_amount")
        if total is not None:
            html += f"<b>Total:</b> {format_currency(total)}<br>"

        # Proforma-specific info
        if doc["type"] == "proforma":
            if doc.get("validity_days"):
                html += f"<b>Validity:</b> {doc['validity_days']} days<br>"
            if doc.get("expiry_date"):
                html += f"<b>Expiry:</b> {doc['expiry_date']}<br>"
            if doc.get("notes"):
                html += f"<b>Notes:</b> {doc['notes']}<br>"
            if doc.get("converted_sale_id"):
                html += f"<b>Converted to Sale:</b> #{doc['converted_sale_id']}<br>"

        # Refund info
        if doc.get("refund_of_sale_id"):
            html += f"<b>Refund of Sale:</b> #{doc['refund_of_sale_id']}<br>"

        self.details_label.setText(html)

        # Populate line items
        items = doc.get("items", [])
        self.items_table.setRowCount(0)
        for idx, item in enumerate(items):
            self.items_table.insertRow(idx)
            self.items_table.setItem(idx, 0, QTableWidgetItem(item.get("product_name", "")))

            qty_item = QTableWidgetItem(f"{item['quantity']:.3f}")
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(idx, 1, qty_item)

            price_item = QTableWidgetItem(format_currency(item["unit_price"]))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(idx, 2, price_item)

            disc = item.get("discount_type", "NONE")
            disc_val = item.get("discount_value", 0)
            disc_text = "" if disc == "NONE" else f"{disc} {disc_val}"
            self.items_table.setItem(idx, 3, QTableWidgetItem(disc_text))

            total_item = QTableWidgetItem(format_currency(item["line_total"]))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.items_table.setItem(idx, 4, total_item)

        # Payment info
        payments = doc.get("payments", [])
        if payments:
            pay_lines = []
            for p in payments:
                pay_lines.append(f"{p['method']}: {format_currency(p['amount'])}")
            self.payment_label.setText("<b>Payments:</b> " + " | ".join(pay_lines))
        else:
            self.payment_label.setText("")

    def reset_action_buttons(self) -> None:
        """Disable all action buttons."""
        self.reprint_btn.setEnabled(False)
        self.refund_btn.setEnabled(False)
        self.convert_btn.setEnabled(False)
        self.void_btn.setEnabled(False)

    def update_action_buttons(self, doc: dict) -> None:
        """Enable relevant action buttons based on document type and status."""
        doc_type = doc.get("type", "")
        status = doc.get("status", "")

        # Reprint — for completed sales/purchases
        self.reprint_btn.setEnabled(doc_type in ("sale", "purchase", "proforma") and status != DocumentStatus.VOID)

        # Refund — only completed sales (not refunds themselves)
        is_refundable = doc_type == "sale" and status == DocumentStatus.COMPLETED and not doc.get("refund_of_sale_id")
        self.refund_btn.setEnabled(is_refundable)

        # Convert to Sale — only QUOTE proformas
        self.convert_btn.setEnabled(doc_type == "proforma" and status == DocumentStatus.QUOTE)

        # Void — any non-void, non-converted document
        self.void_btn.setEnabled(status not in (DocumentStatus.VOID, DocumentStatus.CONVERTED, DocumentStatus.EXPIRED))

    def reprint_document(self) -> None:
        """Reprint the selected document."""
        if not self.current_doc:
            return

        doc_type = self.current_doc.get("type", "")

        try:
            if doc_type == "sale":
                # Use existing receipt reprint flow
                sale = TransactionService.get_sale_details(self.current_doc["id"])
                if sale:
                    from cbpos.core.services.config_service import ConfigService

                    settings = ConfigService.get_all()
                    language = settings.get("language", "en")
                    worker = PrintWorker()

                    if language == "en":
                        receipt_text = ReceiptService.build_receipt_text(sale)
                        worker.add_job("print_receipt", receipt_text)
                    else:
                        receipt_image = ReceiptService.build_receipt_image(sale)
                        worker.add_job("print_image", receipt_image)

                    QMessageBox.information(
                        self,
                        "Success",
                        f"Receipt {self.current_doc['document_number']} sent to printer.",
                    )
            elif doc_type == "proforma":
                from cbpos.core.services.receipt_builder import ReceiptBuilder

                proforma = ProformaService.get_proforma_details(self.current_doc["id"])
                if proforma:
                    commands = ReceiptBuilder.build_proforma(proforma)
                    worker = PrintWorker()
                    worker.add_job("print_commands", commands)
                    QMessageBox.information(
                        self,
                        "Success",
                        f"Quotation {self.current_doc['document_number']} sent to printer.",
                    )
            else:
                QMessageBox.information(self, "Info", "Reprint is not yet supported for this document type.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reprint: {e}")

    def process_refund(self) -> None:
        """Process a refund for the selected sale."""
        if not self.current_doc or self.current_doc.get("type") != "sale":
            return

        reply = QMessageBox.question(
            self,
            "Confirm Refund",
            f"<b>Refund Transaction?</b><br><br>"
            f"Receipt: {self.current_doc['document_number']}<br>"
            f"Amount: {format_currency(self.current_doc['total_amount'])}<br><br>"
            f"<b style='color: #FF4136'>Warning:</b> "
            f"Stock will be restored. This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                current_user = AuthService.get_current_user()
                if not current_user:
                    QMessageBox.warning(self, "Error", "No user logged in.")
                    return

                success = TransactionService.process_refund(self.current_doc["id"], "Customer Return", current_user.id)
                if success:
                    QMessageBox.information(self, "Success", "Refund processed successfully.")
                    self.load_documents()
                else:
                    QMessageBox.critical(self, "Error", "Failed to process refund. Check logs.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Refund failed: {e}")

    def convert_proforma(self) -> None:
        """Convert selected proforma to a sale via SalesView."""
        if not self.current_doc or self.current_doc.get("type") != "proforma":
            return

        reply = QMessageBox.question(
            self,
            "Convert to Sale",
            f"Convert quotation <b>{self.current_doc['document_number']}</b> to a sale?<br><br>"
            f"The items will be loaded into the POS cart for checkout.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            cart_data = ProformaService.convert_to_sale(self.current_doc["id"])
            if cart_data:
                self.convert_to_sale_requested.emit(cart_data)
            else:
                QMessageBox.critical(self, "Error", "Failed to prepare proforma for conversion.")

    def void_document(self) -> None:
        """Void the selected document."""
        if not self.current_doc:
            return

        doc_type = self.current_doc.get("type", "")
        doc_number = self.current_doc.get("document_number", "")

        reply = QMessageBox.question(
            self,
            "Confirm Void",
            f"<b>Void document {doc_number}?</b><br><br>"
            f"<b style='color: #FF4136'>This action cannot be undone.</b>",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if doc_type == "proforma":
                success = ProformaService.void_proforma(self.current_doc["id"])
            elif doc_type == "sale":
                current_user = AuthService.get_current_user()
                if not current_user:
                    QMessageBox.warning(self, "Error", "No user logged in.")
                    return
                success = TransactionService.void_sale(self.current_doc["id"], current_user.id)
            else:
                QMessageBox.information(self, "Info", "Void not supported for this document type.")
                return

            if success:
                QMessageBox.information(self, "Success", f"Document {doc_number} voided.")
                self.load_documents()
            else:
                QMessageBox.critical(self, "Error", "Failed to void document.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Void failed: {e}")

    def open_proforma_dialog(self) -> None:
        """Open the dialog to create a new proforma/quotation."""
        from cbpos.ui.dialogs.proforma_dialog import ProformaDialog

        dialog = ProformaDialog(self)
        if dialog.exec():
            self.load_documents()

    def update_pagination(self) -> None:
        """Update pagination controls."""
        total_pages = max(1, (self.total_docs + 49) // 50)
        self.page_label.setText(f"Page {self.current_page} of {total_pages} ({self.total_docs} docs)")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < total_pages)

    def prev_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self.load_documents()

    def next_page(self) -> None:
        total_pages = max(1, (self.total_docs + 49) // 50)
        if self.current_page < total_pages:
            self.current_page += 1
            self.load_documents()
