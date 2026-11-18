"""Warranty reports for Phase 9 (#830).

Implements:
1. ActiveWarrantiesReport (warranty_active)
2. ExpiringWarrantiesReport (warranty_expiring)
3. ClaimsRegisterReport (warranty_claims_register)
4. ClaimsByProductSupplierReport (warranty_claims_by_product_supplier)
5. ClaimCostReport (warranty_claim_cost)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import desc, func, select
from sqlalchemy.orm import joinedload

from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import (
    Category,
    Product,
    Sale,
    SaleItem,
    Supplier,
    Warranty,
    WarrantyClaim,
)
from cbpos.core.reports.base_report import (
    CATEGORY_WARRANTY,
    DATE,
    INT,
    MONEY,
    PERCENT,
    QTY,
    TEXT,
    BaseReport,
    report_columns,
)
from cbpos.core.reports.sale_filters import completed_sales, date_bounds, refund_documents
from cbpos.core.services.config_service import ConfigService
from cbpos.i18n import _t
from cbpos.ui.resources.icons import Icons


def _get_active_categories() -> list[dict[str, Any]]:
    """Fetch active product categories for filter dropdowns."""
    try:
        with Database().get_session() as session:
            cats = session.query(Category).order_by(Category.name.asc()).all()
            return [{"id": c.id, "label": c.name} for c in cats]
    except Exception:
        return []


def _get_active_suppliers() -> list[dict[str, Any]]:
    """Fetch active suppliers for filter dropdowns."""
    try:
        with Database().get_session() as session:
            suppliers = session.query(Supplier).order_by(Supplier.company_name.asc()).all()
            return [{"id": s.id, "label": s.company_name} for s in suppliers]
    except Exception:
        return []


class ActiveWarrantiesReport(BaseReport):
    """List of all registered warranties with derived status and extended plan revenue (#830)."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "warranty_active"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.warranty_active")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_WARRANTY

    @property
    def required_permissions(self) -> tuple[str, ...]:
        """Dual permissions required to view or run report."""
        return (Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW)

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Filter definitions for active warranties."""
        cat_options = _get_active_categories()
        return [
            {
                "name": "date_range",
                "label": _t("reports.filter_sold_date"),
                "type": "date_range",
            },
            {
                "name": "category_id",
                "label": _t("reports.filter_category"),
                "type": "combo",
                "options": [{"id": None, "label": _t("common.all")}, *cat_options],
            },
            {
                "name": "warranty_type",
                "label": _t("reports.filter_warranty_type"),
                "type": "combo",
                "options": [
                    {"id": None, "label": _t("common.all")},
                    {"id": "SHOP", "label": _t("warranty_policy.type_shop")},
                    {"id": "MANUFACTURER", "label": _t("warranty_policy.type_manufacturer")},
                    {"id": "EXTENDED", "label": _t("warranty_policy.type_extended")},
                ],
            },
            {
                "name": "status",
                "label": _t("reports.filter_status"),
                "type": "combo",
                "options": [
                    {"id": "ALL", "label": _t("common.all")},
                    {"id": "ACTIVE", "label": _t("warranty.status_active")},
                    {"id": "EXPIRING", "label": _t("warranty.status_expiring")},
                    {"id": "EXPIRED", "label": _t("warranty.status_expired")},
                ],
            },
        ]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types."""
        return {
            "columns": report_columns(
                {
                    "Warranty Code": TEXT,
                    "Product": TEXT,
                    "Serial Number": TEXT,
                    "Customer": TEXT,
                    "Phone": TEXT,
                    "Sold Date": DATE,
                    "Valid Until": DATE,
                    "Type": TEXT,
                    "Plan Revenue": MONEY,
                    "Status": TEXT,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """Query warranties and derive status and plan revenue."""
        today = date.today()
        date_range = filters.get("date_range", {})
        start_dt, end_dt = date_bounds(date_range)
        category_id = filters.get("category_id")
        warranty_type = filters.get("warranty_type")
        status_filter = filters.get("status", "ACTIVE")

        with Database().get_session() as session:
            stmt = (
                select(Warranty)
                .options(
                    joinedload(Warranty.product),
                    joinedload(Warranty.customer),
                    joinedload(Warranty.policy),
                    joinedload(Warranty.sale_item).joinedload(SaleItem.sale),
                    joinedload(Warranty.plan_sale_item),
                )
                .order_by(desc(Warranty.id))
            )

            if category_id:
                stmt = stmt.join(Product, Warranty.product_id == Product.id).where(Product.category_id == category_id)

            warranties = session.scalars(stmt).unique().all()

            rows = []
            for w in warranties:
                # Derived status
                if w.status in ("VOID", "CANCELLED", "REPLACED"):
                    derived_status = w.status
                elif w.end_date < today:
                    derived_status = "EXPIRED"
                elif w.end_date <= today + timedelta(days=30):
                    derived_status = "EXPIRING"
                else:
                    derived_status = "ACTIVE"

                # Status filter check
                if status_filter and status_filter != "ALL":
                    if status_filter == "ACTIVE":
                        if derived_status not in ("ACTIVE", "EXPIRING"):
                            continue
                    elif derived_status != status_filter:
                        continue

                # Warranty type filter
                w_type = w.policy.warranty_type if w.policy else "SHOP"
                if warranty_type and w_type != warranty_type:
                    continue

                # Sold date resolution
                sold_date = None
                if w.sale_item and w.sale_item.sale and w.sale_item.sale.date:
                    sold_date = w.sale_item.sale.date
                elif w.start_date:
                    sold_date = datetime.combine(w.start_date, datetime.min.time())

                # Date range filter on sold date
                if start_dt and sold_date and sold_date < start_dt:
                    continue
                if end_dt and sold_date and sold_date >= end_dt:
                    continue

                # Plan revenue
                plan_rev = Decimal("0.00")
                if w.plan_sale_item:
                    plan_rev = (
                        w.plan_sale_item.subtotal
                        if w.plan_sale_item.subtotal is not None
                        else (w.plan_sale_item.unit_price or Decimal("0.00"))
                    )

                prod_name = w.product.name_en if w.product else ""
                cust_name = w.customer.name if w.customer else ""
                cust_phone = w.customer.phone if w.customer else ""

                rows.append(
                    {
                        "Warranty Code": w.code,
                        "Product": prod_name,
                        "Serial Number": w.serial_number or "",
                        "Customer": cust_name,
                        "Phone": cust_phone,
                        "Sold Date": sold_date.strftime("%Y-%m-%d") if sold_date else "",
                        "Valid Until": w.end_date.strftime("%Y-%m-%d") if w.end_date else "",
                        "Type": w_type,
                        "Plan Revenue": plan_rev,
                        "Status": derived_status,
                    }
                )

            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame(
                    columns=[
                        "Warranty Code",
                        "Product",
                        "Serial Number",
                        "Customer",
                        "Phone",
                        "Sold Date",
                        "Valid Until",
                        "Type",
                        "Plan Revenue",
                        "Status",
                    ]
                )
            return df

    def get_summary(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """KPI summary cards."""
        currency = ConfigService.get("currency_symbol") or "Rs."
        if df is None or df.empty:
            return [
                {
                    "key": "total_warranties",
                    "title": _t("reports.summary_total_warranties"),
                    "value": "0",
                    "icon": Icons.WARRANTY,
                    "color": "#00BCEB",
                },
                {
                    "key": "active_warranties",
                    "title": _t("reports.summary_active_warranties"),
                    "value": "0",
                    "icon": Icons.CHECK,
                    "color": "#10B981",
                },
                {
                    "key": "plan_revenue",
                    "title": _t("reports.summary_plan_revenue"),
                    "value": f"{currency} 0.00",
                    "icon": Icons.MONEY,
                    "color": "#F59E0B",
                },
            ]

        total_count = len(df)
        active_count = len(df[df["Status"].isin(["ACTIVE", "EXPIRING"])])
        total_rev = df["Plan Revenue"].sum() if "Plan Revenue" in df.columns else Decimal("0.00")

        return [
            {
                "key": "total_warranties",
                "title": _t("reports.summary_total_warranties"),
                "value": str(total_count),
                "icon": Icons.WARRANTY,
                "color": "#00BCEB",
            },
            {
                "key": "active_warranties",
                "title": _t("reports.summary_active_warranties"),
                "value": str(active_count),
                "icon": Icons.CHECK,
                "color": "#10B981",
            },
            {
                "key": "plan_revenue",
                "title": _t("reports.summary_plan_revenue"),
                "value": f"{currency} {total_rev:,.2f}",
                "icon": Icons.MONEY,
                "color": "#F59E0B",
            },
        ]


class ExpiringWarrantiesReport(BaseReport):
    """Reminder list of warranties expiring within N days with customer phone (#830)."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "warranty_expiring"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.warranty_expiring")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_WARRANTY

    @property
    def required_permissions(self) -> tuple[str, ...]:
        """Dual permissions required to view or run report."""
        return (Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW)

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Filter definitions for expiring warranties."""
        cat_options = _get_active_categories()
        return [
            {
                "name": "days_ahead",
                "label": _t("reports.filter_expiring_within"),
                "type": "combo",
                "options": [
                    {"id": 7, "label": "7 Days"},
                    {"id": 14, "label": "14 Days"},
                    {"id": 30, "label": "30 Days"},
                    {"id": 60, "label": "60 Days"},
                    {"id": 90, "label": "90 Days"},
                ],
                "default": 30,
            },
            {
                "name": "category_id",
                "label": _t("reports.filter_category"),
                "type": "combo",
                "options": [{"id": None, "label": _t("common.all")}, *cat_options],
            },
            {
                "name": "warranty_type",
                "label": _t("reports.filter_warranty_type"),
                "type": "combo",
                "options": [
                    {"id": None, "label": _t("common.all")},
                    {"id": "SHOP", "label": _t("warranty_policy.type_shop")},
                    {"id": "MANUFACTURER", "label": _t("warranty_policy.type_manufacturer")},
                    {"id": "EXTENDED", "label": _t("warranty_policy.type_extended")},
                ],
            },
        ]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types."""
        return {
            "columns": report_columns(
                {
                    "Warranty Code": TEXT,
                    "Customer": TEXT,
                    "Phone": TEXT,
                    "Product": TEXT,
                    "Serial Number": TEXT,
                    "Valid Until": DATE,
                    "Days Remaining": INT,
                    "Type": TEXT,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """Query warranties expiring in the configured window."""
        today = date.today()
        days_ahead_raw = filters.get("days_ahead", 30)
        try:
            days_ahead = int(days_ahead_raw) if days_ahead_raw is not None else 30
        except (ValueError, TypeError):
            days_ahead = 30
        max_date = today + timedelta(days=days_ahead)

        category_id = filters.get("category_id")
        warranty_type = filters.get("warranty_type")

        with Database().get_session() as session:
            stmt = (
                select(Warranty)
                .options(
                    joinedload(Warranty.product),
                    joinedload(Warranty.customer),
                    joinedload(Warranty.policy),
                )
                .where(
                    Warranty.status == "ACTIVE",
                    Warranty.end_date >= today,
                    Warranty.end_date <= max_date,
                )
                .order_by(Warranty.end_date.asc())
            )

            if category_id:
                stmt = stmt.join(Product, Warranty.product_id == Product.id).where(Product.category_id == category_id)

            warranties = session.scalars(stmt).unique().all()

            rows = []
            for w in warranties:
                w_type = w.policy.warranty_type if w.policy else "SHOP"
                if warranty_type and w_type != warranty_type:
                    continue

                days_rem = (w.end_date - today).days

                rows.append(
                    {
                        "Warranty Code": w.code,
                        "Customer": w.customer.name if w.customer else "",
                        "Phone": w.customer.phone if w.customer else "",
                        "Product": w.product.name_en if w.product else "",
                        "Serial Number": w.serial_number or "",
                        "Valid Until": w.end_date.strftime("%Y-%m-%d"),
                        "Days Remaining": days_rem,
                        "Type": w_type,
                    }
                )

            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame(
                    columns=[
                        "Warranty Code",
                        "Customer",
                        "Phone",
                        "Product",
                        "Serial Number",
                        "Valid Until",
                        "Days Remaining",
                        "Type",
                    ]
                )
            return df

    def get_summary(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """KPI summary cards."""
        if df is None or df.empty:
            return [
                {
                    "key": "total_expiring",
                    "title": _t("reports.summary_total_expiring"),
                    "value": "0",
                    "icon": Icons.WARNING,
                    "color": "#F59E0B",
                },
                {
                    "key": "urgent_7_days",
                    "title": _t("reports.summary_urgent_7_days"),
                    "value": "0",
                    "icon": Icons.ALERT,
                    "color": "#EF4444",
                },
            ]

        total_exp = len(df)
        urgent_count = len(df[df["Days Remaining"] <= 7])

        return [
            {
                "key": "total_expiring",
                "title": _t("reports.summary_total_expiring"),
                "value": str(total_exp),
                "icon": Icons.WARNING,
                "color": "#F59E0B",
            },
            {
                "key": "urgent_7_days",
                "title": _t("reports.summary_urgent_7_days"),
                "value": str(urgent_count),
                "icon": Icons.ALERT,
                "color": "#EF4444",
            },
        ]


class ClaimsRegisterReport(BaseReport):
    """Chronological register of all warranty claims (#830)."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "warranty_claims_register"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.warranty_claims_register")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_WARRANTY

    @property
    def required_permissions(self) -> tuple[str, ...]:
        """Dual permissions required to view or run report."""
        return (Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW)

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Filter definitions for claims register."""
        supp_options = _get_active_suppliers()
        return [
            {
                "name": "date_range",
                "label": _t("reports.filter_intake_date"),
                "type": "date_range",
            },
            {
                "name": "claim_status",
                "label": _t("reports.filter_status"),
                "type": "combo",
                "options": [
                    {"id": "ALL", "label": _t("common.all")},
                    {"id": "INTAKE", "label": _t("warranty_claim.status_intake")},
                    {"id": "IN_INSPECTION", "label": _t("warranty_claim.status_in_inspection")},
                    {"id": "SUPPLIER_DISPATCHED", "label": _t("warranty_claim.status_supplier_dispatched")},
                    {"id": "SUPPLIER_RETURNED", "label": _t("warranty_claim.status_supplier_returned")},
                    {"id": "RESOLVED", "label": _t("warranty_claim.status_resolved")},
                    {"id": "COLLECTED", "label": _t("warranty_claim.status_collected")},
                    {"id": "REJECTED", "label": _t("warranty_claim.status_rejected")},
                    {"id": "VOID", "label": _t("warranty_claim.status_void")},
                ],
            },
            {
                "name": "resolution",
                "label": _t("reports.filter_resolution"),
                "type": "combo",
                "options": [
                    {"id": "ALL", "label": _t("common.all")},
                    {"id": "REPAIRED", "label": _t("warranty_claim.resolution_repaired")},
                    {"id": "REPLACED_SAME", "label": _t("warranty_claim.resolution_replaced_same")},
                    {"id": "REPLACED_DIFFERENT", "label": _t("warranty_claim.resolution_replaced_different")},
                    {"id": "REFUNDED", "label": _t("warranty_claim.resolution_refunded")},
                    {"id": "REJECTED_UNCOVERED", "label": _t("warranty_claim.resolution_rejected_uncovered")},
                ],
            },
            {
                "name": "supplier_id",
                "label": _t("reports.filter_supplier"),
                "type": "combo",
                "options": [{"id": None, "label": _t("common.all")}, *supp_options],
            },
        ]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types."""
        return {
            "columns": report_columns(
                {
                    "Claim Number": TEXT,
                    "Intake Date": DATE,
                    "Expected Ready": DATE,
                    "Customer": TEXT,
                    "Phone": TEXT,
                    "Product": TEXT,
                    "Serial Number": TEXT,
                    "Coverage": TEXT,
                    "Status": TEXT,
                    "Resolution": TEXT,
                    "Days Open": INT,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """Query claims register matching filters."""
        today = date.today()
        date_range = filters.get("date_range", {})
        start_dt, end_dt = date_bounds(date_range)
        status_filter = filters.get("claim_status")
        resolution_filter = filters.get("resolution")
        supplier_id = filters.get("supplier_id")

        with Database().get_session() as session:
            stmt = (
                select(WarrantyClaim)
                .options(
                    joinedload(WarrantyClaim.product),
                    joinedload(WarrantyClaim.customer),
                    joinedload(WarrantyClaim.supplier),
                    joinedload(WarrantyClaim.warranty).joinedload(Warranty.policy),
                )
                .order_by(desc(WarrantyClaim.intake_date))
            )

            if start_dt:
                stmt = stmt.where(WarrantyClaim.intake_date >= start_dt)
            if end_dt:
                stmt = stmt.where(WarrantyClaim.intake_date < end_dt)

            if status_filter and status_filter != "ALL":
                stmt = stmt.where(WarrantyClaim.claim_status == status_filter)

            if resolution_filter and resolution_filter != "ALL":
                stmt = stmt.where(WarrantyClaim.resolution == resolution_filter)

            if supplier_id:
                stmt = stmt.where(WarrantyClaim.supplier_id == supplier_id)

            claims = session.scalars(stmt).unique().all()

            rows = []
            for c in claims:
                # Coverage type
                cov = "SHOP"
                if c.warranty and c.warranty.policy:
                    cov = c.warranty.policy.warranty_type

                # Days open
                intake_d = c.intake_date.date()
                if c.claim_status in ("RESOLVED", "COLLECTED", "REJECTED", "VOID"):
                    close_dt = c.resolved_at or c.closed_at
                    days_open = (close_dt.date() - intake_d).days if close_dt else (today - intake_d).days
                else:
                    days_open = (today - intake_d).days
                days_open = max(0, days_open)

                cust_name = c.customer_name_snapshot or (c.customer.name if c.customer else "")
                cust_phone = c.customer_phone_snapshot or (c.customer.phone if c.customer else "")
                prod_name = c.product.name_en if c.product else ""

                rows.append(
                    {
                        "Claim Number": c.document_number,
                        "Intake Date": c.intake_date.strftime("%Y-%m-%d"),
                        "Expected Ready": c.expected_ready_date.strftime("%Y-%m-%d") if c.expected_ready_date else "",
                        "Customer": cust_name,
                        "Phone": cust_phone,
                        "Product": prod_name,
                        "Serial Number": c.item_serial or "",
                        "Coverage": cov,
                        "Status": c.claim_status,
                        "Resolution": c.resolution or "",
                        "Days Open": days_open,
                    }
                )

            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame(
                    columns=[
                        "Claim Number",
                        "Intake Date",
                        "Expected Ready",
                        "Customer",
                        "Phone",
                        "Product",
                        "Serial Number",
                        "Coverage",
                        "Status",
                        "Resolution",
                        "Days Open",
                    ]
                )
            return df

    def get_summary(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """KPI summary cards."""
        if df is None or df.empty:
            return [
                {
                    "key": "total_claims",
                    "title": _t("reports.summary_total_claims"),
                    "value": "0",
                    "icon": Icons.WARRANTY,
                    "color": "#00BCEB",
                },
                {
                    "key": "open_claims",
                    "title": _t("reports.summary_open_claims"),
                    "value": "0",
                    "icon": Icons.INFO,
                    "color": "#F59E0B",
                },
                {
                    "key": "resolved_claims",
                    "title": _t("reports.summary_resolved_claims"),
                    "value": "0",
                    "icon": Icons.CHECK,
                    "color": "#10B981",
                },
            ]

        total_claims = len(df)
        open_count = len(df[df["Status"].isin(["INTAKE", "IN_INSPECTION", "SUPPLIER_DISPATCHED", "SUPPLIER_RETURNED"])])
        resolved_count = len(df[df["Status"].isin(["RESOLVED", "COLLECTED"])])

        return [
            {
                "key": "total_claims",
                "title": _t("reports.summary_total_claims"),
                "value": str(total_claims),
                "icon": Icons.WARRANTY,
                "color": "#00BCEB",
            },
            {
                "key": "open_claims",
                "title": _t("reports.summary_open_claims"),
                "value": str(open_count),
                "icon": Icons.INFO,
                "color": "#F59E0B",
            },
            {
                "key": "resolved_claims",
                "title": _t("reports.summary_resolved_claims"),
                "value": str(resolved_count),
                "icon": Icons.CHECK,
                "color": "#10B981",
            },
        ]


class ClaimsByProductSupplierReport(BaseReport):
    """Defect rate, turnaround, and claim distribution grouped by product or supplier (#830)."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "warranty_claims_by_product_supplier"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.warranty_claims_by_product_supplier")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_WARRANTY

    @property
    def required_permissions(self) -> tuple[str, ...]:
        """Dual permissions required to view or run report."""
        return (Permissions.REPORTS_VIEW_SALES, Permissions.WARRANTY_VIEW)

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Filter definitions."""
        return [
            {
                "name": "date_range",
                "label": _t("reports.filter_date_range"),
                "type": "date_range",
            },
            {
                "name": "group_by",
                "label": _t("reports.filter_group_by"),
                "type": "combo",
                "options": [
                    {"id": "product", "label": _t("reports.group_by_product")},
                    {"id": "supplier", "label": _t("reports.group_by_supplier")},
                ],
                "default": "product",
            },
        ]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types."""
        return {
            "columns": report_columns(
                {
                    "Name": TEXT,
                    "Net Units Sold": QTY,
                    "Total Claims": INT,
                    "Replacements": INT,
                    "Rejections": INT,
                    "Claim Rate": PERCENT,
                    "Avg Turnaround Days": INT,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """Compute net sales, claims, claim rate %, and turnaround days."""
        date_range = filters.get("date_range", {})
        start_dt, end_dt = date_bounds(date_range)
        group_by = filters.get("group_by", "product")

        with Database().get_session() as session:
            # 1. Net units sold per product
            sales_stmt = (
                select(
                    SaleItem.product_id,
                    func.sum(SaleItem.qty).label("sold_qty"),
                )
                .join(Sale, SaleItem.sale_id == Sale.id)
                .where(completed_sales())
            )
            if start_dt:
                sales_stmt = sales_stmt.where(Sale.date >= start_dt)
            if end_dt:
                sales_stmt = sales_stmt.where(Sale.date < end_dt)
            sales_stmt = sales_stmt.group_by(SaleItem.product_id)
            sales_res = session.execute(sales_stmt).all()
            sold_map: dict[int, Decimal] = {r.product_id: Decimal(str(r.sold_qty or 0)) for r in sales_res}

            # Refunds per product
            refunds_stmt = (
                select(
                    SaleItem.product_id,
                    func.sum(SaleItem.qty).label("ref_qty"),
                )
                .join(Sale, SaleItem.sale_id == Sale.id)
                .where(refund_documents())
            )
            if start_dt:
                refunds_stmt = refunds_stmt.where(Sale.date >= start_dt)
            if end_dt:
                refunds_stmt = refunds_stmt.where(Sale.date < end_dt)
            refunds_stmt = refunds_stmt.group_by(SaleItem.product_id)
            refunds_res = session.execute(refunds_stmt).all()
            refund_map: dict[int, Decimal] = {r.product_id: Decimal(str(r.ref_qty or 0)) for r in refunds_res}

            # 2. Claims per product
            claims_stmt = (
                select(WarrantyClaim)
                .options(
                    joinedload(WarrantyClaim.product),
                    joinedload(WarrantyClaim.supplier),
                )
                .where(WarrantyClaim.claim_status != "VOID")
            )
            if start_dt:
                claims_stmt = claims_stmt.where(WarrantyClaim.intake_date >= start_dt)
            if end_dt:
                claims_stmt = claims_stmt.where(WarrantyClaim.intake_date < end_dt)
            claims = session.scalars(claims_stmt).unique().all()

            if group_by == "supplier":
                # Group by Supplier
                suppliers = session.scalars(select(Supplier).order_by(Supplier.company_name.asc())).all()
                prod_to_supp: dict[int, int | None] = {
                    p.id: p.default_supplier_id for p in session.scalars(select(Product)).all()
                }

                supp_data: dict[int, dict[str, Any]] = {}
                for s in suppliers:
                    supp_data[s.id] = {
                        "name": s.company_name,
                        "net_units": Decimal("0.000"),
                        "claims_count": 0,
                        "replacements": 0,
                        "rejections": 0,
                        "turnaround_days": [],
                    }

                # Aggregate net units sold by product supplier
                for pid, s_qty in sold_map.items():
                    sid = prod_to_supp.get(pid)
                    if sid and sid in supp_data:
                        r_qty = refund_map.get(pid, Decimal("0.000"))
                        supp_data[sid]["net_units"] += max(Decimal("0.000"), s_qty - r_qty)

                # Aggregate claims by claim.supplier_id or product.supplier_id
                for c in claims:
                    sid = c.supplier_id or (prod_to_supp.get(c.product_id) if c.product_id else None)
                    if not sid or sid not in supp_data:
                        continue
                    entry = supp_data[sid]
                    entry["claims_count"] += 1
                    if c.resolution in ("REPLACED_SAME", "REPLACED_DIFFERENT"):
                        entry["replacements"] += 1
                    if c.claim_status == "REJECTED" or c.resolution == "REJECTED_UNCOVERED":
                        entry["rejections"] += 1
                    if c.resolved_at:
                        entry["turnaround_days"].append((c.resolved_at.date() - c.intake_date.date()).days)

                rows = []
                for entry in supp_data.values():
                    net_units = entry["net_units"]
                    total_c = entry["claims_count"]
                    if net_units == 0 and total_c == 0:
                        continue
                    if net_units > 0:
                        claim_rate = (Decimal(total_c) / net_units) * Decimal(100)
                        rate_str = f"{claim_rate:.2f}%"
                    else:
                        rate_str = "0.00%"

                    tdays = entry["turnaround_days"]
                    avg_t = round(sum(tdays) / len(tdays)) if tdays else 0

                    rows.append(
                        {
                            "Name": entry["name"],
                            "Net Units Sold": net_units,
                            "Total Claims": total_c,
                            "Replacements": entry["replacements"],
                            "Rejections": entry["rejections"],
                            "Claim Rate": rate_str,
                            "Avg Turnaround Days": avg_t,
                        }
                    )
            else:
                # Group by Product
                products = session.scalars(select(Product).order_by(Product.name_en.asc())).all()
                prod_data: dict[int, dict[str, Any]] = {}
                for p in products:
                    prod_data[p.id] = {
                        "name": p.name_en,
                        "net_units": max(
                            Decimal("0.000"),
                            sold_map.get(p.id, Decimal("0.000")) - refund_map.get(p.id, Decimal("0.000")),
                        ),
                        "claims_count": 0,
                        "replacements": 0,
                        "rejections": 0,
                        "turnaround_days": [],
                    }

                for c in claims:
                    if not c.product_id or c.product_id not in prod_data:
                        continue
                    entry = prod_data[c.product_id]
                    entry["claims_count"] += 1
                    if c.resolution in ("REPLACED_SAME", "REPLACED_DIFFERENT"):
                        entry["replacements"] += 1
                    if c.claim_status == "REJECTED" or c.resolution == "REJECTED_UNCOVERED":
                        entry["rejections"] += 1
                    if c.resolved_at:
                        entry["turnaround_days"].append((c.resolved_at.date() - c.intake_date.date()).days)

                rows = []
                for entry in prod_data.values():
                    net_units = entry["net_units"]
                    total_c = entry["claims_count"]
                    if net_units == 0 and total_c == 0:
                        continue
                    if net_units > 0:
                        claim_rate = (Decimal(total_c) / net_units) * Decimal(100)
                        rate_str = f"{claim_rate:.2f}%"
                    else:
                        rate_str = "0.00%"

                    tdays = entry["turnaround_days"]
                    avg_t = round(sum(tdays) / len(tdays)) if tdays else 0

                    rows.append(
                        {
                            "Name": entry["name"],
                            "Net Units Sold": net_units,
                            "Total Claims": total_c,
                            "Replacements": entry["replacements"],
                            "Rejections": entry["rejections"],
                            "Claim Rate": rate_str,
                            "Avg Turnaround Days": avg_t,
                        }
                    )

            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame(
                    columns=[
                        "Name",
                        "Net Units Sold",
                        "Total Claims",
                        "Replacements",
                        "Rejections",
                        "Claim Rate",
                        "Avg Turnaround Days",
                    ]
                )
            return df

    def get_summary(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """KPI summary cards."""
        if df is None or df.empty:
            return [
                {
                    "key": "total_claims",
                    "title": _t("reports.summary_total_claims"),
                    "value": "0",
                    "icon": Icons.WARRANTY,
                    "color": "#00BCEB",
                },
                {
                    "key": "overall_claim_rate",
                    "title": _t("reports.summary_claim_rate"),
                    "value": "0.00%",
                    "icon": Icons.ALERT,
                    "color": "#F59E0B",
                },
            ]

        total_claims = int(df["Total Claims"].sum()) if "Total Claims" in df.columns else 0
        total_units = Decimal(str(df["Net Units Sold"].sum())) if "Net Units Sold" in df.columns else Decimal(0)

        overall_rate = "0.00%"
        if total_units > 0:
            rate_val = (Decimal(total_claims) / total_units) * Decimal(100)
            overall_rate = f"{rate_val:.2f}%"

        return [
            {
                "key": "total_claims",
                "title": _t("reports.summary_total_claims"),
                "value": str(total_claims),
                "icon": Icons.WARRANTY,
                "color": "#00BCEB",
            },
            {
                "key": "overall_claim_rate",
                "title": _t("reports.summary_claim_rate"),
                "value": overall_rate,
                "icon": Icons.ALERT,
                "color": "#F59E0B",
            },
        ]


class ClaimCostReport(BaseReport):
    """Replacement cost, repair cost, recovery, and net claim cost (#830)."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "warranty_claim_cost"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.warranty_claim_cost")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_WARRANTY

    @property
    def required_permissions(self) -> tuple[str, ...]:
        """Dual permissions required to view or run report (requires profit permission)."""
        return (Permissions.REPORTS_VIEW_PROFIT, Permissions.WARRANTY_VIEW)

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Filter definitions for claim cost report."""
        return [
            {
                "name": "date_range",
                "label": _t("reports.filter_resolution_date"),
                "type": "date_range",
            },
            {
                "name": "resolution",
                "label": _t("reports.filter_resolution"),
                "type": "combo",
                "options": [
                    {"id": "ALL", "label": _t("common.all")},
                    {"id": "REPAIRED", "label": _t("warranty_claim.resolution_repaired")},
                    {"id": "REPLACED_SAME", "label": _t("warranty_claim.resolution_replaced_same")},
                    {"id": "REPLACED_DIFFERENT", "label": _t("warranty_claim.resolution_replaced_different")},
                    {"id": "REFUNDED", "label": _t("warranty_claim.resolution_refunded")},
                ],
            },
        ]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types."""
        return {
            "columns": report_columns(
                {
                    "Claim Number": TEXT,
                    "Product": TEXT,
                    "Replacement Cost": TEXT,
                    "Repair Cost": MONEY,
                    "Customer Charge": MONEY,
                    "Supplier Credit": MONEY,
                    "Net Cost": TEXT,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """Calculate exact net cost per resolved claim, handling unknown replacement cost snapshot."""
        date_range = filters.get("date_range", {})
        start_dt, end_dt = date_bounds(date_range)
        resolution_filter = filters.get("resolution")

        with Database().get_session() as session:
            stmt = (
                select(WarrantyClaim)
                .options(joinedload(WarrantyClaim.product))
                .where(
                    WarrantyClaim.claim_status.in_(["RESOLVED", "COLLECTED"]),
                    WarrantyClaim.resolution.isnot(None),
                )
                .order_by(desc(WarrantyClaim.resolved_at))
            )

            if start_dt:
                stmt = stmt.where(WarrantyClaim.resolved_at >= start_dt)
            if end_dt:
                stmt = stmt.where(WarrantyClaim.resolved_at < end_dt)

            if resolution_filter and resolution_filter != "ALL":
                stmt = stmt.where(WarrantyClaim.resolution == resolution_filter)

            claims = session.scalars(stmt).unique().all()

            rows = []
            for c in claims:
                is_replacement = c.resolution in ("REPLACED_SAME", "REPLACED_DIFFERENT")
                repair_cost = c.repair_cost or Decimal("0.00")
                charge_cust = c.charge_customer or Decimal("0.00")
                supp_credit = c.supplier_credit_amount or Decimal("0.00")

                if is_replacement:
                    if c.replacement_cost_snapshot is not None:
                        rep_cost_str = f"{c.replacement_cost_snapshot:,.2f}"
                        net_cost_val = c.replacement_cost_snapshot + repair_cost - charge_cust - supp_credit
                        net_cost_str = f"{net_cost_val:,.2f}"
                    else:
                        rep_cost_str = "-"
                        net_cost_str = "-"
                else:
                    rep_cost_str = "-"
                    net_cost_val = repair_cost - charge_cust - supp_credit
                    net_cost_str = f"{net_cost_val:,.2f}"

                prod_name = c.product.name_en if c.product else ""

                rows.append(
                    {
                        "Claim Number": c.document_number,
                        "Product": prod_name,
                        "Replacement Cost": rep_cost_str,
                        "Repair Cost": repair_cost,
                        "Customer Charge": charge_cust,
                        "Supplier Credit": supp_credit,
                        "Net Cost": net_cost_str,
                    }
                )

            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame(
                    columns=[
                        "Claim Number",
                        "Product",
                        "Replacement Cost",
                        "Repair Cost",
                        "Customer Charge",
                        "Supplier Credit",
                        "Net Cost",
                    ]
                )
            return df

    def get_summary(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        """KPI summary cards."""
        currency = ConfigService.get("currency_symbol") or "Rs."
        if df is None or df.empty:
            return [
                {
                    "key": "total_claims",
                    "title": _t("reports.summary_total_claims"),
                    "value": "0",
                    "icon": Icons.WARRANTY,
                    "color": "#00BCEB",
                },
                {
                    "key": "repair_costs",
                    "title": _t("reports.summary_repair_costs"),
                    "value": f"{currency} 0.00",
                    "icon": Icons.PRICE_LIST,
                    "color": "#F59E0B",
                },
                {
                    "key": "supplier_recovery",
                    "title": _t("reports.summary_supplier_recovery"),
                    "value": f"{currency} 0.00",
                    "icon": Icons.PURCHASE,
                    "color": "#10B981",
                },
            ]

        total_claims = len(df)
        total_rep = df["Repair Cost"].sum() if "Repair Cost" in df.columns else Decimal("0.00")
        total_supp = df["Supplier Credit"].sum() if "Supplier Credit" in df.columns else Decimal("0.00")

        return [
            {
                "key": "total_claims",
                "title": _t("reports.summary_total_claims"),
                "value": str(total_claims),
                "icon": Icons.WARRANTY,
                "color": "#00BCEB",
            },
            {
                "key": "repair_costs",
                "title": _t("reports.summary_repair_costs"),
                "value": f"{currency} {total_rep:,.2f}",
                "icon": Icons.PRICE_LIST,
                "color": "#F59E0B",
            },
            {
                "key": "supplier_recovery",
                "title": _t("reports.summary_supplier_recovery"),
                "value": f"{currency} {total_supp:,.2f}",
                "icon": Icons.PURCHASE,
                "color": "#10B981",
            },
        ]
