from typing import Any

import pandas as pd
from sqlalchemy import func

from cbpos.core.database import get_db_session
from cbpos.core.models import CashMovement, Product, StockMovement, User
from cbpos.core.reports.base_report import BaseReport


class StockMovementReport(BaseReport):
    @property
    def id(self) -> str:
        return "stock_movement"

    @property
    def name(self) -> str:
        return "Stock Movement Audit"

    @property
    def category(self) -> str:
        return "Audit"

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            query = session.query(StockMovement).join(Product).join(User)

            if start_date:
                query = query.filter(func.date(StockMovement.timestamp) >= start_date)
            if end_date:
                query = query.filter(func.date(StockMovement.timestamp) <= end_date)

            movements = query.order_by(StockMovement.timestamp.desc()).all()

            data = []
            for m in movements:
                data.append(
                    {
                        "Date": m.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "User": m.user.username,
                        "Product": m.product.name_en,
                        "Type": m.type,
                        "Qty Change": float(m.qty_change),
                        "Balance": float(m.balance_after),
                        "Reference": (f"Doc #{m.document_id}" if m.document_id else "N/A"),
                    }
                )

            return pd.DataFrame(data)


class CashMovementAuditReport(BaseReport):
    @property
    def id(self) -> str:
        return "cash_movement_audit"

    @property
    def name(self) -> str:
        return "Cash Movement Audit"

    @property
    def category(self) -> str:
        return "Audit"

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            query = session.query(CashMovement).join(User)

            if start_date:
                query = query.filter(func.date(CashMovement.timestamp) >= start_date)
            if end_date:
                query = query.filter(func.date(CashMovement.timestamp) <= end_date)

            movements = query.order_by(CashMovement.timestamp.desc()).all()

            data = []
            for m in movements:
                data.append(
                    {
                        "Date": m.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "User": m.user.username,
                        "Type": m.type,
                        "Amount": m.amount,
                        "Reason": m.reason,
                    }
                )

            df = pd.DataFrame(data)
            if not df.empty:
                # Calculate Net Movement for Footer/Summary
                # This logic might be better handled in the UI or a separate
                # summary dict,
                # but for a DataFrame report, we can just return the raw data.
                pass

            return df
