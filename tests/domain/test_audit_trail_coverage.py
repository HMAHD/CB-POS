"""
#300: Void, Refund, Permission changes, Purchasing, and Credit adjustments
had zero audit trail. Routine logins were tracked in detail (AuditLog rows
for LOGIN/LOGOUT/TIMEOUT/SECURITY) while the actually consequential
actions -- voiding a sale, refunding a customer, changing what a Cashier
is allowed to do, committing a GRN, adjusting a customer's balance --
left no database record at all, only a plain logger.info() line.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from cbpos.core.models import (
    AuditLog,
    Customer,
    Permission,
    Product,
    Role,
    Sale,
    SaleItem,
    Supplier,
    User,
)
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.services.purchase_service import PurchaseService
from cbpos.core.services.transaction_service import TransactionService

_counter = 0


def _next_suffix() -> str:
    global _counter
    _counter += 1
    return str(_counter)


def _logs_for(db_session, action):
    return db_session.query(AuditLog).filter(AuditLog.action == action).all()


@pytest.fixture
def test_user(db_session):
    suffix = _next_suffix()
    permission = Permission(code=f"audit_test_{suffix}")
    role = Role(name=f"AuditRole_{suffix}", permissions=[permission])
    user = User(username=f"audit_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    suffix = _next_suffix()
    product = Product(
        name_en=f"Product_{suffix}", price=Decimal("100.00"), stock_qty=Decimal("10"), barcode=f"AUD{suffix}"
    )
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def completed_sale(db_session, test_user, test_product):
    sale = Sale(
        document_number=f"REC-AUD-{_next_suffix()}",
        date=datetime.now(),
        total_amount=Decimal("200.00"),
        user_id=test_user.id,
        tax_vat=0,
        tax_sscl=0,
        net_revenue=Decimal("200.00"),
        payment_method="CASH",
        status="COMPLETED",
    )
    db_session.add(sale)
    db_session.flush()

    item = SaleItem(
        sale_id=sale.id,
        product_id=test_product.id,
        qty=Decimal("2"),
        unit_price=Decimal("100.00"),
        original_price=Decimal("100.00"),
        subtotal=Decimal("200.00"),
    )
    db_session.add(item)
    db_session.commit()
    return sale


class TestVoidSaleAuditLog:
    def test_void_sale_writes_an_audit_log(self, db_session, test_user, completed_sale):
        TransactionService.void_sale(completed_sale.id, test_user.id, "Customer changed mind")

        logs = _logs_for(db_session, "VOID_SALE")
        assert len(logs) == 1
        assert logs[0].user_id == test_user.id
        assert logs[0].event_type == "TRANSACTION"
        assert completed_sale.document_number in logs[0].details
        assert "Customer changed mind" in logs[0].details

    def test_voiding_an_already_voided_sale_does_not_double_log(self, db_session, test_user, completed_sale):
        TransactionService.void_sale(completed_sale.id, test_user.id, "First void")
        TransactionService.void_sale(completed_sale.id, test_user.id, "Second attempt")

        assert len(_logs_for(db_session, "VOID_SALE")) == 1


class TestRefundAuditLog:
    def test_refund_writes_an_audit_log(self, db_session, test_user, completed_sale):
        TransactionService.process_refund(completed_sale.id, "Defective item", test_user.id)

        logs = _logs_for(db_session, "REFUND")
        assert len(logs) == 1
        assert logs[0].user_id == test_user.id
        assert logs[0].event_type == "TRANSACTION"
        assert completed_sale.document_number in logs[0].details
        assert "Defective item" in logs[0].details


class TestPermissionChangeAuditLog:
    def test_updating_role_permissions_writes_an_audit_log(self, db_session, test_user):
        suffix = _next_suffix()
        perm = Permission(code=f"perm_scope_{suffix}")
        role = Role(name=f"ScopedRole_{suffix}")
        test_user.role.permissions.append(perm)
        db_session.add_all([perm, role])
        db_session.flush()

        with patch(
            "cbpos.core.services.permission_service.AuthService.get_current_user",
            return_value=test_user,
        ):
            PermissionService.update_role_permissions(role.id, [perm.id])

        logs = _logs_for(db_session, "UPDATE_PERMISSIONS")
        assert len(logs) == 1
        assert logs[0].user_id == test_user.id
        assert logs[0].event_type == "SECURITY"
        assert role.name in logs[0].details

    def test_no_logged_in_user_does_not_crash_and_skips_logging(self, db_session):
        suffix = _next_suffix()
        perm = Permission(code=f"perm_scope_{suffix}")
        role = Role(name=f"ScopedRole_{suffix}")
        db_session.add_all([perm, role])
        db_session.flush()

        with patch(
            "cbpos.core.services.permission_service.AuthService.get_current_user",
            return_value=None,
        ):
            result = PermissionService.update_role_permissions(role.id, [perm.id])

        assert result is True
        assert _logs_for(db_session, "UPDATE_PERMISSIONS") == []


class TestPurchaseCommitAuditLog:
    def test_committing_a_purchase_writes_an_audit_log(self, db_session, test_user, test_product):
        suffix = _next_suffix()
        supplier = Supplier(company_name=f"Supplier_{suffix}")
        db_session.add(supplier)
        db_session.flush()

        purchase = PurchaseService.create_purchase(
            supplier_id=supplier.id,
            reference_external=f"INV-{suffix}",
            user_id=test_user.id,
        )
        PurchaseService.commit_purchase(
            purchase.id,
            [{"product_id": test_product.id, "qty": Decimal("5"), "cost": Decimal("40.00")}],
        )

        logs = _logs_for(db_session, "COMMIT_PURCHASE")
        assert len(logs) == 1
        assert logs[0].user_id == test_user.id
        assert logs[0].event_type == "PURCHASE"
        assert purchase.document_number in logs[0].details


class TestCreditAdjustmentAuditLog:
    def test_recording_an_adjustment_writes_an_audit_log(self, db_session, test_user):
        suffix = _next_suffix()
        customer = Customer(
            name=f"Customer_{suffix}",
            credit_limit=Decimal("10000.00"),
            current_debt=Decimal("500.00"),
        )
        db_session.add(customer)
        db_session.flush()

        CustomerCreditService.record_adjustment(customer.id, Decimal("-100.00"), "Goodwill correction", test_user.id)

        logs = _logs_for(db_session, "CREDIT_ADJUSTMENT")
        assert len(logs) == 1
        assert logs[0].user_id == test_user.id
        assert logs[0].event_type == "CREDIT"
        assert "Goodwill correction" in logs[0].details

    def test_recording_a_payment_writes_an_audit_log(self, db_session, test_user):
        suffix = _next_suffix()
        customer = Customer(
            name=f"Customer_{suffix}",
            credit_limit=Decimal("10000.00"),
            current_debt=Decimal("500.00"),
        )
        db_session.add(customer)
        db_session.flush()

        CustomerCreditService.record_payment(customer.id, Decimal("200.00"), "CASH", test_user.id)

        logs = _logs_for(db_session, "CREDIT_PAYMENT")
        assert len(logs) == 1
        assert logs[0].user_id == test_user.id
        assert logs[0].event_type == "CREDIT"
