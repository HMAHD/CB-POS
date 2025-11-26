import csv
from decimal import Decimal, InvalidOperation
from typing import Dict
from cbpos.core.services.inventory_service import InventoryService


class ImportService:
    def __init__(self):
        self.inventory_service = InventoryService()

    def import_products_from_csv(self, file_path: str) -> Dict[str, int]:
        results = {"success": 0, "failed": 0, "skipped": 0}

        try:
            with open(file_path, mode="r", encoding="utf-8-sig", newline="") as csvfile:
                reader = csv.DictReader(csvfile)

                # Normalize headers if possible, but DictReader uses the first line.
                # We assume standard headers: barcode, name, price, cost, stock
                # We will try to match case-insensitively

                field_map = {}
                if reader.fieldnames:
                    for field in reader.fieldnames:
                        lower_field = field.strip().lower()
                        if "barcode" in lower_field:
                            field_map["barcode"] = field
                        elif "name" in lower_field:
                            field_map["name"] = field
                        elif "price" in lower_field:
                            field_map["price"] = field
                        elif "cost" in lower_field:
                            field_map["cost"] = field
                        elif "stock" in lower_field:
                            field_map["stock"] = field

                for row in reader:
                    try:
                        barcode = row.get(
                            field_map.get("barcode", "Barcode"), ""
                        ).strip()
                        name = row.get(field_map.get("name", "Name"), "").strip()
                        price_str = row.get(
                            field_map.get("price", "Price"), "0"
                        ).strip()
                        cost_str = row.get(field_map.get("cost", "Cost"), "0").strip()
                        stock_str = row.get(
                            field_map.get("stock", "Stock"), "0"
                        ).strip()

                        if not barcode:
                            # Try fallback keys if mapping failed or specific keys used
                            barcode = row.get("barcode", row.get("Barcode", "")).strip()
                        if not name:
                            name = row.get("name", row.get("Name", "")).strip()

                        if not barcode or not name:
                            results["failed"] += 1
                            continue

                        # Check duplicate
                        if self.inventory_service.get_product_by_barcode(barcode):
                            results["skipped"] += 1
                            continue

                        try:
                            price = Decimal(price_str) if price_str else Decimal(0)
                            cost = Decimal(cost_str) if cost_str else Decimal(0)
                            stock = Decimal(stock_str) if stock_str else Decimal(0)
                        except InvalidOperation:
                            results["failed"] += 1
                            continue

                        product_data = {
                            "barcode": barcode,
                            "name_en": name,
                            "price": price,
                            "cost": cost,
                            "stock_qty": stock,
                            "is_active": True,
                        }

                        self.inventory_service.create_product(product_data)
                        results["success"] += 1

                    except Exception as e:
                        print(f"Error importing row: {e}")
                        results["failed"] += 1
        except Exception as e:
            print(f"Error opening file: {e}")
            return results

        return results
