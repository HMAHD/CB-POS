"""Tests for issue #914: Concurrency locking in network mode for void and refund operations."""

import os
import threading
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from cbpos.core.models import Base, Product, Role, Sale, SaleItem, User
from cbpos.core.services.transaction_service import TransactionService


@pytest.fixture
def test_sale(db_session):
    """Fixture providing a committed test sale with one item."""
    role = Role(name="CashierRole_914")
    db_session.add(role)
    db_session.flush()

    user = User(username="cashier_914", pin_hash="hash", role_id=role.id)
    product = Product(
        barcode="BAR914001",
        name_en="Test Item 914",
        price=Decimal("150.00"),
        cost=Decimal("100.00"),
        stock_qty=Decimal("10.00"),
    )
    db_session.add_all([user, product])
    db_session.flush()

    sale = Sale(
        document_number="SALE-914-001",
        date=datetime.now(),
        total_amount=Decimal("150.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user.id,
        terminal_id="TERM-01",
        origin_terminal_id="TERM-01",
    )
    db_session.add(sale)
    db_session.flush()

    item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        qty=Decimal("1.00"),
        unit_price=Decimal("150.00"),
        original_price=Decimal("150.00"),
        subtotal=Decimal("150.00"),
    )
    db_session.add(item)
    db_session.commit()
    return sale


def test_issue_914_void_sale_requests_for_update(db_session, test_sale):
    """void_sale must load the Sale with with_for_update=True to serialize concurrent operations."""
    real_get = db_session.get
    requested_kwargs = []

    def mock_get(entity, ident, **kwargs):
        if entity is Sale:
            requested_kwargs.append(kwargs)
        return real_get(entity, ident, **kwargs)

    with patch("cbpos.core.database.Database.get_session") as mock_db:
        mock_db.return_value.__enter__.return_value = db_session
        mock_db.return_value.__exit__.return_value = False

        with patch.object(db_session, "get", side_effect=mock_get):
            res = TransactionService.void_sale(test_sale.id, user_id=test_sale.user_id, reason="Mistake")
            assert res is True
            assert any(kw.get("with_for_update") is True for kw in requested_kwargs)


def test_issue_914_process_refund_requests_for_update(db_session, test_sale):
    """process_refund must load the Sale with with_for_update=True to serialize concurrent operations."""
    real_get = db_session.get
    requested_kwargs = []

    def mock_get(entity, ident, **kwargs):
        if entity is Sale:
            requested_kwargs.append(kwargs)
        return real_get(entity, ident, **kwargs)

    with patch("cbpos.core.database.Database.get_session") as mock_db:
        mock_db.return_value.__enter__.return_value = db_session
        mock_db.return_value.__exit__.return_value = False

        with patch.object(db_session, "get", side_effect=mock_get):
            res = TransactionService.process_refund(test_sale.id, "Customer return", user_id=test_sale.user_id)
            assert res is True
            assert any(kw.get("with_for_update") is True for kw in requested_kwargs)


def test_issue_914_void_sale_refuses_refunded_sale(db_session, test_sale):
    """void_sale must refuse to void a sale that has already been refunded."""
    refund_sale = Sale(
        document_number="REF-914-001",
        date=datetime.now(),
        total_amount=Decimal("-150.00"),
        status="COMPLETED",
        payment_method="REFUND",
        user_id=test_sale.user_id,
        terminal_id="TERM-01",
        origin_terminal_id="TERM-01",
        refund_of_sale_id=test_sale.id,
    )
    db_session.add(refund_sale)
    db_session.commit()

    with patch("cbpos.core.database.Database.get_session") as mock_db:
        mock_db.return_value.__enter__.return_value = db_session
        mock_db.return_value.__exit__.return_value = False

        with pytest.raises(ValueError, match="sale_has_refund"):
            TransactionService.void_sale(test_sale.id, user_id=test_sale.user_id, reason="Cannot void")

    db_session.refresh(test_sale)
    assert test_sale.status != "VOID"


def test_issue_914_refund_refuses_voided_sale(db_session, test_sale):
    """process_refund must refuse to refund a voided sale."""
    test_sale.status = "VOID"
    db_session.commit()

    with patch("cbpos.core.database.Database.get_session") as mock_db:
        mock_db.return_value.__enter__.return_value = db_session
        mock_db.return_value.__exit__.return_value = False

        res = TransactionService.process_refund(test_sale.id, "Return voided", user_id=test_sale.user_id)
        assert res is False


def test_issue_914_refund_refuses_already_refunded_sale(db_session, test_sale):
    """process_refund must refuse when the sale has already been refunded."""
    with patch("cbpos.core.database.Database.get_session") as mock_db:
        mock_db.return_value.__enter__.return_value = db_session
        mock_db.return_value.__exit__.return_value = False

        # First refund succeeds
        assert TransactionService.process_refund(test_sale.id, "Return 1", user_id=test_sale.user_id) is True

        # Second refund fails
        assert TransactionService.process_refund(test_sale.id, "Return 2", user_id=test_sale.user_id) is False


@pytest.mark.postgres
def test_issue_914_concurrent_full_refunds_one_wins(pg_engine, monkeypatch):
    """Two concurrent threads attempt to refund the same sale in PostgreSQL.

    Row locking via with_for_update=True ensures they serialize, so exactly one
    refund is committed and the other is rejected.
    """
    pg_url = os.environ.get("CBPOS_TEST_PG_URL")
    assert pg_url

    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    Base.metadata.create_all(pg_engine)

    Session = sessionmaker(bind=pg_engine)

    with Session() as s:
        role = Role(name="CashierRole_PG")
        s.add(role)
        s.flush()
        user = User(username="cashier_pg", pin_hash="hash", role_id=role.id)
        prod = Product(
            barcode="BARPG001",
            name_en="PG Item",
            price=Decimal("200.00"),
            cost=Decimal("150.00"),
            stock_qty=Decimal("20.00"),
        )
        s.add_all([user, prod])
        s.flush()

        sale = Sale(
            document_number="SALE-PG-001",
            date=datetime.now(),
            total_amount=Decimal("200.00"),
            status="COMPLETED",
            payment_method="CASH",
            user_id=user.id,
            terminal_id="TERM-01",
            origin_terminal_id="TERM-01",
        )
        s.add(sale)
        s.flush()
        item = SaleItem(
            sale_id=sale.id,
            product_id=prod.id,
            qty=Decimal("1.00"),
            unit_price=Decimal("200.00"),
            original_price=Decimal("200.00"),
            subtotal=Decimal("200.00"),
        )
        s.add(item)
        s.commit()
        sale_id = sale.id
        user_id = user.id

    class MockDatabase:
        def get_session(self):
            return Session()

    monkeypatch.setattr("cbpos.core.services.transaction_service.Database", MockDatabase)

    barrier = threading.Barrier(2)
    results = []

    def run_refund():
        barrier.wait()
        res = TransactionService.process_refund(sale_id, "Race refund", user_id=user_id)
        results.append(res)

    t1 = threading.Thread(target=run_refund)
    t2 = threading.Thread(target=run_refund)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one succeeded and one failed
    assert results.count(True) == 1
    assert results.count(False) == 1

    # Exactly one refund document exists in DB
    with Session() as s:
        refund_count = s.query(Sale).filter(Sale.refund_of_sale_id == sale_id).count()
        assert refund_count == 1


@pytest.mark.postgres
def test_issue_914_concurrent_void_and_refund_one_wins(pg_engine, monkeypatch):
    """Two concurrent threads attempt to void and refund the same sale in PostgreSQL.

    Row locking via with_for_update=True serializes them: either void wins and refund fails,
    or refund wins and void fails. Both never succeed together.
    """
    pg_url = os.environ.get("CBPOS_TEST_PG_URL")
    assert pg_url

    with pg_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    Base.metadata.create_all(pg_engine)

    Session = sessionmaker(bind=pg_engine)

    with Session() as s:
        role = Role(name="CashierRole_PG2")
        s.add(role)
        s.flush()
        user = User(username="cashier_pg2", pin_hash="hash", role_id=role.id)
        prod = Product(
            barcode="BARPG002",
            name_en="PG Item 2",
            price=Decimal("300.00"),
            cost=Decimal("200.00"),
            stock_qty=Decimal("15.00"),
        )
        s.add_all([user, prod])
        s.flush()

        sale = Sale(
            document_number="SALE-PG-002",
            date=datetime.now(),
            total_amount=Decimal("300.00"),
            status="COMPLETED",
            payment_method="CASH",
            user_id=user.id,
            terminal_id="TERM-01",
            origin_terminal_id="TERM-01",
        )
        s.add(sale)
        s.flush()
        item = SaleItem(
            sale_id=sale.id,
            product_id=prod.id,
            qty=Decimal("1.00"),
            unit_price=Decimal("300.00"),
            original_price=Decimal("300.00"),
            subtotal=Decimal("300.00"),
        )
        s.add(item)
        s.commit()
        sale_id = sale.id
        user_id = user.id

    class MockDatabase:
        def get_session(self):
            return Session()

    monkeypatch.setattr("cbpos.core.services.transaction_service.Database", MockDatabase)

    barrier = threading.Barrier(2)
    void_result = []
    refund_result = []

    def run_void():
        barrier.wait()
        res = TransactionService.void_sale(sale_id, user_id=user_id, reason="Concurrent void")
        void_result.append(res)

    def run_refund():
        barrier.wait()
        res = TransactionService.process_refund(sale_id, "Concurrent refund", user_id=user_id)
        refund_result.append(res)

    t1 = threading.Thread(target=run_void)
    t2 = threading.Thread(target=run_refund)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # One and only one operation succeeded
    if void_result == [True]:
        # Void won: refund must have returned False
        assert refund_result == [False]
    else:
        # Refund won: void must have returned False
        assert void_result == [False]
        assert refund_result == [True]
