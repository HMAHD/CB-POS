from typing import List, Dict, Any
import pandas as pd
from sqlalchemy import func
from cbpos.core.reports.base_report import BaseReport
from cbpos.core.database import get_db_session
from cbpos.core.models import Sale, SaleItem, Product
from cbpos.core.utils.formatters import format_currency


class ProfitLossReport(BaseReport):
    @property
    def id(self) -> str:
        return "profit_loss"

    @property
    def name(self) -> str:
        return "Profit & Loss Statement"

    @property
    def category(self) -> str:
        return "Financial"

    def get_filter_definitions(self) -> List[Dict[str, Any]]:
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def generate(self, filters: Dict[str, Any]) -> pd.DataFrame:
        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            # Query Sale Items with Product Cost
            query = (
                session.query(
                    Sale.date,
                    Sale.document_number,
                    SaleItem.qty,
                    SaleItem.unit_price,
                    Product.cost.label("unit_cost"),
                )
                .join(Sale, SaleItem.sale_id == Sale.id)
                .join(Product, SaleItem.product_id == Product.id)
            )

            if start_date:
                query = query.filter(func.date(Sale.date) >= start_date)
            if end_date:
                query = query.filter(func.date(Sale.date) <= end_date)

            results = query.all()

            data = []
            for row in results:
                qty = float(row.qty or 0)
                revenue = qty * float(row.unit_price or 0)
                # Using current product cost as proxy for COGS
                cogs = qty * float(row.unit_cost or 0)
                gross_profit = revenue - cogs
                margin_pct = (gross_profit / revenue * 100) if revenue else 0

                data.append(
                    {
                        "Date": row.date.strftime("%Y-%m-%d"),
                        "Invoice #": row.document_number,
                        "Revenue": format_currency(revenue),
                        "Cost (COGS)": format_currency(cogs),
                        "Gross Profit": format_currency(gross_profit),
                        "Margin %": f"{margin_pct:.2f}%",  # noqa: E231
                    }
                )

            return pd.DataFrame(data)


class TaxLiabilityReport(BaseReport):
    @property
    def id(self) -> str:
        return "tax_liability"

    @property
    def name(self) -> str:
        return "Tax Liability Report"

    @property
    def category(self) -> str:
        return "Financial"

    def get_filter_definitions(self) -> List[Dict[str, Any]]:
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def generate(self, filters: Dict[str, Any]) -> pd.DataFrame:
        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            query = session.query(Sale)

            if start_date:
                query = query.filter(func.date(Sale.date) >= start_date)
            if end_date:
                query = query.filter(func.date(Sale.date) <= end_date)

            sales = query.all()

            data = []
            for sale in sales:
                data.append(
                    {
                        "Date": sale.date.strftime("%Y-%m-%d"),
                        "Invoice #": sale.document_number,
                        "Total Sale": format_currency(sale.total_amount),
                        "Net Revenue": format_currency(sale.net_revenue),
                        "VAT (18%)": format_currency(sale.tax_vat),
                        "SSCL (2.5%)": format_currency(sale.tax_sscl),
                        "Total Tax": format_currency(sale.tax_vat + sale.tax_sscl),
                    }
                )

            return pd.DataFrame(data)
