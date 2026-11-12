"""Unit and integration tests for statutory VAT Tax Credit Notes (#814).

Under VAT Act No. 14 of 2002 Section 25:
- Adjustments/refunds for sales with an issued Tax Invoice must generate a Tax Credit Note.
- Direct voiding of sales with a Tax Invoice is strictly prohibited.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.constants.status import DocumentStatus
from cbpos.core.database import Base
from cbpos.core.models import (
    Permission,
    Product,
    Role,
    Sale,
    SaleItem,
    SalePayment,
    User,
)
from cbpos.core.models.tax_invoice import TaxCreditNote
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.refund_service import RefundLineRequest, RefundService
from cbpos.core.services.tax_invoice_service import TaxInvoiceService
from cbpos.core.services.transaction_service import TransactionService


@pytest.fixture
def test_setup(db_session):
    Base.metadata.create_all(bind=db_session.bind)

    ConfigService.set("vat_registered", True)
    ConfigService.set("tax_vat_enabled", True)
    ConfigService.set("tax_vat_rate", 18.0)
    ConfigService.set("company_tax_id", "100200300")
    ConfigService.set("company_name", "Test Supermarket Ltd")
    ConfigService.set("company_address", "123 Galle Road, Colombo 03")
    ConfigService.set("company_phone", "0112345678")
    ConfigService.set("terminal_id", "TERM-01")
    ConfigService.set("terminal_mode", "standalone")

    role = Role(name="Admin", access_level=9)
    db_session.add(role)
    db_session.flush()

    for perm_code in [Permissions.SALES_TAX_INVOICE, Permissions.SALES_REFUND]:
        perm = db_session.query(Permission).filter_by(code=perm_code).first()
        if not perm:
            perm = Permission(code=perm_code, description=perm_code, group="Sales")
            db_session.add(perm)
            db_session.flush()
        role.permissions.append(perm)

    user = User(username="admin", role_id=role.id, is_active=True, pin_hash=AuthService.hash_pin("1234"))
    db_session.add(user)
    db_session.flush()

    AuthService._current_user = user
    user_id = user.id

    prod = Product(
        name_en="Ceylon Black Tea 500g",
        barcode="479100000001",
        price=Decimal("1180.00"),
        cost=Decimal("800.00"),
        stock_qty=Decimal("100.000"),
        is_active=True,
    )
    db_session.add(prod)
    db_session.flush()

    # Create sale: 1 unit = Rs. 1180.00 inclusive of 18% VAT (Net = 1000.00, VAT = 180.00)
    sale = Sale(
        document_number="INV-2026-0001",
        date=datetime.now(),
        total_amount=Decimal("1180.00"),
        tax_vat=Decimal("180.00"),
        tax_sscl=Decimal("0.00"),
        net_revenue=Decimal("1000.00"),
        vat_rate=Decimal("18.00"),
        payment_method="CASH",
        status=DocumentStatus.COMPLETED,
        user_id=user_id,
    )
    db_session.add(sale)
    db_session.flush()

    item = SaleItem(
        sale_id=sale.id,
        product_id=prod.id,
        qty=Decimal("1.000"),
        unit_price=Decimal("1180.00"),
        original_price=Decimal("1180.00"),
        subtotal=Decimal("1180.00"),
        vat_exempt=False,
        sscl_exempt=True,
    )
    db_session.add(item)

    payment = SalePayment(
        sale_id=sale.id,
        payment_method="CASH",
        amount=Decimal("1180.00"),
    )
    db_session.add(payment)
    db_session.commit()

    return {
        "user_id": user_id,
        "sale_id": sale.id,
        "item_id": item.id,
        "product_id": prod.id,
    }


def test_refund_generates_tax_credit_note(test_setup, db_session):
    user_id = test_setup["user_id"]
    sale_id = test_setup["sale_id"]
    item_id = test_setup["item_id"]

    buyer_details = {
        "name": "Lanka Traders PLC",
        "address": "45 Temple Road, Colombo",
        "phone": "0771234567",
        "tin": "987654321",
    }

    # 1. Issue official VAT Tax Invoice
    invoice = TaxInvoiceService.issue_tax_invoice(
        sale_id=sale_id,
        buyer_details=buyer_details,
        user_id=user_id,
    )
    assert invoice is not None
    assert invoice.serial.startswith("26")

    # 2. Process refund for 1 item
    req = RefundLineRequest(sale_item_id=item_id, qty=Decimal("1.000"), reason="Damaged Packaging")
    result = RefundService.refund(
        sale_id=sale_id,
        lines=[req],
        reason="Customer Return",
        user_id=user_id,
    )
    assert result.total_refund_amount == Decimal("1180.00")

    # 3. Verify TaxCreditNote is created
    cn = db_session.query(TaxCreditNote).filter_by(tax_invoice_id=invoice.id).first()
    assert cn is not None
    assert cn.refund_sale_id == result.refund_sale_id
    assert cn.serial.startswith("CN_") or cn.serial.startswith("CN-")
    assert invoice.serial in cn.serial
    assert cn.total_amount == Decimal("1180.00")
    assert cn.net_amount == Decimal("1000.00")
    assert cn.tax_vat == Decimal("180.00")
    assert "One Thousand One Hundred Eighty Rupees Only" in cn.amount_in_words
    assert cn.reason == "Customer Return"


def test_void_sale_with_tax_invoice_is_blocked(test_setup):
    user_id = test_setup["user_id"]
    sale_id = test_setup["sale_id"]

    buyer_details = {
        "name": "Lanka Traders PLC",
        "address": "45 Temple Road, Colombo",
        "phone": "0771234567",
        "tin": "987654321",
    }

    # Issue tax invoice
    TaxInvoiceService.issue_tax_invoice(
        sale_id=sale_id,
        buyer_details=buyer_details,
        user_id=user_id,
    )

    # Attempting to void the sale must raise ValueError
    with pytest.raises(ValueError, match="cannot_void_tax_invoice_sale"):
        TransactionService.void_sale(sale_id, "Mistake entry", user_id)
