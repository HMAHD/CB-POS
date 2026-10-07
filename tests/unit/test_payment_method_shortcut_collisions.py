"""
#640: payment method shortcut keys could collide with the payment
dialog's own keys (Enter/Return, F12 quick-pay, Esc cancel) or with each
other. Two QShortcuts on the same key are ambiguous in Qt, so *neither*
fires -- assigning F12 to a method silently killed F12 quick-pay.

Covers: service + dialog validation, QKeySequenceEdit round-tripping of
existing "F1"-style values, and the payment dialog defensively skipping
a colliding stored shortcut (old DBs) so F12 still completes payment.
"""

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QKeySequenceEdit, QMessageBox

from cbpos.core.models import PaymentMethod
from cbpos.core.services.payment_service import (
    RESERVED_SHORTCUTS,
    PaymentService,
    ShortcutConflictError,
    normalize_shortcut,
)
from cbpos.ui.dialogs.payment_dialog import PaymentDialog
from cbpos.ui.views.payment_methods_view import PaymentMethodDialog


def _method(db_session, name: str, shortcut: str | None, active: bool = True, is_cash: bool = False):
    m = db_session.query(PaymentMethod).filter_by(name=name).first()
    if m is None:
        m = PaymentMethod(name=name, is_cash=is_cash, is_active=active, shortcut=shortcut)
        db_session.add(m)
    else:
        m.shortcut, m.is_active, m.is_cash = shortcut, active, is_cash
    db_session.commit()
    return m


@pytest.fixture
def no_other_methods(db_session):
    """Deactivate every pre-existing method so only the test's rows count."""
    for m in db_session.query(PaymentMethod).all():
        m.is_active = False
    db_session.commit()
    return db_session


class TestServiceRejectsReservedKeys:
    @pytest.mark.parametrize("key", ["F12", "f12", "Return", "Enter", "Num+Enter", "Esc", "Escape"])
    def test_create_with_reserved_key_is_rejected(self, no_other_methods, key):
        with pytest.raises(ShortcutConflictError) as exc:
            PaymentService.create_method(name="Wallet640", shortcut=key)
        assert exc.value.conflict_with is None

    def test_update_to_reserved_key_is_rejected(self, no_other_methods):
        m = _method(no_other_methods, "Wallet640", "F5")
        with pytest.raises(ShortcutConflictError):
            PaymentService.update_method(m.id, shortcut="F12")


class TestServiceRejectsDuplicatesAmongActive:
    def test_duplicate_of_active_method_rejected(self, no_other_methods):
        _method(no_other_methods, "Card640", "F5")
        with pytest.raises(ShortcutConflictError) as exc:
            PaymentService.create_method(name="Wallet640", shortcut="f5")
        assert exc.value.conflict_with == "Card640"

    def test_duplicate_of_inactive_method_allowed(self, no_other_methods):
        _method(no_other_methods, "Card640", "F5", active=False)
        created = PaymentService.create_method(name="Wallet640", shortcut="F5")
        assert created.shortcut == "F5"

    def test_activating_a_method_whose_key_is_taken_is_rejected(self, no_other_methods):
        _method(no_other_methods, "Card640", "F5")
        other = _method(no_other_methods, "Wallet640", "F5", active=False)
        with pytest.raises(ShortcutConflictError):
            PaymentService.update_method(other.id, is_active=True)

    def test_keeping_own_key_on_edit_is_fine(self, no_other_methods):
        m = _method(no_other_methods, "Card640", "F5")
        updated = PaymentService.update_method(m.id, name="Card640", shortcut="F5")
        assert updated.shortcut == "F5"

    def test_empty_string_clears_shortcut(self, no_other_methods):
        m = _method(no_other_methods, "Card640", "F5")
        updated = PaymentService.update_method(m.id, shortcut="")
        assert updated.shortcut is None


class TestEditDialog:
    def test_shortcut_field_is_a_key_sequence_edit(self, qapp):
        dlg = PaymentMethodDialog()
        try:
            assert isinstance(dlg.txt_shortcut, QKeySequenceEdit)
        finally:
            dlg.deleteLater()

    def test_existing_f1_value_loads_and_saves_unchanged(self, qapp, no_other_methods):
        m = _method(no_other_methods, "Card640", "F1")
        dlg = PaymentMethodDialog(method=m)
        try:
            assert dlg.txt_shortcut.keySequence().toString(QKeySequence.SequenceFormat.PortableText) == "F1"
            dlg.txt_name.setText("Card640")
            dlg._save()
            assert dlg.result_data["shortcut"] == "F1"
        finally:
            dlg.deleteLater()

    def test_cleared_shortcut_saves_as_empty(self, qapp, no_other_methods):
        m = _method(no_other_methods, "Card640", "F1")
        dlg = PaymentMethodDialog(method=m)
        try:
            dlg.txt_shortcut.clear()
            dlg._save()
            assert dlg.result_data["shortcut"] == ""
        finally:
            dlg.deleteLater()

    @pytest.mark.parametrize("key", [Qt.Key.Key_F12, Qt.Key.Key_Return, Qt.Key.Key_Enter])
    def test_reserved_key_is_rejected_on_save(self, qapp, no_other_methods, monkeypatch, key):
        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a))
        dlg = PaymentMethodDialog()
        try:
            dlg.txt_name.setText("Wallet640")
            dlg.txt_shortcut.setKeySequence(QKeySequence(key))
            dlg._save()
            assert warnings, "reserved key must show a validation message"
            assert not hasattr(dlg, "result_data")
        finally:
            dlg.deleteLater()

    def test_key_of_other_active_method_is_rejected_on_save(self, qapp, no_other_methods, monkeypatch):
        _method(no_other_methods, "Card640", "F5")
        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a))
        dlg = PaymentMethodDialog()
        try:
            dlg.txt_name.setText("Wallet640")
            dlg.txt_shortcut.setKeySequence(QKeySequence("F5"))
            dlg._save()
            assert warnings and "Card640" in warnings[0][2]
            assert not hasattr(dlg, "result_data")
        finally:
            dlg.deleteLater()


class TestPaymentDialogWithCollidingStoredShortcut:
    @pytest.fixture
    def dialog(self, qapp, no_other_methods):
        # Old DB: Cash seeded with F12, plus a second method also on F12
        # and a duplicate pair on F11.
        _method(no_other_methods, "Cash", "F12", is_cash=True)
        _method(no_other_methods, "Card640", "F11")
        _method(no_other_methods, "Wallet640", "F11")
        _method(no_other_methods, "Bad640", "F12")
        dlg = PaymentDialog(Decimal("600.00"))
        yield dlg
        dlg.close()
        dlg.deleteLater()

    def _method_shortcut_keys(self, dlg) -> list[str]:
        return [
            sc.key().toString(QKeySequence.SequenceFormat.PortableText)
            for sc in dlg.findChildren(QShortcut)
            if sc is not dlg.shortcut_f12
        ]

    def test_no_method_shortcut_shadows_f12_or_enter(self, dialog):
        keys = self._method_shortcut_keys(dialog)
        assert keys.count("F12") == 0
        assert keys.count("Return") == 1 and keys.count("Enter") == 1

    def test_duplicate_method_keys_register_once(self, dialog):
        assert self._method_shortcut_keys(dialog).count("F11") == 1

    def test_f12_still_completes_payment(self, dialog, qtbot):
        dialog.show()
        dialog.activateWindow()
        qtbot.waitUntil(lambda: QApplication.activeWindow() is dialog, timeout=2000)
        QTest.keyClick(dialog, Qt.Key.Key_F12)
        assert dialog.result() == PaymentDialog.DialogCode.Accepted
        assert dialog.payments == [{"method": "Cash", "amount": Decimal("600.00")}]

    def test_f1_style_method_shortcut_still_selects_method(self, dialog, qtbot):
        dialog.show()
        dialog.activateWindow()
        qtbot.waitUntil(lambda: QApplication.activeWindow() is dialog, timeout=2000)
        QTest.keyClick(dialog, Qt.Key.Key_F11)
        assert dialog.current_method.name == "Card640"


class TestDefaultDataHasNoReservedShortcut:
    """Fresh installs and demo seed used to put Cash on F12, colliding with quick-pay."""

    @pytest.mark.parametrize("path", ["scripts/seed.py", "cbpos/core/services/database_setup_service.py"])
    def test_no_seeded_method_uses_a_reserved_key(self, path):
        tree = ast.parse((Path(__file__).resolve().parents[2] / path).read_text(encoding="utf-8"))
        keys = [
            kw.value.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "PaymentMethod"
            for kw in node.keywords
            if kw.arg == "shortcut" and isinstance(kw.value, ast.Constant) and kw.value.value
        ]
        assert keys, "expected seeded shortcuts (Card F11)"
        assert not [k for k in keys if normalize_shortcut(k) in RESERVED_SHORTCUTS]
