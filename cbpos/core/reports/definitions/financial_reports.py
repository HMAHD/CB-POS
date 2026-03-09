from decimal import Decimal
from typing import List, Dict, Any
import pandas as pd
from sqlalchemy import func

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
        Uses SQL aggregation for performance on large datasets.
        Returns a single-period summary as a vertical key-value DataFrame.
        """
        with get_db_session() as session:
            date_range = filters.get("date_range", {})
            start_date = date_range.get("start")
            end_date = date_range.get("end")

            # Date filter helper
            def _date_filter(q):
                if start_date:
                    q = q.filter(func.date(Sale.date) >= start_date)
                if end_date:
                    q = q.filter(func.date(Sale.date) <= end_date)
                return q

            # Aggregate regular sales (non-void, non-refund)
            regular_q = _date_filter(
                session.query(
                    func.coalesce(func.sum(Sale.total_amount), 0),
                    func.coalesce(func.sum(Sale.tax_vat), 0),
                    func.coalesce(func.sum(Sale.tax_sscl), 0),
                    func.coalesce(func.sum(Sale.net_revenue), 0),
                    func.count(Sale.id),
                ).filter(Sale.status != "VOID", Sale.refund_of_sale_id.is_(None))
            )
            reg = regular_q.one()
            total_sales_mrp = Decimal(str(reg[0]))
            taxable_vat = Decimal(str(reg[1]))
            taxable_sscl = Decimal(str(reg[2]))
            taxable_net_revenue = Decimal(str(reg[3]))
            regular_count = reg[4]

            # Aggregate refund sales (non-void, has refund_of_sale_id)
            refund_q = _date_filter(
                session.query(
                    func.coalesce(func.sum(func.abs(Sale.total_amount)), 0),
                    func.coalesce(func.sum(func.abs(Sale.tax_vat)), 0),
                    func.coalesce(func.sum(func.abs(Sale.tax_sscl)), 0),
                    func.coalesce(func.sum(func.abs(Sale.net_revenue)), 0),
                    func.count(Sale.id),
                ).filter(Sale.status != "VOID", Sale.refund_of_sale_id.isnot(None))
            )
            ref = refund_q.one()
            total_refunds = Decimal(str(ref[0]))
            refund_vat = Decimal(str(ref[1]))
            refund_sscl = Decimal(str(ref[2]))
            refund_net_revenue = Decimal(str(ref[3]))
            refund_count = ref[4]

            # Computed values
            net_sales = total_sales_mrp - total_refunds
            total_discounts = self.ZERO  # Discount tracking requires item-level data
            vat_base = taxable_net_revenue - refund_net_revenue
            vat_liability = taxable_vat - refund_vat
            sscl_liable_turnover = net_sales * Decimal("0.5")
            sscl_liability = taxable_sscl - refund_sscl
            total_tax_liability = vat_liability + sscl_liability

            # Payment summary via SQL aggregation
            from cbpos.core.models import SalePayment

            payment_q = _date_filter(
                session.query(
                    SalePayment.payment_method,
                    func.sum(SalePayment.amount),
                )
                .join(Sale, SalePayment.sale_id == Sale.id)
                .filter(Sale.status != "VOID")
            ).group_by(SalePayment.payment_method)

            payment_totals: Dict[str, Decimal] = {}
            for method, total in payment_q.all():
                payment_totals[method] = Decimal(str(total or 0))

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
                    "Amount": Decimal(str(regular_count)),
                },
                {
                    "Section": "",
                    "Description": "Number of Refunds",
                    "Amount": Decimal(str(refund_count)),
                },
                {
                    "Section": "VAT COMPUTATION",
                    "Description": "VAT Base (Net Revenue)",
                    "Amount": vat_base,
                },
                {
                    "Section": "",
                    "Description": "VAT Liability",
                    "Amount": vat_liability,
                },
                {
                    "Section": "SSCL COMPUTATION",
                    "Description": "Liable Turnover (50%)",
                    "Amount": sscl_liable_turnover,
                },
                {
                    "Section": "",
                    "Description": "SSCL Liability",
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
