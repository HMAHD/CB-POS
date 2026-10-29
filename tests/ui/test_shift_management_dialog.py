"""
#605: the side menu had two shift tiles (Shift Status, Close Shift -- the
latter with a calculator icon) and CashMovementDialog was never opened, so
cash drops and payouts couldn't be recorded and the expected cash at
close-out was wrong. One Shift tile now opens ShiftManagementDialog: the
X-read figures, Cash In / Cash Out, and End Shift.

Also keeps the old ShiftStatusDialog guarantee (#478): just opening it
never changes the shift.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QDialog

from cbpos.core.constants.status import ShiftStatus
from cbpos.core.models import CashMovement, Permission, Role, Shift, User
from cbpos.core.services.shift_service import ShiftService
from cbpos.core.utils.formatters import format_currency
from cbpos.ui.dialogs.cash_movement_dialog import CashMovementDialog
from cbpos.ui.dialogs.shift_closing_dialog import ShiftClosingDialog
from cbpos.ui.dialogs.shift_management_dialog import ShiftManagementDialog
from cbpos.ui.widgets.side_menu import SideMenu

pytestmark = pytest.mark.usefixtures("qapp")

_counter = 0


@pytest.fixture
def test_user(db_session):
    """Create a test user with an open shift for the dialog to read."""
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"shift_mgmt_test_{suffix}")
    role = Role(name=f"ShiftMgmtRole_{suffix}", permissions=[permission])
    user = User(username=f"shift_mgmt_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.commit()
    return user


@pytest.fixture
def open_shift(db_session, test_user):
    with patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01"):
        return ShiftService().start_shift(test_user.id, Decimal("5000.00"))


@pytest.fixture
def allow_permissions(monkeypatch):
    monkeypatch.setattr(
        "cbpos.core.utils.permission_helper.check_permission_with_override",
        lambda perm, parent: True,
    )


@pytest.fixture
def dialog(qapp, db_session, test_user, open_shift):
    dlg = ShiftManagementDialog(open_shift.id, test_user.id)
    yield dlg
    dlg.close()
    dlg.deleteLater()


def _fill_movement(amount: str, reason: str):
    def fake_exec(dlg: CashMovementDialog) -> int:
        dlg.txt_amount.setText(amount)
        dlg.txt_reason.setText(reason)
        dlg.validate_and_save()
        return dlg.result()

    return fake_exec


# ── Side menu ───────────────────────────────────────────────────────


def test_side_menu_has_exactly_one_shift_tile(qapp):
    menu = SideMenu()
    try:
        shift_tiles = [t for t in menu._nav_buttons if "shift" in t._text_key]
        assert shift_tiles == [menu.btn_shift]
        assert menu.btn_shift.icon_name != "fa5s.calculator"
        assert not hasattr(menu, "btn_close_shift")
        assert not hasattr(menu, "btn_shift_status")
    finally:
        menu.deleteLater()


def test_shift_tile_emits_shift_clicked(qtbot, qapp):
    menu = SideMenu()
    try:
        with qtbot.waitSignal(menu.shift_clicked, timeout=1000):
            menu.btn_shift.click()
    finally:
        menu.deleteLater()


# ── Dialog ──────────────────────────────────────────────────────────


def test_opening_the_dialog_shows_the_x_read_without_changing_the_shift(dialog, db_session, open_shift):
    assert dialog.windowTitle() != ""
    assert dialog.value_labels["expected_cash"].text() == format_currency(Decimal("5000.00"))

    db_session.expire_all()
    shift = db_session.get(Shift, open_shift.id)
    assert shift.status == ShiftStatus.OPEN
    assert shift.actual_cash is None
    assert shift.end_time is None


def test_cash_out_is_recorded_and_lowers_expected_cash(dialog, db_session, open_shift, allow_permissions, monkeypatch):
    monkeypatch.setattr(CashMovementDialog, "exec", _fill_movement("1500", "Bank drop"))

    dialog.btn_cash_out.click()

    movements = db_session.query(CashMovement).filter_by(shift_id=open_shift.id).all()
    assert [(m.type, m.amount, m.reason) for m in movements] == [("OUT", Decimal("1500.00"), "Bank drop")]
    assert dialog.value_labels["cash_out"].text() == format_currency(Decimal("1500.00"))
    assert dialog.value_labels["expected_cash"].text() == format_currency(Decimal("3500.00"))


def test_cash_in_raises_expected_cash(dialog, open_shift, allow_permissions, monkeypatch):
    monkeypatch.setattr(CashMovementDialog, "exec", _fill_movement("250", "Extra change"))

    dialog.btn_cash_in.click()

    assert dialog.value_labels["cash_in"].text() == format_currency(Decimal("250.00"))
    assert dialog.value_labels["expected_cash"].text() == format_currency(Decimal("5250.00"))


def test_cancelled_cash_movement_records_nothing(dialog, db_session, open_shift, allow_permissions, monkeypatch):
    monkeypatch.setattr(CashMovementDialog, "exec", lambda dlg: QDialog.DialogCode.Rejected)

    dialog.btn_cash_out.click()

    assert db_session.query(CashMovement).filter_by(shift_id=open_shift.id).count() == 0


def test_cash_movement_needs_the_drawer_permission(dialog, db_session, open_shift, monkeypatch):
    monkeypatch.setattr(
        "cbpos.core.utils.permission_helper.check_permission_with_override",
        lambda perm, parent: False,
    )
    opened = []
    monkeypatch.setattr(CashMovementDialog, "exec", lambda dlg: opened.append(dlg) or 0)

    dialog.btn_cash_out.click()

    assert opened == []
    assert db_session.query(CashMovement).filter_by(shift_id=open_shift.id).count() == 0


def test_z_read_expected_cash_includes_the_cash_drop(open_shift, test_user):
    service = ShiftService()
    service.record_cash_movement(open_shift.id, "OUT", Decimal("1000.00"), "Safe drop", test_user.id)
    service.record_cash_movement(open_shift.id, "IN", Decimal("200.00"), "Float top-up", test_user.id)

    closed = service.close_shift(open_shift.id, Decimal("4200.00"))

    assert closed["expected_cash"] == Decimal("4200.00")
    assert closed["variance"] == Decimal("0.00")


def test_end_shift_opens_the_closing_dialog_and_marks_the_shift_ended(dialog, monkeypatch):
    seen = []

    def fake_exec(dlg: ShiftClosingDialog) -> int:
        seen.append(dlg.shift_id)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ShiftClosingDialog, "exec", fake_exec)

    dialog.btn_end_shift.click()

    assert seen == [dialog.shift_id]
    assert dialog.shift_ended is True
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_backing_out_of_end_shift_keeps_the_dialog_open(dialog, monkeypatch):
    monkeypatch.setattr(ShiftClosingDialog, "exec", lambda dlg: QDialog.DialogCode.Rejected)

    dialog.btn_end_shift.click()

    assert dialog.shift_ended is False


# ── SalesView wiring ────────────────────────────────────────────────


def _fake_sales_view(emitted: list):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    return SimpleNamespace(
        side_menu=SimpleNamespace(isVisible=lambda: False),
        toggle_side_menu=MagicMock(),
        barcode_input=MagicMock(),
        _focus_search=MagicMock(),
        shift_closed=SimpleNamespace(emit=lambda: emitted.append("closed")),
    )


@pytest.mark.parametrize("ended, expected", [(True, ["closed"]), (False, [])])
def test_sales_view_logs_out_only_after_the_shift_ended(monkeypatch, test_user, open_shift, ended, expected):
    from cbpos.ui.views.sales_view import SalesView

    monkeypatch.setattr("cbpos.core.services.auth_service.AuthService.get_current_user", lambda: test_user)
    monkeypatch.setattr("cbpos.core.services.shift_service.ConfigService.get", lambda key: "TERM-01")

    def fake_exec(dlg: ShiftManagementDialog) -> int:
        dlg.shift_ended = ended
        return QDialog.DialogCode.Accepted if ended else QDialog.DialogCode.Rejected

    monkeypatch.setattr(ShiftManagementDialog, "exec", fake_exec)
    monkeypatch.setattr(ShiftManagementDialog, "__init__", _light_init)

    emitted: list = []
    SalesView.open_shift_management(_fake_sales_view(emitted))

    assert emitted == expected


def _light_init(self, shift_id, user_id, parent=None):
    QDialog.__init__(self)
    self.shift_id = shift_id
    self.shift_ended = False
