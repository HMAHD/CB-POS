"""Dialog for selecting serial numbers when performing partial refunds (#823, #824)."""

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard


class SerialRefundSelectionDialog(QDialog):
    """Modal dialog allowing the cashier to choose which serial units are being refunded."""

    def __init__(
        self,
        product_name: str,
        active_serials: list[str],
        required_count: int,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("SerialRefundSelectionDialog")
        self.product_name = product_name
        self.active_serials = list(active_serials or [])
        self.required_count = max(1, int(required_count))

        self._checkboxes: list[QCheckBox] = []

        self.setWindowTitle(_t("refund.select_serials_title", default="Select Serials to Refund"))
        self.setMinimumWidth(440)
        self.resize(460, min(560, 180 + len(self.active_serials) * 45))

        self.init_ui()
        install_wheel_guard(self)

    def init_ui(self) -> None:
        """Initialize the dialog layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Info
        lbl_product = QLabel(self.product_name)
        lbl_product.setProperty("class", "dialog-title")
        layout.addWidget(lbl_product)

        lbl_hint = QLabel(
            _t(
                "refund.select_serials_hint",
                count=self.required_count,
                default=f"Select {self.required_count} serial number(s) to refund:",
            )
        )
        lbl_hint.setProperty("class", "muted")
        layout.addWidget(lbl_hint)

        # Scrollable checkboxes list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(4, 4, 4, 4)
        c_layout.setSpacing(8)

        for sn in self.active_serials:
            chk = QCheckBox(sn)
            chk.setObjectName(f"chk_serial_{sn}")
            chk.toggled.connect(self._on_toggled)
            c_layout.addWidget(chk)
            self._checkboxes.append(chk)

        c_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Counter Label
        self.lbl_counter = QLabel("")
        self.lbl_counter.setProperty("class", "muted")
        layout.addWidget(self.lbl_counter)

        # Action Buttons
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 8, 0, 0)
        footer.setSpacing(10)

        self.btn_cancel = QPushButton(_t("common.cancel", default="Cancel"))
        self.btn_cancel.setFixedHeight(40)
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)

        footer.addStretch()

        self.btn_confirm = QPushButton(_t("common.confirm", default="Confirm"))
        self.btn_confirm.setFixedHeight(40)
        self.btn_confirm.setProperty("class", "primary")
        self.btn_confirm.clicked.connect(self.accept)
        footer.addWidget(self.btn_confirm)

        layout.addLayout(footer)

        self._update_counter()

    def _on_toggled(self) -> None:
        self._update_counter()

    def _update_counter(self) -> None:
        selected = len(self.get_selected_serials())
        self.lbl_counter.setText(
            _t(
                "refund.serials_selected_count",
                selected=selected,
                required=self.required_count,
                default=f"Selected {selected} of {self.required_count} required",
            )
        )
        self.btn_confirm.setEnabled(selected == self.required_count)

    def get_selected_serials(self) -> list[str]:
        """Return the list of checked serial numbers."""
        return [chk.text() for chk in self._checkboxes if chk.isChecked()]
