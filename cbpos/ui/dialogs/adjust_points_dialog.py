"""
Dialog for adjusting customer loyalty points with signed-mode safety.
"""

import logging

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.loyalty_service import LoyaltyService
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons
from cbpos.ui.styles.style_helpers import set_status_class
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


def _set_button_icon(btn: QPushButton, icon_name: str, color: str, pad_right: int = 8, size: int = 14) -> None:
    """Set button icon with transparent trailing padding to ensure clear spacing before label text."""
    base_pixmap = Icons.get(icon_name, color).pixmap(size, size)
    padded = QPixmap(size + pad_right, size)
    padded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(padded)
    painter.drawPixmap(0, 0, base_pixmap)
    painter.end()
    btn.setIconSize(QSize(size + pad_right, size))
    btn.setIcon(QIcon(padded))


class AdjustPointsDialog(QDialog):
    """
    Dedicated dialog for adjusting customer loyalty points.
    Features signed-mode segmented toggle, strictly positive input,
    quick increment chips, live balance preview, and non-negative guard.
    """

    MODE_ADD = "add"
    MODE_DEDUCT = "deduct"
    MODE_SET = "set"

    def __init__(self, customer, parent=None):
        super().__init__(parent)
        self.customer = customer
        self.mode = self.MODE_ADD

        self.setWindowTitle(_t("adjust_points.title"))
        self.setMinimumWidth(480)
        self.setObjectName("AdjustPointsDialog")

        self._init_ui()
        install_wheel_guard(self)
        self._recalculate()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Customer Hero Card
        header_card = QFrame()
        header_card.setObjectName("AdjustHeaderCard")
        card_layout = QHBoxLayout(header_card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(12)

        lbl_avatar = QLabel()
        lbl_avatar.setPixmap(Icons.get("fa5s.star", "#F59E0B").pixmap(30, 30))
        card_layout.addWidget(lbl_avatar)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        lbl_name = QLabel(self.customer.name)
        lbl_name.setObjectName("AdjustCustName")
        info_layout.addWidget(lbl_name)

        curr_pts = getattr(self.customer, "loyalty_points", 0) or 0
        lbl_pts = QLabel(f"{_t('adjust_points.current_points')} {curr_pts} pts")
        lbl_pts.setObjectName("AdjustCustPoints")
        info_layout.addWidget(lbl_pts)

        card_layout.addLayout(info_layout)
        card_layout.addStretch()
        layout.addWidget(header_card)

        # 2. Segmented Mode Selector
        mode_label = QLabel(_t("customer_editor.points_header_type"))
        mode_label.setProperty("class", "muted")
        layout.addWidget(mode_label)

        mode_box = QHBoxLayout()
        mode_box.setSpacing(8)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        self.btn_mode_add = QPushButton(_t("adjust_points.mode_add"))
        self.btn_mode_add.setCheckable(True)
        self.btn_mode_add.setChecked(True)
        self.btn_mode_add.setObjectName("ModeAddPtsBtn")
        self.btn_mode_add.clicked.connect(lambda: self.set_mode(self.MODE_ADD))
        self.btn_group.addButton(self.btn_mode_add)
        mode_box.addWidget(self.btn_mode_add)

        self.btn_mode_deduct = QPushButton(_t("adjust_points.mode_deduct"))
        self.btn_mode_deduct.setCheckable(True)
        self.btn_mode_deduct.setObjectName("ModeDeductPtsBtn")
        self.btn_mode_deduct.clicked.connect(lambda: self.set_mode(self.MODE_DEDUCT))
        self.btn_group.addButton(self.btn_mode_deduct)
        mode_box.addWidget(self.btn_mode_deduct)

        self.btn_mode_set = QPushButton(_t("adjust_points.mode_set"))
        self.btn_mode_set.setCheckable(True)
        self.btn_mode_set.setObjectName("ModeSetPtsBtn")
        self.btn_mode_set.clicked.connect(lambda: self.set_mode(self.MODE_SET))
        self.btn_group.addButton(self.btn_mode_set)
        mode_box.addWidget(self.btn_mode_set)

        layout.addLayout(mode_box)

        # 3. Points Input & Quick increment chips
        pts_label = QLabel(_t("adjust_points.points"))
        pts_label.setProperty("class", "muted")
        layout.addWidget(pts_label)

        spin_chips_layout = QHBoxLayout()
        spin_chips_layout.setSpacing(10)

        self.points_spin = QSpinBox()
        self.points_spin.setRange(1, 999999)
        self.points_spin.setValue(10)
        self.points_spin.setSuffix(" pts")
        self.points_spin.setObjectName("AdjustPointsSpin")
        self.points_spin.valueChanged.connect(self._recalculate)
        spin_chips_layout.addWidget(self.points_spin, stretch=1)

        # Increment chips
        for inc in [10, 50, 100, 500]:
            btn_inc = QPushButton(f"+{inc}")
            btn_inc.setProperty("class", "secondary")
            btn_inc.clicked.connect(lambda _, v=inc: self._add_spin_val(v))
            spin_chips_layout.addWidget(btn_inc)

        layout.addLayout(spin_chips_layout)

        # 4. Live Calculation & Preview Card
        self.preview_card = QFrame()
        self.preview_card.setObjectName("AdjustPreviewCard")
        prev_layout = QVBoxLayout(self.preview_card)
        prev_layout.setContentsMargins(12, 10, 12, 10)
        prev_layout.setSpacing(4)

        self.lbl_formula = QLabel()
        self.lbl_formula.setObjectName("AdjustFormulaLabel")
        prev_layout.addWidget(self.lbl_formula)

        self.lbl_preview = QLabel()
        self.lbl_preview.setObjectName("AdjustPreviewLabel")
        prev_layout.addWidget(self.lbl_preview)

        layout.addWidget(self.preview_card)

        # 5. Reason Input & Chips
        reason_label = QLabel(_t("adjust_points.reason"))
        reason_label.setProperty("class", "muted")
        layout.addWidget(reason_label)

        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText(_t("adjust_points.reason_placeholder"))
        self.reason_edit.setObjectName("AdjustReasonEdit")
        self.reason_edit.textChanged.connect(self._recalculate)
        layout.addWidget(self.reason_edit)

        # Quick chips
        chips_layout = QHBoxLayout()
        chips_layout.setSpacing(6)
        chips = [
            "Promotional Bonus",
            "Customer Goodwill",
            "Redemption Correction",
            "Data Entry Fix",
        ]
        for chip_text in chips:
            btn_chip = QPushButton(chip_text)
            btn_chip.setProperty("class", "chip")
            btn_chip.clicked.connect(lambda _, t=chip_text: self.reason_edit.setText(t))
            chips_layout.addWidget(btn_chip)
        chips_layout.addStretch()
        layout.addLayout(chips_layout)

        # 6. Action buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        btn_cancel = QPushButton(_t("common.cancel"))
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.setProperty("class", "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        self.btn_save = QPushButton(_t("adjust_points.confirm"))
        self.btn_save.setProperty("class", "accent")
        _set_button_icon(self.btn_save, "fa5s.check", "#FFFFFF", pad_right=8, size=13)
        self.btn_save.clicked.connect(self.save)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

    def _add_spin_val(self, inc: int) -> None:
        self.points_spin.setValue(self.points_spin.value() + inc)

    def set_mode(self, mode: str) -> None:
        """Switch adjustment mode."""
        self.mode = mode
        if mode == self.MODE_ADD:
            self.btn_mode_add.setChecked(True)
        elif mode == self.MODE_DEDUCT:
            self.btn_mode_deduct.setChecked(True)
        elif mode == self.MODE_SET:
            self.btn_mode_set.setChecked(True)
        self._recalculate()

    def calculate_delta(self) -> int:
        """Calculate the points delta."""
        pts = self.points_spin.value()
        curr = getattr(self.customer, "loyalty_points", 0) or 0
        if self.mode == self.MODE_ADD:
            return pts
        elif self.mode == self.MODE_DEDUCT:
            return -pts
        else:  # MODE_SET
            return pts - curr

    def calculate_new_balance(self) -> int:
        """Calculate the resulting points balance."""
        curr = getattr(self.customer, "loyalty_points", 0) or 0
        return curr + self.calculate_delta()

    def _recalculate(self) -> None:
        """Update formula and preview display."""
        curr = getattr(self.customer, "loyalty_points", 0) or 0
        pts = self.points_spin.value()
        new_pts = self.calculate_new_balance()

        if self.mode == self.MODE_ADD:
            formula = f"{curr} + {pts}"
        elif self.mode == self.MODE_DEDUCT:
            formula = f"{curr} - {pts}"
        else:
            formula = f"= {pts}"

        self.lbl_formula.setText(f"Calculation: {formula}")
        self.lbl_preview.setText(_t("adjust_points.preview", value=new_pts))

        if new_pts < 0:
            set_status_class(self.lbl_preview, "status-err")
        else:
            set_status_class(self.lbl_preview, "")

    def validate(self) -> bool:
        """Validate input values."""
        if self.points_spin.value() <= 0:
            return False
        if self.calculate_new_balance() < 0:
            return False
        return bool(self.reason_edit.text().strip())

    def save(self) -> None:
        """Record the points adjustment."""
        if not self.validate():
            if self.points_spin.value() <= 0:
                QMessageBox.warning(self, _t("common.error"), _t("adjust_points.invalid_points"))
            elif self.calculate_new_balance() < 0:
                QMessageBox.warning(self, _t("common.error"), _t("adjust_points.below_zero"))
            else:
                QMessageBox.warning(self, _t("common.error"), _t("adjust_points.reason_required"))
            return

        current_user = AuthService.get_current_user()
        user_id = current_user.id if current_user else 1

        delta = self.calculate_delta()
        reason = self.reason_edit.text().strip()

        try:
            entry = LoyaltyService.adjust_points(
                customer_id=self.customer.id,
                points_delta=delta,
                reason=reason,
                user_id=user_id,
            )
            self.customer.loyalty_points = entry.balance_after
            self.accept()
        except Exception as e:
            logger.error("Failed to record points adjustment: %s", e)
            QMessageBox.critical(self, _t("common.error"), str(e))
