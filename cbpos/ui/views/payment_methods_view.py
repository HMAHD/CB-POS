"""
Payment Methods management view for Settings.
Card-based list with inline toggle, edit, and delete actions.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cbpos.core.services.payment_service import PaymentMethodInUseError, PaymentService, ShortcutConflictError
from cbpos.i18n import _t, register_language_callback
from cbpos.ui.dialogs.payment_method_dialog import PaymentMethodDialog

logger = logging.getLogger(__name__)

_PORTABLE = QKeySequence.SequenceFormat.PortableText


def _shortcut_error_text(err: ShortcutConflictError) -> str:
    """Translated message for a rejected payment method shortcut (#640)."""
    if err.conflict_with is None:
        return _t("payment_methods.shortcut_reserved", shortcut=err.shortcut)
    return _t("payment_methods.shortcut_taken", shortcut=err.shortcut, name=err.conflict_with)


class _MethodCard(QFrame):
    """A single payment method row card."""

    def __init__(self, method, parent_view: "PaymentMethodsView", parent=None, has_history: bool = False):
        """Build the card showing the method's name, tags, status, and action buttons.

        Args:
            method: The payment method shown.
            parent_view: View that handles the card's actions.
            parent: Parent widget.
            has_history: True when past payments use the method, so it can't
                be deleted (only deactivated) or renamed (#639).
        """
        super().__init__(parent)
        self.method = method
        self.has_history = has_history
        self._parent_view = parent_view
        self.setObjectName("PMCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._init_ui()

    def _status_pill(self) -> QLabel:
        """Borderless Active/Inactive pill (styled by #PMCardStatus in the QSS)."""
        if self.method.is_active:
            status_text = _t("payment_methods.status_active")
            status_class = "pm-active"
        else:
            status_text = _t("payment_methods.status_inactive")
            status_class = "pm-inactive"
        self.status_label = QLabel(status_text)
        self.status_label.setObjectName("PMCardStatus")
        self.status_label.setProperty("class", status_class)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return self.status_label

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # --- Left: Name + tags ---
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        name_label = QLabel(self.method.name)
        name_label.setObjectName("PMCardName")
        # Status pill sits beside the name, away from the action buttons,
        # so it doesn't read as a button (#560).
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(name_label)
        name_row.addWidget(self._status_pill())
        name_row.addStretch()
        info_layout.addLayout(name_row)

        # Tags line: properties as small text
        tags = []
        if self.method.is_cash:
            tags.append(_t("payment_methods.tag_cash"))
        if self.method.open_drawer:
            tags.append(_t("payment_methods.tag_opens_drawer"))
        if self.method.shortcut:
            tags.append(self.method.shortcut)
        if self.has_history:
            tags.append(_t("payment_methods.tag_has_history"))

        if tags:
            tag_label = QLabel(" \u00b7 ".join(tags))
            tag_label.setObjectName("PMCardTags")
            info_layout.addWidget(tag_label)

        layout.addLayout(info_layout, 1)

        # --- Right: Action buttons ---
        self.btn_layout = btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_edit = QPushButton(_t("payment_methods.btn_edit"))
        btn_edit.setObjectName("PMCardBtn")
        btn_edit.setProperty("class", "secondary")
        btn_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_edit.clicked.connect(lambda: self._parent_view._edit_method(self.method, self.has_history))
        btn_layout.addWidget(btn_edit)

        if self.method.is_active:
            toggle_text = _t("payment_methods.btn_deactivate")
            toggle_class = "warning"
        else:
            toggle_text = _t("payment_methods.btn_activate")
            toggle_class = "accent"
        btn_toggle = QPushButton(toggle_text)
        btn_toggle.setObjectName("PMCardBtn")
        btn_toggle.setProperty("class", toggle_class)
        btn_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_toggle.clicked.connect(lambda: self._parent_view._toggle_method(self.method))
        btn_layout.addWidget(btn_toggle)

        # Cash can't be deleted, nor can a method with payment history
        # (#639: Deactivate is the only way out for those). The button still
        # gets added (just hidden, with its layout slot retained) rather than
        # omitted -- otherwise the narrower 2-button group shifts left,
        # landing its Edit button out of line with every other row's.
        self.btn_delete = QPushButton(_t("payment_methods.btn_delete"))
        self.btn_delete.setObjectName("PMCardBtn")
        self.btn_delete.setProperty("class", "danger")
        self.btn_delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_delete.clicked.connect(lambda: self._parent_view._delete_method(self.method))
        if self.method.is_cash or self.has_history:
            self.btn_delete.setVisible(False)
            size_policy = self.btn_delete.sizePolicy()
            size_policy.setRetainSizeWhenHidden(True)
            self.btn_delete.setSizePolicy(size_policy)
        btn_layout.addWidget(self.btn_delete)

        layout.addLayout(btn_layout)


class PaymentMethodsView(QWidget):
    """Payment Methods management — card-based list with actions."""

    def __init__(self, parent=None):
        """Build the header, add button, and scrollable card list."""
        super().__init__(parent)
        self.setObjectName("PaymentMethodsView")
        self._methods = []
        self._init_ui()
        self.retranslate_ui()
        register_language_callback(self.retranslate_ui, owner=self)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        self._title = QLabel()
        self._title.setProperty("class", "dialog-title")
        layout.addWidget(self._title)

        self._subtitle = QLabel()
        self._subtitle.setProperty("class", "muted")
        layout.addWidget(self._subtitle)

        # Action bar
        action_bar = QHBoxLayout()
        action_bar.addStretch()

        self.btn_add = QPushButton()
        self.btn_add.setObjectName("PaymentMethodAddBtn")
        self.btn_add.setProperty("class", "primary")
        self.btn_add.clicked.connect(self._add_method)
        action_bar.addWidget(self.btn_add)

        layout.addLayout(action_bar)

        # Scrollable card list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setObjectName("PMCardScroll")

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()

        self.scroll.setWidget(self._list_container)
        layout.addWidget(self.scroll, 1)

        # Hint
        self._hint = QLabel()
        self._hint.setProperty("class", "muted")
        layout.addWidget(self._hint)

    def retranslate_ui(self) -> None:
        """Update all translatable strings."""
        self._title.setText(_t("payment_methods.title"))
        self._subtitle.setText(_t("payment_methods.subtitle"))
        self.btn_add.setText("  " + _t("payment_methods.btn_add_method") + "  ")
        self._hint.setText(_t("payment_methods.hint"))

    def showEvent(self, event) -> None:
        """Reload the method list when the view becomes visible."""
        super().showEvent(event)
        self._load_methods()

    def _load_methods(self) -> None:
        """Rebuild the card list from database."""
        self._methods = PaymentService.get_all_methods()
        used_ids = PaymentService.get_used_method_ids()

        # Clear existing cards
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add cards
        for i, method in enumerate(self._methods):
            card = _MethodCard(method, parent_view=self, has_history=method.id in used_ids)
            self._list_layout.insertWidget(i, card)

    def _add_method(self) -> None:
        dialog = PaymentMethodDialog(parent=self)
        if dialog.exec():
            data = dialog.result_data
            try:
                PaymentService.create_method(
                    name=data["name"],
                    is_cash=data["is_cash"],
                    open_drawer=data["open_drawer"],
                    shortcut=data["shortcut"],
                )
                self._load_methods()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    _t("common.error"),
                    _t("payment_methods.error_create", error=str(e)),
                )

    def _edit_method(self, method, has_history: bool = False) -> None:
        dialog = PaymentMethodDialog(method=method, parent=self, name_locked=has_history)
        if dialog.exec():
            data = dialog.result_data
            try:
                PaymentService.update_method(
                    method_id=method.id,
                    name=data["name"],
                    is_cash=data["is_cash"],
                    open_drawer=data["open_drawer"],
                    shortcut=data["shortcut"],
                )
                self._load_methods()
            except PaymentMethodInUseError as e:
                QMessageBox.warning(
                    self,
                    _t("payment_methods.validation_title"),
                    _t("payment_methods.rename_blocked", name=e.name),
                )
                self._load_methods()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    _t("common.error"),
                    _t("payment_methods.error_update", error=str(e)),
                )

    def _toggle_method(self, method) -> None:
        """Toggle active/inactive state."""
        new_state = not method.is_active
        action = "activate" if new_state else "deactivate"
        try:
            PaymentService.update_method(method_id=method.id, is_active=new_state)
            self._load_methods()
            logger.info("Payment method '%s' %sd", method.name, action)
        except ShortcutConflictError as e:
            QMessageBox.warning(self, _t("payment_methods.validation_title"), _shortcut_error_text(e))
        except Exception as e:
            QMessageBox.critical(
                self,
                _t("common.error"),
                _t("payment_methods.error_toggle", action=action, error=str(e)),
            )

    def _delete_method(self, method) -> None:
        if method.is_cash:
            QMessageBox.warning(
                self,
                _t("payment_methods.cannot_delete_title"),
                _t("payment_methods.cannot_delete_cash"),
            )
            return

        reply = QMessageBox.question(
            self,
            _t("payment_methods.delete_confirm_title"),
            _t("payment_methods.delete_confirm_message", name=method.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # The card hides Delete for a used method, but history may
                # have arrived since the list loaded (another till, LAN Sync).
                kept_for_history = PaymentService.is_method_used(method.id)
                PaymentService.delete_method(method.id)
                self._load_methods()
                if kept_for_history:
                    QMessageBox.information(
                        self,
                        _t("payment_methods.deactivated_instead_title"),
                        _t("payment_methods.deactivated_instead_message", name=method.name),
                    )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    _t("common.error"),
                    _t("payment_methods.error_delete", error=str(e)),
                )
