"""
Tests for StartShiftDialog -- the mandatory post-login dialog that opens a
shift with a starting cash float.

Regression coverage for the finding that the entire shift open/close feature
was built but never wired into the running UI (no menu, no button, no login
hook called start_shift() or opened ShiftClosingDialog anywhere).
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.status import ShiftStatus
from cbpos.core.models import Permission, Role, Shift, User
from cbpos.ui.dialogs.start_shift_dialog import StartShiftDialog

_counter = 0


@pytest.fixture
def test_user(db_session):
    """Create a test user for the dialog to start a shift against."""
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"start_shift_test_{suffix}")
    role = Role(name=f"StartShiftRole_{suffix}", permissions=[permission])
    user = User(username=f"start_shift_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.commit()
    return user


@pytest.fixture
def dialog(qapp, test_user):
    dlg = StartShiftDialog(test_user.id)
    yield dlg
    dlg.deleteLater()


@patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01")
def test_start_shift_creates_an_open_shift_with_the_counted_float(mock_config, dialog, db_session, test_user):
    """Confirming the count opens a shift with that amount and accepts the dialog."""
    dialog.starting_cash = Decimal("5000.00")
    dialog._start_shift()

    shift = db_session.query(Shift).filter_by(user_id=test_user.id).first()
    assert shift is not None
    assert shift.starting_cash == Decimal("5000.00")
    assert shift.status == ShiftStatus.OPEN
    assert dialog.result() == dialog.DialogCode.Accepted


def test_close_event_is_ignored_starting_a_shift_is_mandatory(dialog):
    """The dialog cannot be dismissed via the window close button."""
    from PyQt6.QtGui import QCloseEvent

    event = QCloseEvent()
    dialog.closeEvent(event)
    assert not event.isAccepted()


def test_reject_is_a_no_op_escape_cannot_skip_it(dialog):
    """Escape/Alt+F4 (QDialog.reject()) does not hide or close the dialog."""
    dialog.show()
    dialog.reject()
    assert dialog.isVisible()
