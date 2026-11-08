"""
Unit tests for shared sale filters (sale_filters.py).

Verifies composable SQLAlchemy criteria on real ORM rows in an SQLite session:
- completed_sales(): selects completed sales, excludes refunds and voids.
- refund_documents(): selects completed refunds, excludes sales and voids.
- revenue_documents(): selects completed sales + refunds, excludes voids and drafts.
- voided(): selects only voids.
- Disjointness: no overlap between completed sales and refunds.
"""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Customer, Sale, User
from cbpos.core.reports.sale_filters import (
    completed_sales,
    refund_documents,
    revenue_documents,
    voided,
)


@pytest.fixture
def sales_fixture(db_session):
    """Seed sample sales with various statuses, payments, and refund links."""
    u = User(username="filter_user", pin_hash="hash", is_active=True)
    c = Customer(name="Filter Customer")
    db_session.add_all([u, c])
    db_session.flush()

    # 1. Ordinary completed cash sale
    sale1 = Sale(
        document_number="S-001",
        date=datetime(2026, 11, 1, 10, 0),
        status=DocumentStatus.COMPLETED,
        total_amount=Decimal("1000.00"),
        net_revenue=Decimal("847.46"),
        tax_vat=Decimal("152.54"),
        payment_method="CASH",
        user_id=u.id,
        customer_id=c.id,
    )

    # 2. Ordinary completed card sale
    sale2 = Sale(
        document_number="S-002",
        date=datetime(2026, 11, 1, 11, 0),
        status=DocumentStatus.COMPLETED,
        total_amount=Decimal("500.00"),
        net_revenue=Decimal("423.73"),
        tax_vat=Decimal("76.27"),
        payment_method="CARD",
        user_id=u.id,
        customer_id=c.id,
    )

    db_session.add_all([sale1, sale2])
    db_session.flush()

    # 3. Linked refund document (COMPLETED with refund_of_sale_id)
    ref1 = Sale(
        document_number="REF-001",
        date=datetime(2026, 11, 2, 9, 0),
        status=DocumentStatus.COMPLETED,
        total_amount=Decimal("-300.00"),
        net_revenue=Decimal("-254.24"),
        tax_vat=Decimal("-45.76"),
        payment_method="CASH",
        refund_of_sale_id=sale1.id,
        user_id=u.id,
        customer_id=c.id,
    )

    # 4. Legacy refund document (payment_method == "REFUND", refund_of_sale_id is None)
    ref2 = Sale(
        document_number="REF-002",
        date=datetime(2026, 11, 2, 10, 0),
        status=DocumentStatus.COMPLETED,
        total_amount=Decimal("-200.00"),
        net_revenue=Decimal("-169.49"),
        tax_vat=Decimal("-30.51"),
        payment_method="REFUND",
        refund_of_sale_id=None,
        user_id=u.id,
        customer_id=c.id,
    )

    # 5. Voided sale
    void_sale = Sale(
        document_number="VOID-001",
        date=datetime(2026, 11, 1, 12, 0),
        status=DocumentStatus.VOID,
        total_amount=Decimal("800.00"),
        net_revenue=Decimal("677.97"),
        tax_vat=Decimal("122.03"),
        payment_method="CASH",
        user_id=u.id,
        customer_id=c.id,
    )

    # 6. Draft sale (unrelated status)
    draft_sale = Sale(
        document_number="DRAFT-001",
        date=datetime(2026, 11, 1, 13, 0),
        status=DocumentStatus.DRAFT,
        total_amount=Decimal("400.00"),
        net_revenue=Decimal("338.98"),
        tax_vat=Decimal("61.02"),
        payment_method="CASH",
        user_id=u.id,
        customer_id=c.id,
    )

    # 7. Suspended sale (unrelated status)
    suspended_sale = Sale(
        document_number="SUSP-001",
        date=datetime(2026, 11, 1, 14, 0),
        status=DocumentStatus.SUSPENDED,
        total_amount=Decimal("150.00"),
        net_revenue=Decimal("127.12"),
        tax_vat=Decimal("22.88"),
        payment_method="CASH",
        user_id=u.id,
        customer_id=c.id,
    )

    db_session.add_all([ref1, ref2, void_sale, draft_sale, suspended_sale])
    db_session.commit()

    return {
        "sales": [sale1, sale2],
        "refunds": [ref1, ref2],
        "voids": [void_sale],
        "others": [draft_sale, suspended_sale],
    }


def test_completed_sales_filter(db_session, sales_fixture):
    """completed_sales() matches ordinary sales and excludes refunds, voids, and drafts."""
    results = db_session.scalars(select(Sale).where(completed_sales())).all()
    doc_nums = {s.document_number for s in results}

    assert doc_nums == {"S-001", "S-002"}
    assert "REF-001" not in doc_nums
    assert "REF-002" not in doc_nums
    assert "VOID-001" not in doc_nums
    assert "DRAFT-001" not in doc_nums
    assert "SUSP-001" not in doc_nums


def test_refund_documents_filter(db_session, sales_fixture):
    """refund_documents() matches linked and legacy refunds and excludes regular sales and voids."""
    results = db_session.scalars(select(Sale).where(refund_documents())).all()
    doc_nums = {s.document_number for s in results}

    assert doc_nums == {"REF-001", "REF-002"}
    assert "S-001" not in doc_nums
    assert "S-002" not in doc_nums
    assert "VOID-001" not in doc_nums


def test_revenue_documents_filter(db_session, sales_fixture):
    """revenue_documents() matches all completed sales and refunds, excluding voids and non-completed."""
    results = db_session.scalars(select(Sale).where(revenue_documents())).all()
    doc_nums = {s.document_number for s in results}

    assert doc_nums == {"S-001", "S-002", "REF-001", "REF-002"}
    assert "VOID-001" not in doc_nums
    assert "DRAFT-001" not in doc_nums
    assert "SUSP-001" not in doc_nums


def test_voided_filter(db_session, sales_fixture):
    """voided() matches only void documents."""
    results = db_session.scalars(select(Sale).where(voided())).all()
    doc_nums = {s.document_number for s in results}

    assert doc_nums == {"VOID-001"}


def test_filters_are_disjoint_and_partition_revenue(db_session, sales_fixture):
    """completed_sales and refund_documents are mutually exclusive and union to revenue_documents."""
    sales_set = set(db_session.scalars(select(Sale.id).where(completed_sales())).all())
    refunds_set = set(db_session.scalars(select(Sale.id).where(refund_documents())).all())
    revenue_set = set(db_session.scalars(select(Sale.id).where(revenue_documents())).all())

    # Disjoint
    assert sales_set.isdisjoint(refunds_set)
    # Union equals revenue set
    assert sales_set | refunds_set == revenue_set
