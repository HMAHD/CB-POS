from typing import Any

import pandas as pd

from cbpos.core.reports.base_report import CATEGORY_FINANCIAL, DATE, INT, MONEY, TEXT, BaseReport, report_columns
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.i18n import _t


class OverdueCustomersReport(BaseReport):
    """Report showing customers with overdue credit balances."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "overdue_customers"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.overdue_customers")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_FINANCIAL

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """No filters; always shows all customers currently overdue."""
        return []

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so money and day counts right-align with separators."""
        return {
            "columns": report_columns(
                {
                    "Customer": TEXT,
                    "Phone": TEXT,
                    "Outstanding": MONEY,
                    "Credit Limit": MONEY,
                    "Days Overdue": INT,
                    "Last Payment": DATE,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """List overdue customers with outstanding balance, credit limit, and days overdue.

        Delegates the overdue calculation to ``CustomerCreditService``.
        """
        overdue = CustomerCreditService.get_overdue_customers()

        data = []
        for item in overdue:
            data.append(
                {
                    "Customer": item["name"],
                    "Phone": item["phone"],
                    "Outstanding": item["outstanding"],
                    "Credit Limit": item["credit_limit"],
                    "Days Overdue": item["days_overdue"],
                    "Last Payment": (
                        item["last_payment_date"].strftime("%Y-%m-%d") if item["last_payment_date"] else "Never"
                    ),
                }
            )

        df = pd.DataFrame(data)
        if df.empty:
            df = pd.DataFrame(
                columns=["Customer", "Phone", "Outstanding", "Credit Limit", "Days Overdue", "Last Payment"]
            )
        return df
