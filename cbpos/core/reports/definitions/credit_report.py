from typing import Any

import pandas as pd
from sqlalchemy import select

from cbpos.core.database import Database
from cbpos.core.models import Customer
from cbpos.core.reports.base_report import MONEY, TEXT, BaseReport, report_columns
from cbpos.i18n import _t


class CustomerCreditReport(BaseReport):
    """Outstanding credit balances per customer with credit limit info."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "customer_credit"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.customer_credit")

    @property
    def category(self) -> str:
        """Report category."""
        return _t("reports.category_financial")

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """No filters; always shows all customers with an outstanding balance."""
        return []

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so money right-aligns with separators."""
        return {
            "columns": report_columns(
                {
                    "Customer": TEXT,
                    "Phone": TEXT,
                    "Credit Limit": MONEY,
                    "Outstanding": MONEY,
                    "Available": MONEY,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """List customers with debt > 0, ordered highest debt first.

        Includes credit limit and remaining available credit
        (limit minus current debt).
        """
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
