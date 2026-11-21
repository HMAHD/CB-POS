"""Domain tests for PriceBoardService (#931)."""

from decimal import Decimal

import pytest

from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import AuditLog, Product, Role, User
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.inventory_service import StaleProductError
from cbpos.core.services.price_board_service import PriceBoardService
from cbpos.core.utils.terminal_guard import CatalogReadOnlyError


@pytest.fixture
def test_users(db_session):
    """Seed or fetch an admin user and an unprivileged cashier user."""
    admin_role = db_session.query(Role).filter_by(name="Admin").first()
    if not admin_role:
        admin_role = Role(name="Admin")
        db_session.add(admin_role)
        db_session.flush()

    cashier_role = db_session.query(Role).filter_by(name="Cashier").first()
    if not cashier_role:
        cashier_role = Role(name="Cashier")
        db_session.add(cashier_role)
        db_session.flush()

    admin_user = db_session.query(User).filter_by(username="admin_pb").first()
    if not admin_user:
        admin_user = User(username="admin_pb", pin_hash="hash1", role_id=admin_role.id, is_active=True)
        db_session.add(admin_user)

    cashier_user = db_session.query(User).filter_by(username="cashier_pb").first()
    if not cashier_user:
        cashier_user = User(username="cashier_pb", pin_hash="hash2", role_id=cashier_role.id, is_active=True)
        db_session.add(cashier_user)

    db_session.commit()
    return {"admin_id": admin_user.id, "cashier_id": cashier_user.id}


@pytest.fixture
def sample_products(db_session):
    """Seed sample products with varying price_changes_often and active states."""
    p1 = Product(
        barcode="VEG001",
        name_en="Carrot 1kg",
        name_si="කැරට් 1kg",
        name_ta="கேரட் 1kg",
        price=Decimal("250.00"),
        cost=Decimal("180.00"),
        is_active=True,
        price_changes_often=True,
        version_id=1,
    )
    p2 = Product(
        barcode="VEG002",
        name_en="Beans 1kg",
        name_si="බෝංචි 1kg",
        name_ta="பீன்ஸ் 1kg",
        price=Decimal("320.00"),
        cost=Decimal("240.00"),
        is_active=True,
        price_changes_often=True,
        version_id=1,
    )
    p3 = Product(
        barcode="GRO001",
        name_en="Biscuit Pack",
        name_si="බිස්කට්",
        name_ta="பிஸ்கட்",
        price=Decimal("150.00"),
        cost=Decimal("120.00"),
        is_active=True,
        price_changes_often=False,  # Not on price board
        version_id=1,
    )
    p4 = Product(
        barcode="VEG003",
        name_en="Tomato 1kg (Inactive)",
        name_si="තක්කාලි",
        name_ta="தக்காளி",
        price=Decimal("200.00"),
        cost=Decimal("150.00"),
        is_active=False,  # Inactive
        price_changes_often=True,
        version_id=1,
    )
    db_session.add_all([p1, p2, p3, p4])
    db_session.commit()
    return {
        "p1_id": p1.id,
        "p2_id": p2.id,
        "p3_id": p3.id,
        "p4_id": p4.id,
    }


@pytest.mark.domain
class TestPriceBoardService:
    """Test suite verifying PriceBoardService domain rules."""

    def test_get_price_board_items_filters_flagged_and_active(self, db_session, sample_products):
        """Only active products with price_changes_often=True are returned."""
        svc = PriceBoardService()
        items = svc.get_price_board_items()

        barcodes = [item.barcode for item in items]
        assert "VEG001" in barcodes
        assert "VEG002" in barcodes
        assert "GRO001" not in barcodes  # price_changes_often=False
        assert "VEG003" not in barcodes  # is_active=False

        # Verify display names and fields
        item1 = next(it for it in items if it.barcode == "VEG001")
        assert item1.current_price == Decimal("250.00")
        assert item1.version_id == 1
        assert item1.get_display_name("en") == "Carrot 1kg"
        assert item1.get_display_name("si") == "කැරට් 1kg"
        assert item1.get_display_name("ta") == "கேரட் 1kg"

    def test_batch_update_prices_rejects_till_terminal(self, db_session, sample_products, test_users, monkeypatch):
        """A till terminal ('terminal' mode) is blocked by require_catalog_writable()."""
        monkeypatch.setattr(
            ConfigService, "get", lambda k, default=None: "terminal" if k == "terminal_mode" else default
        )
        svc = PriceBoardService()

        updates = [{"product_id": sample_products["p1_id"], "expected_version_id": 1, "new_price": Decimal("280.00")}]

        with pytest.raises(CatalogReadOnlyError):
            svc.batch_update_prices(updates, acting_user_id=test_users["admin_id"])

    def test_batch_update_prices_requires_permission(self, db_session, sample_products, test_users):
        """Users without Permissions.PRICING_MANAGE are rejected with PermissionError."""
        svc = PriceBoardService()

        updates = [{"product_id": sample_products["p1_id"], "expected_version_id": 1, "new_price": Decimal("280.00")}]

        with pytest.raises(PermissionError) as exc_info:
            svc.batch_update_prices(updates, acting_user_id=test_users["cashier_id"])
        assert Permissions.PRICING_MANAGE in str(exc_info.value)

    def test_batch_update_prices_validates_amounts(self, db_session, sample_products, test_users):
        """Negative or non-numeric prices fail closed with ValueError."""
        svc = PriceBoardService()

        # Negative price
        updates_negative = [
            {"product_id": sample_products["p1_id"], "expected_version_id": 1, "new_price": Decimal("-10.00")}
        ]
        with pytest.raises(ValueError, match="negative"):
            svc.batch_update_prices(updates_negative, acting_user_id=test_users["admin_id"])

        # Invalid string
        updates_invalid = [{"product_id": sample_products["p1_id"], "expected_version_id": 1, "new_price": "abc"}]
        with pytest.raises(ValueError, match="Invalid price"):
            svc.batch_update_prices(updates_invalid, acting_user_id=test_users["admin_id"])

    def test_batch_update_prices_rejects_duplicate_product_ids(self, sample_products, test_users):
        """Batch update rejects duplicate entries for the same product_id."""
        svc = PriceBoardService()
        with pytest.raises(ValueError, match="Duplicate product_id in batch update"):
            svc.batch_update_prices(
                [
                    {"product_id": sample_products["p1_id"], "expected_version_id": 1, "new_price": Decimal("260.00")},
                    {"product_id": sample_products["p1_id"], "expected_version_id": 1, "new_price": Decimal("270.00")},
                ],
                acting_user_id=test_users["admin_id"],
            )

    def test_batch_update_prices_optimistic_lock_stale_rollback(self, db_session, sample_products, test_users):
        """If ANY product has a stale version_id, the entire batch rolls back with StaleProductError."""
        svc = PriceBoardService()

        updates = [
            {"product_id": sample_products["p1_id"], "expected_version_id": 1, "new_price": Decimal("280.00")},
            {
                "product_id": sample_products["p2_id"],
                "expected_version_id": 999,
                "new_price": Decimal("350.00"),
            },  # Stale!
        ]

        with pytest.raises(StaleProductError):
            svc.batch_update_prices(updates, acting_user_id=test_users["admin_id"])

        # Prove rollback: p1 price must still be 250.00, p2 price must still be 320.00
        p1 = db_session.get(Product, sample_products["p1_id"])
        p2 = db_session.get(Product, sample_products["p2_id"])
        assert p1.price == Decimal("250.00")
        assert p2.price == Decimal("320.00")

        # Prove no audit logs were written
        audits = db_session.query(AuditLog).filter(AuditLog.action == "PRICE_CHANGE").all()
        assert len(audits) == 0

    def test_batch_update_prices_success_single_commit_and_audit(self, db_session, sample_products, test_users):
        """Valid batch applies changes, logs audits for actual changes, and increments version_id."""
        svc = PriceBoardService()

        updates = [
            # p1 changed from 250.00 -> 280.00
            {"product_id": sample_products["p1_id"], "expected_version_id": 1, "new_price": Decimal("280.00")},
            # p2 unchanged at 320.00
            {"product_id": sample_products["p2_id"], "expected_version_id": 1, "new_price": Decimal("320.00")},
        ]

        changed_ids = svc.batch_update_prices(updates, acting_user_id=test_users["admin_id"])

        # Only p1 actually changed
        assert changed_ids == [sample_products["p1_id"]]

        p1 = db_session.get(Product, sample_products["p1_id"])
        p2 = db_session.get(Product, sample_products["p2_id"])

        assert p1.price == Decimal("280.00")
        assert p1.version_id == 2  # Incremented
        assert p2.price == Decimal("320.00")

        # Audit log check: exactly one row for p1
        audits = db_session.query(AuditLog).filter(AuditLog.action == "PRICE_CHANGE").all()
        assert len(audits) == 1
        audit = audits[0]
        assert audit.user_id == test_users["admin_id"]
        assert audit.event_type == "INVENTORY"
        assert "250" in audit.details
        assert "280" in audit.details
        assert "VEG001" in audit.details

    def test_batch_update_prices_commit_time_stale_data_error_translated_and_rolled_back(
        self, db_session, sample_products, test_users
    ):
        """SQLAlchemy StaleDataError during commit is translated to StaleProductError and rolled back."""
        from sqlalchemy import event, text
        from sqlalchemy.orm import Session

        svc = PriceBoardService()
        updates = [
            {"product_id": sample_products["p1_id"], "expected_version_id": 1, "new_price": Decimal("290.00")},
        ]
        p1_id = sample_products["p1_id"]

        # Simulate concurrent transaction incrementing version_id between pre-check and SQL flush
        def bump_version_during_flush(session, flush_context, instances):
            session.connection().execute(text(f"UPDATE products SET version_id = 99 WHERE id = {p1_id}"))

        event.listen(Session, "before_flush", bump_version_during_flush, once=True)

        with pytest.raises(StaleProductError) as exc_info:
            svc.batch_update_prices(updates, acting_user_id=test_users["admin_id"])

        assert "modified by another" in str(exc_info.value)

        db_session.rollback()
        p1 = db_session.get(Product, p1_id)
        assert p1.price == Decimal("250.00")  # Price not updated

        # Prove no audit logs were written
        audits = db_session.query(AuditLog).filter(AuditLog.action == "PRICE_CHANGE").all()
        assert len(audits) == 0
