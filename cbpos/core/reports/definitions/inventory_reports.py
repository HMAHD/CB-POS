from typing import Any

import pandas as pd

from cbpos.core.database import get_db_session
from cbpos.core.models import Category, Product
from cbpos.core.reports.base_report import CATEGORY_INVENTORY, MONEY, QTY, TEXT, BaseReport, report_columns
from cbpos.i18n import _t


class InventoryValuationReport(BaseReport):
    """Current stock quantity and cost/retail value per active product."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "inventory_valuation"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.inventory_valuation")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_INVENTORY

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """Optional category filter, populated from active categories in the DB."""
        with get_db_session() as session:
            categories = session.query(Category).all()
            cat_options = [{"id": c.id, "label": c.name} for c in categories]

        return [
            {
                "name": "category_id",
                "label": "Category",
                "type": "combo",
                "options": [{"id": None, "label": "All Categories"}, *cat_options],
            }
        ]

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so quantities and money right-align with separators."""
        return {
            "columns": report_columns(
                {
                    "Barcode": TEXT,
                    "Name": TEXT,
                    "Category": TEXT,
                    "Qty": QTY,
                    "Cost": MONEY,
                    "Retail Price": MONEY,
                    "Total Cost Value": MONEY,
                    "Total Retail Value": MONEY,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """List active products with on-hand qty, cost, retail price, and their totals.

        Total Cost Value / Total Retail Value are ``stock_qty * cost`` and
        ``stock_qty * price`` respectively. Filter by ``category_id`` to scope
        to one category.
        """
        with get_db_session() as session:
            query = session.query(Product).filter(Product.is_active)

            category_id = filters.get("category_id")
            if category_id:
                query = query.filter(Product.category_id == category_id)

            products = query.all()

            data = []
            for p in products:
                total_cost = (p.stock_qty or 0) * (p.cost or 0)
                total_retail = (p.stock_qty or 0) * (p.price or 0)

                data.append(
                    {
                        "Barcode": p.barcode,
                        "Name": p.name_en,
                        "Category": p.category.name if p.category else "Uncategorized",
                        "Qty": float(p.stock_qty or 0),
                        "Cost": float(p.cost or 0),
                        "Retail Price": float(p.price or 0),
                        "Total Cost Value": float(total_cost),
                        "Total Retail Value": float(total_retail),
                    }
                )

            return pd.DataFrame(data)


class LowStockReport(BaseReport):
    """Active products at or below their reorder point, for restocking."""

    @property
    def id(self) -> str:
        """Report identifier."""
        return "low_stock"

    @property
    def name(self) -> str:
        """Display name."""
        return _t("reports.low_stock")

    @property
    def category(self) -> str:
        """Report category."""
        return CATEGORY_INVENTORY

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        """No filters; always shows all products at or below their reorder point."""
        return []

    def get_render_hints(self) -> dict[str, Any]:
        """Declare column types so quantities right-align with separators."""
        return {
            "columns": report_columns(
                {
                    "Name": TEXT,
                    "Supplier": TEXT,
                    "Current Stock": QTY,
                    "Reorder Point": QTY,
                    "Preferred Qty": QTY,
                }
            )
        }

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
        """List products where stock <= reorder point, with their default supplier."""
        with get_db_session() as session:
            # Filter products where stock <= reorder_point
            products = (
                session.query(Product)
                .filter(Product.is_active)
                .filter(Product.stock_qty <= Product.reorder_point)
                .all()
            )

            data = []
            for p in products:
                supplier_name = p.default_supplier.company_name if p.default_supplier else "Unknown"

                data.append(
                    {
                        "Name": p.name_en,
                        "Supplier": supplier_name,
                        "Current Stock": float(p.stock_qty or 0),
                        "Reorder Point": float(p.reorder_point or 0),
                        "Preferred Qty": float(p.preferred_qty or 0),
                    }
                )

            return pd.DataFrame(data)
