from typing import List, Dict, Any
import pandas as pd
from sqlalchemy import func
from cbpos.core.reports.base_report import BaseReport
from cbpos.core.database import get_db_session
from cbpos.core.models import StockMovement, Product, User


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

    def get_filter_definitions(self) -> List[Dict[str, Any]]:
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def generate(self, filters: Dict[str, Any]) -> pd.DataFrame:
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
                        "Reference": (
                            f"Doc #{m.document_id}" if m.document_id else "N/A"
                        ),
                    }
                )

            return pd.DataFrame(data)
