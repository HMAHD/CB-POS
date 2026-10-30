"""Modal dialog to create or edit a user's username, PIN, role, and active status."""

import logging

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from cbpos.core.services.user_service import UserService
from cbpos.core.utils.display_labels import display_role_name
from cbpos.core.utils.error_messages import translate_error
from cbpos.i18n import _t
from cbpos.ui.widgets.wheel_guard import install_wheel_guard

logger = logging.getLogger(__name__)


class UserDialog(QDialog):
    """Modal dialog to create or edit a user's username, PIN, role, and active status."""

    def __init__(self, user=None, parent=None):
        """Set the dialog title and build the form, pre-filling fields when editing an existing user."""
        super().__init__(parent)
        self.user = user
        self.setWindowTitle(_t("user.add_user") if not user else _t("user.edit_user"))
        self.setFixedWidth(400)
        self.init_ui()
        install_wheel_guard(self)  # hover + wheel scrolls, never changes a field (#598)

    def init_ui(self):
        """Build the username, PIN, role, and active-status form fields plus Save/Cancel buttons."""
        layout = QVBoxLayout(self)

        # Username
        layout.addWidget(QLabel(_t("user.username_label")))
        self.txt_username = QLineEdit()
        if self.user:
            self.txt_username.setText(self.user.username)
        layout.addWidget(self.txt_username)

        # PIN
        layout.addWidget(QLabel(_t("user.pin_keep_unchanged") if self.user else _t("user.pin_label")))
        self.txt_pin = QLineEdit()
        self.txt_pin.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.txt_pin)

        # Role
        layout.addWidget(QLabel(_t("user.role_label")))
        self.cmb_role = QComboBox()
        self.roles = UserService.get_all_roles()
        for role in self.roles:
            self.cmb_role.addItem(display_role_name(role), role.id)

        if self.user and self.user.role:
            index = self.cmb_role.findData(self.user.role_id)
            if index >= 0:
                self.cmb_role.setCurrentIndex(index)
        layout.addWidget(self.cmb_role)

        # Active
        self.chk_active = QCheckBox(_t("common.active"))
        self.chk_active.setChecked(True)
        if self.user:
            self.chk_active.setChecked(self.user.is_active)
        layout.addWidget(self.chk_active)

        if self.user and UserService.is_last_active_admin(self.user.id):
            last_admin_msg = _t("users.last_admin")
            self.cmb_role.setEnabled(False)
            self.cmb_role.setToolTip(last_admin_msg)
            self.chk_active.setEnabled(False)
            self.chk_active.setToolTip(last_admin_msg)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton(_t("common.save"))
        btn_save.setObjectName("BtnSave")
        btn_save.setProperty("class", "primary")
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton(_t("common.cancel"))
        btn_cancel.setObjectName("BtnCancel")
        btn_cancel.setProperty("class", "secondary")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def save(self):
        """Validate the form and create or update the user via UserService, closing the dialog on success."""
        username = self.txt_username.text().strip()
        pin = self.txt_pin.text().strip()
        role_id = self.cmb_role.currentData()
        is_active = self.chk_active.isChecked()

        if not username:
            QMessageBox.warning(self, _t("common.error"), _t("user.username_required"))
            return

        if not self.user and not pin:
            QMessageBox.warning(self, _t("common.error"), _t("user.pin_required"))
            return

        if pin and (len(pin) < 4 or len(pin) > 6 or not pin.isdigit()):
            QMessageBox.warning(self, _t("common.error"), _t("user.pin_invalid"))
            return

        try:
            if self.user:
                UserService.update_user(self.user.id, username, pin if pin else None, role_id, is_active)
            else:
                UserService.create_user(username, pin, role_id)
            self.accept()
        except ValueError as e:
            err_code = str(e)
            if err_code == "pin_in_use":
                msg = _t("users.pin_in_use")
            elif err_code == "pin_required_on_reactivate":
                msg = _t("users.pin_required_on_reactivate")
            elif err_code == "last_admin":
                msg = _t("users.last_admin")
            else:
                msg = translate_error(err_code)
            QMessageBox.warning(self, _t("common.error"), msg)
            if err_code != "last_admin":
                self.txt_pin.setFocus()
                self.txt_pin.selectAll()
        except Exception as e:
            logger.exception("Failed to save user: %s", e)
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("user.save_failed", error=translate_error(str(e))),
            )
