"""
Tests for SaleQueryService -- specifically that sale.payments is safe to
access on the detached Sale objects these methods return.

get_sales_history() and get_sale_details() both expunge() the Sale before
returning it, so any relationship not eager-loaded via joinedload() raises
DetachedInstanceError the moment something (SalesReceiptBuilder.build_receipt,
used by the reprint actions in sale_history_dialog.py and
receipt_reprint_dialog.py) tries to read it -- a real crash reported in
production. get_last_sale() already eager-loads payments correctly; the
other two methods didn't.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from cbpos.core.models import Permission, Product, Role, Sale, SaleItem, SalePayment, User
from cbpos.core.services.sale_query_service import SaleQueryService

_counter = 0


@pytest.fixture
def test_user(db_session):
    global _counter
    _counter += 1
    suffix = str(_counter)
    permission = Permission(code=f"sqs_test_{suffix}")
    role = Role(name=f"SqsRole_{suffix}", permissions=[permission])
    user = User(username=f"sqs_user_{suffix}", pin_hash="hash", role=role)
    db_session.add_all([permission, role, user])
    db_session.flush()
    return user


@pytest.fixture
def test_product(db_session):
    global _counter
    _counter += 1
    product = Product(
        name_en=f"SqsProduct_{_counter}",
        price=100.0,
        stock_qty=10.0,
        barcode=f"SQS{_counter:04d}",
    )
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def sale_with_payments(db_session, test_user, test_product):
    """A completed sale with one item and two payment rows (split payment)."""
    global _counter
    _counter += 1
    sale = Sale(
        document_number=f"REC-SQS-{_counter}",
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
    db_session.add(SalePayment(sale_id=sale.id, payment_method="Cash", amount=Decimal("150.00")))
    db_session.add(SalePayment(sale_id=sale.id, payment_method="Card", amount=Decimal("50.00")))
    db_session.commit()
    return sale


class TestPaymentsAreEagerLoaded:
    def test_get_sales_history_payments_accessible_after_session_closes(self, db_session, sale_with_payments):
        now = datetime.now()
        results = SaleQueryService.get_sales_history(now - timedelta(days=1), now + timedelta(days=1))

        matching = [s for s in results if s.id == sale_with_payments.id]
        assert len(matching) == 1
        sale = matching[0]

        # This is the exact access pattern that crashed with
        # DetachedInstanceError before payments was eager-loaded.
        amounts = sorted(p.amount for p in sale.payments)
        assert amounts == [Decimal("50.00"), Decimal("150.00")]

    def test_get_sale_details_payments_accessible_after_session_closes(self, db_session, sale_with_payments):
        sale_id = sale_with_payments.id

        # session.get()'s identity-map short-circuit returns an
        # already-resident instance as-is, ignoring joinedload options --
        # unlike production, where SaleQueryService always gets a brand
        # new, empty-identity-map session per call. Expunging the one
        # instance the fixture just inserted (the only thing that would
        # otherwise satisfy that short-circuit) forces get_sale_details()
        # below to actually run its query with the given options, so this
        # test exercises the same code path production does.
        db_session.expunge(sale_with_payments)

        sale = SaleQueryService.get_sale_details(sale_id)

        assert sale is not None
        amounts = sorted(p.amount for p in sale.payments)
        assert amounts == [Decimal("50.00"), Decimal("150.00")]


class TestSearchFilter:
    def test_search_by_customer_name_case_insensitive_and_phone(self, db_session, test_user, test_product):
        from cbpos.core.models import Customer

        cust = Customer(name="Sunil Perera", phone="0779876543")
        db_session.add(cust)
        db_session.flush()

        sale = Sale(
            document_number="REC-CUST-SEARCH-1",
            date=datetime.now(),
            user_id=test_user.id,
            customer_id=cust.id,
            total_amount=Decimal("200.00"),
            payment_method="CASH",
            status="COMPLETED",
        )
        db_session.add(sale)
        db_session.commit()

        now = datetime.now()
        start = now - timedelta(days=1)
        end = now + timedelta(days=1)

        # Search by partial lowercase customer name
        res_name = SaleQueryService.get_sales_history(start, end, search_term="sunil")
        assert any(s.id == sale.id for s in res_name)

        # Search by customer phone
        res_phone = SaleQueryService.get_sales_history(start, end, search_term="077987")
        assert any(s.id == sale.id for s in res_phone)

        # Search by receipt number
        res_rec = SaleQueryService.get_sales_history(start, end, search_term="CUST-SEARCH-1")
        assert any(s.id == sale.id for s in res_rec)
