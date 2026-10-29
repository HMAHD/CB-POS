"""
#327: ReceiptPreviewDialog was a genuine "see the real receipt before it
prints" surface, but a full-repo grep found no caller instantiating it
anywhere -- built, but dead. The only preview a user ever saw was the
Settings page's mock, built from a dummy sale, never the real one about
to print. Wire it into the post-checkout ReceiptOptionsDialog (the
dialog that already gates printing) as a "Preview" button, reusing the
same ReceiptBuilder.build_receipt() the real print job and the Settings
mock both already use.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, User
from cbpos.infrastructure.hardware.escpos_driver import PrintWorker
from cbpos.ui.dialogs.receipt_options_dialog import ReceiptOptionsDialog

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"rop_test_{suffix}")
    role = Role(name=f"RopRole_{suffix}", permissions=[permission])
    user = User(username=f"rop_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(name_en=f"RopProduct_{_counter}", price=100.0, stock_qty=10.0, barcode=f"ROP{_counter:04d}")
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def sale(db_session, test_user, test_product):
    global _counter
    _counter += 1
    sale = Sale(
        document_number=f"REC-ROP-{_counter}",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=200,
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.flush()
    db_session.add(
        SaleItem(
            sale_id=sale.id,
            product_id=test_product.id,
            qty=2.0,
            unit_price=100.0,
            original_price=100.0,
            subtotal=200.0,
        )
    )
    db_session.commit()
    return sale


@pytest.fixture
def dialog(qapp, sale):
    dlg = ReceiptOptionsDialog(sale)
    yield dlg
    PrintWorker.shutdown()
    dlg.deleteLater()


class TestPreviewButtonShowsTheRealReceipt:
    def test_preview_button_exists(self, dialog):
        assert dialog.btn_preview is not None

    def test_clicking_preview_opens_a_dialog_built_from_the_real_sale(self, dialog, sale):
        with patch("cbpos.ui.dialogs.receipt_options_dialog.ReceiptPreviewDialog") as mock_preview_cls:
            mock_preview_cls.return_value.exec.return_value = None
            dialog.show_preview()

        args, _ = mock_preview_cls.call_args
        commands = args[0]
        assert isinstance(commands, list)
        assert len(commands) > 0
        mock_preview_cls.return_value.exec.assert_called_once()
