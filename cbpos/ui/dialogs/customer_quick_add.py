from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from cbpos.core.services.customer_service import CustomerService
from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer


class CustomerQuickAddDialog(QDialog):
    """Lightweight dialog for adding a customer (name and phone only) without leaving checkout."""

    def __init__(self, parent=None):
        """Initialize the dialog and build the quick-add form."""
        super().__init__(parent)
        self.customer_service = CustomerService()
        self.created_customer = None

        self.setWindowTitle(_t("customer_quick_add.title"))
        self.setMinimumWidth(300)
        self.setMinimumHeight(350)
        self.setObjectName("CustomerQuickAddDialog")
        self.setup_ui()

    def setup_ui(self):
        """Build the name and phone input form with save/cancel buttons."""
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)

        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()

        form.addRow(_t("customer_quick_add.name_label"), self.name_input)
        form.addRow(_t("customer_quick_add.phone_label"), self.phone_input)

        layout.addLayout(form)

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self.save,
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)

        self.name_input.setFocus()

    def save(self):
        """Validate the name, create the customer, and accept the dialog."""
        data = {
            "name": self.name_input.text().strip(),
            "phone": self.phone_input.text().strip() or None,
            "is_active": True,
        }

        if not data["name"]:
            QMessageBox.warning(self, _t("common.error"), _t("customer_quick_add.name_required"))
            return

        try:
            self.created_customer = self.customer_service.create_customer(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, _t("common.error"), str(e))
