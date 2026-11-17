"""Warranty Claims Board View and Dialog (#826, #820).

Master-detail board for viewing, inspecting, dispatching, resolving,
and collecting warranty claims.
"""

import logging
from decimal import Decimal

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
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

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.warranty_claim_receipt_builder import WarrantyClaimReceiptBuilder
from cbpos.core.services.warranty_claim_service import WarrantyClaimService
from cbpos.core.services.warranty_dto import WarrantyClaimDTO
from cbpos.core.utils.formatters import format_currency, format_datetime
from cbpos.i18n import _t, register_language_callback
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.components.activation import Activatable
from cbpos.ui.dialogs.warranty_claim_intake_dialog import WarrantyClaimIntakeDialog
from cbpos.ui.dialogs.warranty_claim_resolve_dialog import WarrantyClaimResolveDialog
from cbpos.ui.resources.icons import Icons
from cbpos.ui.widgets.dialog_footer import make_close_footer
from cbpos.ui.widgets.table_helpers import attach_table_empty_state, batch_table_update

logger = logging.getLogger(__name__)

CLAIM_ID_ROLE = Qt.ItemDataRole.UserRole


class WarrantyClaimsBoardView(QWidget, Activatable):
    """Master-detail view for managing warranty claims lifecycle (#826)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._claims: list[WarrantyClaimDTO] = []
        self._selected_claim: WarrantyClaimDTO | None = None
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._do_search)

        self.init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)
        self.load_data()

    def init_ui(self) -> None:
        """Initialize filter bar, master table, and detail inspector layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "heading-2")
        toolbar.addWidget(self.lbl_title)

        toolbar.addSpacing(16)

        # Status filter combo
        self.lbl_status_filter = QLabel()
        toolbar.addWidget(self.lbl_status_filter)

        self.cmb_status = QComboBox()
        self.cmb_status.addItem(_t("common.all", default="All"), "ALL")
        self.cmb_status.addItem(_t("warranty_claim.status_intake", default="Intake"), "INTAKE")
        self.cmb_status.addItem(_t("warranty_claim.status_in_inspection", default="In Inspection"), "IN_INSPECTION")
        self.cmb_status.addItem(
            _t("warranty_claim.status_supplier_dispatched", default="At Supplier"), "SUPPLIER_DISPATCHED"
        )
        self.cmb_status.addItem(
            _t("warranty_claim.status_supplier_returned", default="Supplier Returned"), "SUPPLIER_RETURNED"
        )
        self.cmb_status.addItem(_t("warranty_claim.status_resolved", default="Resolved"), "RESOLVED")
        self.cmb_status.addItem(_t("warranty_claim.status_collected", default="Collected"), "COLLECTED")
        self.cmb_status.addItem(_t("warranty_claim.status_rejected", default="Rejected"), "REJECTED")
        self.cmb_status.addItem(_t("warranty_claim.status_void", default="Void"), "VOID")
        self.cmb_status.currentIndexChanged.connect(self._do_search)
        toolbar.addWidget(self.cmb_status)

        toolbar.addStretch()

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            _t("warranty_claim.search_placeholder", default="Search claim #, serial, customer...")
        )
        self.search_input.setFixedWidth(240)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(lambda: self._search_timer.start())
        self.search_input.returnPressed.connect(self._do_search)
        toolbar.addWidget(self.search_input)

        # Refresh button
        self.btn_refresh = QPushButton()
        self.btn_refresh.setIcon(Icons.get("fa5s.sync-alt"))
        self.btn_refresh.clicked.connect(self.load_data)
        toolbar.addWidget(self.btn_refresh)

        # New Claim Button
        self.btn_new_claim = QPushButton()
        self.btn_new_claim.setProperty("class", "primary")
        self.btn_new_claim.setIcon(Icons.get(Icons.ADD))
        self.btn_new_claim.clicked.connect(self._on_new_claim)
        toolbar.addWidget(self.btn_new_claim)

        main_layout.addLayout(toolbar)

        # Main splitter (Master left, Detail right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left pane: Table
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        attach_table_empty_state(
            self.table,
            Icons.WARRANTY,
            "warranty_claim.no_claims_found",
            "warranty_claim.select_claim_prompt",
        )
        left_layout.addWidget(self.table)

        splitter.addWidget(left_widget)

        # Right pane: Detail Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setMinimumWidth(400)

        self.detail_container = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(12, 12, 12, 12)
        self.detail_layout.setSpacing(12)

        # Empty state prompt
        self.lbl_empty_detail = QLabel(
            _t("warranty_claim.select_claim_prompt", default="Select a claim to view details and lifecycle history")
        )
        self.lbl_empty_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_detail.setStyleSheet("color: #757575; font-style: italic; margin-top: 60px;")
        self.detail_layout.addWidget(self.lbl_empty_detail)

        # Detail content widget (hidden when nothing selected)
        self.detail_content = QWidget()
        detail_form_layout = QVBoxLayout(self.detail_content)
        detail_form_layout.setContentsMargins(0, 0, 0, 0)
        detail_form_layout.setSpacing(10)

        # Header: Document # + Status Badge + Coverage Badge
        hdr_row = QHBoxLayout()
        self.lbl_detail_doc = QLabel()
        self.lbl_detail_doc.setStyleSheet("font-size: 16px; font-weight: bold;")
        hdr_row.addWidget(self.lbl_detail_doc)

        hdr_row.addStretch()

        self.lbl_coverage_badge = QLabel()
        hdr_row.addWidget(self.lbl_coverage_badge)

        self.lbl_status_badge = QLabel()
        hdr_row.addWidget(self.lbl_status_badge)
        detail_form_layout.addLayout(hdr_row)

        # Product, Serial, Customer Info
        self.lbl_product_info = QLabel()
        detail_form_layout.addWidget(self.lbl_product_info)

        self.lbl_customer_info = QLabel()
        detail_form_layout.addWidget(self.lbl_customer_info)

        self.lbl_dates_info = QLabel()
        detail_form_layout.addWidget(self.lbl_dates_info)

        # Divider
        div1 = QFrame()
        div1.setFrameShape(QFrame.Shape.HLine)
        div1.setStyleSheet("color: #E0E0E0;")
        detail_form_layout.addWidget(div1)

        # Defect Box
        lbl_defect_title = QLabel(_t("warranty_claim.defect", default="Defect Description") + ":")
        lbl_defect_title.setStyleSheet("font-weight: bold;")
        detail_form_layout.addWidget(lbl_defect_title)

        self.lbl_defect_val = QLabel()
        self.lbl_defect_val.setWordWrap(True)
        self.lbl_defect_val.setStyleSheet("background: #F5F5F5; padding: 8px; border-radius: 4px;")
        detail_form_layout.addWidget(self.lbl_defect_val)

        # Condition & Accessories
        self.lbl_condition_acc = QLabel()
        self.lbl_condition_acc.setWordWrap(True)
        detail_form_layout.addWidget(self.lbl_condition_acc)

        # Resolution details frame
        self.frame_resolution = QFrame()
        self.frame_resolution.setStyleSheet("background: #E8F5E9; border-radius: 4px; padding: 8px;")
        res_layout = QVBoxLayout(self.frame_resolution)
        res_layout.setContentsMargins(8, 8, 8, 8)
        res_layout.setSpacing(4)
        self.lbl_res_title = QLabel(_t("warranty_claim.resolution_details", default="Resolution Details"))
        self.lbl_res_title.setStyleSheet("font-weight: bold; color: #2E7D32;")
        res_layout.addWidget(self.lbl_res_title)
        self.lbl_res_content = QLabel()
        self.lbl_res_content.setWordWrap(True)
        res_layout.addWidget(self.lbl_res_content)
        detail_form_layout.addWidget(self.frame_resolution)

        # Lifecycle Timeline
        lbl_events_title = QLabel(_t("warranty_claim.event_history", default="Event History") + ":")
        lbl_events_title.setStyleSheet("font-weight: bold;")
        detail_form_layout.addWidget(lbl_events_title)

        self.txt_timeline = QTextEdit()
        self.txt_timeline.setReadOnly(True)
        self.txt_timeline.setFixedHeight(120)
        detail_form_layout.addWidget(self.txt_timeline)

        # Action Buttons Layout
        self.actions_box = QVBoxLayout()
        self.actions_box.setSpacing(6)

        # State transition buttons row
        self.row_state_actions = QHBoxLayout()
        self.btn_inspect = QPushButton(_t("warranty_claim.btn_inspect", default="Begin Inspection"))
        self.btn_inspect.clicked.connect(self._on_begin_inspection)
        self.row_state_actions.addWidget(self.btn_inspect)

        self.btn_dispatch_supplier = QPushButton(_t("warranty_claim.btn_supplier_dispatch", default="Send to Supplier"))
        self.btn_dispatch_supplier.clicked.connect(self._on_supplier_dispatch)
        self.row_state_actions.addWidget(self.btn_dispatch_supplier)

        self.btn_supplier_returned = QPushButton(
            _t("warranty_claim.btn_supplier_return", default="Mark Supplier Returned")
        )
        self.btn_supplier_returned.clicked.connect(self._on_supplier_returned)
        self.row_state_actions.addWidget(self.btn_supplier_returned)

        self.btn_resolve = QPushButton(_t("warranty_claim.btn_resolve", default="Resolve Claim"))
        self.btn_resolve.setProperty("class", "primary")
        self.btn_resolve.clicked.connect(self._on_resolve_claim)
        self.row_state_actions.addWidget(self.btn_resolve)

        self.btn_collect = QPushButton(_t("warranty_claim.btn_collect", default="Mark Collected"))
        self.btn_collect.setProperty("class", "primary")
        self.btn_collect.clicked.connect(self._on_mark_collected)
        self.row_state_actions.addWidget(self.btn_collect)

        self.actions_box.addLayout(self.row_state_actions)

        # Slips & Rejection row
        self.row_secondary_actions = QHBoxLayout()
        self.btn_print_intake = QPushButton(_t("warranty_claim.btn_print_intake", default="Print Intake Slip"))
        self.btn_print_intake.setIcon(Icons.get(Icons.PRINT))
        self.btn_print_intake.clicked.connect(self._on_print_intake_slip)
        self.row_secondary_actions.addWidget(self.btn_print_intake)

        self.btn_print_collection = QPushButton(
            _t("warranty_claim.btn_print_collection", default="Print Collection Slip")
        )
        self.btn_print_collection.setIcon(Icons.get(Icons.PRINT))
        self.btn_print_collection.clicked.connect(self._on_print_collection_slip)
        self.row_secondary_actions.addWidget(self.btn_print_collection)

        self.btn_reject = QPushButton(_t("warranty_claim.btn_reject", default="Reject Claim"))
        self.btn_reject.setProperty("class", "danger")
        self.btn_reject.clicked.connect(self._on_reject_claim)
        self.row_secondary_actions.addWidget(self.btn_reject)

        self.btn_void = QPushButton(_t("warranty_claim.btn_void", default="Void Claim"))
        self.btn_void.setProperty("class", "danger")
        self.btn_void.clicked.connect(self._on_void_claim)
        self.row_secondary_actions.addWidget(self.btn_void)

        self.actions_box.addLayout(self.row_secondary_actions)

        detail_form_layout.addLayout(self.actions_box)
        detail_form_layout.addStretch()

        self.detail_layout.addWidget(self.detail_content)
        self.detail_content.hide()

        self.scroll_area.setWidget(self.detail_container)
        splitter.addWidget(self.scroll_area)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, 1)

    def retranslate_ui(self) -> None:
        """Update localized text across board view."""
        self.lbl_title.setText(_t("warranty_claim.board_title", default="Warranty Claims Board"))
        self.lbl_status_filter.setText(_t("status", default="Status") + ":")
        self.search_input.setPlaceholderText(
            _t("warranty_claim.search_placeholder", default="Search claim #, serial, customer...")
        )
        self.btn_refresh.setToolTip(_t("common.refresh", default="Refresh"))
        self.btn_new_claim.setText(_t("warranty_claim.btn_new_claim", default="New Claim"))

        # Table headers
        headers = [
            _t("warranty_claim.claim_no", default="Claim #"),
            _t("date", default="Date"),
            _t("status", default="Status"),
            _t("warranty_claim.coverage", default="Coverage"),
            _t("customer", default="Customer"),
            _t("product", default="Product"),
            _t("warranty.serial_number", default="Serial"),
        ]
        self.table.setHorizontalHeaderLabels(headers)

    def load_data(self) -> None:
        """Fetch and populate claims."""
        self._do_search()

    def _do_search(self) -> None:
        """Query claims with current status and text filters."""
        status = self.cmb_status.currentData()
        search = self.search_input.text().strip() or None

        try:
            self._claims = WarrantyClaimService.list_claims(status=status, search=search)
            self._populate_table()
        except Exception as e:
            logger.error("Failed to query warranty claims: %s", e, exc_info=True)
            QMessageBox.critical(self, _t("common.error", default="Error"), str(e))

    def _populate_table(self) -> None:
        """Fill table with queried claims."""
        with batch_table_update(self.table):
            self.table.setRowCount(0)
            TableItem = QTableWidgetItem

            for row_idx, dto in enumerate(self._claims):
                self.table.insertRow(row_idx)

                item_doc = TableItem(dto.document_number)
                item_doc.setData(CLAIM_ID_ROLE, dto.id)
                self.table.setItem(row_idx, 0, item_doc)

                item_date = TableItem(format_datetime(dto.intake_date) if dto.intake_date else "-")
                self.table.setItem(row_idx, 1, item_date)

                item_status = TableItem(dto.claim_status)
                self.table.setItem(row_idx, 2, item_status)

                cov_text = (
                    _t("warranty_claim.covered_short", default="Covered")
                    if dto.is_covered
                    else _t("warranty_claim.uncovered_short", default="Out of warranty")
                )
                item_cov = TableItem(cov_text)
                self.table.setItem(row_idx, 3, item_cov)

                item_cust = TableItem(dto.customer_name or "-")
                self.table.setItem(row_idx, 4, item_cust)

                item_prod = TableItem(dto.product_name)
                self.table.setItem(row_idx, 5, item_prod)

                item_sn = TableItem(dto.item_serial or "-")
                self.table.setItem(row_idx, 6, item_sn)

        if self._claims:
            self.table.selectRow(0)
        else:
            self._selected_claim = None
            self.detail_content.hide()
            self.lbl_empty_detail.show()

    def _on_selection_changed(self) -> None:
        """Display detail pane for selected claim."""
        rows = self.table.selectedItems()
        if not rows:
            self._selected_claim = None
            self.detail_content.hide()
            self.lbl_empty_detail.show()
            return

        row = self.table.currentRow()
        if 0 <= row < len(self._claims):
            dto = self._claims[row]
            self._selected_claim = dto
            self._display_detail(dto)
        else:
            self._selected_claim = None
            self.detail_content.hide()
            self.lbl_empty_detail.show()

    def _display_detail(self, claim: WarrantyClaimDTO) -> None:
        """Populate right inspector with selected claim fields."""
        self.lbl_empty_detail.hide()
        self.detail_content.show()

        self.lbl_detail_doc.setText(claim.document_number)

        # Coverage Badge
        if claim.is_covered:
            self.lbl_coverage_badge.setText(f" {_t('warranty_claim.covered_yes', default='Covered')} ")
            self.lbl_coverage_badge.setStyleSheet(
                "background-color: #E8F5E9; color: #2E7D32; font-weight: bold; border-radius: 4px; padding: 2px 6px;"
            )
        else:
            self.lbl_coverage_badge.setText(f" {_t('warranty_claim.covered_no', default='Out of Warranty')} ")
            self.lbl_coverage_badge.setStyleSheet(
                "background-color: #FFF3E0; color: #E65100; font-weight: bold; border-radius: 4px; padding: 2px 6px;"
            )

        # Status Badge
        self.lbl_status_badge.setText(f" {claim.claim_status} ")
        if claim.claim_status in ("RESOLVED", "COLLECTED"):
            self.lbl_status_badge.setStyleSheet(
                "background-color: #E8F5E9; color: #2E7D32; font-weight: bold; border-radius: 4px; padding: 2px 6px;"
            )
        elif claim.claim_status in ("REJECTED", "VOID", "CANCELLED"):
            self.lbl_status_badge.setStyleSheet(
                "background-color: #FFEBEE; color: #C62828; font-weight: bold; border-radius: 4px; padding: 2px 6px;"
            )
        else:
            self.lbl_status_badge.setStyleSheet(
                "background-color: #E3F2FD; color: #1565C0; font-weight: bold; border-radius: 4px; padding: 2px 6px;"
            )

        # Product & Serial
        w_text = f" | {claim.warranty_code}" if claim.warranty_code else ""
        sn_text = f" | SN: {claim.item_serial}" if claim.item_serial else ""
        self.lbl_product_info.setText(
            f"<b>{_t('product', default='Product')}:</b> {claim.product_name}{sn_text}{w_text}"
        )

        # Customer Info
        c_name = claim.customer_name or _t("warranty_lookup.walk_in", default="Walk-in Customer")
        c_phone = f" ({claim.customer_phone})" if claim.customer_phone else ""
        self.lbl_customer_info.setText(f"<b>{_t('customer', default='Customer')}:</b> {c_name}{c_phone}")

        # Dates
        intake_str = format_datetime(claim.intake_date) if claim.intake_date else "-"
        self.lbl_dates_info.setText(f"<b>{_t('warranty_claim.intake_date', default='Intake Date')}:</b> {intake_str}")

        # Defect
        self.lbl_defect_val.setText(claim.defect_description)

        # Condition & Accessories
        cond_str = claim.item_condition or _t("warranty_claim.none", default="None")
        acc_str = claim.accessories_received or _t("warranty_claim.none", default="None")
        self.lbl_condition_acc.setText(
            f"<b>{_t('warranty_claim.condition', default='Condition')}:</b> {cond_str} | "
            f"<b>{_t('warranty_claim.accessories', default='Accessories')}:</b> {acc_str}"
        )

        # Resolution box visibility
        if claim.resolution or claim.rejection_reason:
            self.frame_resolution.show()
            res_lines = []
            if claim.resolution:
                res_lines.append(f"<b>{_t('warranty_claim.resolution', default='Resolution')}:</b> {claim.resolution}")
            if claim.rejection_reason:
                res_lines.append(
                    f"<b>{_t('warranty_claim.rejection_reason', default='Rejection Reason')}:</b> {claim.rejection_reason}"
                )
            if claim.resolution_notes:
                res_lines.append(f"<b>{_t('notes', default='Notes')}:</b> {claim.resolution_notes}")
            if claim.replacement_serial:
                res_lines.append(
                    f"<b>{_t('warranty_claim.replacement_serial', default='Replacement Serial')}:</b> {claim.replacement_serial}"
                )
            if claim.charge_customer and claim.charge_customer > Decimal("0.00"):
                res_lines.append(
                    f"<b>{_t('warranty_claim.customer_charge', default='Customer Charge')}:</b> {format_currency(claim.charge_customer)}"
                )
            if claim.repair_cost and claim.repair_cost > Decimal("0.00"):
                res_lines.append(
                    f"<b>{_t('warranty_claim.repair_cost', default='Repair Cost')}:</b> {format_currency(claim.repair_cost)}"
                )
            if claim.collected_by_name:
                c_date = format_datetime(claim.collected_at) if claim.collected_at else ""
                res_lines.append(
                    f"<b>{_t('warranty_claim.collected_by', default='Collected By')}:</b> {claim.collected_by_name} ({c_date})"
                )

            self.lbl_res_content.setText("<br>".join(res_lines))
        else:
            self.frame_resolution.hide()

        # Timeline
        timeline_text = []
        for ev in claim.events:
            t_str = format_datetime(ev.event_time) if ev.event_time else ""
            trans_str = f"{ev.from_status or 'START'} → {ev.to_status}"
            note_str = f" - {ev.notes}" if ev.notes else ""
            timeline_text.append(f"[{t_str}] {trans_str} ({ev.username}){note_str}")
        self.txt_timeline.setPlainText("\n".join(timeline_text))

        # Dynamic Action Buttons
        self._update_action_buttons(claim)

    def _update_action_buttons(self, claim: WarrantyClaimDTO) -> None:
        """Enable, disable, and show relevant action buttons for claim state."""
        st = claim.claim_status

        self.btn_inspect.setVisible(st in ("INTAKE", "SUPPLIER_RETURNED"))
        self.btn_dispatch_supplier.setVisible(st == "IN_INSPECTION")
        self.btn_supplier_returned.setVisible(st == "SUPPLIER_DISPATCHED")
        self.btn_resolve.setVisible(st in ("IN_INSPECTION", "SUPPLIER_RETURNED"))
        self.btn_collect.setVisible(st == "RESOLVED")

        # Rejection & Voiding allowed on active non-final states
        can_reject = st not in ("COLLECTED", "REJECTED", "VOID", "CANCELLED")
        self.btn_reject.setVisible(can_reject)
        self.btn_void.setVisible(can_reject)

        # Print buttons
        self.btn_print_intake.setVisible(True)
        self.btn_print_collection.setVisible(st in ("RESOLVED", "COLLECTED"))

    def _on_new_claim(self) -> None:
        """Open intake dialog for a new claim."""
        dlg = WarrantyClaimIntakeDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_data()

    def _on_begin_inspection(self) -> None:
        """Transition claim to IN_INSPECTION."""
        if not self._selected_claim:
            return
        self._transition_to("IN_INSPECTION", notes="Inspection started")

    def _on_supplier_dispatch(self) -> None:
        """Transition claim to SUPPLIER_DISPATCHED."""
        if not self._selected_claim:
            return
        self._transition_to("SUPPLIER_DISPATCHED", notes="Item dispatched to supplier service center")

    def _on_supplier_returned(self) -> None:
        """Transition claim to SUPPLIER_RETURNED."""
        if not self._selected_claim:
            return
        self._transition_to("SUPPLIER_RETURNED", notes="Item returned from supplier service center")

    def _transition_to(self, to_status: str, notes: str | None = None) -> None:
        """Call service to update status and reload."""
        if not self._selected_claim:
            return
        actor_id = self._get_actor_id()
        if actor_id is None:
            return

        try:
            dto = WarrantyClaimService.transition_status(
                claim_id=self._selected_claim.id,
                to_status=to_status,
                user_id=actor_id,
                notes=notes,
            )
            self._selected_claim = dto
            self.load_data()
        except Exception as e:
            logger.error("Failed to transition status: %s", e)
            QMessageBox.critical(self, _t("common.error", default="Error"), str(e))

    def _on_resolve_claim(self) -> None:
        """Open resolution dialog."""
        if not self._selected_claim:
            return
        dlg = WarrantyClaimResolveDialog(claim=self._selected_claim, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.load_data()

    def _on_mark_collected(self) -> None:
        """Mark resolved claim as collected."""
        if not self._selected_claim:
            return

        default_name = self._selected_claim.customer_name or ""
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self,
            _t("warranty_claim.collect_title", default="Mark Claim Collected"),
            _t("warranty_claim.collector_name_prompt", default="Name of person collecting item:"),
            text=default_name,
        )
        if not ok or not name.strip():
            return

        actor_id = self._get_actor_id()
        if actor_id is None:
            return

        try:
            dto = WarrantyClaimService.mark_collected(
                claim_id=self._selected_claim.id,
                collected_by_name=name.strip(),
                user_id=actor_id,
            )
            self._selected_claim = dto

            # Print collection slip
            self._print_collection_slip(dto)

            QMessageBox.information(
                self,
                _t("common.success", default="Success"),
                _t("warranty_claim.collected_success", default="Item collection recorded successfully"),
            )
            self.load_data()
        except Exception as e:
            logger.error("Failed to mark collected: %s", e)
            QMessageBox.critical(self, _t("common.error", default="Error"), str(e))

    def _on_reject_claim(self) -> None:
        """Reject claim with prompt for mandatory reason."""
        if not self._selected_claim:
            return

        from PyQt6.QtWidgets import QInputDialog

        reason, ok = QInputDialog.getText(
            self,
            _t("warranty_claim.reject_title", default="Reject Warranty Claim"),
            _t("warranty_claim.rejection_reason_prompt", default="Reason for claim rejection:"),
        )
        if not ok or not reason.strip():
            return

        actor_id = self._get_actor_id()
        if actor_id is None:
            return

        try:
            dto = WarrantyClaimService.reject_claim(
                claim_id=self._selected_claim.id,
                reason=reason.strip(),
                user_id=actor_id,
            )
            self._selected_claim = dto
            self.load_data()
        except Exception as e:
            logger.error("Failed to reject claim: %s", e)
            QMessageBox.critical(self, _t("common.error", default="Error"), str(e))

    def _on_void_claim(self) -> None:
        """Void claim administratively with confirmation and reason."""
        if not self._selected_claim:
            return

        from PyQt6.QtWidgets import QInputDialog

        reason, ok = QInputDialog.getText(
            self,
            _t("warranty_claim.void_title", default="Void Warranty Claim"),
            _t("warranty_claim.void_reason_prompt", default="Administrative reason to void claim:"),
        )
        if not ok or not reason.strip():
            return

        actor_id = self._get_actor_id()
        if actor_id is None:
            return

        try:
            dto = WarrantyClaimService.void_claim(
                claim_id=self._selected_claim.id,
                reason=reason.strip(),
                user_id=actor_id,
            )
            self._selected_claim = dto
            self.load_data()
        except Exception as e:
            logger.error("Failed to void claim: %s", e)
            QMessageBox.critical(self, _t("common.error", default="Error"), str(e))

    def _on_print_intake_slip(self) -> None:
        """Print intake slip for current claim."""
        if not self._selected_claim:
            return
        try:
            commands = WarrantyClaimReceiptBuilder.build_intake_slip(self._selected_claim)
            PrintWorker.instance().add_job("print_commands", commands)
            QMessageBox.information(
                self,
                _t("common.success", default="Success"),
                _t("warranty_claim.print_job_sent", default="Print job sent to printer"),
            )
        except Exception as e:
            logger.error("Print intake slip failed: %s", e)
            QMessageBox.critical(self, _t("common.error", default="Error"), str(e))

    def _on_print_collection_slip(self) -> None:
        """Print collection slip for current claim."""
        if not self._selected_claim:
            return
        self._print_collection_slip(self._selected_claim)

    def _print_collection_slip(self, claim: WarrantyClaimDTO) -> None:
        """Dispatch collection slip print job."""
        try:
            commands = WarrantyClaimReceiptBuilder.build_collection_slip(claim)
            PrintWorker.instance().add_job("print_commands", commands)
        except Exception as e:
            logger.warning("Failed to print collection slip: %s", e)

    def _get_actor_id(self) -> int | None:
        """Return authenticated user ID or show error."""
        curr = AuthService.get_current_user()
        if not curr:
            QMessageBox.critical(
                self,
                _t("common.error", default="Error"),
                _t("errors.unauthorized", default="No authenticated user session"),
            )
            return None
        return curr.id


class WarrantyClaimsBoardDialog(QDialog):
    """Modal wrapper dialog for WarrantyClaimsBoardView."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WarrantyClaimsBoardDialog")
        self.setWindowTitle(_t("warranty_claim.board_title", default="Warranty Claims Board"))
        self.resize(1050, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.board_view = WarrantyClaimsBoardView(parent=self)
        layout.addWidget(self.board_view, 1)

        footer_layout, self.btn_close = make_close_footer(on_close=self.accept)
        layout.addLayout(footer_layout)
