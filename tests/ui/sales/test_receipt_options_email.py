from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from cbpos.core.models import Permission, Role, Sale, User
from cbpos.core.services.email_service import EmailService
from cbpos.ui.dialogs.receipt_options_dialog import ReceiptOptionsDialog

_counter = 0


@pytest.fixture
def email_ui_sale(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"email_ui_perm_{_counter}")
    role = Role(name=f"EmailUiRole_{_counter}", permissions=[permission])
    user = User(username=f"email_ui_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()

    sale = Sale(
        document_number=f"REC-UI-EML-{_counter:04d}",
        date=datetime.now(),
        total_amount=Decimal("2500.00"),
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=2500,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.commit()
    return sale


class DummyWorker(QObject):
    finished = pyqtSignal(bool, str)


@pytest.mark.ui
def test_issue_792_not_configured_button_disabled(qapp, email_ui_sale):
    with patch.object(EmailService, "is_configured", return_value=False):
        dialog = ReceiptOptionsDialog(email_ui_sale)
        assert dialog.btn_email.isEnabled() is False
        assert len(dialog.btn_email.toolTip()) > 0


@pytest.mark.ui
def test_issue_792_configured_button_sends_email(qapp, email_ui_sale):
    dummy_worker = DummyWorker()
    with (
        patch.object(EmailService, "is_configured", return_value=True),
        patch.object(EmailService, "send_receipt", return_value=dummy_worker) as mock_send,
        patch("cbpos.ui.dialogs.receipt_options_dialog.QInputDialog.getText", return_value=("test@example.com", True)),
        patch("cbpos.ui.dialogs.receipt_options_dialog.QMessageBox.information") as mock_info,
    ):
        dialog = ReceiptOptionsDialog(email_ui_sale)
        assert dialog.btn_email.isEnabled() is True

        dialog.email_receipt()

        mock_send.assert_called_once_with(email_ui_sale, "test@example.com")
        assert dialog.btn_email.isEnabled() is False

        dummy_worker.finished.emit(True, "")
        assert dialog.btn_email.isEnabled() is True
        mock_info.assert_called_once()
