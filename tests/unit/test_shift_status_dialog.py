"""
Tests for ShiftStatusDialog -- the read-only mid-shift snapshot (X-Read, #478).

Confirms the dialog builds from a real shift summary and, critically, that
opening it never changes shift state (no counted-cash input, no closing).
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.constants.status import ShiftStatus
from cbpos.core.models import Permission, Role, Shift, User
from cbpos.core.services.shift_service import ShiftService
from cbpos.ui.dialogs.shift_status_dialog import ShiftStatusDialog

_counter = 0


@pytest.fixture
def test_user(db_session):
    """Create a test user with an open shift for the status dialog to read."""
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"shift_status_test_{suffix}")
    role = Role(name=f"ShiftStatusRole_{suffix}", permissions=[permission])
    user = User(username=f"shift_status_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.commit()
    return user


@pytest.fixture
def open_shift(db_session, test_user):
    with patch("cbpos.core.services.shift_service.ConfigService.get", return_value="TERM-01"):
        return ShiftService().start_shift(test_user.id, Decimal("5000.00"))


def test_dialog_shows_the_current_shift_summary_without_changing_its_state(qapp, db_session, test_user, open_shift):
    """Opening the dialog reads the summary but leaves the shift open and unmodified."""
    dialog = ShiftStatusDialog(open_shift.id)

    assert dialog.windowTitle() != ""

    db_session.expire_all()
    shift = db_session.get(Shift, open_shift.id)
    assert shift.status == ShiftStatus.OPEN
    assert shift.actual_cash is None
    assert shift.end_time is None

    dialog.deleteLater()
