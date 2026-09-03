"""
Tests for the sync protocol module.

Tests serialization roundtrips, envelope validation, and model mapping.
"""

import json
import pytest
from datetime import datetime, date
from decimal import Decimal

from cbpos.core.services.sync_protocol import (
    SyncEncoder,
    sync_json_dumps,
    sync_json_loads,
    model_to_dict,
    dict_to_model,
    make_envelope,
    validate_envelope,
    get_model_for_table,
    get_table_model_map,
    CATALOG_TABLES,
    TRANSACTION_TABLES,
    SYNC_PROTOCOL_VERSION,
)
from cbpos.core.models import (
    Product,
    Sale,
    SaleItem,
    SalePayment,
    Category,
    Customer,
    SyncLog,
    SyncQueue,
)


# ---------------------------------------------------------------------------
# SyncEncoder Tests
# ---------------------------------------------------------------------------

class TestSyncEncoder:
    """Test the custom JSON encoder."""

    def test_decimal_to_str(self):
        """Decimal values serialize as strings to preserve precision."""
        data = {"price": Decimal("99.95"), "tax": Decimal("0.00")}
        result = json.loads(sync_json_dumps(data))
        assert result["price"] == "99.95"
        assert result["tax"] == "0.00"
        assert isinstance(result["price"], str)

    def test_datetime_to_iso(self):
        """Datetime values serialize as ISO 8601 strings."""
        dt = datetime(2026, 9, 3, 14, 30, 0)
        result = json.loads(sync_json_dumps({"ts": dt}))
        assert result["ts"] == "2026-09-03T14:30:00"

    def test_date_to_iso(self):
        """Date values serialize as ISO 8601 date strings."""
        d = date(2026, 9, 3)
        result = json.loads(sync_json_dumps({"d": d}))
        assert result["d"] == "2026-09-03"

    def test_mixed_types(self):
        """Encoder handles mixed type dicts without errors."""
        data = {
            "id": 1,
            "name": "Test",
            "price": Decimal("100.50"),
            "created": datetime(2026, 1, 1, 12, 0),
            "active": True,
            "tags": ["a", "b"],
        }
        result = json.loads(sync_json_dumps(data))
        assert result["id"] == 1
        assert result["name"] == "Test"
        assert result["price"] == "100.50"
        assert result["active"] is True


# ---------------------------------------------------------------------------
# model_to_dict / dict_to_model Tests
# ---------------------------------------------------------------------------

class TestModelConversion:
    """Test SQLAlchemy model ↔ dict conversion."""

    def test_product_roundtrip(self):
        """Product model survives a dict roundtrip with correct types."""
        product = Product(
            id=42,
            barcode="1234567890123",
            name_en="Test Widget",
            price=Decimal("250.00"),
            cost=Decimal("150.00"),
            stock_qty=Decimal("100"),
            is_active=True,
            is_weighted=False,
            is_composite=False,
            is_service=False,
            last_modified=datetime(2026, 9, 3, 10, 0, 0),
        )

        d = model_to_dict(product)
        assert isinstance(d["price"], str)
        assert d["price"] == "250.00"
        assert isinstance(d["last_modified"], str)
        assert d["is_active"] is True
        assert d["barcode"] == "1234567890123"

        restored = dict_to_model(Product, d)
        assert isinstance(restored.price, Decimal)
        assert restored.price == Decimal("250.00")
        assert isinstance(restored.cost, Decimal)
        assert restored.cost == Decimal("150.00")
        assert isinstance(restored.last_modified, datetime)
        assert restored.is_active is True
        assert restored.barcode == "1234567890123"

    def test_decimal_precision_preserved(self):
        """Decimal precision is never lost through serialization."""
        product = Product(
            price=Decimal("1234567890.99"),
            cost=Decimal("0.01"),
            stock_qty=Decimal("999999.999"),
        )
        d = model_to_dict(product)
        restored = dict_to_model(Product, d)
        assert restored.price == Decimal("1234567890.99")
        assert restored.cost == Decimal("0.01")
        assert str(restored.stock_qty) == "999999.999"

    def test_none_values_preserved(self):
        """None/null values pass through cleanly."""
        product = Product(
            barcode=None,
            name_en="Test",
            category_id=None,
        )
        d = model_to_dict(product)
        assert d["barcode"] is None
        assert d["category_id"] is None

        restored = dict_to_model(Product, d)
        assert restored.barcode is None
        assert restored.category_id is None

    def test_boolean_coercion(self):
        """Boolean values are coerced correctly from various representations."""
        product = dict_to_model(Product, {
            "is_active": "true",
            "is_weighted": "false",
            "is_composite": 1,
            "is_service": 0,
        })
        assert product.is_active is True
        assert product.is_weighted is False
        assert product.is_composite is True
        assert product.is_service is False

    def test_relationship_serialization(self):
        """Sale with items and payments serializes relationships correctly."""
        sale = Sale(
            id=1,
            document_number="INV-2026-00001",
            total_amount=Decimal("500.00"),
            tax_vat=Decimal("50.00"),
            tax_sscl=Decimal("10.00"),
            net_revenue=Decimal("440.00"),
            payment_method="CASH",
        )
        sale.items = [
            SaleItem(
                id=1,
                sale_id=1,
                product_id=42,
                qty=Decimal("2"),
                unit_price=Decimal("250.00"),
                original_price=Decimal("250.00"),
                subtotal=Decimal("500.00"),
            ),
        ]
        sale.payments = [
            SalePayment(
                id=1,
                sale_id=1,
                payment_method="CASH",
                amount=Decimal("500.00"),
            ),
        ]

        d = model_to_dict(sale, include_relationships=True)
        assert "items" in d
        assert "payments" in d
        assert len(d["items"]) == 1
        assert len(d["payments"]) == 1
        assert d["items"][0]["qty"] == "2"
        assert d["payments"][0]["amount"] == "500.00"

    def test_relationship_excluded_by_default(self):
        """By default, relationships are not serialized."""
        sale = Sale(id=1, document_number="X")
        sale.items = [SaleItem(id=1)]
        d = model_to_dict(sale, include_relationships=False)
        assert "items" not in d

    def test_sync_log_model(self):
        """SyncLog model roundtrips correctly."""
        log = SyncLog(
            terminal_id="TERM-02",
            direction="PUSH",
            sync_type="TRANSACTIONS",
            records_count=15,
            status="SUCCESS",
            started_at=datetime(2026, 9, 3, 10, 0, 0),
            completed_at=datetime(2026, 9, 3, 10, 0, 5),
        )
        d = model_to_dict(log)
        restored = dict_to_model(SyncLog, d)
        assert restored.terminal_id == "TERM-02"
        assert restored.direction == "PUSH"
        assert restored.records_count == 15

    def test_list_values_skipped_in_dict_to_model(self):
        """dict_to_model skips list values (relationship children)."""
        data = {
            "id": 1,
            "document_number": "INV-001",
            "total_amount": "100.00",
            "items": [{"id": 1, "qty": "2"}],  # Should be skipped
        }
        sale = dict_to_model(Sale, data)
        assert sale.id == 1
        assert sale.total_amount == Decimal("100.00")
        # items should not be set as a column value
        assert not hasattr(sale, "_items_from_dict")


# ---------------------------------------------------------------------------
# Envelope Tests
# ---------------------------------------------------------------------------

class TestEnvelope:
    """Test sync envelope creation and validation."""

    def test_make_envelope(self):
        """make_envelope creates a valid envelope."""
        env = make_envelope("TERM-02", "PUSH_TRANSACTIONS", {"sales": []}, sequence=5)
        assert env["protocol_version"] == SYNC_PROTOCOL_VERSION
        assert env["terminal_id"] == "TERM-02"
        assert env["type"] == "PUSH_TRANSACTIONS"
        assert env["sequence"] == 5
        assert "timestamp" in env

    def test_envelope_json_roundtrip(self):
        """Envelope survives JSON serialization/deserialization."""
        env = make_envelope("TERM-01", "PULL_CATALOG", {"tables": CATALOG_TABLES})
        json_str = sync_json_dumps(env)
        parsed = sync_json_loads(json_str)
        assert parsed["terminal_id"] == "TERM-01"
        assert parsed["type"] == "PULL_CATALOG"

    def test_validate_valid_envelope(self):
        """Valid envelope passes validation."""
        env = make_envelope("TERM-01", "HEARTBEAT", {})
        ok, err = validate_envelope(env)
        assert ok is True
        assert err == ""

    def test_validate_missing_field(self):
        """Envelope missing required fields fails validation."""
        ok, err = validate_envelope({"protocol_version": "1.0"})
        assert ok is False
        assert "Missing required field" in err

    def test_validate_incompatible_version(self):
        """Envelope with incompatible version fails validation."""
        env = make_envelope("TERM-01", "TEST", {})
        env["protocol_version"] = "2.0"
        ok, err = validate_envelope(env)
        assert ok is False
        assert "Incompatible" in err

    def test_validate_compatible_minor_version(self):
        """Minor version changes are compatible."""
        env = make_envelope("TERM-01", "TEST", {})
        env["protocol_version"] = "1.5"
        ok, err = validate_envelope(env)
        assert ok is True


# ---------------------------------------------------------------------------
# Table Model Map Tests
# ---------------------------------------------------------------------------

class TestTableModelMap:
    """Test table name → model class mapping."""

    def test_catalog_tables_have_models(self):
        """Every catalog table name maps to a model class."""
        for table in CATALOG_TABLES:
            model = get_model_for_table(table)
            assert model is not None, f"No model for catalog table: {table}"

    def test_transaction_tables_have_models(self):
        """Every transaction table name maps to a model class."""
        for table in TRANSACTION_TABLES:
            model = get_model_for_table(table)
            assert model is not None, f"No model for transaction table: {table}"

    def test_products_maps_to_product(self):
        assert get_model_for_table("products") is Product

    def test_unknown_table_returns_none(self):
        assert get_model_for_table("nonexistent_table") is None

    def test_sync_tables_mapped(self):
        assert get_model_for_table("sync_logs") is SyncLog
        assert get_model_for_table("sync_queue") is SyncQueue


# ---------------------------------------------------------------------------
# Full Roundtrip Simulation
# ---------------------------------------------------------------------------

class TestFullRoundtrip:
    """Test a complete push payload simulation."""

    def test_sale_push_payload_roundtrip(self):
        """Simulate a complete sale being serialized for push and deserialized on receive."""
        sale = Sale(
            id=100,
            document_number="INV-2026-02-00001",
            date=datetime(2026, 9, 3),
            total_amount=Decimal("1500.00"),
            tax_vat=Decimal("225.00"),
            tax_sscl=Decimal("37.50"),
            net_revenue=Decimal("1237.50"),
            payment_method="CASH",
            user_id=1,
            terminal_id="TERM-02",
            origin_terminal_id="TERM-02",
            synced=False,
        )
        sale.items = [
            SaleItem(
                id=200,
                sale_id=100,
                product_id=10,
                qty=Decimal("3"),
                unit_price=Decimal("500.00"),
                original_price=Decimal("500.00"),
                subtotal=Decimal("1500.00"),
            ),
        ]
        sale.payments = [
            SalePayment(
                id=300,
                sale_id=100,
                payment_method="CASH",
                amount=Decimal("1500.00"),
            ),
        ]

        # Serialize
        sale_dict = model_to_dict(sale, include_relationships=True)
        envelope = make_envelope("TERM-02", "PUSH_TRANSACTIONS", {
            "sales": [sale_dict],
        }, sequence=1)
        json_str = sync_json_dumps(envelope)

        # Simulate network transfer
        received = sync_json_loads(json_str)
        ok, err = validate_envelope(received)
        assert ok is True

        # Deserialize
        payload = received["payload"]
        received_sales = payload["sales"]
        assert len(received_sales) == 1

        restored = dict_to_model(Sale, received_sales[0])
        assert restored.id == 100
        assert restored.total_amount == Decimal("1500.00")
        assert restored.tax_vat == Decimal("225.00")
        assert restored.origin_terminal_id == "TERM-02"
        assert restored.document_number == "INV-2026-02-00001"

        # Verify items came through
        items_data = received_sales[0]["items"]
        assert len(items_data) == 1
        item = dict_to_model(SaleItem, items_data[0])
        assert item.qty == Decimal("3")
        assert item.unit_price == Decimal("500.00")
