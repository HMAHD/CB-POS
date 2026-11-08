import logging
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from cbpos.core.constants.status import PaymentMethodKind
from cbpos.core.database import get_db_session
from cbpos.core.models import Purchase, Sale
from cbpos.core.reports.base_report import CATEGORY_FINANCIAL, DATE, MONEY, PERCENT, TEXT, BaseReport, report_columns
from cbpos.core.reports.sale_filters import completed_sales, date_bounds, refund_documents, revenue_documents
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.payment_service import classify_method_name
from cbpos.core.services.tax_service import TaxService
from cbpos.core.utils.money import round_money
from cbpos.i18n import _t

logger = logging.getLogger(__name__)


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
        """Declare column types: Revenue, Cost (COGS), SSCL Expense and Gross Profit are money."""
        return {
            "columns": report_columns(
                {
                    "Date": DATE,
                    "Invoice #": TEXT,
                    "Revenue": MONEY,
                    "Cost (COGS)": MONEY,
                    "SSCL Expense": MONEY,
                    "Gross Profit": MONEY,
                    "Margin %": PERCENT,
                }
            ),
            "total_row_column": "Invoice #",
            "total_row_values": ["TOTAL"],
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """List revenue, cost (COGS), SSCL expense, gross profit and margin per completed revenue document.

        Uses stored historical SaleItem.unit_cost for COGS (never product's current cost),
        revenue net of VAT (net_revenue + tax_sscl), SSCL as an explicit expense,
        and excludes voided transactions.
        """
        with get_db_session() as session:
            start_dt, end_dt = date_bounds(filters.get("date_range"))

            query = session.query(Sale).options(joinedload(Sale.items)).filter(revenue_documents())
            if start_dt:
                query = query.filter(Sale.date >= start_dt)
            if end_dt:
                query = query.filter(Sale.date < end_dt)

            sales = query.order_by(Sale.date.asc()).all()

            data = []
            total_rev = Decimal("0.00")
            total_cogs = Decimal("0.00")
            total_sscl = Decimal("0.00")

            for sale in sales:
                rev = round_money((sale.net_revenue or Decimal("0.00")) + (sale.tax_sscl or Decimal("0.00")))
                sscl = round_money(sale.tax_sscl or Decimal("0.00"))

                cogs = Decimal("0.00")
                for item in sale.items:
                    if item.unit_cost is not None:
                        line_cost = item.unit_cost
                    else:
                        logger.warning("SaleItem %s has null unit_cost; using 0.00 to preserve history", item.id)
                        line_cost = Decimal("0.00")
                    cogs += round_money(line_cost * (item.qty or Decimal("0.000")))

                cogs = round_money(cogs)
                gp = rev - cogs - sscl
                margin = round_money(gp / rev * Decimal("100")) if rev != Decimal("0.00") else Decimal("0.00")

                data.append(
                    {
                        "Date": sale.date.strftime("%Y-%m-%d") if sale.date else "",
                        "Invoice #": sale.document_number or "",
                        "Revenue": rev,
                        "Cost (COGS)": cogs,
                        "SSCL Expense": sscl,
                        "Gross Profit": gp,
                        "Margin %": f"{margin:.2f}%",
                    }
                )

                total_rev += rev
                total_cogs += cogs
                total_sscl += sscl

            if data:
                total_gp = total_rev - total_cogs - total_sscl
                total_margin = (
                    round_money(total_gp / total_rev * Decimal("100"))
                    if total_rev != Decimal("0.00")
                    else Decimal("0.00")
                )
                data.append(
                    {
                        "Date": "",
                        "Invoice #": "TOTAL",
                        "Revenue": total_rev,
                        "Cost (COGS)": total_cogs,
                        "SSCL Expense": total_sscl,
                        "Gross Profit": total_gp,
                        "Margin %": f"{total_margin:.2f}%",
                    }
                )
                df = pd.DataFrame(data)
            else:
                df = pd.DataFrame(
                    columns=["Date", "Invoice #", "Revenue", "Cost (COGS)", "SSCL Expense", "Gross Profit", "Margin %"]
                )

            return df


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
            input_vat_query = session.query(func.coalesce(func.sum(Purchase.input_vat), Decimal("0"))).filter(
                Purchase.status == "COMPLETED"
            )
            if start_dt:
                input_vat_query = input_vat_query.filter(Purchase.date >= start_dt)
            if end_dt:
                input_vat_query = input_vat_query.filter(Purchase.date < end_dt)
            input_vat_total = input_vat_query.scalar() or Decimal("0")

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
        Returns a single-period summary as a vertical key-value DataFrame.
        """
        with get_db_session() as session:
            start_dt, end_dt = date_bounds(filters.get("date_range"))

            # Query completed sales (excluding refund docs and voids)
            sales_q = (
                session.query(Sale).options(joinedload(Sale.items), joinedload(Sale.payments)).filter(completed_sales())
            )
            if start_dt:
                sales_q = sales_q.filter(Sale.date >= start_dt)
            if end_dt:
                sales_q = sales_q.filter(Sale.date < end_dt)
            completed = sales_q.order_by(Sale.date.asc()).all()

            # Query completed refund documents
            refunds_q = (
                session.query(Sale)
                .options(joinedload(Sale.items), joinedload(Sale.payments))
                .filter(refund_documents())
            )
            if start_dt:
                refunds_q = refunds_q.filter(Sale.date >= start_dt)
            if end_dt:
                refunds_q = refunds_q.filter(Sale.date < end_dt)
            refunds = refunds_q.order_by(Sale.date.asc()).all()

            # Aggregations
            total_sales_mrp = sum((s.total_amount or Decimal("0")) for s in completed)
            total_refunds = sum(abs(r.total_amount or Decimal("0")) for r in refunds)
            net_sales = total_sales_mrp - total_refunds
            regular_count = len(completed)
            refund_count = len(refunds)

            taxable_vat = sum((s.tax_vat or Decimal("0")) for s in completed)
            refund_vat = sum(abs(r.tax_vat or Decimal("0")) for r in refunds)
            vat_liability = taxable_vat - refund_vat

            taxable_sscl = sum((s.tax_sscl or Decimal("0")) for s in completed)
            refund_sscl = sum(abs(r.tax_sscl or Decimal("0")) for r in refunds)
            sscl_liability = taxable_sscl - refund_sscl

            taxable_net_revenue = sum((s.net_revenue or Decimal("0")) for s in completed)
            refund_net_revenue = sum(abs(r.net_revenue or Decimal("0")) for r in refunds)
            vat_base = taxable_net_revenue - refund_net_revenue

            # Discounts over completed sales (line discounts + bill discount + loyalty discount)
            total_discounts = Decimal("0.00")
            for s in completed:
                line_disc = Decimal("0.00")
                for it in s.items:
                    orig_price = it.original_price if it.original_price is not None else it.unit_price
                    if orig_price is not None and it.qty is not None and it.subtotal is not None:
                        line_disc += max(Decimal("0.00"), (orig_price * it.qty) - it.subtotal)

                bill_disc = Decimal("0.00")
                if s.additional_discount_type == "PERCENTAGE" and s.additional_discount_value:
                    items_subtotal = sum((it.subtotal or Decimal("0.00")) for it in s.items)
                    bill_disc = round_money(items_subtotal * (s.additional_discount_value / Decimal("100")))
                elif s.additional_discount_type == "FIXED" and s.additional_discount_value:
                    bill_disc = s.additional_discount_value

                loyalty_disc = s.loyalty_points_value or Decimal("0.00")
                total_discounts += line_disc + bill_disc + loyalty_disc

            # SSCL liable turnover (VAT-exclusive basis reconciled with tax_sscl)
            total_sscl_turnover = Decimal("0.00")
            default_turnover_pct = Decimal(str(ConfigService.get("tax_sscl_turnover_pct") or 50.0))
            for s in completed:
                if s.sscl_registered or (s.tax_sscl and s.tax_sscl > Decimal("0")):
                    base = (
                        s.sscl_base
                        if s.sscl_base is not None
                        else ((s.net_revenue or Decimal("0")) + (s.tax_sscl or Decimal("0")))
                    )
                    pct = s.sscl_turnover_pct if s.sscl_turnover_pct is not None else default_turnover_pct
                    total_sscl_turnover += base * (pct / Decimal("100"))

            for r in refunds:
                if r.sscl_registered or (r.tax_sscl and r.tax_sscl != Decimal("0")):
                    base = (
                        abs(r.sscl_base)
                        if r.sscl_base is not None
                        else abs((r.net_revenue or Decimal("0")) + (r.tax_sscl or Decimal("0")))
                    )
                    pct = r.sscl_turnover_pct if r.sscl_turnover_pct is not None else default_turnover_pct
                    total_sscl_turnover -= base * (pct / Decimal("100"))

            sscl_liable_turnover = round_money(total_sscl_turnover)
            total_tax_liability = vat_liability + sscl_liability

            # Stored or configured SSCL rate for display
            configured_sscl_rate = Decimal(str(ConfigService.get("tax_sscl_rate") or "2.50"))

            # Payment summary grouped by method_kind (3A, #844)
            payment_totals: dict[str, Decimal] = {}
            for s in completed:
                if s.payments:
                    for p in s.payments:
                        kind = p.method_kind or classify_method_name(p.payment_method)
                        payment_totals[kind] = payment_totals.get(kind, Decimal("0.00")) + (p.amount or Decimal("0.00"))
                else:
                    kind = classify_method_name(s.payment_method)
                    payment_totals[kind] = payment_totals.get(kind, Decimal("0.00")) + (
                        s.total_amount or Decimal("0.00")
                    )

            for r in refunds:
                if r.payments:
                    for p in r.payments:
                        kind = p.method_kind or classify_method_name(p.payment_method)
                        payment_totals[kind] = payment_totals.get(kind, Decimal("0.00")) - abs(
                            p.amount or Decimal("0.00")
                        )
                else:
                    kind = classify_method_name(r.payment_method)
                    payment_totals[kind] = payment_totals.get(kind, Decimal("0.00")) - abs(
                        r.total_amount or Decimal("0.00")
                    )

            KIND_DISPLAY = {
                PaymentMethodKind.CASH: "Cash",
                PaymentMethodKind.CARD: "Card",
                PaymentMethodKind.CREDIT: "Credit",
                PaymentMethodKind.QR: "QR Code",
                PaymentMethodKind.TRANSFER: "Bank Transfer",
                PaymentMethodKind.CHEQUE: "Cheque",
                PaymentMethodKind.OTHER: "Other",
            }

            data = [
                {
                    "Section": "SALES SUMMARY",
                    "Description": "Total Sales (MRP)",
                    "Amount": total_sales_mrp,
                },
                {
                    "Section": "",
                    "Description": "Discounts given on sales",
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
                    "Description": "Liable Turnover",
                    "Amount": sscl_liable_turnover,
                },
                {
                    "Section": "",
                    "Description": "SSCL Liability",
                    "Amount": sscl_liability,
                },
                {
                    "Section": "SSCL FOR THE QUARTER",
                    "Description": "Quarterly Liable Turnover",
                    "Amount": sscl_liable_turnover,
                },
                {
                    "Section": "",
                    "Description": "SSCL Rate",
                    "Amount": configured_sscl_rate,
                },
                {
                    "Section": "",
                    "Description": "Quarterly SSCL Liability",
                    "Amount": sscl_liability,
                },
                {
                    "Section": "TOTAL TAX",
                    "Description": "Total Tax Liability",
                    "Amount": total_tax_liability,
                },
            ]

            # Payment breakdown
            for i, kind in enumerate(sorted(payment_totals.keys())):
                label = KIND_DISPLAY.get(kind, str(kind).capitalize())
                data.append(
                    {
                        "Section": "PAYMENT SUMMARY" if i == 0 else "",
                        "Description": label,
                        "Amount": payment_totals[kind],
                    }
                )

            return pd.DataFrame(data)
