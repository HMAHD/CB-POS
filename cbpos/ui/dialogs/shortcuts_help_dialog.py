from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
)
from PyQt6.QtCore import Qt


class ShortcutsHelpDialog(QDialog):
    """F1 keyboard shortcuts overlay for the Sales view."""

    SHORTCUTS = [
        ("F1", "This help screen"),
        ("F2", "Select customer"),
        ("F3", "Advanced search"),
        ("F4", "Change line quantity"),
        ("F5", "Process payment"),
        ("F6", "Hold / Suspend bill"),
        ("F7", "Recall suspended bill"),
        ("F8", "Open cash drawer"),
        ("F10", "Process payment"),
        ("F12", "Quick close (cash)"),
        ("Ctrl+D", "Open cash drawer"),
        ("PgUp", "Select first cart item"),
        ("PgDn", "Select last cart item"),
        ("Enter", "Add product from search"),
        ("Delete", "Void current bill"),
        ("Esc", "Close dialog / Cancel"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setFixedSize(450, 580)
        self.setObjectName("ShortcutsHelpDialog")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        title = QLabel("Keyboard Shortcuts")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        subtitle = QLabel("Press F1 anytime to see this screen")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setProperty("class", "muted")
        layout.addWidget(subtitle)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Shortcut", "Action"])
        table.setRowCount(len(self.SHORTCUTS))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)

        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 100)

        for row, (key, action) in enumerate(self.SHORTCUTS):
            key_item = QTableWidgetItem(key)
            key_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            key_item.setForeground(Qt.GlobalColor.cyan)
            table.setItem(row, 0, key_item)

            action_item = QTableWidgetItem(action)
            table.setItem(row, 1, action_item)

        layout.addWidget(table)

        btn_close = QPushButton("Close (Esc)")
        btn_close.setObjectName("BtnCancel")
        btn_close.setFixedHeight(35)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
