"""
Composable SQLAlchemy criteria for Sale document classification in reports.

Provides reusable query criteria:
- completed_sales(): ordinary completed sales (COMPLETED, not a refund document)
- refund_documents(): completed refund documents (COMPLETED, linked refund or payment_method == "REFUND")
- revenue_documents(): all completed revenue documents (completed_sales + refund_documents)
- voided(): voided documents (status == VOID)
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, or_

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Sale


def date_bounds(date_range: dict[str, Any] | None) -> tuple[datetime | None, datetime | None]:
    """Resolve start/end date filter to half-open datetime bounds [start, end)."""
    if not date_range:
        return None, None
    raw_start = date_range.get("start")
    raw_end = date_range.get("end")

    start_dt = None
    if raw_start:
        if isinstance(raw_start, datetime):
            start_dt = raw_start
        elif isinstance(raw_start, date):
            start_dt = datetime.combine(raw_start, time.min)
        elif isinstance(raw_start, str):
            start_dt = datetime.combine(date.fromisoformat(raw_start), time.min)

    end_dt = None
    if raw_end:
        if isinstance(raw_end, datetime):
            end_dt = raw_end
        elif isinstance(raw_end, date):
            end_dt = datetime.combine(raw_end + timedelta(days=1), time.min)
        elif isinstance(raw_end, str):
            end_dt = datetime.combine(date.fromisoformat(raw_end) + timedelta(days=1), time.min)

    return start_dt, end_dt


def completed_sales() -> Any:
    """Criteria for ordinary completed sales (excluding refund documents)."""
    return and_(
        Sale.status == DocumentStatus.COMPLETED,
        Sale.refund_of_sale_id.is_(None),
        Sale.payment_method != "REFUND",
    )


def refund_documents() -> Any:
    """Criteria for completed refund documents."""
    return and_(
        Sale.status == DocumentStatus.COMPLETED,
        or_(
            Sale.refund_of_sale_id.isnot(None),
            Sale.payment_method == "REFUND",
        ),
    )


def revenue_documents() -> Any:
    """Criteria for all revenue-affecting documents (completed sales and refunds, excluding voids)."""
    return Sale.status == DocumentStatus.COMPLETED


def voided() -> Any:
    """Criteria for voided sales."""
    return Sale.status == DocumentStatus.VOID
