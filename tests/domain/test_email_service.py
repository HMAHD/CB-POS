from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import Permission, Role, Sale, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.email_service import EmailService

_counter = 0


@pytest.fixture
def email_test_sale(db_session):
    global _counter
    _counter += 1
    permission = Permission(code=f"email_perm_{_counter}")
    role = Role(name=f"EmailRole_{_counter}", permissions=[permission])
    user = User(username=f"email_user_{_counter}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()

    sale = Sale(
        document_number=f"REC-EML-{_counter:04d}",
        date=datetime.now(),
        total_amount=Decimal("1500.00"),
        user_id=user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=1500,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.commit()
    return sale


@pytest.mark.domain
def test_issue_792_send_receipt_attaches_pdf(email_test_sale):
    with (
        patch("cbpos.core.services.email_service.deliver_email") as mock_deliver,
        patch("cbpos.core.services.invoice_service.InvoiceService.generate_pdf") as mock_pdf,
        patch.object(ConfigService, "get", side_effect=lambda k, d="": "Test Shop" if "shop" in k else "en"),
    ):
        worker = EmailService.send_receipt(email_test_sale, "buyer@example.com")
        assert worker.wait(5000), "Worker timed out"

        mock_pdf.assert_called_once()
        mock_deliver.assert_called_once()
        call_args = mock_deliver.call_args[0]
        to_email, subject, body, attachment = call_args

        assert to_email == "buyer@example.com"
        assert email_test_sale.document_number in subject
        assert "Test Shop" in subject
        assert email_test_sale.document_number in body
        assert attachment.endswith(".pdf")


@pytest.mark.domain
def test_issue_792_invalid_email_fails(qapp, email_test_sale):
    with patch("cbpos.core.services.email_service.deliver_email") as mock_deliver:
        results = []
        worker = EmailService.send_receipt(
            email_test_sale, "not-an-email", callback=lambda ok, msg: results.append((ok, msg))
        )
        assert worker.wait(5000), "Worker timed out"
        qapp.processEvents()

        assert results == [(False, "Invalid email address.")]
        assert worker.result_status == (False, "Invalid email address.")
        mock_deliver.assert_not_called()
