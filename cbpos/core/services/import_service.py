"""Bulk-imports products from CSV files into inventory."""

import csv
import io
import logging
import re
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import Category, Product, Role, Unit, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.inventory_service import InventoryService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.utils.terminal_guard import require_catalog_writable
from cbpos.core.utils.validators import ProductValidator

logger = logging.getLogger(__name__)


class ImportError_(Exception):
    """Raised when file-level errors prevent CSV import."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(message or code)


class ImportMappingError(Exception):
    """Raised when CSV column headers cannot be mapped or contain duplicates."""

    def __init__(self, code: str, field: str = "", header: str = "", message: str = ""):
        self.code = code
        self.field = field
        self.header = header
        msg = message or f"Column mapping error ({code}): field='{field}', header='{header}'"
        super().__init__(msg)


CANONICAL_FIELDS: dict[str, set[str]] = {
    "barcode": {"barcode", "code", "sku", "itemcode"},
    "name_en": {"name", "nameen", "nameenglish", "productname", "itemname", "description"},
    "name_si": {"namesi", "namesinhala", "sinhalaname", "sinhala"},
    "name_ta": {"nameta", "nametamil", "tamilname", "tamil"},
    "price": {"price", "sellingprice", "sellprice", "retailprice", "mrp", "saleprice"},
    "cost": {"cost", "costprice", "buyingprice", "purchaseprice", "unitcost"},
    "stock_qty": {"stock", "qty", "quantity", "stockqty", "onhand"},
    "category": {"category", "categoryname"},
    "unit": {"unit", "unitname", "uom"},
    "reorder_point": {"reorderpoint", "reorderlevel", "reorder", "minstock"},
}


def normalize_header(header: str) -> str:
    """Normalize a header string: lowercase, strip, collapse spaces, remove _ - ( ) ."""
    return re.sub(r"[\s_\-().]+", "", header.strip().lower())


class ImportService:
    """Bulk-imports products from CSV files into inventory."""

    def __init__(self):
        """Create an InventoryService instance used to create/lookup imported products."""
        self.inventory_service = InventoryService()

    @staticmethod
    def _validate_file_path(file_path: str, must_exist: bool = True) -> Path:
        """Validate file path existence and .csv extension."""
        resolved = Path(file_path).resolve()
        if must_exist and not resolved.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        if resolved.suffix.lower() != ".csv":
            raise ValueError(f"Not a CSV file: {file_path}")
        return resolved

    @staticmethod
    def read_csv_text(file_path: str | Path) -> str:
        """Read CSV file content trying utf-8-sig first, falling back to cp1252."""
        path = Path(file_path)
        try:
            raw_bytes = path.read_bytes()
        except Exception as e:
            raise ImportError_("file_unreadable", str(e)) from e

        if not raw_bytes:
            raise ImportError_("empty", "File is empty")

        try:
            return raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                return raw_bytes.decode("cp1252")
            except UnicodeDecodeError as e:
                raise ImportError_("encoding", f"Unsupported file encoding: {e}") from e

    @classmethod
    def detect_mapping(cls, fieldnames: list[str]) -> dict[str, str]:
        """Auto-detect mapping from CSV headers to CB POS field names.

        Raises:
            ImportMappingError("duplicate_column", field, header) if two headers map to the same field.
        """
        field_to_header: dict[str, str] = {}
        mapping: dict[str, str] = {}

        for header in fieldnames:
            norm = normalize_header(header)
            matched_field = None
            for field, aliases in CANONICAL_FIELDS.items():
                if norm in aliases:
                    matched_field = field
                    break

            if matched_field:
                if matched_field in field_to_header:
                    raise ImportMappingError(
                        code="duplicate_column",
                        field=matched_field,
                        header=header,
                        message=f"Two columns ('{field_to_header[matched_field]}' and '{header}') map to '{matched_field}'.",
                    )
                field_to_header[matched_field] = header
                mapping[header] = matched_field
            else:
                mapping[header] = "(ignore)"

        return mapping

    @staticmethod
    def validate_mapping(mapping: dict[str, str]) -> None:
        """Validate that no two CSV headers map to the same non-ignored target field."""
        target_to_header: dict[str, str] = {}
        for header, target in mapping.items():
            if target and target not in ("(ignore)", "ignore"):
                if target in target_to_header:
                    raise ImportMappingError(
                        code="duplicate_column",
                        field=target,
                        header=header,
                        message=f"Two columns ('{target_to_header[target]}' and '{header}') map to '{target}'.",
                    )
                target_to_header[target] = header

    def parse_preview(
        self,
        file_path: str,
        max_rows: int = 5,
    ) -> tuple[list[str], dict[str, str], list[dict[str, str]], int]:
        """Parse first rows and default mapping for preview.

        Returns:
            (headers, default_mapping, preview_rows, total_rows)
        """
        validated_path = self._validate_file_path(file_path)
        content = self.read_csv_text(validated_path)

        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            raise ImportError_("no_header", "CSV file has no headers")

        headers = list(reader.fieldnames)
        try:
            default_mapping = self.detect_mapping(headers)
        except ImportMappingError:
            default_mapping = dict.fromkeys(headers, "(ignore)")

        preview_rows = []
        total_rows = 0
        for row in reader:
            total_rows += 1
            if len(preview_rows) < max_rows:
                preview_rows.append(row)

        if total_rows == 0:
            raise ImportError_("empty", "The file has no rows")

        return headers, default_mapping, preview_rows, total_rows

    def import_products_from_csv(
        self,
        file_path: str,
        mapping: dict[str, str] | None = None,
        acting_user_id: int | None = None,
    ) -> dict[str, Any]:
        """Import products from a CSV file without progress reporting."""
        return self._import_csv(file_path, progress_callback=None, mapping=mapping, acting_user_id=acting_user_id)

    def import_products_from_csv_with_progress(
        self,
        file_path: str,
        progress_callback: Callable[[int], None] | None = None,
        mapping: dict[str, str] | None = None,
        acting_user_id: int | None = None,
    ) -> dict[str, Any]:
        """Import products with a progress callback called after each row."""
        return self._import_csv(
            file_path, progress_callback=progress_callback, mapping=mapping, acting_user_id=acting_user_id
        )

    def _import_csv(
        self,
        file_path: str,
        progress_callback: Callable[[int], None] | None = None,
        mapping: dict[str, str] | None = None,
        acting_user_id: int | None = None,
    ) -> dict[str, Any]:
        require_catalog_writable()

        effective_user_id = acting_user_id
        if effective_user_id is None:
            curr = AuthService.get_current_user()
            if curr:
                effective_user_id = curr.id

        if effective_user_id is not None:
            db_auth = Database()
            with db_auth.get_session() as auth_session:
                user = auth_session.get(
                    User, effective_user_id, options=[joinedload(User.role).joinedload(Role.permissions)]
                )
                if not user or not PermissionService.user_has_permission(user, Permissions.INVENTORY_EDIT):
                    raise PermissionError("Permission denied: inventory.edit required")

        results: dict[str, Any] = {"success": 0, "failed": 0, "skipped": 0, "errors": []}

        validated_path = self._validate_file_path(file_path)
        content = self.read_csv_text(validated_path)

        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            raise ImportError_("no_header", "CSV file has no headers")

        if mapping is None:
            active_mapping = self.detect_mapping(reader.fieldnames)
        else:
            self.validate_mapping(mapping)
            active_mapping = mapping

        col_to_field = {
            col: field for col, field in active_mapping.items() if field and field not in ("(ignore)", "ignore")
        }

        db = Database()
        with db.get_session() as session:
            for row_num, row in enumerate(reader, start=1):
                if progress_callback:
                    progress_callback(row_num)

                mapped = {}
                for col, field in col_to_field.items():
                    val = row.get(col)
                    if val is not None:
                        mapped[field] = val.strip()

                barcode = mapped.get("barcode", "").strip()
                name_en = mapped.get("name_en", "").strip()
                name_si = mapped.get("name_si", "").strip() or None
                name_ta = mapped.get("name_ta", "").strip() or None
                price_str = mapped.get("price", "0").strip()
                cost_str = mapped.get("cost", "0").strip()
                stock_str = mapped.get("stock_qty", "0").strip()
                reorder_str = mapped.get("reorder_point", "0").strip()
                category_name = mapped.get("category", "").strip()
                unit_name = mapped.get("unit", "").strip()

                if not barcode or not name_en:
                    results["failed"] += 1
                    results["errors"].append(f"Row {row_num}: Barcode and product name are required.")
                    continue

                # Check duplicate barcode
                existing = session.scalar(select(Product).where(Product.barcode == barcode))
                if existing:
                    results["skipped"] += 1
                    continue

                try:
                    price = (
                        Decimal(price_str).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        if price_str
                        else Decimal("0.00")
                    )
                    cost = (
                        Decimal(cost_str).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        if cost_str
                        else Decimal("0.00")
                    )
                    stock = (
                        Decimal(stock_str).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                        if stock_str
                        else Decimal("0.000")
                    )
                    reorder_point = (
                        Decimal(reorder_str).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                        if reorder_str
                        else Decimal("0.000")
                    )
                except (InvalidOperation, ValueError):
                    results["failed"] += 1
                    results["errors"].append(f"Row {row_num}: Invalid number for price, cost, or stock.")
                    continue

                product_data = {
                    "barcode": barcode,
                    "name_en": name_en,
                    "name_si": name_si,
                    "name_ta": name_ta,
                    "price": price,
                    "cost": cost,
                    "stock_qty": stock,
                    "reorder_point": reorder_point,
                    "is_active": True,
                }

                errors = ProductValidator.validate_product_data(product_data)
                if errors:
                    results["failed"] += 1
                    results["errors"].append(f"Row {row_num}: {'; '.join(errors)}")
                    continue

                if category_name:
                    cat = session.scalar(select(Category).where(func.lower(Category.name_en) == category_name.lower()))
                    if cat:
                        product_data["category_id"] = cat.id

                if unit_name:
                    u = session.scalar(select(Unit).where(func.lower(Unit.name) == unit_name.lower()))
                    if u:
                        product_data["unit_id"] = u.id

                self.inventory_service.create_product(product_data, session=session)
                results["success"] += 1

            session.commit()

        return results

    @staticmethod
    def generate_template() -> str:
        """Return CSV template content with headers and example row."""
        return "Barcode,Name,Price,Cost,Stock\n8901234567890,Sample Product,150.00,100.00,50\n"
