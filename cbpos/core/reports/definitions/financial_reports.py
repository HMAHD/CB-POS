from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import func

from cbpos.core.database import get_db_session
from cbpos.core.models import Product, Purchase, Sale, SaleItem
from cbpos.core.reports.base_report import CATEGORY_FINANCIAL, DATE, MONEY, PERCENT, TEXT, BaseReport, report_columns
from cbpos.core.reports.sale_filters import completed_sales, date_bounds, refund_documents
from cbpos.core.services.tax_service import TaxService
from cbpos.core.utils.money import round_money
from cbpos.i18n import _t


class ProfitLossReport(BaseReport):
    """Per-sale-line revenue, cost, gross profit, and margin within a date range."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "profit_loss"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.profit_loss")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_FINANCIAL

    @property
    def required_permission(self) -> str:
        """Required permission code."""
        from cbpos.core.constants.permissions import Permissions

        return Permissions.REPORTS_VIEW_PROFIT

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Date range filter only."""
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types: Revenue, Cost (COGS) and Gross Profit are money."""
        return {
            "columns": report_columns(
                {
                    "Date": DATE,
                    "Invoice #": TEXT,
                    "Revenue": MONEY,
                    "Cost (COGS)": MONEY,
                    "Gross Profit": MONEY,
                    "Margin %": PERCENT,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """List revenue/cost/profit per sale item, one row per (sale, line item).

        COGS uses the product's *current* cost as a proxy — it is not the
        historical AVCO cost at the time of sale, so margins for products
        whose cost has since changed will be approximate.
        """
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
                        "Margin %": f"{margin_pct:.2f}%",
                    }
                )

            return pd.DataFrame(data)


class TaxLiabilityReport(BaseReport):
    """Per-sale VAT and SSCL breakdown, plus net VAT liability (Output - Input), within a date range."""

    requires_vat = True

    @property
    def id(self) -> str:
        """Report identifier."""
        return "tax_liability"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.tax_liability")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_FINANCIAL

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Date range filter only."""
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare money columns and bold the summary rows."""
        return {
            "columns": report_columns(
                {
                    "Date": DATE,
                    "Invoice #": TEXT,
                    "Total Sale": MONEY,
                    "Net Revenue": MONEY,
                    "VAT": MONEY,
                    "SSCL": MONEY,
                    "Total Tax": MONEY,
                    "Input VAT": MONEY,
                    "Net VAT Liability": MONEY,
                }
            ),
            "total_row_column": "Invoice #",
            "total_row_values": ["NET VAT LIABILITY", "TOTAL SALES", "TOTAL REFUNDS", "NET TOTALS"],
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """List each sale's total, net revenue, VAT, and SSCL within the range,
        with refunds shown in a separate section and netted,
        followed by one summary row: total Output VAT collected minus total Input VAT paid
        to suppliers (entered manually at GRN time, ``Purchase.input_vat``) = net VAT owed.

        If more than one distinct VAT rate was charged across the period's sales,
        appends a per-rate breakdown table.
        """
        with get_db_session() as session:
            start_dt, end_dt = date_bounds(filters.get("date_range"))

            # Query completed sales (excluding refund docs and voids)
            sales_q = session.query(Sale).filter(completed_sales())
            if start_dt:
                sales_q = sales_q.filter(Sale.date >= start_dt)
            if end_dt:
                sales_q = sales_q.filter(Sale.date < end_dt)
            sales = sales_q.order_by(Sale.date.asc()).all()

            # Query completed refund documents
            refunds_q = session.query(Sale).filter(refund_documents())
            if start_dt:
                refunds_q = refunds_q.filter(Sale.date >= start_dt)
            if end_dt:
                refunds_q = refunds_q.filter(Sale.date < end_dt)
            refunds = refunds_q.order_by(Sale.date.asc()).all()

            data = []

            # Sales section
            sales_total = Decimal("0")
            sales_net = Decimal("0")
            sales_vat = Decimal("0")
            sales_sscl = Decimal("0")
            sales_tax = Decimal("0")

            rate_stats: dict[Decimal, dict[str, Decimal]] = {}

            for s in sales:
                tot = s.total_amount or Decimal("0")
                net = s.net_revenue or Decimal("0")
                vat = s.tax_vat or Decimal("0")
                sscl = s.tax_sscl or Decimal("0")
                total_tax = vat + sscl

                sales_total += tot
                sales_net += net
                sales_vat += vat
                sales_sscl += sscl
                sales_tax += total_tax

                r = round_money(TaxService.resolve_historical_vat_rate(s))
                if r not in rate_stats:
                    rate_stats[r] = {"net": Decimal("0"), "vat": Decimal("0")}
                rate_stats[r]["net"] += net
                rate_stats[r]["vat"] += vat

                data.append(
                    {
                        "Date": s.date.strftime("%Y-%m-%d"),
                        "Invoice #": s.document_number,
                        "Total Sale": tot,
                        "Net Revenue": net,
                        "VAT": vat,
                        "SSCL": sscl,
                        "Total Tax": total_tax,
                        "Input VAT": None,
                        "Net VAT Liability": None,
                    }
                )

            data.append(
                {
                    "Date": "",
                    "Invoice #": "TOTAL SALES",
                    "Total Sale": sales_total,
                    "Net Revenue": sales_net,
                    "VAT": sales_vat,
                    "SSCL": sales_sscl,
                    "Total Tax": sales_tax,
                    "Input VAT": None,
                    "Net VAT Liability": None,
                }
            )

            # Refunds section
            refunds_total = Decimal("0")
            refunds_net = Decimal("0")
            refunds_vat = Decimal("0")
            refunds_sscl = Decimal("0")
            refunds_tax = Decimal("0")

            if refunds:
                for ref in refunds:
                    tot = -abs(ref.total_amount or Decimal("0"))
                    net = -abs(ref.net_revenue or Decimal("0"))
                    vat = -abs(ref.tax_vat or Decimal("0"))
                    sscl = -abs(ref.tax_sscl or Decimal("0"))
                    total_tax = vat + sscl

                    refunds_total += tot
                    refunds_net += net
                    refunds_vat += vat
                    refunds_sscl += sscl
                    refunds_tax += total_tax

                    r = round_money(TaxService.resolve_historical_vat_rate(ref))
                    if r not in rate_stats:
                        rate_stats[r] = {"net": Decimal("0"), "vat": Decimal("0")}
                    rate_stats[r]["net"] += net
                    rate_stats[r]["vat"] += vat

                    data.append(
                        {
                            "Date": ref.date.strftime("%Y-%m-%d"),
                            "Invoice #": ref.document_number,
                            "Total Sale": tot,
                            "Net Revenue": net,
                            "VAT": vat,
                            "SSCL": sscl,
                            "Total Tax": total_tax,
                            "Input VAT": None,
                            "Net VAT Liability": None,
                        }
                    )

                data.append(
                    {
                        "Date": "",
                        "Invoice #": "TOTAL REFUNDS",
                        "Total Sale": refunds_total,
                        "Net Revenue": refunds_net,
                        "VAT": refunds_vat,
                        "SSCL": refunds_sscl,
                        "Total Tax": refunds_tax,
                        "Input VAT": None,
                        "Net VAT Liability": None,
                    }
                )

                data.append(
                    {
                        "Date": "",
                        "Invoice #": "NET TOTALS",
                        "Total Sale": sales_total + refunds_total,
                        "Net Revenue": sales_net + refunds_net,
                        "VAT": sales_vat + refunds_vat,
                        "SSCL": sales_sscl + refunds_sscl,
                        "Total Tax": sales_tax + refunds_tax,
                        "Input VAT": None,
                        "Net VAT Liability": None,
                    }
                )

            # Input VAT from completed purchases
            purchase_query = session.query(Purchase).filter(Purchase.status == "COMPLETED")
            if start_dt:
                purchase_query = purchase_query.filter(Purchase.date >= start_dt)
            if end_dt:
                purchase_query = purchase_query.filter(Purchase.date < end_dt)
            input_vat_total = sum((p.input_vat for p in purchase_query.all()), Decimal("0"))

            output_vat_net = sales_vat + refunds_vat

            data.append(
                {
                    "Date": "",
                    "Invoice #": "NET VAT LIABILITY",
                    "Total Sale": None,
                    "Net Revenue": None,
                    "VAT": output_vat_net,
                    "SSCL": None,
                    "Total Tax": None,
                    "Input VAT": input_vat_total,
                    "Net VAT Liability": output_vat_net - input_vat_total,
                }
            )

            # Rate breakdown table (only if more than one distinct rate exists in the period)
            if len(rate_stats) > 1:
                data.append(
                    {
                        "Date": "",
                        "Invoice #": _t("reports.vat_by_rate"),
                        "Total Sale": None,
                        "Net Revenue": None,
                        "VAT": None,
                        "SSCL": None,
                        "Total Tax": None,
                        "Input VAT": None,
                        "Net VAT Liability": None,
                    }
                )
                for rate in sorted(rate_stats.keys()):
                    stats = rate_stats[rate]
                    rate_str = TaxService.format_rate(rate)
                    data.append(
                        {
                            "Date": "",
                            "Invoice #": f"VAT @ {rate_str}%",
                            "Total Sale": None,
                            "Net Revenue": stats["net"],
                            "VAT": stats["vat"],
                            "SSCL": None,
                            "Total Tax": stats["vat"],
                            "Input VAT": None,
                            "Net VAT Liability": None,
                        }
                    )

            return pd.DataFrame(data)


class TaxFilingSummaryReport(BaseReport):
    """Period summary report for filing VAT/SSCL returns with Inland Revenue."""

    requires_vat = True
    ZERO = Decimal("0")

    @property
    def id(self) -> str:
        """Report identifier."""
        return "tax_filing_summary"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.tax_filing_summary")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_FINANCIAL

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Period preset (monthly/quarterly/custom) plus the date range it resolves to."""
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

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so amounts right-align with separators."""
        return {
            "columns": report_columns(
                {
                    "Section": TEXT,
                    "Description": TEXT,
                    "Amount": MONEY,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
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
            # TODO(#844): use method_kind
            from cbpos.core.models import SalePayment

            payment_q = _date_filter(
                session.query(
                    SalePayment.payment_method,  # TODO(#844): use method_kind
                    func.sum(SalePayment.amount),
                )
                .join(Sale, SalePayment.sale_id == Sale.id)
                .filter(Sale.status != "VOID")
            ).group_by(SalePayment.payment_method)

            payment_totals: dict[str, Decimal] = {}
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
