"""
Sync Protocol for CB-POS Multi-Terminal LAN Sync.

Provides JSON serialization/deserialization for SQLAlchemy models,
sync envelope format, and shared constants for the sync server/client.
"""

import json
import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import RelationshipProperty

from cbpos.core.database import Base

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sync Protocol Version — bump when envelope format changes.
# Server and client must agree on the major version.
# ---------------------------------------------------------------------------
SYNC_PROTOCOL_VERSION = "1.4"

# ---------------------------------------------------------------------------
# Default sync server port
# ---------------------------------------------------------------------------
DEFAULT_SYNC_PORT = 5555

# ---------------------------------------------------------------------------
# Sync Endpoints (URL paths for the HTTP sync server)
# ---------------------------------------------------------------------------
EP_HEARTBEAT = "/sync/heartbeat"
EP_REGISTER = "/sync/register"
EP_PUSH_TRANSACTIONS = "/sync/push-transactions"
EP_PULL_CATALOG = "/sync/pull-catalog"
EP_PULL_STOCK = "/sync/pull-stock"
EP_PUSH_AUDIT = "/sync/push-audit"

# ---------------------------------------------------------------------------
# Catalog tables — Main PC is the master, terminals pull these.
# Order matters: tables without FKs first, then tables with dependencies.
# ---------------------------------------------------------------------------
CATALOG_TABLES = [
    "permissions",
    "roles",
    "users",
    "void_reasons",
    "units",
    "warranty_policies",
    "categories",
    "suppliers",
    "customers",
    "price_lists",
    "price_list_items",
    "products",
    "promotions",
    "payment_methods",
    "composite_items",
]

# Reverse FK dependency order for catalog deletions (children deleted before parents)
CATALOG_DELETION_ORDER = [
    "composite_items",
    "price_list_items",
    "products",
    "promotions",
    "payment_methods",
    "price_lists",
    "suppliers",
    "categories",
    "warranty_policies",
    "units",
    "void_reasons",
    "users",
    "roles",
    "permissions",
]

# Push reply error for a table the Main PC doesn't take, followed by the
# table name. Every Main PC version answers this way, so a till can tell
# which of its rows an older Main PC turned away (and keep them to re-send).
REJECTED_TABLE_ERROR = "Table not allowed for push: "

# ---------------------------------------------------------------------------
# Transaction tables — Terminals push these to the Main PC.
# Order: parent tables before children (for FK integrity).
# ---------------------------------------------------------------------------
TRANSACTION_TABLES = [
    "customers",  # Only those created on the till (#680); first, as sales point at them
    "customer_contacts",  # Only those of the customers above, pushed with them (#717)
    "documents",  # Base (polymorphic: sale, purchase, proforma, stock_count)
    "sales",
    "sale_items",
    "sale_payments",
    "warranties",
    "purchases",
    "purchase_items",
    "stock_movements",
    "shifts",
    "cash_movements",
    "audit_logs",
    "customer_payments",
    "customer_ledger",
    "loyalty_ledger",  # Loyalty points move by event (#716)
    "supplier_payments",
    "supplier_ledger",
    "suspended_transactions",
    "inventory_logs",
]


# ---------------------------------------------------------------------------
# JSON Encoder — handles Decimal, datetime, date
# ---------------------------------------------------------------------------
class SyncEncoder(json.JSONEncoder):
    """JSON encoder that handles Python types used in SQLAlchemy models.

    - ``Decimal`` → ``str`` (preserves precision, avoids float errors)
    - ``datetime`` → ISO 8601 string
    - ``date`` → ISO 8601 date string
    - ``time`` → ISO 8601 time string
    """

    def default(self, obj: Any) -> Any:
        """Convert Decimal/datetime/date/time to their JSON-safe representations; defer everything else."""
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        # datetime is a subclass of date, but not of time, so this branch is separate and safe
        if isinstance(obj, time):
            return obj.isoformat()
        return super().default(obj)


def sync_json_dumps(obj: Any) -> str:
    """Serialize ``obj`` to a JSON string using the sync encoder."""
    return json.dumps(obj, cls=SyncEncoder, ensure_ascii=False)


def sync_json_loads(s: str) -> Any:
    """Deserialize a JSON string.  Decimal/datetime decoding is done
    explicitly by :func:`dict_to_model` using column type introspection."""
    return json.loads(s)


# ---------------------------------------------------------------------------
# Model ↔ Dict Conversion
# ---------------------------------------------------------------------------
def model_to_dict(instance: Base, include_relationships: bool = False) -> dict[str, Any]:
    """Convert a SQLAlchemy model instance to a plain dict.

    Only scalar (column) attributes are included by default.
    Relationship attributes are excluded unless ``include_relationships``
    is True, in which case one-to-many children are serialized recursively
    (used for pushing Sale + SaleItems + SalePayments as a single unit).

    Args:
        instance: A SQLAlchemy model instance.
        include_relationships: If True, include list-type relationships
            (e.g. Sale.items, Sale.payments) as nested dicts.

    Returns:
        Dict with column names as keys and Python values.
    """
    mapper = sa_inspect(type(instance))
    result: dict[str, Any] = {}

    # Scalar columns
    for col in mapper.columns:
        key = col.key
        value = getattr(instance, key, None)
        if isinstance(value, Decimal):
            value = str(value)
        elif isinstance(value, (datetime, date, time)):
            value = value.isoformat()
        result[key] = value

    if include_relationships:
        rel: RelationshipProperty
        for rel in mapper.relationships:
            if rel.uselist:  # one-to-many
                children = getattr(instance, rel.key, []) or []
                result[rel.key] = [model_to_dict(child) for child in children]

    return result


def dict_to_model(model_class: type[Base], data: dict[str, Any]) -> Base:
    """Create a SQLAlchemy model instance from a dict.

    Values are coerced as described in :func:`coerce_columns`.

    Args:
        model_class: The SQLAlchemy model class.
        data: Dict with column names as keys.

    Returns:
        An unsaved model instance (not added to any session).
    """
    return model_class(**coerce_columns(model_class, data))


def coerce_columns(model_class: type[Base], data: dict[str, Any]) -> dict[str, Any]:
    """Return ``data``'s column values converted to the model's Python types.

    Keys that are not columns of ``model_class`` (and list values, i.e.
    nested relationships) are dropped.

    Handles type coercion:
    - ``Decimal`` columns: str → Decimal
    - ``DateTime`` columns: ISO string → datetime
    - ``Date`` columns: ISO string → date
    - ``Boolean`` columns: int/str → bool
    - ``Integer`` columns: str → int

    Args:
        model_class: The SQLAlchemy model class.
        data: Dict with column names as keys.

    Returns:
        Dict of column key → coerced value.
    """
    mapper = sa_inspect(model_class)
    column_types = {}
    for col in mapper.columns:
        column_types[col.key] = col.type

    kwargs = {}
    for key, value in data.items():
        if value is None:
            kwargs[key] = None
            continue

        # Skip relationship keys (lists of dicts)
        if isinstance(value, list):
            continue

        col_type = column_types.get(key)
        if col_type is None:
            # Not a column on this model — skip (could be a relationship key)
            continue

        type_name = type(col_type).__name__

        if type_name in ("Numeric", "NUMERIC"):
            kwargs[key] = Decimal(str(value))
        elif type_name in ("DateTime", "DATETIME"):
            if isinstance(value, str):
                kwargs[key] = datetime.fromisoformat(value)
            else:
                kwargs[key] = value
        elif type_name in ("Date", "DATE"):
            if isinstance(value, str):
                kwargs[key] = date.fromisoformat(value)
            else:
                kwargs[key] = value
        elif type_name in ("Time", "TIME"):
            if isinstance(value, str):
                kwargs[key] = time.fromisoformat(value)
            else:
                kwargs[key] = value
        elif type_name in ("Boolean", "BOOLEAN"):
            if isinstance(value, str):
                kwargs[key] = value.lower() in ("true", "1", "yes")
            else:
                kwargs[key] = bool(value)
        elif type_name in ("Integer", "INTEGER"):
            kwargs[key] = int(value) if value is not None else None
        else:
            kwargs[key] = value

    return kwargs


# ---------------------------------------------------------------------------
# Sync Envelope — the wrapper around all sync messages
# ---------------------------------------------------------------------------
def make_envelope(
    terminal_id: str,
    msg_type: str,
    payload: Any,
    sequence: int | None = None,
    db_instance_id: str | None = None,
) -> dict[str, Any]:
    """Create a sync envelope for transmission.

    Args:
        terminal_id: The sending terminal's ID (e.g. "TERM-02").
        msg_type: Message type (e.g. "PUSH_TRANSACTIONS", "PULL_CATALOG").
        payload: The data payload (will be JSON-serialized).
        sequence: Optional sync sequence number for resumable sync.
        db_instance_id: Optional database instance UUID (#866).

    Returns:
        Dict ready for JSON serialization.
    """
    if db_instance_id is None:
        try:
            from cbpos.core.services.local_identity_service import LocalIdentityService

            db_instance_id = LocalIdentityService.get()
        except Exception:
            db_instance_id = ""

    return {
        "protocol_version": SYNC_PROTOCOL_VERSION,
        "terminal_id": terminal_id,
        "db_instance_id": db_instance_id,
        "timestamp": datetime.now().isoformat(),
        "sequence": sequence,
        "type": msg_type,
        "payload": payload,
    }


def validate_envelope(data: dict[str, Any]) -> tuple[bool, str]:
    """Validate a received sync envelope.

    Returns:
        Tuple of (is_valid, error_message).
    """
    required = ("protocol_version", "terminal_id", "db_instance_id", "type", "payload")
    for field in required:
        if field not in data:
            return False, f"Missing required field: {field}"

    version = data.get("protocol_version", "")
    if not isinstance(version, str) or not version.startswith("1."):
        return False, f"Incompatible protocol version: {version}"

    try:
        parts = [int(p) for p in version.split(".")]
        if parts < [1, 1]:
            return False, "protocol_too_old"
    except Exception:
        return False, f"Invalid protocol version: {version}"

    if not data.get("db_instance_id"):
        return False, "Missing required field: db_instance_id"

    return True, ""


# ---------------------------------------------------------------------------
# Table name → Model class mapping (lazy-loaded to avoid circular imports)
# ---------------------------------------------------------------------------
_TABLE_MODEL_MAP: dict[str, type[Base]] | None = None


def get_table_model_map() -> dict[str, type[Base]]:
    """Return a dict mapping table names to their SQLAlchemy model classes.

    Lazy-loaded on first call to avoid circular import issues.
    """
    global _TABLE_MODEL_MAP
    if _TABLE_MODEL_MAP is not None:
        return _TABLE_MODEL_MAP

    from cbpos.core.models import (
        AuditLog,
        CashMovement,
        Category,
        CompositeItem,
        Customer,
        CustomerContact,
        CustomerLedgerEntry,
        CustomerPayment,
        Document,
        InventoryLog,
        LoyaltyLedgerEntry,
        PaymentMethod,
        Permission,
        PriceList,
        PriceListItem,
        Product,
        Proforma,
        ProformaItem,
        Promotion,
        Purchase,
        PurchaseItem,
        Role,
        Sale,
        SaleItem,
        SalePayment,
        Shift,
        StockCount,
        StockCountItem,
        StockMovement,
        Supplier,
        SupplierLedgerEntry,
        SupplierPayment,
        SuspendedTransaction,
        SyncLog,
        SyncQueue,
        Unit,
        User,
        VoidReason,
        Warranty,
        WarrantyPolicy,
    )

    _TABLE_MODEL_MAP = {
        "roles": Role,
        "permissions": Permission,
        "users": User,
        "warranty_policies": WarrantyPolicy,
        "warranties": Warranty,
        "price_lists": PriceList,
        "price_list_items": PriceListItem,
        "promotions": Promotion,
        "void_reasons": VoidReason,
        "units": Unit,
        "categories": Category,
        "products": Product,
        "customers": Customer,
        "customer_contacts": CustomerContact,
        "suppliers": Supplier,
        "composite_items": CompositeItem,
        "payment_methods": PaymentMethod,
        "documents": Document,
        "sales": Sale,
        "sale_items": SaleItem,
        "sale_payments": SalePayment,
        "purchases": Purchase,
        "purchase_items": PurchaseItem,
        "proformas": Proforma,
        "proforma_items": ProformaItem,
        "stock_movements": StockMovement,
        "audit_logs": AuditLog,
        "inventory_logs": InventoryLog,
        "shifts": Shift,
        "cash_movements": CashMovement,
        "suspended_transactions": SuspendedTransaction,
        "customer_payments": CustomerPayment,
        "customer_ledger": CustomerLedgerEntry,
        "loyalty_ledger": LoyaltyLedgerEntry,
        "stock_counts": StockCount,
        "stock_count_items": StockCountItem,
        "supplier_payments": SupplierPayment,
        "supplier_ledger": SupplierLedgerEntry,
        "sync_logs": SyncLog,
        "sync_queue": SyncQueue,
    }
    return _TABLE_MODEL_MAP


def get_model_for_table(table_name: str) -> type[Base] | None:
    """Return the SQLAlchemy model class for a given table name."""
    return get_table_model_map().get(table_name)
