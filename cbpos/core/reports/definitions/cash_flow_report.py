from typing import List, Dict, Any
import pandas as pd
from sqlalchemy import func
from cbpos.core.reports.base_report import BaseReport
from cbpos.core.database import get_db_session
from cbpos.core.models import Sale


class CashFlowReport(BaseReport):
    @property
    def id(self) -> str:
        return "cash_flow"

    @property
    def name(self) -> str:
        return "Cash Flow Report"

    @property
    def category(self) -> str:
        return "Financial"

    def get_filter_definitions(self) -> List[Dict[str, Any]]:
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def generate(self, filters: Dict[str, Any] = None) -> pd.DataFrame:
        if filters is None:
            filters = {}

        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            # 1. Total Sales (Inflow)
            query_sales = session.query(func.sum(Sale.total_amount)).filter(Sale.status == "COMPLETED")

            if start_date:
                query_sales = query_sales.filter(func.date(Sale.date) >= start_date)
            if end_date:
                query_sales = query_sales.filter(func.date(Sale.date) <= end_date)

            total_sales = float(query_sales.scalar() or 0)

            # 2. Refunds (Outflow)
            # Assuming refunds are tracked via negative sales or specific status
            # For now, let's query Sales where total_amount < 0 or specific refund logic
            # The system seems to use refund_of_sale_id for refunds, but are they stored as new Sales
            # with negative amount?
            # Based on HistoryView, refunds are new sales.
            # Let's check if they have negative amounts.
            # If not, we might need to check is_refund flag if it exists, or just rely on negative total.
            # I'll assume standard POS behavior: Refunds are negative or separate type.
            # OR better: check if refund_of_sale_id is not None.

            query_refunds = session.query(func.sum(Sale.total_amount)).filter(Sale.refund_of_sale_id.isnot(None))
            if start_date:
                query_refunds = query_refunds.filter(func.date(Sale.date) >= start_date)
            if end_date:
                query_refunds = query_refunds.filter(func.date(Sale.date) <= end_date)

            total_refunds = float(query_refunds.scalar() or 0)

            # 3. Expenses (Outflow) - Placeholder as no Expense model yet
            total_expenses = 0.0

            data = [
                {"Category": "Total Sales", "Amount": float(total_sales), "Type": "Inflow"},
                {"Category": "Refunds", "Amount": float(total_refunds), "Type": "Outflow"},
                {"Category": "Expenses", "Amount": float(total_expenses), "Type": "Outflow"},
                {
                    "Category": "Net Cash Flow",
                    "Amount": float(total_sales - total_refunds - total_expenses),
                    "Type": "Net",
                },
            ]

            return pd.DataFrame(data)
