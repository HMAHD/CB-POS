from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import func, select

from cbpos.core.constants.status import DocumentStatus
from cbpos.core.database import Database
from cbpos.core.models import Sale, User
from cbpos.core.reports.base_report import BaseReport
from cbpos.i18n import _t


class VoidRefundReport(BaseReport):
    """All voided and refunded transactions with reasons and user."""

    @property
    def id(self) -> str:
        return "void_refund"

    @property
    def name(self) -> str:
        return _t("reports.void_refund")

    @property
    def category(self) -> str:
        return _t("reports.category_audit")

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "date_range",
                "type": "date_range",
                "label": "Date Range",
                "default_start": date.today(),
                "default_end": date.today(),
            }
        ]

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        date_range = filters.get("date_range", {})
        start_date = date_range.get("start")
        end_date = date_range.get("end")

        with Database().get_session() as session:
            query = (
                session.query(Sale, User.username)
                .join(User, Sale.user_id == User.id)
                .filter(
                    Sale.status.in_([DocumentStatus.VOID, "REFUND"]),
                )
            )

            if start_date:
                query = query.filter(func.date(Sale.date) >= start_date)
            if end_date:
                query = query.filter(func.date(Sale.date) <= end_date)

            results = query.order_by(Sale.date.desc()).all()

            data = []
            for sale, username in results:
                data.append(
                    {
                        "Date": sale.date.strftime("%Y-%m-%d %H:%M") if sale.date else "",
                        "Document #": sale.document_number or "",
                        "Status": sale.status,
                        "Amount": float(sale.total_amount or 0),
                        "User": username,
                        "Payment": sale.payment_method or "",
                    }
                )

            df = pd.DataFrame(data)
            if df.empty:
                df = pd.DataFrame(columns=["Date", "Document #", "Status", "Amount", "User", "Payment"])
            return df


class PaymentMethodSummaryReport(BaseReport):
    """Breakdown of sales by payment method for a given period."""

    @property
    def id(self) -> str:
        return "payment_method_summary"

    @property
    def name(self) -> str:
        return _t("reports.payment_method_summary")

    @property
    def category(self) -> str:
        return _t("reports.category_sales")

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "date_range",
                "type": "date_range",
                "label": "Date Range",
                "default_start": date.today(),
                "default_end": date.today(),
            }
        ]

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        from cbpos.core.models import SalePayment

        date_range = filters.get("date_range", {})
        start_date = date_range.get("start")
        end_date = date_range.get("end")

        with Database().get_session() as session:
            stmt = (
                select(
                    SalePayment.payment_method,
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
                        "Total Amount": float(row.total) if row.total else 0.0,
                    }
                )

            df = pd.DataFrame(data)
            if df.empty:
                df = pd.DataFrame(columns=["Payment Method", "Transactions", "Total Amount"])
            return df
