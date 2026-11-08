from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import select

from cbpos.core.constants.status import DocumentStatus, PaymentMethodKind
from cbpos.core.database import get_db_session
from cbpos.core.models import CashMovement, Sale, SalePayment
from cbpos.core.reports.base_report import CATEGORY_FINANCIAL, MONEY, TEXT, BaseReport, report_columns
from cbpos.core.reports.sale_filters import date_bounds
from cbpos.core.services.refund_breakdown import refund_cash_back
from cbpos.i18n import _t


class CashFlowReport(BaseReport):
    """Net cash flow for a period: sales inflow minus refunds and drawer cash movements."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "cash_flow"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.cash_flow")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_FINANCIAL

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Date range filter only."""
        return [{"name": "date_range", "label": "Date Range", "type": "date_range"}]

    def get_render_hints(self) -> dict[str, Any]:
        """Color inflow/outflow rows and bold the Net Cash Flow total row."""
        return {
            "columns": report_columns({"Category": TEXT, "Amount": MONEY, "Type": TEXT}),
            "total_row_column": "Type",
            "total_row_values": ["Net"],
            "color_column": "Type",
            "color_map": {"Inflow": "success", "Outflow": "danger"},
        }

    def generate(self, filters: dict[str, Any] | None = None) -> pd.DataFrame:
        """Compute cash flow from payments grouped by PaymentMethodKind and drawer movements.

        - Cash Inflow = sum of positive CASH-kind payments from completed sales.
        - Cash Outflow = sum of absolute negative CASH-kind payments, plus legacy cash-back share.
        - Drawer In / Out = genuine cash drawer movements.
        - Other tenders reported with their respective inflow, refund and net.
        - Pure Decimal throughout (#844).
        """
        if filters is None:
            filters = {}

        date_range = filters.get("date_range", {})
        start_dt, end_dt = date_bounds(date_range)

        with get_db_session() as session:
            # 1. Query payments from valid completed revenue documents (sales & completed refunds)
            stmt_payments = (
                select(SalePayment)
                .join(Sale, SalePayment.sale_id == Sale.id)
                .where(Sale.status == DocumentStatus.COMPLETED)
            )
            if start_dt:
                stmt_payments = stmt_payments.where(Sale.date >= start_dt)
            if end_dt:
                stmt_payments = stmt_payments.where(Sale.date < end_dt)

            payments = session.scalars(stmt_payments).all()

            inflows: dict[str, Decimal] = {}
            refunds: dict[str, Decimal] = {}
            refunded_sale_ids_with_payments: set[int] = set()

            for p in payments:
                amt = p.amount or Decimal("0.00")
                kind = p.method_kind or PaymentMethodKind.OTHER

                if kind == PaymentMethodKind.REFUND_LEGACY:
                    cash_portion = refund_cash_back(abs(amt), Decimal("0.00"))
                    refunds[PaymentMethodKind.CASH] = (
                        refunds.get(PaymentMethodKind.CASH, Decimal("0.00")) + cash_portion
                    )
                    refunded_sale_ids_with_payments.add(p.sale_id)
                else:
                    if amt > 0:
                        inflows[kind] = inflows.get(kind, Decimal("0.00")) + amt
                    elif amt < 0:
                        refunds[kind] = refunds.get(kind, Decimal("0.00")) + abs(amt)
                        refunded_sale_ids_with_payments.add(p.sale_id)

            # 2. Check for legacy completed refund sales that have NO SalePayment rows
            stmt_legacy_refunds = select(Sale).where(
                Sale.status == DocumentStatus.COMPLETED,
                Sale.refund_of_sale_id.isnot(None),
            )
            if start_dt:
                stmt_legacy_refunds = stmt_legacy_refunds.where(Sale.date >= start_dt)
            if end_dt:
                stmt_legacy_refunds = stmt_legacy_refunds.where(Sale.date < end_dt)

            legacy_refund_sales = session.scalars(stmt_legacy_refunds).all()
            for rfs in legacy_refund_sales:
                if rfs.id not in refunded_sale_ids_with_payments:
                    cash_portion = refund_cash_back(abs(rfs.total_amount or Decimal("0.00")), Decimal("0.00"))
                    refunds[PaymentMethodKind.CASH] = (
                        refunds.get(PaymentMethodKind.CASH, Decimal("0.00")) + cash_portion
                    )

            # 3. Drawer movements
            stmt_movements = select(CashMovement)
            if start_dt:
                stmt_movements = stmt_movements.where(CashMovement.timestamp >= start_dt)
            if end_dt:
                stmt_movements = stmt_movements.where(CashMovement.timestamp < end_dt)

            movements = session.scalars(stmt_movements).all()
            drawer_in = Decimal("0.00")
            drawer_out = Decimal("0.00")
            for m in movements:
                m_type = (m.type or "").upper()
                amt = m.amount or Decimal("0.00")
                if m_type == "IN":
                    drawer_in += amt
                elif m_type in ("OUT", "DROP", "PAYOUT"):
                    drawer_out += amt

            # 4. Build output data
            data: list[dict[str, Any]] = []

            # Physical Cash Section
            cash_in = inflows.get(PaymentMethodKind.CASH, Decimal("0.00"))
            cash_refunded = refunds.get(PaymentMethodKind.CASH, Decimal("0.00"))
            net_cash = cash_in - cash_refunded + drawer_in - drawer_out

            data.append({"Category": "Cash Sales", "Amount": cash_in, "Type": "Inflow"})
            data.append({"Category": "Cash Refunds", "Amount": cash_refunded, "Type": "Outflow"})
            if drawer_in > 0:
                data.append({"Category": "Cash In (Drawer)", "Amount": drawer_in, "Type": "Inflow"})
            if drawer_out > 0:
                data.append({"Category": "Cash Out (Drawer)", "Amount": drawer_out, "Type": "Outflow"})
            data.append({"Category": "Net Cash", "Amount": net_cash, "Type": "Net"})

            # Other tenders
            kind_labels = {
                PaymentMethodKind.CARD: "Card",
                PaymentMethodKind.CREDIT: "Store Credit",
                PaymentMethodKind.QR: "QR / Digital",
                PaymentMethodKind.CHEQUE: "Cheque",
                PaymentMethodKind.TRANSFER: "Bank Transfer",
                PaymentMethodKind.OTHER: "Other",
            }

            total_other_net = Decimal("0.00")
            for kind, label in kind_labels.items():
                k_in = inflows.get(kind, Decimal("0.00"))
                k_ref = refunds.get(kind, Decimal("0.00"))
                if k_in > 0 or k_ref > 0:
                    k_net = k_in - k_ref
                    total_other_net += k_net
                    data.append({"Category": f"{label} Sales", "Amount": k_in, "Type": "Inflow"})
                    if k_ref > 0:
                        data.append({"Category": f"{label} Refunds", "Amount": k_ref, "Type": "Outflow"})
                    data.append({"Category": f"Net {label}", "Amount": k_net, "Type": "Net"})

            # Overall Net Cash Flow
            total_net_flow = net_cash + total_other_net
            data.append({"Category": "Net Cash Flow", "Amount": total_net_flow, "Type": "Net"})

            return pd.DataFrame(data)
