"""Facade module — preserves backward compatibility.

All receipt building has been split into focused builders:
- SalesReceiptBuilder (build_receipt)
- VoidReceiptBuilder (build_void_receipt)
- RefundReceiptBuilder (build_refund_receipt)
- ProformaReceiptBuilder (build_proforma)
- StatementReceiptBuilder (build_customer_statement)

This module re-exports a unified ReceiptBuilder class that delegates
to the appropriate builder, so existing callers don't need to change.
"""

from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder  # noqa: F401
from cbpos.core.services.void_receipt_builder import VoidReceiptBuilder  # noqa: F401
from cbpos.core.services.refund_receipt_builder import RefundReceiptBuilder  # noqa: F401
from cbpos.core.services.proforma_receipt_builder import ProformaReceiptBuilder  # noqa: F401
from cbpos.core.services.statement_receipt_builder import StatementReceiptBuilder  # noqa: F401


class ReceiptBuilder(
    SalesReceiptBuilder,
    VoidReceiptBuilder,
    RefundReceiptBuilder,
    ProformaReceiptBuilder,
    StatementReceiptBuilder,
):
    """Backward-compatible facade delegating to focused builders."""

    pass
