from typing import Any

import pandas as pd

from cbpos.core.database import get_db_session
from cbpos.core.models import Category, Product
from cbpos.core.reports.base_report import BaseReport


class InventoryValuationReport(BaseReport):
    @property
    def id(self) -> str:
        return "inventory_valuation"

    @property
    def name(self) -> str:
        return "Inventory Valuation"

    @property
    def category(self) -> str:
        return "Inventory"

    def get_filter_definitions(self) -> list[dict[str, Any]]:
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

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
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
    @property
    def id(self) -> str:
        return "low_stock"

    @property
    def name(self) -> str:
        return "Low Stock Alert"

    @property
    def category(self) -> str:
        return "Inventory"

    def get_filter_definitions(self) -> list[dict[str, Any]]:
        return []

    def generate(self, filters: dict[str, Any]) -> pd.DataFrame:
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
