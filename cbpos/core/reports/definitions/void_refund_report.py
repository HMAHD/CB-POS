import re
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Sale
from cbpos.core.reports.base_report import (
    CATEGORY_AUDIT,
    CATEGORY_SALES,
    DATE,
    INT,
    MONEY,
    TEXT,
    BaseReport,
    report_columns,
)
from cbpos.core.reports.sale_filters import date_bounds, refund_documents, voided
from cbpos.core.services.refund_service import RefundService
from cbpos.i18n import _t


class VoidRefundReport(BaseReport):
    """All voided and refunded transactions with reasons and user."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "void_refund"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.void_refund")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_AUDIT

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Date range filter, defaulting to today."""
        return [
            {
                "name": "date_range",
                "type": "date_range",
                "label": "Date Range",
                "default_start": date.today(),
                "default_end": date.today(),
            }
        ]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so amounts right-align with separators."""
        return {
            "columns": report_columns(
                {
                    "Date": DATE,
                    "Document #": TEXT,
                    "Type": TEXT,
                    "Scope": TEXT,
                    "Original Receipt": TEXT,
                    "Amount": MONEY,
                    "User": TEXT,
                    "Approver": TEXT,
                    "Reason": TEXT,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """List voided and completed refund documents within the date range, newest first.

        Includes original receipt, acting cashier, manager approver from AuditLog,
        translated type/scope, and negative amounts for refunds (#843).
        """
        date_range = filters.get("date_range", {})
        start_dt, end_dt = date_bounds(date_range)

        with Database().get_session() as session:
            query = (
                session.query(Sale)
                .options(
                    joinedload(Sale.user),
                    joinedload(Sale.refund_of_sale),
                    joinedload(Sale.void_reason),
                    joinedload(Sale.items),
                )
                .filter(
                    or_(voided(), refund_documents()),
                )
            )

            if start_dt:
                query = query.filter(Sale.date >= start_dt)
            if end_dt:
                query = query.filter(Sale.date < end_dt)

            sales = query.order_by(Sale.date.desc()).all()

            if not sales:
                return pd.DataFrame(
                    columns=[
                        "Date",
                        "Document #",
                        "Type",
                        "Scope",
                        "Original Receipt",
                        "Amount",
                        "User",
                        "Approver",
                        "Reason",
                    ]
                )

            orig_sale_ids = [s.refund_of_sale_id for s in sales if s.refund_of_sale_id]
            refund_states = RefundService.refund_states(orig_sale_ids, session=session) if orig_sale_ids else {}

            doc_numbers = [s.document_number for s in sales if s.document_number]
            doc_audits: dict[str, list[AuditLog]] = {}
            if doc_numbers:
                # Query in chunks of 100 to avoid SQLite expression tree limits
                chunk_size = 100
                audit_entries: list[AuditLog] = []
                for i in range(0, len(doc_numbers), chunk_size):
                    chunk = doc_numbers[i : i + chunk_size]
                    audit_entries.extend(
                        session.query(AuditLog)
                        .options(joinedload(AuditLog.user))
                        .filter(
                            AuditLog.action.in_(["VOID_SALE", "REFUND", "REFUND_TENDER_OVERRIDE", "OVERRIDE_AUTH"]),
                            or_(*[AuditLog.details.like(f"%{doc_no}%") for doc_no in chunk]),
                        )
                        .order_by(AuditLog.id.asc())
                        .all()
                    )

                for audit in audit_entries:
                    details = audit.details or ""
                    for doc_no in doc_numbers:
                        if doc_no in details:
                            doc_audits.setdefault(doc_no, []).append(audit)

            data = []
            for sale in sales:
                is_void = sale.status == DocumentStatus.VOID
                doc_no = sale.document_number or ""
                matching_audits = doc_audits.get(doc_no, [])

                # 1. Type
                doc_type = _t("reports.type_void") if is_void else _t("reports.type_refund")

                # 2. Scope
                if is_void:
                    scope = "-"
                else:
                    rf_state = refund_states.get(sale.refund_of_sale_id, "NONE")
                    scope = _t("reports.scope_full") if rf_state == "FULL" else _t("reports.scope_part")

                # 3. Original receipt
                orig_receipt = (
                    sale.refund_of_sale.document_number
                    if (sale.refund_of_sale and sale.refund_of_sale.document_number)
                    else "-"
                )

                # 4. Amount (negative for refunds)
                amount = sale.total_amount or Decimal(0)
                if not is_void:
                    amount = -abs(amount)

                # 5. Acting user
                user_name = sale.user.username if sale.user else ""

                # 6. Approver
                approver = None
                primary_actions = ["VOID_SALE"] if is_void else ["REFUND"]
                for audit in matching_audits:
                    if audit.action in primary_actions and audit.user and audit.user.username:
                        approver = audit.user.username
                        break
                if not approver:
                    for audit in matching_audits:
                        if audit.user and audit.user.username:
                            approver = audit.user.username
                            break
                if not approver:
                    approver = user_name

                # 7. Reason
                reason = ""
                if is_void:
                    if sale.void_reason and sale.void_reason.description:
                        reason = sale.void_reason.description
                else:
                    item_reasons = [it.refund_reason for it in sale.items if it.refund_reason]
                    if item_reasons:
                        reason = ", ".join(dict.fromkeys(item_reasons))

                if not reason:
                    for audit in matching_audits:
                        details = audit.details or ""
                        if "Reason:" in details:
                            match = re.search(r"Reason:\s*([^.]+)", details)
                            if match:
                                reason = match.group(1).strip()
                                break
                            else:
                                reason = details.split("Reason:", 1)[1].strip()
                                break

                data.append(
                    {
                        "Date": sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "",
                        "Document #": doc_no,
                        "Type": doc_type,
                        "Scope": scope,
                        "Original Receipt": orig_receipt,
                        "Amount": amount,
                        "User": user_name,
                        "Approver": approver,
                        "Reason": reason,
                    }
                )

            return pd.DataFrame(data)


class PaymentMethodSummaryReport(BaseReport):
    """Breakdown of sales by payment method for a given period."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "payment_method_summary"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.payment_method_summary")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_SALES

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Date range filter, defaulting to today."""
        return [
            {
                "name": "date_range",
                "type": "date_range",
                "label": "Date Range",
                "default_start": date.today(),
                "default_end": date.today(),
            }
        ]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so counts and money right-align with separators."""
        return {
            "columns": report_columns(
                {
                    "Payment Method": TEXT,
                    "Transactions": INT,
                    "Total Amount": MONEY,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """Sum transaction count and total amount per payment method for completed sales."""
        from cbpos.core.models import SalePayment

        date_range = filters.get("date_range", {})
        start_date = date_range.get("start")
        end_date = date_range.get("end")

        with Database().get_session() as session:
            # TODO(#844): use method_kind
            stmt = (
                select(
                    SalePayment.payment_method,  # TODO(#844): use method_kind
                    func.count(SalePayment.id).label("count"),
                    func.sum(SalePayment.amount).label("total"),
                )
                .join(Sale)
                .where(Sale.status == DocumentStatus.COMPLETED)
            )

            if start_date:
                stmt = stmt.where(func.date(Sale.date) >= start_date)
            if end_date:
                stmt = stmt.where(func.date(Sale.date) <= end_date)

            stmt = stmt.group_by(SalePayment.payment_method).order_by(func.sum(SalePayment.amount).desc())

            results = session.execute(stmt).all()

            data = []
            for row in results:
                data.append(
                    {
                        "Payment Method": row.payment_method,
                        "Transactions": row.count,
                        "Total Amount": row.total if row.total is not None else Decimal(0),
                    }
                )

            df = pd.DataFrame(data)
            if df.empty:
                df = pd.DataFrame(columns=["Payment Method", "Transactions", "Total Amount"])
            return df
