"""Warranty Lookup and Status Dialog (#825)."""

import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.constants.permissions import Permissions
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.warranty_dto import WarrantyDTO
from cbpos.core.services.warranty_service import WarrantyService
from cbpos.core.utils.formatters import format_datetime
from cbpos.core.utils.permission_helper import check_permission_with_override
from cbpos.i18n import _t
from cbpos.ui.dialogs.warranty_correction_dialog import WarrantyCorrectionDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.dialog_footer import make_close_footer
from cbpos.ui.widgets.table_helpers import (
    attach_table_empty_state,
    batch_table_update,
    configure_table_columns,
)

logger = logging.getLogger(__name__)

WARRANTY_ID_ROLE = Qt.ItemDataRole.UserRole


class WarrantyLookupDialog(QDialog):
    """Modal lookup dialog for finding warranties by serial, receipt, code, or customer (#825)."""

    accepts_scans = True

    def __init__(self, initial_query: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("WarrantyLookupDialog")
        self.setWindowTitle(_t("warranty_lookup.title"))
        self.resize(1020, 640)
        self.setMinimumSize(860, 520)

        self._warranties: list[WarrantyDTO] = []
        self._selected_dto: WarrantyDTO | None = None

        # Debounce timer for search input
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._do_search)

        self.init_ui()

        if initial_query:
            self.search_input.setText(initial_query)
            self._do_search()

    def process_barcode_external(self, barcode: str) -> None:
        """Handle hardware barcode scanner input immediately without debounce."""
        clean = (barcode or "").strip()
        if clean:
            self.search_input.setText(clean)
            self._do_search()

    def init_ui(self) -> None:
        """Build search bar, master-detail layout, and footer."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # ── Search Bar ───────────────────────────────────────────
        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("WarrantySearchInput")
        self.search_input.setPlaceholderText(_t("warranty_lookup.search_placeholder"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._do_search)
        search_row.addWidget(self.search_input, 1)

        self.btn_search = QPushButton(_t("common.search"))
        self.btn_search.setObjectName("BtnWarrantySearch")
        self.btn_search.setIcon(Icons.get(Icons.SEARCH))
        self.btn_search.clicked.connect(self._do_search)
        search_row.addWidget(self.btn_search)

        main_layout.addLayout(search_row)

        # ── Splitter: Results Table (Left) + Detail Card (Right) ─
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # Left: Results Table
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)

        self.table = QTableWidget()
        self.table.setObjectName("WarrantyResultsTable")
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                _t("warranty_lookup.col_product"),
                _t("warranty_lookup.col_serial"),
                _t("warranty_lookup.col_customer"),
                _t("warranty_lookup.col_sold_date"),
                _t("warranty_lookup.col_valid_until"),
                _t("warranty_lookup.col_status"),
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,
                1: QHeaderView.ResizeMode.ResizeToContents,
                2: QHeaderView.ResizeMode.ResizeToContents,
                3: QHeaderView.ResizeMode.ResizeToContents,
                4: QHeaderView.ResizeMode.ResizeToContents,
                5: QHeaderView.ResizeMode.ResizeToContents,
            },
        )
        attach_table_empty_state(self.table, Icons.WARRANTY, "warranty_lookup.no_warranties_found")
        table_layout.addWidget(self.table)

        self.lbl_result_count = QLabel("")
        self.lbl_result_count.setStyleSheet("color: #6C757D; font-size: 11px;")
        table_layout.addWidget(self.lbl_result_count)

        self.splitter.addWidget(table_container)

        # Right: Detail Card Pane
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("WarrantyDetailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.StyledPanel)

        self.detail_container = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(14, 14, 14, 14)
        self.detail_layout.setSpacing(12)

        # Empty State for Detail
        self.lbl_empty_detail = QLabel(_t("warranty_lookup.select_to_view_details"))
        self.lbl_empty_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_detail.setStyleSheet("color: #6C757D; padding: 40px;")
        self.lbl_empty_detail.setWordWrap(True)
        self.detail_layout.addWidget(self.lbl_empty_detail)

        # Content Widget for Detail
        self.detail_content = QWidget()
        detail_form_layout = QVBoxLayout(self.detail_content)
        detail_form_layout.setContentsMargins(0, 0, 0, 0)
        detail_form_layout.setSpacing(12)

        # Header: Code + Status Badge
        header_row = QHBoxLayout()
        self.lbl_detail_code = QLabel()
        self.lbl_detail_code.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_row.addWidget(self.lbl_detail_code)
        header_row.addStretch()

        self.lbl_detail_badge = QLabel()
        self.lbl_detail_badge.setObjectName("WarrantyStatusBadge")
        header_row.addWidget(self.lbl_detail_badge)
        detail_form_layout.addLayout(header_row)

        # Metadata Form
        form = QFormLayout()
        form.setSpacing(6)
        self.lbl_val_product = QLabel()
        form.addRow(_t("warranty_lookup.product_label") + ":", self.lbl_val_product)

        self.lbl_val_serial = QLabel()
        form.addRow(_t("warranty_lookup.col_serial") + ":", self.lbl_val_serial)

        self.lbl_val_sale = QLabel()
        form.addRow(_t("warranty_lookup.sale_label") + ":", self.lbl_val_sale)

        self.lbl_val_sold = QLabel()
        form.addRow(_t("warranty_lookup.col_sold_date") + ":", self.lbl_val_sold)

        self.lbl_val_customer = QLabel()
        form.addRow(_t("warranty_lookup.col_customer") + ":", self.lbl_val_customer)

        self.lbl_val_coverage = QLabel()
        form.addRow(_t("warranty_lookup.coverage_period") + ":", self.lbl_val_coverage)

        self.lbl_val_duration_remedy = QLabel()
        form.addRow(_t("warranty_lookup.duration_remedy") + ":", self.lbl_val_duration_remedy)

        detail_form_layout.addLayout(form)

        # Terms & Exclusions Snapshot
        lbl_terms_head = QLabel(_t("warranty.terms_label"))
        lbl_terms_head.setStyleSheet("font-weight: bold; margin-top: 6px;")
        detail_form_layout.addWidget(lbl_terms_head)

        self.txt_terms = QTextEdit()
        self.txt_terms.setReadOnly(True)
        self.txt_terms.setMaximumHeight(70)
        detail_form_layout.addWidget(self.txt_terms)

        lbl_exclusions_head = QLabel(_t("warranty.exclusions_label"))
        lbl_exclusions_head.setStyleSheet("font-weight: bold; margin-top: 6px;")
        detail_form_layout.addWidget(lbl_exclusions_head)

        self.txt_exclusions = QTextEdit()
        self.txt_exclusions.setReadOnly(True)
        self.txt_exclusions.setMaximumHeight(70)
        detail_form_layout.addWidget(self.txt_exclusions)

        # Actions Row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self.btn_reprint_card = QPushButton(_t("warranty_lookup.btn_reprint_card"))
        self.btn_reprint_card.setIcon(Icons.get(Icons.PRINT))
        self.btn_reprint_card.clicked.connect(self._on_reprint_card)
        actions_row.addWidget(self.btn_reprint_card)

        self.btn_export_pdf = QPushButton(_t("warranty_lookup.btn_export_pdf"))
        self.btn_export_pdf.setIcon(Icons.get("fa5s.file-pdf"))
        self.btn_export_pdf.clicked.connect(self._on_export_pdf)
        actions_row.addWidget(self.btn_export_pdf)

        self.btn_edit_admin = QPushButton(_t("warranty_lookup.btn_edit"))
        self.btn_edit_admin.setIcon(Icons.get(Icons.EDIT))
        self.btn_edit_admin.clicked.connect(self._on_edit_admin)
        actions_row.addWidget(self.btn_edit_admin)

        detail_form_layout.addLayout(actions_row)

        # Claim Button Row (#826)
        claim_row = QHBoxLayout()
        self.btn_start_claim = QPushButton(_t("warranty_lookup.btn_start_claim"))
        self.btn_start_claim.setProperty("class", "primary")
        self.btn_start_claim.setEnabled(False)
        self.btn_start_claim.clicked.connect(self._on_start_claim)
        claim_row.addWidget(self.btn_start_claim)
        detail_form_layout.addLayout(claim_row)

        detail_form_layout.addStretch(1)

        self.detail_layout.addWidget(self.detail_content)
        self.detail_content.hide()

        self.detail_scroll.setWidget(self.detail_container)
        self.splitter.addWidget(self.detail_scroll)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        main_layout.addWidget(self.splitter, 1)

        # ── Footer ───────────────────────────────────────────────
        footer_layout, self.btn_close = make_close_footer(
            close_key="common.close",
            on_close=self.accept,
            close_object_name="BtnCloseWarrantyLookup",
        )
        main_layout.addLayout(footer_layout)

    def _on_search_text_changed(self) -> None:
        """Start or restart debounce timer on search text input."""
        self._search_timer.start()

    def _do_search(self) -> None:
        """Execute search via WarrantyService and update results table."""
        self._search_timer.stop()
        query = self.search_input.text().strip()
        if not query:
            self._warranties = []
            self._populate_table()
            return

        try:
            self._warranties = WarrantyService.search(query)
            self._populate_table()
        except Exception as e:
            logger.error("Warranty search failed: %s", e)
            QMessageBox.critical(self, _t("common.error"), str(e))

    def _populate_table(self) -> None:
        """Populate results table with search outcomes."""
        with batch_table_update(self.table):
            self.table.setRowCount(0)
            TableItem = QTableWidgetItem

            for row_idx, dto in enumerate(self._warranties):
                self.table.insertRow(row_idx)

                item_prod = TableItem(dto.product_name)
                item_prod.setData(WARRANTY_ID_ROLE, dto.id)
                self.table.setItem(row_idx, 0, item_prod)

                item_sn = TableItem(dto.serial_number or "-")
                self.table.setItem(row_idx, 1, item_sn)

                cust_text = dto.customer_name or _t("warranty_lookup.walk_in")
                if dto.customer_phone:
                    cust_text += f" ({dto.customer_phone})"
                item_cust = TableItem(cust_text)
                self.table.setItem(row_idx, 2, item_cust)

                sold_str = format_datetime(dto.sold_date) if dto.sold_date else "-"
                item_sold = TableItem(sold_str)
                self.table.setItem(row_idx, 3, item_sold)

                valid_str = dto.end_date.strftime("%Y-%m-%d") if dto.end_date else "-"
                item_valid = TableItem(valid_str)
                self.table.setItem(row_idx, 4, item_valid)

                item_status = TableItem(self._format_status_label(dto.effective_status, dto.days_remaining))
                self.table.setItem(row_idx, 5, item_status)

        count = len(self._warranties)
        self.lbl_result_count.setText(_t("warranty_lookup.count_found", count=count) if count > 0 else "")

        if self._warranties:
            self.table.selectRow(0)
        else:
            self._selected_dto = None
            self.detail_content.hide()
            self.lbl_empty_detail.show()

    def _format_status_label(self, eff_status: str, days_remaining: int) -> str:
        """Return localized label for effective warranty status."""
        if eff_status == "ACTIVE":
            return _t("warranty.status_active")
        elif eff_status == "EXPIRING":
            return _t("warranty.status_expiring", days=days_remaining)
        elif eff_status == "EXPIRED":
            return _t("warranty.status_expired")
        elif eff_status == "VOID":
            return _t("warranty.status_void")
        elif eff_status == "CANCELLED":
            return _t("warranty.status_cancelled")
        elif eff_status == "REPLACED":
            return _t("warranty.status_replaced")
        return eff_status

    def _on_selection_changed(self) -> None:
        """Update detail pane based on selected table row."""
        rows = self.table.selectedItems()
        if not rows:
            self._selected_dto = None
            self.detail_content.hide()
            self.lbl_empty_detail.show()
            return

        row = self.table.currentRow()
        if 0 <= row < len(self._warranties):
            dto = self._warranties[row]
            self._selected_dto = dto
            self._display_detail(dto)
        else:
            self._selected_dto = None
            self.detail_content.hide()
            self.lbl_empty_detail.show()

    def _display_detail(self, dto: WarrantyDTO) -> None:
        """Fill detail pane fields from WarrantyDTO."""
        self.lbl_empty_detail.hide()
        self.detail_content.show()

        self.lbl_detail_code.setText(dto.code)

        # Style status badge
        badge_text = self._format_status_label(dto.effective_status, dto.days_remaining)
        self.lbl_detail_badge.setText(f" {badge_text} ")
        if dto.effective_status == "ACTIVE":
            self.lbl_detail_badge.setStyleSheet(
                "background-color: #E8F5E9; color: #2E7D32; font-weight: bold; border-radius: 4px; padding: 4px 8px;"
            )
        elif dto.effective_status == "EXPIRING":
            self.lbl_detail_badge.setStyleSheet(
                "background-color: #FFF3E0; color: #EF6C00; font-weight: bold; border-radius: 4px; padding: 4px 8px;"
            )
        elif dto.effective_status == "EXPIRED":
            self.lbl_detail_badge.setStyleSheet(
                "background-color: #FFEBEE; color: #C62828; font-weight: bold; border-radius: 4px; padding: 4px 8px;"
            )
        else:
            self.lbl_detail_badge.setStyleSheet(
                "background-color: #EEEEEE; color: #616161; font-weight: bold; border-radius: 4px; padding: 4px 8px;"
            )

        self.lbl_val_product.setText(dto.product_name)
        self.lbl_val_serial.setText(dto.serial_number or "-")
        self.lbl_val_sale.setText(dto.sale_document_number)
        self.lbl_val_sold.setText(format_datetime(dto.sold_date) if dto.sold_date else "-")

        cust_str = dto.customer_name or _t("warranty_lookup.walk_in")
        if dto.customer_phone:
            cust_str += f" ({dto.customer_phone})"
        self.lbl_val_customer.setText(cust_str)

        start_s = dto.start_date.strftime("%Y-%m-%d") if dto.start_date else "-"
        end_s = dto.end_date.strftime("%Y-%m-%d") if dto.end_date else "-"
        self.lbl_val_coverage.setText(f"{start_s}  →  {end_s}")

        unit_str = _t(f"warranty.unit_{dto.duration_unit.lower()}")
        remedy_str = _t(f"warranty.remedy_{dto.remedy.lower()}")
        type_str = _t(f"warranty.type_{dto.warranty_type.lower()}", default=dto.warranty_type.capitalize())
        if dto.warranty_type == "EXTENDED" and dto.covers_warranty_id:
            type_str += f" ({_t('warranty.covers_base', default='Covers')} #{dto.covers_warranty_id})"
        self.lbl_val_duration_remedy.setText(f"[{type_str}] {dto.duration} {unit_str} ({remedy_str})")

        self.txt_terms.setPlainText(dto.terms_snapshot or _t("common.none"))
        self.txt_exclusions.setPlainText(dto.exclusions_snapshot or _t("common.none"))

        # Permissions check for admin edit
        curr = AuthService.get_current_user()
        can_edit = bool(curr and PermissionService.user_has_permission(curr, Permissions.WARRANTY_EDIT))
        self.btn_edit_admin.setEnabled(can_edit and dto.status not in ("VOID", "CANCELLED"))

        # Claim button state (#826)
        if dto.has_active_claim:
            self.btn_start_claim.setEnabled(False)
            self.btn_start_claim.setText(_t("warranty_lookup.claim_in_progress"))
            self.btn_start_claim.setToolTip(_t("warranty_lookup.active_claim_tooltip"))
        elif dto.status in ("VOID", "CANCELLED"):
            self.btn_start_claim.setEnabled(False)
            self.btn_start_claim.setText(_t("warranty_lookup.btn_start_claim"))
            self.btn_start_claim.setToolTip(_t("warranty_lookup.claim_void_disabled"))
        else:
            self.btn_start_claim.setEnabled(True)
            self.btn_start_claim.setText(_t("warranty_lookup.btn_start_claim"))
            self.btn_start_claim.setToolTip("")

    def _on_reprint_card(self) -> None:
        """Reprint warranty card via background worker."""
        if not self._selected_dto:
            return

        authorized_user = check_permission_with_override(Permissions.SALES_REPRINT, self)
        if not authorized_user:
            return

        curr = AuthService.get_current_user()
        curr_id = curr.id if curr else None
        auth_id = getattr(authorized_user, "id", None)
        user_id = curr_id or auth_id or 1
        approver_id = auth_id if (auth_id and curr_id and auth_id != curr_id) else None

        from cbpos.ui.workers import PrintWorker, WarrantyReprintWorker, start_background_job

        self.btn_reprint_card.setEnabled(False)
        worker = WarrantyReprintWorker(
            self._selected_dto.sale_id, user_id=user_id, approver_id=approver_id, parent=None
        )

        def _on_result(commands: list) -> None:
            self.btn_reprint_card.setEnabled(True)
            worker_inst = PrintWorker.instance()
            worker_inst.add_job("print_commands", commands)
            QMessageBox.information(self, _t("common.success"), _t("warranty_lookup.reprint_sent"))

        def _on_error(err_str: str) -> None:
            self.btn_reprint_card.setEnabled(True)
            logger.error("Warranty reprint failed: %s", err_str)
            QMessageBox.critical(self, _t("common.error"), str(err_str))

        worker.result.connect(_on_result)
        worker.error.connect(_on_error)
        start_background_job(worker)

    def _on_export_pdf(self) -> None:
        """Export standalone warranty certificate PDF for the sale."""
        if not self._selected_dto:
            return

        curr = AuthService.get_current_user()
        user_id = curr.id if curr else 1

        path, _ = QFileDialog.getSaveFileName(
            self,
            _t("warranty.export_pdf_title"),
            f"Warranty_{self._selected_dto.code}.pdf",
            "PDF Files (*.pdf)",
        )
        if not path:
            return

        from cbpos.ui.workers import WarrantyExportPdfWorker, start_background_job

        self.btn_export_pdf.setEnabled(False)
        worker = WarrantyExportPdfWorker(self._selected_dto.sale_id, path, user_id=user_id, parent=None)

        def _on_result(saved_path: str) -> None:
            self.btn_export_pdf.setEnabled(True)
            QMessageBox.information(self, _t("common.success"), _t("warranty.pdf_exported_to", path=saved_path))

        def _on_error(err_str: str) -> None:
            self.btn_export_pdf.setEnabled(True)
            logger.error("Warranty PDF export failed: %s", err_str)
            QMessageBox.critical(self, _t("common.error"), str(err_str))

        worker.result.connect(_on_result)
        worker.error.connect(_on_error)
        start_background_job(worker)

    def _on_edit_admin(self) -> None:
        """Open WarrantyCorrectionDialog and refresh upon save."""
        if not self._selected_dto:
            return

        dlg = WarrantyCorrectionDialog(self._selected_dto, parent=self)
        if dlg.exec():
            # Refresh search results
            self._do_search()

    def _on_start_claim(self) -> None:
        """Open WarrantyClaimIntakeDialog for the selected warranty (#826)."""
        if not self._selected_dto:
            return

        from cbpos.ui.dialogs.warranty_claim_intake_dialog import WarrantyClaimIntakeDialog

        dlg = WarrantyClaimIntakeDialog(warranty=self._selected_dto, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._do_search()
