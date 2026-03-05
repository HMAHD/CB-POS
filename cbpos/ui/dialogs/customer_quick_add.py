from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from cbpos.core.services.customer_service import CustomerService


class CustomerQuickAddDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.customer_service = CustomerService()
        self.created_customer = None

        self.setWindowTitle("Quick Add Customer")
        self.setMinimumWidth(300)
        self.setObjectName("CustomerQuickAddDialog")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()

        form.addRow("Name:", self.name_input)
        form.addRow("Phone:", self.phone_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.name_input.setFocus()

    def save(self):
        data = {
            "name": self.name_input.text().strip(),
            "phone": self.phone_input.text().strip() or None,
            "is_active": True,
        }

        if not data["name"]:
            QMessageBox.warning(self, "Error", "Name is required")
            return

        try:
            self.created_customer = self.customer_service.create_customer(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
