"""Tests for DashboardService PostgreSQL compatibility (#886).

func.strftime is SQLite-only and fails on PostgreSQL.
Queries must use extract() and half-open date ranges.
"""

import os
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from cbpos.core.models import Base, Role, Sale, User
from cbpos.core.services.dashboard_service import DashboardService


@pytest.fixture
def user(db_session):
    u = User(username="dash_user", pin_hash="x", role_id=None, is_active=True)
    db_session.add(u)
    db_session.flush()
    return u


def test_issue_886_compiled_pg_sql_has_no_strftime(db_session):
    """Compile dashboard monthly and hourly queries for PostgreSQL dialect and assert no strftime."""
    monthly_q = DashboardService._monthly_sales_query(db_session, 2026)
    compiled_monthly = str(monthly_q.statement.compile(dialect=postgresql.dialect())).lower()
    assert "strftime" not in compiled_monthly, f"Found strftime in compiled monthly SQL: {compiled_monthly}"
    assert "extract" in compiled_monthly

    hourly_q = DashboardService._hourly_sales_query(db_session, date(2026, 1, 1), date(2026, 1, 31))
    compiled_hourly = str(hourly_q.statement.compile(dialect=postgresql.dialect())).lower()
    assert "strftime" not in compiled_hourly, f"Found strftime in compiled hourly SQL: {compiled_hourly}"
    assert "extract" in compiled_hourly


def test_issue_886_monthly_sales_aggregation_values(db_session, user):
    """Test get_monthly_sales aggregates correctly on SQLite."""
    # Seed sales in different months and years
    s1 = Sale(
        document_number="INV-2026-00001",
        date=datetime(2026, 1, 15, 10, 0, 0),
        total_amount=Decimal("1500.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user.id,
    )
    s2 = Sale(
        document_number="INV-2026-00002",
        date=datetime(2026, 1, 20, 11, 0, 0),
        total_amount=Decimal("500.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user.id,
    )
    s3 = Sale(
        document_number="INV-2026-00003",
        date=datetime(2026, 5, 1, 9, 0, 0),
        total_amount=Decimal("3000.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user.id,
    )
    s_other_year = Sale(
        document_number="INV-2025-00001",
        date=datetime(2025, 1, 15, 10, 0, 0),
        total_amount=Decimal("9999.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user.id,
    )
    db_session.add_all([s1, s2, s3, s_other_year])
    db_session.commit()

    monthly = DashboardService.get_monthly_sales(2026)
    assert len(monthly) == 12
    # Month 1 (Jan) total should be 2000.00
    jan = next(m for m in monthly if m["month"] == 1)
    assert jan["total"] == Decimal("2000.00")
    # Month 5 (May) total should be 3000.00
    may = next(m for m in monthly if m["month"] == 5)
    assert may["total"] == Decimal("3000.00")
    # Month 2 (Feb) total should be 0
    feb = next(m for m in monthly if m["month"] == 2)
    assert feb["total"] == Decimal("0")


def test_issue_886_hourly_sales_aggregation_values(db_session, user):
    """Test get_hourly_sales aggregates correctly on SQLite."""
    s1 = Sale(
        document_number="INV-2026-00010",
        date=datetime(2026, 3, 10, 9, 15, 0),
        total_amount=Decimal("1200.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user.id,
    )
    s2 = Sale(
        document_number="INV-2026-00011",
        date=datetime(2026, 3, 10, 9, 45, 0),
        total_amount=Decimal("800.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user.id,
    )
    s3 = Sale(
        document_number="INV-2026-00012",
        date=datetime(2026, 3, 10, 14, 0, 0),
        total_amount=Decimal("2500.00"),
        status="COMPLETED",
        payment_method="CASH",
        user_id=user.id,
    )
    db_session.add_all([s1, s2, s3])
    db_session.commit()

    hourly = DashboardService.get_hourly_sales(date(2026, 3, 10), date(2026, 3, 10))
    # 6AM to 10PM (17 hours: 6 to 22 inclusive)
    h9 = next(h for h in hourly if h["hour"] == 9)
    assert h9["total"] == Decimal("2000.00")

    h14 = next(h for h in hourly if h["hour"] == 14)
    assert h14["total"] == Decimal("2500.00")

    h10 = next(h for h in hourly if h["hour"] == 10)
    assert h10["total"] == Decimal("0")


@pytest.mark.postgres
def test_issue_886_dashboard_on_postgres(pg_engine, monkeypatch):
    """Run monthly and hourly sales against real PostgreSQL database."""
    pg_url = os.environ.get("CBPOS_TEST_PG_URL")
    assert pg_url

    Base.metadata.create_all(pg_engine)

    Session = sessionmaker(bind=pg_engine)
    with Session() as s:
        role = Role(name="Cashier")
        s.add(role)
        s.flush()
        user_obj = User(username="cashier1", role_id=role.id, pin_hash="x", is_active=True)
        s.add(user_obj)
        s.flush()

        sale = Sale(
            document_number="INV-PG-0001",
            date=datetime(2026, 2, 14, 11, 30, 0),
            total_amount=Decimal("1800.00"),
            status="COMPLETED",
            payment_method="CASH",
            user_id=user_obj.id,
        )
        s.add(sale)
        s.commit()

    # Monkeypatch Database.get_session to use pg_engine
    class MockDatabase:
        def get_session(self):
            return Session()

    monkeypatch.setattr("cbpos.core.services.dashboard_service.Database", MockDatabase)

    monthly = DashboardService.get_monthly_sales(2026)
    feb = next(m for m in monthly if m["month"] == 2)
    assert feb["total"] == Decimal("1800.00")

    hourly = DashboardService.get_hourly_sales(date(2026, 2, 1), date(2026, 2, 28))
    h11 = next(h for h in hourly if h["hour"] == 11)
    assert h11["total"] == Decimal("1800.00")
