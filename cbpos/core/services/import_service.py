import csv
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict
from cbpos.core.services.inventory_service import InventoryService

logger = logging.getLogger(__name__)


class ImportService:
    def __init__(self):
        self.inventory_service = InventoryService()

    @staticmethod
    def _validate_file_path(file_path: str, must_exist: bool = True) -> Path:
        """Validate file path to prevent path traversal attacks."""
        resolved = Path(file_path).resolve()
        # Block paths containing traversal patterns
        if ".." in Path(file_path).parts:
            raise ValueError(f"Path traversal detected: {file_path}")
        # Ensure the path is under the user's home directory or common data locations
        home = Path.home().resolve()
        if not str(resolved).startswith(str(home)) and not str(resolved).startswith("/tmp"):
            raise ValueError(f"Path outside allowed directories: {file_path}")
        if must_exist and not resolved.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        return resolved

    def import_products_from_csv(self, file_path: str) -> Dict[str, int]:
        results = {"success": 0, "failed": 0, "skipped": 0}

        try:
            validated_path = self._validate_file_path(file_path)
            with open(validated_path, mode="r", encoding="utf-8-sig", newline="") as csvfile:
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
                        barcode = row.get(field_map.get("barcode", "Barcode"), "").strip()
                        name = row.get(field_map.get("name", "Name"), "").strip()
                        price_str = row.get(field_map.get("price", "Price"), "0").strip()
                        cost_str = row.get(field_map.get("cost", "Cost"), "0").strip()
                        stock_str = row.get(field_map.get("stock", "Stock"), "0").strip()

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
                        logger.error("Error importing row: %s", e)
                        results["failed"] += 1
        except Exception as e:
            logger.error("Error opening file: %s", e)
            return results

        return results
