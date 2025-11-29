from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QScrollArea,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from cbpos.core.services.transaction_service import TransactionService


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
        self.setStyleSheet(
            "background-color: #001F3F; border-bottom: 2px solid #003366;"
        )

        self.init_ui()
        self.refresh_tabs()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # 1. Label
        lbl_title = QLabel("ORDERS:")
        lbl_title.setStyleSheet("color: #AAAAAA; font-weight: bold;")
        layout.addWidget(lbl_title)

        # 2. Scroll Area for Tabs
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.tabs_container = QWidget()
        self.tabs_layout = QHBoxLayout(self.tabs_container)
        self.tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs_layout.setSpacing(5)
        self.tabs_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.scroll_area.setWidget(self.tabs_container)
        layout.addWidget(self.scroll_area)

        # 3. New Order Button (+)
        self.btn_new = QPushButton("+")
        self.btn_new.setFixedSize(50, 40)
        self.btn_new.setStyleSheet(
            """
            QPushButton {
                background-color: #39FF14;
                color: black;
                font-weight: bold;
                font-size: 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #32CD32;
            }
        """
        )
        self.btn_new.clicked.connect(self.new_tab_requested.emit)
        layout.addWidget(self.btn_new)

    def refresh_tabs(self):
        """Fetch held bills and rebuild tabs."""
        # Clear existing
        for i in reversed(range(self.tabs_layout.count())):
            widget = self.tabs_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        # Fetch from DB
        held_bills = TransactionService.get_held_bills()

        for i, bill in enumerate(held_bills):
            # Format: "Order {ID} ({Time})"
            time_str = bill.timestamp.strftime("%H:%M")
            label = f"#{bill.id} {time_str}"
            if bill.note:
                label += f" - {bill.note}"

            btn = QPushButton(label)
            btn.setFixedHeight(40)
            btn.setCheckable(True)
            # Style
            btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #0074D9;
                    color: white;
                    font-weight: bold;
                    padding: 5px 15px;
                    border-radius: 5px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #005bb5;
                }
            """
            )

            # Connect
            # Use closure to capture bill.id
            btn.clicked.connect(
                lambda checked, bid=bill.id: self.tab_switched.emit(bid)
            )

            self.tabs_layout.addWidget(btn)

        # Add stretch to keep buttons left-aligned
        self.tabs_layout.addStretch()
