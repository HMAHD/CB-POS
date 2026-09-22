from typing import Any

import pandas as pd
from sqlalchemy import select

from cbpos.core.database import Database
from cbpos.core.models import Customer
from cbpos.core.reports.base_report import BaseReport
from cbpos.i18n import _t


class CustomerCreditReport(BaseReport):
    """Outstanding credit balances per customer with credit limit info."""

    @property
    def id(self) -> str:
        return "customer_credit"

    @property
    def name(self) -> str:
        return _t("reports.customer_credit")

    @property
    def category(self) -> str:
        return _t("reports.category_financial")

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        return []

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        with Database().get_session() as session:
            stmt = (
                select(
                    Customer.name,
                    Customer.phone,
                    Customer.credit_limit,
                    Customer.current_debt,
                )
                .where(Customer.current_debt > 0)
                .order_by(Customer.current_debt.desc())
            )

            results = session.execute(stmt).all()

            data = []
            for row in results:
                available = float(row.credit_limit or 0) - float(row.current_debt or 0)
                data.append(
                    {
                        "Customer": row.name,
                        "Phone": row.phone or "",
                        "Credit Limit": float(row.credit_limit or 0),
                        "Outstanding": float(row.current_debt or 0),
                        "Available": available,
                    }
                )

            df = pd.DataFrame(data)
            if df.empty:
                df = pd.DataFrame(columns=["Customer", "Phone", "Credit Limit", "Outstanding", "Available"])
            return df
