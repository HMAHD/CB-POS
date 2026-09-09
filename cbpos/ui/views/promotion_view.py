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
from cbpos.i18n import _t, register_language_callback, unregister_language_callback
from cbpos.ui.widgets.table_helpers import configure_table_columns


class PromotionView(QWidget):
    def __init__(self):
        super().__init__()
        self.promotion_service = PromotionService()
        self.init_ui()
        self.load_promotions()

        self.retranslate_ui()
        register_language_callback(self.retranslate_ui)
        self.destroyed.connect(lambda: unregister_language_callback(self.retranslate_ui))

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        self.lbl_title = QLabel()
        self.lbl_title.setProperty("class", "dialog-title")
        header.addWidget(self.lbl_title)
        header.addStretch()

        self.btn_add = QPushButton()
        self.btn_add.setProperty("class", "accent")
        self.btn_add.clicked.connect(self.add_promotion)
        header.addWidget(self.btn_add)

        layout.addLayout(header)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        configure_table_columns(
            self.table.horizontalHeader(),
            {
                0: QHeaderView.ResizeMode.Stretch,  # Name - needs the room
                1: QHeaderView.ResizeMode.ResizeToContents,  # Type
                2: QHeaderView.ResizeMode.ResizeToContents,  # Value
                3: QHeaderView.ResizeMode.ResizeToContents,  # Start
                4: QHeaderView.ResizeMode.ResizeToContents,  # End
                5: QHeaderView.ResizeMode.ResizeToContents,  # Status
            },
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def retranslate_ui(self):
        self.lbl_title.setText(_t("promotion.title"))
        self.btn_add.setText(_t("promotion.create_promotion"))
        self.table.setHorizontalHeaderLabels(
            [
                _t("common.name"),
                _t("promotion.type"),
                _t("promotion.value"),
                _t("promotion.start"),
                _t("promotion.end"),
                _t("common.status"),
            ]
        )

    def load_promotions(self):
        promos = self.promotion_service.get_all_promotions()
        self.table.setRowCount(0)
        for p in promos:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(p.name))
            self.table.setItem(row, 1, QTableWidgetItem(p.type))
            self.table.setItem(row, 2, QTableWidgetItem("{:.2f}".format(p.value)))
            self.table.setItem(row, 3, QTableWidgetItem(p.start_time.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 4, QTableWidgetItem(p.end_time.strftime("%Y-%m-%d %H:%M")))

            status = _t("common.active") if p.is_active else _t("common.inactive")
            self.table.setItem(row, 5, QTableWidgetItem(status))

    def add_promotion(self):
        dialog = PromotionDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                self.promotion_service.create_promotion(**data)
                self.load_promotions()
            except Exception as e:
                QMessageBox.critical(self, _t("common.error"), str(e))


class PromotionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("promotion.new_promotion"))
        self.setMinimumWidth(400)
        self.init_ui()

    def init_ui(self):
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
        self.days_input.setPlaceholderText(_t("promotion.days_placeholder"))

        form.addRow(_t("promotion.name_label"), self.name_input)
        form.addRow(_t("promotion.type_label"), self.type_combo)
        form.addRow(_t("promotion.value_label"), self.value_input)
        form.addRow(_t("promotion.start_time_label"), self.start_dt)
        form.addRow(_t("promotion.end_time_label"), self.end_dt)
        form.addRow(_t("promotion.days_label"), self.days_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
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
