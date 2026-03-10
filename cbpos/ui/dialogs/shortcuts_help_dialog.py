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
from cbpos.i18n import _t


class ShortcutsHelpDialog(QDialog):
    """F1 keyboard shortcuts overlay for the Sales view."""

    @staticmethod
    def _get_shortcuts():
        return [
            ("F1", _t("shortcuts.help_screen")),
            ("F2", _t("shortcuts.select_customer")),
            ("F3", _t("shortcuts.advanced_search")),
            ("F4", _t("shortcuts.change_quantity")),
            ("F5", _t("shortcuts.process_payment")),
            ("F6", _t("shortcuts.hold_bill")),
            ("F7", _t("shortcuts.recall_bill")),
            ("F8", _t("shortcuts.open_drawer")),
            ("F10", _t("shortcuts.process_payment")),
            ("F12", _t("shortcuts.quick_close")),
            ("Ctrl+D", _t("shortcuts.open_drawer")),
            ("PgUp", _t("shortcuts.first_cart_item")),
            ("PgDn", _t("shortcuts.last_cart_item")),
            ("Enter", _t("shortcuts.add_product")),
            ("Delete", _t("shortcuts.void_bill")),
            ("Esc", _t("shortcuts.close_cancel")),
        ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("shortcuts.title"))
        self.setFixedSize(450, 580)
        self.setObjectName("ShortcutsHelpDialog")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(15)

        title = QLabel(_t("shortcuts.title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setProperty("class", "dialog-title")
        layout.addWidget(title)

        subtitle = QLabel(_t("shortcuts.subtitle"))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setProperty("class", "muted")
        layout.addWidget(subtitle)

        shortcuts = self._get_shortcuts()
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([_t("shortcuts.col_shortcut"), _t("shortcuts.col_action")])
        table.setRowCount(len(shortcuts))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)

        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 100)

        for row, (key, action) in enumerate(shortcuts):
            key_item = QTableWidgetItem(key)
            key_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            key_item.setForeground(Qt.GlobalColor.cyan)
            table.setItem(row, 0, key_item)

            action_item = QTableWidgetItem(action)
            table.setItem(row, 1, action_item)

        layout.addWidget(table)

        btn_close = QPushButton(_t("shortcuts.close_esc"))
        btn_close.setObjectName("BtnCancel")
        btn_close.setFixedHeight(35)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
