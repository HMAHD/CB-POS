"""Dialog to collect admin PIN when settings exist but a new database is being created (#791)."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from cbpos.i18n import _t
from cbpos.ui.widgets.dialog_footer import make_dialog_footer
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


def validate_pin(pin: str, pin_confirm: str) -> tuple[str, str] | None:
    """Validate admin PIN input.

    Returns:
        (title_key, message_key) tuple on error, or None if valid.
    """
    if not pin or len(pin) < 4:
        return ("setup_wizard.required_title", "setup_wizard.pin_min_length")
    if not pin.isdigit():
        return ("setup_wizard.invalid_title", "setup_wizard.pin_digits_only")
    if pin != pin_confirm:
        return ("setup_wizard.mismatch_title", "setup_wizard.pin_mismatch")
    return None


class AdminPinDialog(QDialog):
    """Dialog to choose the admin PIN on a fresh database."""

    def __init__(self, parent=None):
        """Initialize the AdminPinDialog."""
        super().__init__(parent)
        self.setObjectName("AdminPinDialog")
        self.setMinimumSize(480, 280)
        self.resize(480, 280)
        self._pin: str | None = None
        self._init_ui()
        install_wheel_guard(self)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(15)

        self.lbl_body = QLabel()
        self.lbl_body.setProperty("class", "muted")
        self.lbl_body.setWordWrap(True)
        layout.addWidget(self.lbl_body)

        self.form_layout = QFormLayout()
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form_layout.setVerticalSpacing(15)
        self.form_layout.setHorizontalSpacing(20)

        self.input_pin = QLineEdit()
        self.input_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pin.setMaxLength(6)

        self.input_pin_confirm = QLineEdit()
        self.input_pin_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_pin_confirm.setMaxLength(6)

        self.lbl_admin_pin = QLabel()
        self.lbl_confirm_pin = QLabel()

        self.form_layout.addRow(self.lbl_admin_pin, self.input_pin)
        self.form_layout.addRow(self.lbl_confirm_pin, self.input_pin_confirm)
        layout.addLayout(self.form_layout)
        layout.addStretch()

        footer_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="admin_pin.btn_save",
            on_primary=self._on_save,
            cancel_key="setup_wizard.btn_cancel",
            on_cancel=self.reject,
        )
        layout.addLayout(footer_layout)

        self.retranslate_ui()
        self.input_pin.setFocus()

    def retranslate_ui(self) -> None:
        """Set all translatable text using _t()."""
        self.setWindowTitle(_t("admin_pin.title"))
        self.lbl_body.setText(_t("admin_pin.body"))
        self.lbl_admin_pin.setText(_t("setup_wizard.admin_pin"))
        self.lbl_confirm_pin.setText(_t("setup_wizard.confirm_pin"))
        self.input_pin.setPlaceholderText(_t("setup_wizard.pin_placeholder"))
        self.input_pin_confirm.setPlaceholderText(_t("setup_wizard.pin_confirm_placeholder"))
        self.btn_save.setText(_t("admin_pin.btn_save"))
        self.btn_cancel.setText(_t("setup_wizard.btn_cancel"))

    def _on_save(self) -> None:
        """Validate input PIN and accept if valid."""
        pin = self.input_pin.text()
        confirm = self.input_pin_confirm.text()

        err = validate_pin(pin, confirm)
        if err is not None:
            title_key, msg_key = err
            QMessageBox.warning(self, _t(title_key), _t(msg_key))
            if title_key == "setup_wizard.mismatch_title":
                self.input_pin_confirm.setFocus()
            else:
                self.input_pin.setFocus()
            return

        self._pin = pin
        self.accept()

    def pin(self) -> str | None:
        """Return the confirmed admin PIN, or None if rejected."""
        return self._pin
