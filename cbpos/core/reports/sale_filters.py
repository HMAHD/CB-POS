"""
Composable SQLAlchemy criteria for Sale document classification in reports.

Provides reusable query criteria:
- completed_sales(): ordinary completed sales (COMPLETED, not a refund document)
- refund_documents(): completed refund documents (COMPLETED, linked refund or payment_method == "REFUND")
- revenue_documents(): all completed revenue documents (completed_sales + refund_documents)
- voided(): voided documents (status == VOID)
"""

from typing import Any

from sqlalchemy import and_, or_

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.models import Sale


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
