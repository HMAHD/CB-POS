"""Serial / IMEI entry dialog for capturing per-unit serial numbers at checkout (#823)."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.product_service import ProductService
from cbpos.core.services.warranty_service import WarrantyService
from cbpos.core.utils.validators import validate_imei_luhn
from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class SerialEntryDialog(QDialog):
    """Modal dialog for scanning or typing serial/IMEI numbers per unit."""

    accepts_scans = True

    def __init__(
        self,
        product,
        unit_count: int,
        parent=None,
        serial_mode: str = "REQUIRED",
        existing_serials: list[str | None] | None = None,
        external_cart_serials: set[str] | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("SerialEntryDialog")
        self.product = product
        self.unit_count = max(1, int(unit_count))
        self.serial_mode = (serial_mode or "REQUIRED").upper()
        self.existing_serials = list(existing_serials or [])
        self.external_cart_serials = set(external_cart_serials or set())

        self._line_edits: list[QLineEdit] = []
        self._warning_labels: list[QLabel] = []
        self._error_labels: list[QLabel] = []
        self.btn_skip: QPushButton | None = None

        self.setWindowTitle(_t("serial_entry.title", default="Enter Serial / IMEI Numbers"))
        self.setMinimumWidth(520)
        self.resize(540, min(650, 200 + self.unit_count * 75))

        self.init_ui()
        install_wheel_guard(self)
        self._populate_existing()
        QTimer.singleShot(50, self._focus_first_empty)

    def init_ui(self) -> None:
        """Initialize dialog layout, inputs and action buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Info
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        prod_name = str(ProductService.display_name(self.product)) if self.product else ""
        self.lbl_product = QLabel(prod_name)
        self.lbl_product.setProperty("class", "dialog-title")
        header_layout.addWidget(self.lbl_product)

        hint_text = (
            _t(
                "serial_entry.hint_required",
                count=self.unit_count,
                default=f"Please enter or scan {self.unit_count} serial number(s).",
            )
            if self.serial_mode == "REQUIRED"
            else _t(
                "serial_entry.hint_optional",
                count=self.unit_count,
                default=f"Enter serial numbers for {self.unit_count} unit(s), or Skip.",
            )
        )
        self.lbl_hint = QLabel(hint_text)
        self.lbl_hint.setProperty("class", "muted")
        self.lbl_hint.setWordWrap(True)
        header_layout.addWidget(self.lbl_hint)

        layout.addWidget(header_widget)

        # Scrollable Rows Container
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        rows_container = QWidget()
        rows_layout = QVBoxLayout(rows_container)
        rows_layout.setContentsMargins(0, 8, 0, 8)
        rows_layout.setSpacing(10)

        for i in range(1, self.unit_count + 1):
            row_card = QWidget()
            row_card.setObjectName("SerialRowCard")
            row_layout = QVBoxLayout(row_card)
            row_layout.setContentsMargins(4, 4, 4, 4)
            row_layout.setSpacing(4)

            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.setSpacing(8)

            unit_lbl = QLabel(_t("serial_entry.unit_label", index=i, default=f"Unit {i}:"))
            unit_lbl.setFixedWidth(80)
            top_row.addWidget(unit_lbl)

            edit = QLineEdit()
            edit.setFixedHeight(44)
            edit.setPlaceholderText(_t("serial_entry.input_placeholder", default="Scan or enter serial / IMEI"))
            edit.returnPressed.connect(lambda idx=i - 1: self._on_field_enter(idx))
            top_row.addWidget(edit, 1)

            row_layout.addLayout(top_row)

            # Warning label (Luhn / historical active warranty)
            warn_lbl = QLabel("")
            warn_lbl.setObjectName("SerialWarningLabel")
            warn_lbl.setStyleSheet("color: #FFB300; font-size: 11px;")
            warn_lbl.setVisible(False)
            row_layout.addWidget(warn_lbl)

            # Error label (Duplicate)
            err_lbl = QLabel("")
            err_lbl.setObjectName("SerialErrorLabel")
            err_lbl.setStyleSheet("color: #DC3545; font-size: 11px; font-weight: bold;")
            err_lbl.setVisible(False)
            row_layout.addWidget(err_lbl)

            rows_layout.addWidget(row_card)
            self._line_edits.append(edit)
            self._warning_labels.append(warn_lbl)
            self._error_labels.append(err_lbl)

        rows_layout.addStretch()
        scroll_area.setWidget(rows_container)
        layout.addWidget(scroll_area, 1)

        # Action Buttons
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 8, 0, 0)
        footer_layout.setSpacing(10)

        self.btn_cancel = QPushButton(_t("common.cancel", default="Cancel"))
        self.btn_cancel.setFixedHeight(44)
        self.btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(self.btn_cancel)

        if self.serial_mode == "OPTIONAL":
            self.btn_skip = QPushButton(_t("serial_entry.btn_skip", default="Skip"))
            self.btn_skip.setFixedHeight(44)
            self.btn_skip.clicked.connect(self._on_skip)
            footer_layout.addWidget(self.btn_skip)

        footer_layout.addStretch()

        self.btn_confirm = QPushButton(_t("common.confirm", default="Confirm"))
        self.btn_confirm.setFixedHeight(44)
        self.btn_confirm.setProperty("class", "primary")
        self.btn_confirm.clicked.connect(self._on_confirm)
        footer_layout.addWidget(self.btn_confirm)

        layout.addLayout(footer_layout)

    def _populate_existing(self) -> None:
        """Populate initial inputs from existing serials."""
        for idx, serial in enumerate(self.existing_serials[: self.unit_count]):
            if serial and str(serial).strip():
                self._line_edits[idx].setText(str(serial).strip().upper())
                self._validate_field(idx, show_warnings=False)

    def _focus_first_empty(self) -> None:
        """Focus the first empty input row."""
        for edit in self._line_edits:
            if not edit.text().strip():
                edit.setFocus()
                return
        if self._line_edits:
            self._line_edits[0].setFocus()

    def process_barcode_external(self, barcode: str) -> bool:
        """Receive barcode scan from main application hook."""
        clean = (barcode or "").strip().upper()
        if not clean:
            return False

        target_edit = None
        target_idx = 0
        focused = self.focusWidget()
        for idx, edit in enumerate(self._line_edits):
            if edit == focused:
                target_edit = edit
                target_idx = idx
                break

        if target_edit is None:
            for idx, edit in enumerate(self._line_edits):
                if not edit.text().strip():
                    target_edit = edit
                    target_idx = idx
                    break

        if target_edit is None and self._line_edits:
            target_edit = self._line_edits[0]
            target_idx = 0

        if target_edit:
            target_edit.setText(clean)
            self._on_field_enter(target_idx)
            return True
        return False

    def _validate_field(self, index: int, show_warnings: bool = True) -> bool:
        """Validate single field for uniqueness, Luhn and active warranty."""
        if not (0 <= index < len(self._line_edits)):
            return False

        edit = self._line_edits[index]
        err_lbl = self._error_labels[index]
        warn_lbl = self._warning_labels[index]

        raw = edit.text().strip()
        if not raw:
            err_lbl.setVisible(False)
            warn_lbl.setVisible(False)
            return self.serial_mode == "OPTIONAL"

        val = raw.upper()
        edit.setText(val)

        # 1. Uniqueness check in dialog
        for other_idx, other_edit in enumerate(self._line_edits):
            if other_idx != index and other_edit.text().strip().upper() == val:
                err_lbl.setText(_t("serial_entry.err_duplicate_in_dialog", default="Duplicate serial entered"))
                err_lbl.setVisible(True)
                return False

        # 2. Uniqueness check against other cart lines
        if val in self.external_cart_serials:
            err_lbl.setText(_t("serial_entry.err_duplicate_in_cart", default="Serial already in another cart line"))
            err_lbl.setVisible(True)
            return False

        err_lbl.setVisible(False)

        # 3. Advisory Warnings (Non-blocking)
        if show_warnings:
            warnings = []
            if len(val) == 15 and val.isdigit():
                if not validate_imei_luhn(val):
                    warnings.append(_t("serial_entry.imei_luhn_warning", default="IMEI check digit mismatch (warning)"))

            if self.product and getattr(self.product, "id", None):
                active = WarrantyService.find_active_warranties_by_serials(self.product.id, [val])
                if val in active:
                    doc_no = active[val]
                    warnings.append(
                        _t(
                            "serial_entry.active_warranty_warning",
                            receipt=doc_no,
                            default=f"Active warranty exists on bill {doc_no}",
                        )
                    )

            if warnings:
                warn_lbl.setText(" • ".join(warnings))
                warn_lbl.setVisible(True)
            else:
                warn_lbl.setVisible(False)

        return True

    def _on_field_enter(self, index: int) -> None:
        """Handle Enter key in input field: validate and advance."""
        valid = self._validate_field(index, show_warnings=True)
        if not valid:
            self._line_edits[index].setFocus()
            self._line_edits[index].selectAll()
            return

        # Advance to next empty row
        for next_idx in range(index + 1, self.unit_count):
            if not self._line_edits[next_idx].text().strip():
                self._line_edits[next_idx].setFocus()
                return

        # If this was the last row or all rows filled, confirm
        if all(self._line_edits[i].text().strip() for i in range(self.unit_count)):
            self._on_confirm()
        elif index + 1 < self.unit_count:
            self._line_edits[index + 1].setFocus()

    def _on_skip(self) -> None:
        """Skip serial capture (Optional mode only)."""
        if self.serial_mode != "OPTIONAL":
            return
        # Clear unfilled fields and accept
        for edit in self._line_edits:
            if not edit.text().strip():
                edit.clear()
        self.accept()

    def _on_confirm(self) -> None:
        """Validate all rows and accept dialog if valid."""
        for idx in range(self.unit_count):
            edit = self._line_edits[idx]
            val = edit.text().strip()
            if self.serial_mode == "REQUIRED" and not val:
                self._error_labels[idx].setText(_t("serial_entry.err_required", default="Serial number is required"))
                self._error_labels[idx].setVisible(True)
                edit.setFocus()
                return
            if not self._validate_field(idx, show_warnings=True):
                edit.setFocus()
                return

        self.accept()

    def get_serials(self) -> list[str | None]:
        """Return list of captured normalized serials."""
        res: list[str | None] = []
        for edit in self._line_edits:
            val = edit.text().strip().upper()
            res.append(val if val else None)
        return res
