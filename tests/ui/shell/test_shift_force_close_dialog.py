"""Tests for force-closing shifts and stale shift handling (#884)."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import Permission, Role, Shift, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.shift_service import ShiftService
from cbpos.ui.dialogs.force_close_shift_dialog import ForceCloseShiftDialog
from cbpos.ui.dialogs.shift_management_dialog import ShiftManagementDialog
from cbpos.ui.dialogs.stale_shifts_dialog import StaleShiftsDialog

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


@pytest.fixture
def manager_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    perm = Permission(code=Permissions.SHIFT_FORCE_CLOSE)
    role = Role(name=f"ManagerRole_{suffix}", permissions=[perm])
    user = User(username=f"manager_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([perm, role, user])
    db_session.commit()
    return user


@pytest.fixture
def regular_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    role = Role(name=f"CashierRole_{suffix}", permissions=[])
    user = User(username=f"cashier_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([role, user])
    db_session.commit()
    return user


def test_force_close_dialog_ui_toggle(qapp, manager_user, monkeypatch):
    monkeypatch.setattr(AuthService, "get_current_user", lambda: manager_user)
    with patch.object(ShiftService, "get_shift_summary", return_value={"terminal_id": "TERM-01"}):
        dlg = ForceCloseShiftDialog(shift_id=42)
        try:
            assert dlg.txt_cash.isEnabled()
            assert not dlg.chk_dont_know.isChecked()
            assert dlg.txt_reason.text() == ""
            assert not dlg.btn_confirm.isEnabled()

            # Type reason enables confirm button
            dlg.txt_reason.setText("Left drawer locked")
            assert dlg.btn_confirm.isEnabled()

            # Clear reason disables confirm button
            dlg.txt_reason.setText("")
            assert not dlg.btn_confirm.isEnabled()

            # Entering text into cash
            dlg.txt_cash.setText("123.45")

            # Toggle don't know clears and disables cash input
            dlg.chk_dont_know.setChecked(True)
            assert not dlg.txt_cash.isEnabled()
            assert dlg.txt_cash.text() == ""

            # Unchecking re-enables cash input
            dlg.chk_dont_know.setChecked(False)
            assert dlg.txt_cash.isEnabled()
        finally:
            dlg.close()
            dlg.deleteLater()


def test_force_close_dialog_validation_invalid_cash(qapp, manager_user, monkeypatch):
    monkeypatch.setattr(AuthService, "get_current_user", lambda: manager_user)
    with patch.object(ShiftService, "get_shift_summary", return_value={"terminal_id": "TERM-01"}):
        dlg = ForceCloseShiftDialog(shift_id=42)
        try:
            dlg.txt_reason.setText("Forgot to close")
            dlg.txt_cash.setText("invalid-cash")

            warned = []
            monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(args))
            service_mock = MagicMock()
            monkeypatch.setattr(ShiftService, "force_close_shift", service_mock)

            dlg._on_confirm()

            assert len(warned) == 1
            assert not service_mock.called
            assert dlg.result() != QDialog.DialogCode.Accepted
        finally:
            dlg.close()
            dlg.deleteLater()


def test_force_close_dialog_submit_success(qapp, manager_user, monkeypatch):
    monkeypatch.setattr(AuthService, "get_current_user", lambda: manager_user)
    with patch.object(ShiftService, "get_shift_summary", return_value={"terminal_id": "TERM-01"}):
        dlg = ForceCloseShiftDialog(shift_id=42)
        try:
            dlg.txt_reason.setText("Cashier departed")
            dlg.txt_cash.setText("2500.00")

            closed_args = []

            def fake_force_close(self, shift_id, counted_cash, reason, closed_by_user_id):
                closed_args.append((shift_id, counted_cash, reason, closed_by_user_id))
                return {}

            monkeypatch.setattr(ShiftService, "force_close_shift", fake_force_close)
            monkeypatch.setattr(QMessageBox, "information", lambda *args: None)

            dlg._on_confirm()

            assert closed_args == [(42, Decimal("2500.00"), "Cashier departed", manager_user.id)]
            assert dlg.result() == QDialog.DialogCode.Accepted
        finally:
            dlg.close()
            dlg.deleteLater()


def test_force_close_dialog_submit_dont_know(qapp, manager_user, monkeypatch):
    monkeypatch.setattr(AuthService, "get_current_user", lambda: manager_user)
    with patch.object(ShiftService, "get_shift_summary", return_value={"terminal_id": "TERM-01"}):
        dlg = ForceCloseShiftDialog(shift_id=42)
        try:
            dlg.txt_reason.setText("Drawer key missing")
            dlg.chk_dont_know.setChecked(True)

            closed_args = []

            def fake_force_close(self, shift_id, counted_cash, reason, closed_by_user_id):
                closed_args.append((shift_id, counted_cash, reason, closed_by_user_id))
                return {}

            monkeypatch.setattr(ShiftService, "force_close_shift", fake_force_close)
            monkeypatch.setattr(QMessageBox, "information", lambda *args: None)

            dlg._on_confirm()

            assert closed_args == [(42, None, "Drawer key missing", manager_user.id)]
            assert dlg.result() == QDialog.DialogCode.Accepted
        finally:
            dlg.close()
            dlg.deleteLater()


def test_shift_management_dialog_stale_banner(qapp, db_session, manager_user, regular_user, monkeypatch):
    stale_start = datetime.now() - timedelta(hours=28)
    shift = Shift(
        user_id=regular_user.id,
        terminal_id="TERM-02",
        start_time=stale_start,
        starting_cash=Decimal("1000.00"),
        status="OPEN",
    )
    db_session.add(shift)
    db_session.commit()

    monkeypatch.setattr("cbpos.core.services.config_service.ConfigService.get", lambda k: "TERM-01")

    # 1. As regular user without permission
    monkeypatch.setattr(AuthService, "get_current_user", lambda: regular_user)
    dlg_cashier = ShiftManagementDialog(shift.id, regular_user.id)
    try:
        dlg_cashier.show()
        assert dlg_cashier.stale_banner.isVisible()
        assert not dlg_cashier.btn_force_close.isVisible()
    finally:
        dlg_cashier.close()
        dlg_cashier.deleteLater()

    # 2. As manager with permission
    monkeypatch.setattr(AuthService, "get_current_user", lambda: manager_user)
    dlg_mgr = ShiftManagementDialog(shift.id, manager_user.id)
    try:
        dlg_mgr.show()
        assert dlg_mgr.stale_banner.isVisible()
        assert dlg_mgr.btn_force_close.isVisible()
    finally:
        dlg_mgr.close()
        dlg_mgr.deleteLater()


def test_stale_shifts_dialog_empty_and_populated(qapp, db_session, manager_user, monkeypatch):
    monkeypatch.setattr(AuthService, "get_current_user", lambda: manager_user)

    # Empty case
    with patch.object(ShiftService, "get_stale_shifts", return_value=[]):
        dlg = StaleShiftsDialog()
        try:
            dlg.show()
            assert dlg.lbl_empty.isVisible()
            assert not dlg.table.isVisible()
        finally:
            dlg.close()
            dlg.deleteLater()

    # Populated case
    mock_shift = Shift(
        id=99,
        user_id=manager_user.id,
        terminal_id="TERM-02",
        start_time=datetime.now() - timedelta(hours=30),
        starting_cash=Decimal("500.00"),
        status="OPEN",
    )
    mock_shift.user = manager_user

    with patch.object(ShiftService, "get_stale_shifts", return_value=[mock_shift]):
        with patch.object(ShiftService, "get_shift_summary", return_value={"expected_cash": Decimal("500.00")}):
            dlg2 = StaleShiftsDialog()
            try:
                dlg2.show()
                assert not dlg2.lbl_empty.isVisible()
                assert dlg2.table.isVisible()
                assert dlg2.table.rowCount() == 1
                assert "99" in dlg2.table.item(0, 0).text()
                assert dlg2.table.item(0, 1).text() == "TERM-02"
            finally:
                dlg2.close()
                dlg2.deleteLater()
