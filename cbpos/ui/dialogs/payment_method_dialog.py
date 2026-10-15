"""Dialog to add or edit a payment method."""

from PyQt6.QtCore import QKeyCombination, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from cbpos.core.services.payment_service import PaymentService, ShortcutConflictError
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.widgets.dialog_footer import make_dialog_footer

_PORTABLE = QKeySequence.SequenceFormat.PortableText


def _shortcut_error_text(err: ShortcutConflictError) -> str:
    """Translated message for a rejected payment method shortcut (#640)."""
    if err.conflict_with is None:
        return _t("payment_methods.shortcut_reserved", shortcut=err.shortcut)
    return _t("payment_methods.shortcut_taken", shortcut=err.shortcut, name=err.conflict_with)


class PaymentMethodDialog(QDialog):
    """Dialog to add or edit a payment method."""

    def __init__(self, method=None, parent=None, name_locked: bool = False):
        """Build the form, pre-filled with `method`'s values when editing.

        Args:
            method: The method being edited, or None to add a new one.
            parent: Parent widget.
            name_locked: True when the method has payment history, so its
                name can't change (#639).
        """
        super().__init__(parent)
        self.method = method
        self._name_locked = bool(method) and name_locked
        self.setMinimumWidth(400)
        self.setObjectName("PaymentMethodDialog")
        self._init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self._form = QFormLayout()
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.txt_name = QLineEdit()
        self.txt_name.setMaxLength(50)
        self._lbl_name = QLabel()
        self._form.addRow(self._lbl_name, self.txt_name)

        # Payments store the method by name, so a used method's name is
        # read-only -- renaming it would cut it off from its history (#639).
        self.txt_name.setReadOnly(self._name_locked)
        self.lbl_name_locked = QLabel()
        self.lbl_name_locked.setProperty("class", "muted")
        self.lbl_name_locked.setWordWrap(True)
        self.lbl_name_locked.setVisible(self._name_locked)
        self._form.addRow("", self.lbl_name_locked)

        # Captures a real key press instead of free text, so typos can't be
        # stored and the value is always in the format QShortcut parses (#640).
        self.txt_shortcut = QKeySequenceEdit()
        self.txt_shortcut.setMaximumSequenceLength(1)
        self.txt_shortcut.setClearButtonEnabled(True)
        self._lbl_shortcut = QLabel()
        self._form.addRow(self._lbl_shortcut, self.txt_shortcut)

        self.chk_cash = QCheckBox()
        self._form.addRow("", self.chk_cash)

        self.chk_drawer = QCheckBox()
        self._form.addRow("", self.chk_drawer)

        layout.addLayout(self._form)

        # Shortcut/drawer-open only ever got set for Cash in seed data --
        # nothing in the code special-cases it, but that made it look like
        # a Cash-only feature rather than something available to any
        # method (#337).
        self.lbl_hint = QLabel()
        self.lbl_hint.setProperty("class", "muted")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)

        # Buttons
        btn_layout, self.btn_save, self.btn_cancel = make_dialog_footer(
            primary_key="common.save",
            on_primary=self._save,
            on_cancel=self.reject,
        )
        layout.addLayout(btn_layout)

        # Load existing values
        if self.method:
            self.txt_name.setText(self.method.name)
            self.txt_shortcut.setKeySequence(QKeySequence.fromString(self.method.shortcut or "", _PORTABLE))
            self.chk_cash.setChecked(self.method.is_cash)
            self.chk_drawer.setChecked(self.method.open_drawer)

    def retranslate_ui(self) -> None:
        """Update all translatable strings, including the Add/Edit window title."""
        if self.method:
            self.setWindowTitle(_t("payment_methods.dialog_edit_title"))
        else:
            self.setWindowTitle(_t("payment_methods.dialog_add_title"))
        self._lbl_name.setText(_t("payment_methods.form_name"))
        self.lbl_name_locked.setText(_t("payment_methods.name_locked_hint"))
        self.txt_name.setPlaceholderText(_t("payment_methods.name_placeholder"))
        self._lbl_shortcut.setText(_t("payment_methods.form_shortcut"))
        line_edit = self.txt_shortcut.findChild(QLineEdit)
        if line_edit is not None:
            line_edit.setPlaceholderText(_t("payment_methods.shortcut_placeholder"))
        self.chk_cash.setText(_t("payment_methods.chk_is_cash"))
        self.chk_drawer.setText(_t("payment_methods.chk_open_drawer"))
        self.lbl_hint.setText(_t("payment_methods.form_hint"))
        self.btn_cancel.setText(_t("common.cancel"))
        self.btn_save.setText(_t("common.save"))

    def _save(self) -> None:
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                _t("payment_methods.validation_title"),
                _t("payment_methods.name_required"),
            )
            self.txt_name.setFocus()
            return

        shortcut = self._shortcut_text()
        try:
            PaymentService.validate_shortcut(
                shortcut,
                exclude_id=self.method.id if self.method else None,
                active=self.method.is_active if self.method else True,
            )
        except ShortcutConflictError as e:
            QMessageBox.warning(self, _t("payment_methods.validation_title"), _shortcut_error_text(e))
            self.txt_shortcut.setFocus()
            return

        self.result_data = {
            "name": name,
            # "" (not None) so clearing the field actually clears the stored key.
            "shortcut": shortcut,
            "is_cash": self.chk_cash.isChecked(),
            "open_drawer": self.chk_drawer.isChecked(),
        }
        self.accept()

    def _shortcut_text(self) -> str:
        """Captured key as Qt portable text ("F5", "Ctrl+F5"), or "" for none.

        The keypad flag is dropped so keypad Enter is stored (and validated)
        as plain "Enter", which is how QShortcut matches it anyway.
        """
        seq = self.txt_shortcut.keySequence()
        if seq.isEmpty():
            return ""
        combo = seq[0]
        mods = combo.keyboardModifiers() & ~Qt.KeyboardModifier.KeypadModifier
        return QKeySequence(QKeyCombination(mods, combo.key())).toString(_PORTABLE)
