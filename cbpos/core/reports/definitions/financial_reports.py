from decimal import Decimal
from typing import List, Dict, Any
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from cbpos.core.reports.base_report import BaseReport
from cbpos.core.database import get_db_session
from cbpos.core.models import Sale, SaleItem, Product


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
                        "Revenue": revenue,
                        "Cost (COGS)": cogs,
                        "Gross Profit": gross_profit,
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
                        "Total Sale": sale.total_amount,
                        "Net Revenue": sale.net_revenue,
                        "VAT (18%)": sale.tax_vat,
                        "SSCL (2.5%)": sale.tax_sscl,
                        "Total Tax": sale.tax_vat + sale.tax_sscl,
                    }
                )

            return pd.DataFrame(data)


class TaxFilingSummaryReport(BaseReport):
    """Period summary report for filing VAT/SSCL returns with Inland Revenue."""

    ZERO = Decimal("0")

    @property
    def id(self) -> str:
        return "tax_filing_summary"

    @property
    def name(self) -> str:
        return "Tax Filing Summary"

    @property
    def category(self) -> str:
        return "Financial"

    def get_filter_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "period",
                "label": "Period",
                "type": "combo",
                "options": [
                    {"id": "month", "label": "Monthly"},
                    {"id": "quarter", "label": "Quarterly"},
                    {"id": "custom", "label": "Custom Date Range"},
                ],
            },
            {"name": "date_range", "label": "Date Range", "type": "date_range"},
        ]

    def generate(self, filters: Dict[str, Any]) -> pd.DataFrame:
        """Generate tax filing summary for the selected period.

        Excludes voided sales. Refunds are subtracted from taxable amounts.
        Returns a single-period summary as a vertical key-value DataFrame.
        """
        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            # Base query: all non-void sales in period, eager-load payments
            query = session.query(Sale).options(joinedload(Sale.payments)).filter(Sale.status != "VOID")

            if start_date:
                query = query.filter(func.date(Sale.date) >= start_date)
            if end_date:
                query = query.filter(func.date(Sale.date) <= end_date)

            sales = query.all()

            # Separate regular sales from refunds
            regular_sales = [s for s in sales if s.refund_of_sale_id is None]
            refund_sales = [s for s in sales if s.refund_of_sale_id is not None]

            # --- Sales Summary ---
            total_sales_mrp = sum((s.total_amount or self.ZERO) for s in regular_sales)
            total_discounts = sum(
                (s.additional_discount_value or self.ZERO)
                for s in regular_sales
                if s.additional_discount_type != "NONE"
            )
            total_refunds = sum(abs(s.total_amount or self.ZERO) for s in refund_sales)
            net_sales = total_sales_mrp - total_refunds

            # --- VAT Computation ---
            taxable_vat = sum((s.tax_vat or self.ZERO) for s in regular_sales)
            refund_vat = sum(abs(s.tax_vat or self.ZERO) for s in refund_sales)
            taxable_net_revenue = sum((s.net_revenue or self.ZERO) for s in regular_sales)
            refund_net_revenue = sum(abs(s.net_revenue or self.ZERO) for s in refund_sales)
            vat_base = taxable_net_revenue - refund_net_revenue
            vat_liability = taxable_vat - refund_vat

            # --- SSCL Computation ---
            taxable_sscl = sum((s.tax_sscl or self.ZERO) for s in regular_sales)
            refund_sscl = sum(abs(s.tax_sscl or self.ZERO) for s in refund_sales)
            sscl_liable_turnover = net_sales * Decimal("0.5")
            sscl_liability = taxable_sscl - refund_sscl

            # --- Total Tax ---
            total_tax_liability = vat_liability + sscl_liability

            # --- Payment Summary ---
            payment_totals: Dict[str, Decimal] = {}
            for sale in sales:
                for payment in sale.payments:
                    method = payment.payment_method
                    amount = payment.amount or self.ZERO
                    # Refund payments reduce the total
                    if sale.refund_of_sale_id is not None:
                        amount = -abs(amount)
                    payment_totals[method] = payment_totals.get(method, self.ZERO) + amount

            # Build the summary as key-value rows
            sorted_methods = sorted(payment_totals.keys())
            data = [
                {
                    "Section": "SALES SUMMARY",
                    "Description": "Total Sales (MRP)",
                    "Amount": total_sales_mrp,
                },
                {
                    "Section": "",
                    "Description": "Total Discounts",
                    "Amount": total_discounts,
                },
                {
                    "Section": "",
                    "Description": "Total Refunds",
                    "Amount": total_refunds,
                },
                {
                    "Section": "",
                    "Description": "Net Sales",
                    "Amount": net_sales,
                },
                {
                    "Section": "",
                    "Description": "Number of Sales",
                    "Amount": Decimal(str(len(regular_sales))),
                },
                {
                    "Section": "",
                    "Description": "Number of Refunds",
                    "Amount": Decimal(str(len(refund_sales))),
                },
                {
                    "Section": "VAT COMPUTATION",
                    "Description": "VAT Base (Net Revenue)",
                    "Amount": vat_base,
                },
                {
                    "Section": "",
                    "Description": "VAT Liability (18%)",
                    "Amount": vat_liability,
                },
                {
                    "Section": "SSCL COMPUTATION",
                    "Description": "Liable Turnover (50%)",
                    "Amount": sscl_liable_turnover,
                },
                {
                    "Section": "",
                    "Description": "SSCL Liability (2.5%)",
                    "Amount": sscl_liability,
                },
                {
                    "Section": "TOTAL TAX",
                    "Description": "Total Tax Liability",
                    "Amount": total_tax_liability,
                },
            ]

            # Add payment method breakdown
            for i, method in enumerate(sorted_methods):
                data.append(
                    {
                        "Section": "PAYMENT SUMMARY" if i == 0 else "",
                        "Description": method,
                        "Amount": payment_totals[method],
                    }
                )

            return pd.DataFrame(data)
