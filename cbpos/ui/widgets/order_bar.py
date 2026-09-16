from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
)

from cbpos.core.services.suspended_transaction_service import SuspendedTransactionService
from cbpos.i18n import _t, register_language_callback, unregister_language_callback


class OrderBar(QWidget):
    """
    A horizontal bar displaying active orders (Held Bills) as tabs.
    Implements 'Database-First' switching:
    - Switching tabs holds the current cart and recalls the target.
    """

    tab_switched = pyqtSignal(int)  # Emits suspended_id
    new_tab_requested = pyqtSignal()  # Request to clear current and start new

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setObjectName("OrderBar")
        self._active_bill_id: int | None = None  # Currently active (recalled) bill ID

        self.init_ui()
        self.refresh_tabs()

        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # 1. Label
        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "muted")
        layout.addWidget(self.lbl_title)

        # 2. Scroll Area for Tabs
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setProperty("class", "transparent")
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.tabs_container = QWidget()
        self.tabs_layout = QHBoxLayout(self.tabs_container)
        self.tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs_layout.setSpacing(5)

        self.scroll_area.setWidget(self.tabs_container)
        layout.addWidget(self.scroll_area)

        # 3. New Order Button (+)
        self.btn_new = QPushButton()
        self.btn_new.setFixedSize(50, 40)
        self.btn_new.setProperty("class", "primary")
        self.btn_new.clicked.connect(self.new_tab_requested.emit)
        layout.addWidget(self.btn_new)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Update all translatable widget text (called on language change)."""
        self.lbl_title.setText(_t("orders.title"))
        self.btn_new.setText(_t("orders.new_order"))
        # Refresh tabs to re-translate "Current" label
        self.refresh_tabs()

    def set_active_bill(self, bill_id: int | None) -> None:
        """Track which bill is currently loaded in the cart."""
        self._active_bill_id = bill_id

    def refresh_tabs(self):
        """Fetch held bills and rebuild tabs."""
        # Clear existing (widgets and spacers)
        while self.tabs_layout.count():
            item = self.tabs_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Current order tab (always shown, always active)
        if self._active_bill_id is not None:
            current_label = _t("orders.current_with_id", id=self._active_bill_id)
        else:
            current_label = _t("orders.current")
        btn_current = QPushButton(current_label)
        btn_current.setFixedHeight(40)
        btn_current.setCheckable(True)
        btn_current.setChecked(True)
        btn_current.setProperty("class", "accent")
        btn_current.setStyleSheet("font-weight: bold; border-bottom: 3px solid #00BCEB;")
        btn_current.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabs_layout.addWidget(btn_current)

        # Fetch from DB
        held_bills = SuspendedTransactionService.get_held_bills()

        for _i, bill in enumerate(held_bills):
            # Format: "Order {ID} ({Time})"
            time_str = bill.timestamp.strftime("%H:%M")
            label = f"#{bill.id} {time_str}"
            if bill.note:
                label += f" - {bill.note}"

            btn = QPushButton(label)
            btn.setFixedHeight(40)
            btn.setCheckable(True)
            btn.setProperty("class", "accent")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            # Connect
            # Use closure to capture bill.id
            btn.clicked.connect(lambda checked, bid=bill.id: self.tab_switched.emit(bid))

            self.tabs_layout.addWidget(btn)

        # Add stretch to keep buttons left-aligned
        self.tabs_layout.addStretch()
