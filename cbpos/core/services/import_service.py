import csv
import logging
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.utils.terminal_guard import require_catalog_writable

logger = logging.getLogger(__name__)


class ImportService:
    """Bulk-imports products from CSV files into inventory."""

    def __init__(self):
        """Create an InventoryService instance used to create/lookup imported products."""
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

    def import_products_from_csv(self, file_path: str) -> dict[str, int]:
        """Import products from a CSV file without progress reporting.

        Returns:
            dict with "success", "failed", and "skipped" row counts. Rows missing a
            barcode/name, with an invalid price/cost/stock number, or whose barcode
            already exists are counted as failed/skipped rather than raising.
        """
        return self._import_csv(file_path, progress_callback=None)

    def import_products_from_csv_with_progress(
        self,
        file_path: str,
        progress_callback: Callable[[int], None] | None = None,
    ) -> dict[str, int]:
        """Import products with a progress callback called after each row.

        Args:
            file_path: Path to the CSV file.
            progress_callback: Called with the current row number (1-based).
        """
        return self._import_csv(file_path, progress_callback=progress_callback)

    def _import_csv(
        self,
        file_path: str,
        progress_callback: Callable[[int], None] | None = None,
    ) -> dict[str, int]:
        require_catalog_writable()
        results = {"success": 0, "failed": 0, "skipped": 0}

        try:
            validated_path = self._validate_file_path(file_path)
            with open(validated_path, encoding="utf-8-sig", newline="") as csvfile:
                reader = csv.DictReader(csvfile)

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

                for row_num, row in enumerate(reader, start=1):
                    if progress_callback:
                        progress_callback(row_num)

                    try:
                        barcode = row.get(field_map.get("barcode", "Barcode"), "").strip()
                        name = row.get(field_map.get("name", "Name"), "").strip()
                        price_str = row.get(field_map.get("price", "Price"), "0").strip()
                        cost_str = row.get(field_map.get("cost", "Cost"), "0").strip()
                        stock_str = row.get(field_map.get("stock", "Stock"), "0").strip()

                        if not barcode:
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
                            price = (
                                Decimal(str(price_str).strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                                if price_str
                                else Decimal("0.00")
                            )
                            cost = (
                                Decimal(str(cost_str).strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                                if cost_str
                                else Decimal("0.00")
                            )
                            stock = (
                                Decimal(str(stock_str).strip()).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                                if stock_str
                                else Decimal("0.000")
                            )
                        except (InvalidOperation, ValueError):
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

    @staticmethod
    def generate_template() -> str:
        """Return CSV template content with headers and example row."""
        return "Barcode,Name,Price,Cost,Stock\n8901234567890,Sample Product,150.00,100.00,50\n"
