from decimal import Decimal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QDialog,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDoubleSpinBox,
    QDateTimeEdit,
    QDialogButtonBox,
    QMessageBox,
    QLabel,
)
from PyQt6.QtCore import QDateTime
from cbpos.core.services.promotion_service import PromotionService


class PromotionView(QWidget):
    def __init__(self):
        super().__init__()
        self.promotion_service = PromotionService()
        self.setup_ui()
        self.load_promotions()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        lbl_title = QLabel("Promotions & Campaigns")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        header.addWidget(lbl_title)
        header.addStretch()

        btn_add = QPushButton("Create Promotion")
        btn_add.setStyleSheet(
            "background-color: #00BCEB; color: white; font-weight: bold; padding: 8px;"
        )
        btn_add.clicked.connect(self.add_promotion)
        header.addWidget(btn_add)

        layout.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Type", "Value", "Start", "End", "Status"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def load_promotions(self):
        promos = self.promotion_service.get_all_promotions()
        self.table.setRowCount(0)
        for p in promos:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(p.name))
            self.table.setItem(row, 1, QTableWidgetItem(p.type))
            self.table.setItem(row, 2, QTableWidgetItem("{:.2f}".format(p.value)))
            self.table.setItem(
                row, 3, QTableWidgetItem(p.start_time.strftime("%Y-%m-%d %H:%M"))
            )
            self.table.setItem(
                row, 4, QTableWidgetItem(p.end_time.strftime("%Y-%m-%d %H:%M"))
            )

            status = "Active" if p.is_active else "Inactive"
            self.table.setItem(row, 5, QTableWidgetItem(status))

    def add_promotion(self):
        dialog = PromotionDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                self.promotion_service.create_promotion(**data)
                self.load_promotions()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))


class PromotionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Promotion")
        self.setMinimumWidth(400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit()

        self.type_combo = QComboBox()
        self.type_combo.addItems(["PERCENTAGE", "FIXED_AMOUNT"])

        self.value_input = QDoubleSpinBox()
        self.value_input.setRange(0, 100000)
        self.value_input.setDecimals(2)

        self.start_dt = QDateTimeEdit()
        self.start_dt.setDateTime(QDateTime.currentDateTime())
        self.start_dt.setCalendarPopup(True)

        self.end_dt = QDateTimeEdit()
        self.end_dt.setDateTime(QDateTime.currentDateTime().addDays(7))
        self.end_dt.setCalendarPopup(True)

        self.days_input = QLineEdit()
        self.days_input.setPlaceholderText("0,1,2 (0=Mon, 6=Sun) - Leave empty for all")

        form.addRow("Name:", self.name_input)
        form.addRow("Type:", self.type_combo)
        form.addRow("Value:", self.value_input)
        form.addRow("Start Time:", self.start_dt)
        form.addRow("End Time:", self.end_dt)
        form.addRow("Days (Optional):", self.days_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return {
            "name": self.name_input.text(),
            "type": self.type_combo.currentText(),
            "value": Decimal(str(self.value_input.value())),
            "start_time": self.start_dt.dateTime().toPyDateTime(),
            "end_time": self.end_dt.dateTime().toPyDateTime(),
            "days_of_week": self.days_input.text().strip() or None,
        }
