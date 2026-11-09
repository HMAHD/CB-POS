"""
Composable SQLAlchemy criteria for Sale document classification in reports.

Provides reusable query criteria:
- completed_sales(): ordinary completed sales (COMPLETED, not a refund document)
- refund_documents(): completed refund documents (COMPLETED, linked refund or payment_method == "REFUND")
- revenue_documents(): all completed revenue documents (completed_sales + refund_documents)
- voided(): voided documents (status == VOID)
"""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Sale
from cbpos.core.utils.date_ranges import range_for


def date_bounds(date_range: dict[str, Any] | None) -> tuple[datetime | None, datetime | None]:
    """Resolve start/end date filter to half-open datetime bounds [start, end)."""
    if not date_range:
        return None, None
    return range_for(date_range.get("start"), date_range.get("end"))


def completed_sales() -> Any:
    """Criteria for ordinary completed sales (excluding refund documents)."""
    return and_(
        Sale.status == DocumentStatus.COMPLETED,
        Sale.refund_of_sale_id.is_(None),
        or_(Sale.payment_method.is_(None), Sale.payment_method != "REFUND"),
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
