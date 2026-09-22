from typing import Any

import pandas as pd

from cbpos.core.reports.base_report import BaseReport
from cbpos.core.services.customer_credit_service import CustomerCreditService
from cbpos.i18n import _t


class OverdueCustomersReport(BaseReport):
    """Report showing customers with overdue credit balances."""

    @property
    def id(self) -> str:
        return "overdue_customers"

    @property
    def name(self) -> str:
        return _t("reports.overdue_customers")

    @property
    def category(self) -> str:
        return _t("reports.category_financial")

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        return []

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        overdue = CustomerCreditService.get_overdue_customers()

        data = []
        for item in overdue:
            data.append(
                {
                    "Customer": item["name"],
                    "Phone": item["phone"],
                    "Outstanding": float(item["outstanding"]),
                    "Credit Limit": float(item["credit_limit"]),
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
