"""Unit and domain tests for Warranty W1 (#821): Warranty policies, resolution precedence,
feature gating, permissions, audit trails, and calendar-aware end-date calculations.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import Permissions
from cbpos.core.models import (
    AuditLog,
    Category,
    Permission,
    Product,
    Role,
    User,
    WarrantyPolicy,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.warranty_service import WarrantyService
from cbpos.core.utils.terminal_guard import CatalogReadOnlyError


def _create_user_with_permissions(db_session, username: str, perms: list[str]) -> User:
    role = Role(name=f"Role_{username}")
    db_session.add(role)
    db_session.flush()

    for code in perms:
        perm = db_session.execute(select(Permission).where(Permission.code == code)).scalar_one_or_none()
        if not perm:
            perm = Permission(code=code, description=code, group="Warranty")
            db_session.add(perm)
            db_session.flush()
        role.permissions.append(perm)

    user = User(username=username, pin_hash=AuthService.hash_pin("1234"), role_id=role.id, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


class TestWarrantyDateArithmetic:
    """Inclusive calendar-aware date calculation: start + duration - 1 day."""

    def test_issue_821_compute_end_date_calendar_math(self):
        # 12 months from 2026-10-21 -> 2027-10-20
        assert WarrantyService.compute_end_date(date(2026, 10, 21), 12, "MONTHS") == date(2027, 10, 20)

        # 1 month from Jan 31 -> Feb 27 (2026 is non-leap year: Jan 31 + 1M clamps to Feb 28, minus 1 day = Feb 27)
        assert WarrantyService.compute_end_date(date(2026, 1, 31), 1, "MONTHS") == date(2026, 2, 27)

        # 1 year from leap day 2024-02-29 -> 2025-02-27 (2024-02-29 + 1Y clamps to 2025-02-28, minus 1 day = 2025-02-27)
        assert WarrantyService.compute_end_date(date(2024, 2, 29), 1, "YEARS") == date(2025, 2, 27)

        # 1 year from 2023-02-28 -> 2024-02-27
        assert WarrantyService.compute_end_date(date(2023, 2, 28), 1, "YEARS") == date(2024, 2, 27)

        # 7 days from 2026-10-21 -> 2026-10-27 (inclusive: 21, 22, 23, 24, 25, 26, 27 = 7 days)
        assert WarrantyService.compute_end_date(date(2026, 10, 21), 7, "DAYS") == date(2026, 10, 27)

    def test_issue_821_compute_end_date_validation(self):
        with pytest.raises(ValueError, match="duration must be positive"):
            WarrantyService.compute_end_date(date(2026, 1, 1), 0, "MONTHS")

        with pytest.raises(ValueError, match="duration must be positive"):
            WarrantyService.compute_end_date(date(2026, 1, 1), -5, "DAYS")

        with pytest.raises(ValueError, match="Invalid duration unit"):
            WarrantyService.compute_end_date(date(2026, 1, 1), 1, "HOURS")


class TestWarrantyPolicyResolution:
    """Precedence: Product explicit policy > Category default > Parent Category default > None."""

    def test_issue_821_resolve_policy_precedence(self, db_session):
        policy_parent = WarrantyPolicy(
            name="Parent Category Warranty",
            warranty_type="SHOP",
            duration=6,
            duration_unit="MONTHS",
            remedy="REPAIR_OR_REPLACE",
            is_active=True,
        )
        policy_child = WarrantyPolicy(
            name="Child Category Warranty",
            warranty_type="SHOP",
            duration=1,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            is_active=True,
        )
        policy_product = WarrantyPolicy(
            name="Product Specific Warranty",
            warranty_type="MANUFACTURER",
            duration=2,
            duration_unit="YEARS",
            remedy="REPAIR_ONLY",
            is_active=True,
        )
        db_session.add_all([policy_parent, policy_child, policy_product])
        db_session.flush()

        cat_parent = Category(name="Electronics", default_warranty_policy_id=policy_parent.id)
        db_session.add(cat_parent)
        db_session.flush()

        cat_child = Category(name="Phones", parent_id=cat_parent.id, default_warranty_policy_id=policy_child.id)
        cat_no_default = Category(name="Accessories", parent_id=cat_parent.id, default_warranty_policy_id=None)
        db_session.add_all([cat_child, cat_no_default])
        db_session.flush()

        prod_explicit = Product(
            barcode="PROD_EXP",
            name_en="Phone Model X",
            price=Decimal("100.00"),
            category_id=cat_child.id,
            warranty_override="POLICY",
            warranty_policy_id=policy_product.id,
        )
        prod_inherit_child = Product(
            barcode="PROD_INH_CHILD",
            name_en="Phone Model Y",
            price=Decimal("100.00"),
            category_id=cat_child.id,
            warranty_override="INHERIT",
        )
        prod_inherit_parent = Product(
            barcode="PROD_INH_PARENT",
            name_en="Cable Z",
            price=Decimal("100.00"),
            category_id=cat_no_default.id,
            warranty_override="INHERIT",
        )
        prod_no_cat = Product(
            barcode="PROD_NO_CAT",
            name_en="Generic Item",
            price=Decimal("100.00"),
            category_id=None,
            warranty_override="INHERIT",
        )
        db_session.add_all([prod_explicit, prod_inherit_child, prod_inherit_parent, prod_no_cat])
        db_session.commit()

        # 1. Product explicit POLICY wins
        res = WarrantyService.resolve_policy(prod_explicit, session=db_session)
        assert res is not None
        assert res.id == policy_product.id

        # 2. Child category default wins when product INHERIT
        res = WarrantyService.resolve_policy(prod_inherit_child, session=db_session)
        assert res is not None
        assert res.id == policy_child.id

        # 3. Parent category default wins when child category has no default
        res = WarrantyService.resolve_policy(prod_inherit_parent, session=db_session)
        assert res is not None
        assert res.id == policy_parent.id

        # 4. None when no category and no product policy
        assert WarrantyService.resolve_policy(prod_no_cat, session=db_session) is None

    def test_issue_821_resolve_policy_explicit_none_blocks_category(self, db_session):
        policy = WarrantyPolicy(
            name="Category 1 Year Warranty",
            warranty_type="SHOP",
            duration=1,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            is_active=True,
        )
        db_session.add(policy)
        db_session.flush()

        cat = Category(name="Electronics", default_warranty_policy_id=policy.id)
        db_session.add(cat)
        db_session.flush()

        prod = Product(
            barcode="PROD_NONE",
            name_en="Clearance Item",
            price=Decimal("100.00"),
            category_id=cat.id,
            warranty_override="NONE",
            warranty_policy_id=None,
        )
        db_session.add(prod)
        db_session.commit()

        # Explicit NONE must return None even though Category has an active policy
        assert WarrantyService.resolve_policy(prod, session=db_session) is None

    def test_issue_821_resolve_policy_weighted_product_rejected(self, db_session):
        policy = WarrantyPolicy(
            name="1 Year Shop",
            warranty_type="SHOP",
            duration=1,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            is_active=True,
        )
        db_session.add(policy)
        db_session.flush()

        prod = Product(
            barcode="PROD_WEIGHTED",
            name_en="Bulk Nails 1kg",
            price=Decimal("100.00"),
            is_weighted=True,
            warranty_override="POLICY",
            warranty_policy_id=policy.id,
        )
        db_session.add(prod)
        db_session.commit()

        # Weighted products never receive warranty coverage
        assert WarrantyService.resolve_policy(prod, session=db_session) is None

        # Setting warranty on weighted product raises ValueError
        user = _create_user_with_permissions(db_session, "user_weighted", [Permissions.WARRANTY_EDIT])
        with pytest.raises(ValueError, match="Weighted products cannot receive a warranty policy"):
            WarrantyService.set_product_warranty(
                prod.id, override="POLICY", policy_id=policy.id, acting_user_id=user.id, session=db_session
            )

    def test_issue_821_deactivated_policy_remains_on_assigned_products(self, db_session):
        policy = WarrantyPolicy(
            name="Legacy 3 Year Warranty",
            warranty_type="SHOP",
            duration=3,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            is_active=False,  # Deactivated policy
        )
        cat_policy = WarrantyPolicy(
            name="Active Category 1 Year",
            warranty_type="SHOP",
            duration=1,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            is_active=True,
        )
        db_session.add_all([policy, cat_policy])
        db_session.flush()

        cat = Category(name="Laptops", default_warranty_policy_id=cat_policy.id)
        db_session.add(cat)
        db_session.flush()

        prod = Product(
            barcode="PROD_LEGACY",
            name_en="Older Laptop",
            price=Decimal("100.00"),
            category_id=cat.id,
            warranty_override="POLICY",
            warranty_policy_id=policy.id,
        )
        db_session.add(prod)
        db_session.commit()

        # Deactivated policy still resolves on the product that already holds it
        resolved = WarrantyService.resolve_policy(prod, session=db_session)
        assert resolved is not None
        assert resolved.id == policy.id
        assert resolved.is_active is False


class TestWarrantyFeatureGating:
    """Feature is off by default; fresh DB with only inactive templates stays hidden."""

    def test_issue_821_feature_gating_fresh_db_hidden(self, db_session):
        # Simulate fresh DB: Config is unset or False, 4 inactive templates exist
        ConfigService.set("warranty_enabled", False)
        templates = [
            WarrantyPolicy(
                name="7 days shop replacement",
                warranty_type="SHOP",
                duration=7,
                duration_unit="DAYS",
                remedy="REPLACE_ONLY",
                is_active=False,
                is_template=True,
            ),
            WarrantyPolicy(
                name="6 months shop warranty",
                warranty_type="SHOP",
                duration=6,
                duration_unit="MONTHS",
                remedy="REPAIR_OR_REPLACE",
                is_active=False,
                is_template=True,
            ),
            WarrantyPolicy(
                name="1 year shop warranty",
                warranty_type="SHOP",
                duration=1,
                duration_unit="YEARS",
                remedy="REPAIR_OR_REPLACE",
                is_active=False,
                is_template=True,
            ),
            WarrantyPolicy(
                name="1 year manufacturer warranty",
                warranty_type="MANUFACTURER",
                duration=1,
                duration_unit="YEARS",
                remedy="REPAIR_OR_REPLACE",
                is_active=False,
                is_template=True,
            ),
        ]
        db_session.add_all(templates)
        db_session.commit()

        assert WarrantyService.is_enabled(session=db_session) is False

    def test_issue_821_feature_gating_active_or_user_policy_enables(self, db_session):
        ConfigService.set("warranty_enabled", False)

        # 1. User-created policy (is_template=False) enables feature
        user_policy = WarrantyPolicy(
            name="Custom Electronics Warranty",
            warranty_type="SHOP",
            duration=12,
            duration_unit="MONTHS",
            remedy="REPAIR_OR_REPLACE",
            is_active=True,
            is_template=False,
        )
        db_session.add(user_policy)
        db_session.commit()

        assert WarrantyService.is_enabled(session=db_session) is True

    def test_issue_821_feature_gating_config_toggle_enables(self, db_session):
        ConfigService.set("warranty_enabled", True)
        assert WarrantyService.is_enabled(session=db_session) is True


class TestWarrantyPermissionsAndAudit:
    """Service-level permission enforcement and atomic audit logging."""

    def test_issue_821_create_policy_permissions_and_audit(self, db_session):
        admin = _create_user_with_permissions(
            db_session, "admin_user", [Permissions.WARRANTY_VIEW, Permissions.WARRANTY_MANAGE_POLICIES]
        )
        cashier = _create_user_with_permissions(db_session, "cashier_user", [Permissions.WARRANTY_VIEW])

        policy_data = {
            "name": "1 Year Gold Warranty",
            "name_si": "වසර 1ක රන් වගකීම",
            "name_ta": "1 வருட தங்க உத்தரவாதம்",
            "warranty_type": "SHOP",
            "duration": 1,
            "duration_unit": "YEARS",
            "remedy": "REPAIR_OR_REPLACE",
            "provider_name": "Ceylon Byte",
            "terms_text": "Valid with original invoice.",
            "terms_text_si": "මුල් ඉන්වොයිසිය සමඟ වලංගු වේ.",
            "exclusions_text": "Physical damage not covered.",
            "supplier_cover_months": 12,
        }

        # Cashier lacking warranty.manage_policies is rejected
        with pytest.raises(PermissionError, match=r"warranty\.manage_policies"):
            WarrantyService.create_policy(policy_data, acting_user_id=cashier.id, session=db_session)

        # Admin succeeds
        policy = WarrantyService.create_policy(policy_data, acting_user_id=admin.id, session=db_session)
        assert policy.id is not None
        assert policy.name == "1 Year Gold Warranty"

        # Verify audit log was recorded in the same transaction
        audit = (
            db_session.execute(
                select(AuditLog).where(AuditLog.event_type == WARRANTY_EVENT).where(AuditLog.action == "CREATE_POLICY")
            )
            .scalars()
            .first()
        )
        assert audit is not None
        assert audit.user_id == admin.id
        import json

        details = json.loads(audit.details) if isinstance(audit.details, str) else audit.details
        assert details["name"] == "1 Year Gold Warranty"

    def test_issue_821_update_and_deactivate_policy(self, db_session):
        admin = _create_user_with_permissions(db_session, "admin_pol", [Permissions.WARRANTY_MANAGE_POLICIES])
        policy_data = {
            "name": "Initial Policy",
            "warranty_type": "SHOP",
            "duration": 6,
            "duration_unit": "MONTHS",
            "remedy": "REPAIR_ONLY",
        }
        policy = WarrantyService.create_policy(policy_data, acting_user_id=admin.id, session=db_session)

        # Update
        updated = WarrantyService.update_policy(
            policy.id, {"duration": 9, "remedy": "REPAIR_OR_REPLACE"}, acting_user_id=admin.id, session=db_session
        )
        assert updated.duration == 9
        assert updated.remedy == "REPAIR_OR_REPLACE"

        # Deactivate
        deactivated = WarrantyService.deactivate_policy(policy.id, acting_user_id=admin.id, session=db_session)
        assert deactivated.is_active is False

        # Reactivate
        reactivated = WarrantyService.activate_policy(policy.id, acting_user_id=admin.id, session=db_session)
        assert reactivated.is_active is True

    def test_issue_821_policy_validation_rules(self, db_session):
        admin = _create_user_with_permissions(db_session, "admin_val", [Permissions.WARRANTY_MANAGE_POLICIES])

        # Missing English name
        with pytest.raises(ValueError, match="English name is required"):
            WarrantyService.create_policy(
                {"name": "", "warranty_type": "SHOP", "duration": 1, "duration_unit": "YEARS", "remedy": "REFUND"},
                acting_user_id=admin.id,
                session=db_session,
            )

        # Duration <= 0
        with pytest.raises(ValueError, match="duration must be positive"):
            WarrantyService.create_policy(
                {
                    "name": "Valid Name",
                    "warranty_type": "SHOP",
                    "duration": 0,
                    "duration_unit": "YEARS",
                    "remedy": "REFUND",
                },
                acting_user_id=admin.id,
                session=db_session,
            )

        # Translated terms provided without English terms
        with pytest.raises(ValueError, match="English terms must be provided"):
            WarrantyService.create_policy(
                {
                    "name": "Terms Test",
                    "warranty_type": "SHOP",
                    "duration": 1,
                    "duration_unit": "YEARS",
                    "remedy": "REFUND",
                    "terms_text": "",
                    "terms_text_si": "සිංහල කොන්දේසි",
                },
                acting_user_id=admin.id,
                session=db_session,
            )

    def test_issue_821_failure_injection_atomic_rollback(self, db_session):
        """Rule 4: failure injection proves complete transaction rollback on failure."""
        admin = _create_user_with_permissions(db_session, "admin_fail", [Permissions.WARRANTY_MANAGE_POLICIES])
        policy_data = {
            "name": "Rollback Test Policy",
            "warranty_type": "SHOP",
            "duration": 6,
            "duration_unit": "MONTHS",
            "remedy": "REPAIR_ONLY",
        }

        # Simulate exception during audit log flush
        with patch.object(AuditLog, "__init__", side_effect=RuntimeError("Injected Audit Error")):
            with pytest.raises(RuntimeError, match="Injected Audit Error"):
                WarrantyService.create_policy(policy_data, acting_user_id=admin.id, session=db_session)

        # Verify no policy was committed
        policy = (
            db_session.execute(select(WarrantyPolicy).where(WarrantyPolicy.name == "Rollback Test Policy"))
            .scalars()
            .first()
        )
        assert policy is None

    def test_issue_821_till_read_only_protection(self, db_session):
        admin = _create_user_with_permissions(db_session, "admin_till", [Permissions.WARRANTY_MANAGE_POLICIES])
        ConfigService.set("terminal_mode", "terminal")
        try:
            with pytest.raises(CatalogReadOnlyError):
                WarrantyService.create_policy(
                    {
                        "name": "Till Fail",
                        "warranty_type": "SHOP",
                        "duration": 1,
                        "duration_unit": "YEARS",
                        "remedy": "REFUND",
                    },
                    acting_user_id=admin.id,
                    session=db_session,
                )
        finally:
            ConfigService.set("terminal_mode", "standalone")

    def test_issue_821_unauthenticated_mutation_fails_closed(self, db_session):
        """Unauthenticated mutations without acting_user_id or current user fail closed with PermissionError."""
        # Ensure no logged in user
        with patch.object(AuthService, "get_current_user", return_value=None):
            with pytest.raises(PermissionError, match=r"warranty\.manage_policies"):
                WarrantyService.create_policy(
                    {
                        "name": "Unauth Policy",
                        "warranty_type": "SHOP",
                        "duration": 1,
                        "duration_unit": "YEARS",
                        "remedy": "REFUND",
                    },
                    acting_user_id=None,
                    session=db_session,
                )

            with pytest.raises(PermissionError, match=r"warranty\.manage_policies"):
                WarrantyService.update_policy(1, {"duration": 2}, acting_user_id=None, session=db_session)

            with pytest.raises(PermissionError, match=r"warranty\.manage_policies"):
                WarrantyService.deactivate_policy(1, acting_user_id=None, session=db_session)

            with pytest.raises(PermissionError, match=r"warranty\.manage_policies"):
                WarrantyService.activate_policy(1, acting_user_id=None, session=db_session)

            with pytest.raises(PermissionError, match=r"warranty\.edit"):
                WarrantyService.set_product_warranty(1, "NONE", acting_user_id=None, session=db_session)

            with pytest.raises(PermissionError, match=r"warranty\.edit"):
                WarrantyService.set_category_default_warranty(1, None, acting_user_id=None, session=db_session)

    def test_issue_821_current_user_fallback_writes_id_to_audit_log(self, db_session):
        """When acting_user_id is None, AuthService.get_current_user() is used and its ID written to AuditLog."""
        admin = _create_user_with_permissions(db_session, "admin_audit", [Permissions.WARRANTY_MANAGE_POLICIES])

        with patch.object(AuthService, "get_current_user", return_value=admin):
            policy = WarrantyService.create_policy(
                {
                    "name": "Audit Fallback Policy",
                    "warranty_type": "SHOP",
                    "duration": 6,
                    "duration_unit": "MONTHS",
                    "remedy": "REPAIR_OR_REPLACE",
                },
                acting_user_id=None,
                session=db_session,
            )
            assert policy.id is not None

            audit = (
                db_session.execute(
                    select(AuditLog)
                    .where(AuditLog.event_type == WARRANTY_EVENT, AuditLog.action == "CREATE_POLICY")
                    .order_by(AuditLog.id.desc())
                )
                .scalars()
                .first()
            )
            assert audit is not None
            assert audit.user_id == admin.id
            assert audit.user_id is not None

    def test_issue_821_new_assignment_to_inactive_policy_rejected(self, db_session):
        """Assigning an inactive policy as a new assignment raises ValueError."""
        admin = _create_user_with_permissions(
            db_session, "admin_assign", [Permissions.WARRANTY_EDIT, Permissions.WARRANTY_MANAGE_POLICIES]
        )
        policy = WarrantyPolicy(
            name="Inactive Policy",
            warranty_type="SHOP",
            duration=1,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            is_active=False,
        )
        cat = Category(name="Cat Inactive Test")
        prod = Product(
            barcode="INACT-PROD-01",
            name_en="Prod Inactive Test",
            price=Decimal("100.00"),
            stock_qty=Decimal("5"),
        )
        db_session.add_all([policy, cat, prod])
        db_session.commit()

        # Direct service assignment must reject inactive policy
        with pytest.raises(ValueError, match="Cannot assign inactive warranty policy"):
            WarrantyService.set_product_warranty(
                prod.id, override="POLICY", policy_id=policy.id, acting_user_id=admin.id, session=db_session
            )

        with pytest.raises(ValueError, match="Cannot assign inactive warranty policy"):
            WarrantyService.set_category_default_warranty(
                cat.id, policy_id=policy.id, acting_user_id=admin.id, session=db_session
            )

    def test_issue_821_supplier_cover_months_validation(self, db_session):
        """Supplier cover months cannot be negative."""
        admin = _create_user_with_permissions(db_session, "admin_cover", [Permissions.WARRANTY_MANAGE_POLICIES])

        with pytest.raises(ValueError, match="supplier_cover_months cannot be negative"):
            WarrantyService.create_policy(
                {
                    "name": "Negative Cover Policy",
                    "warranty_type": "SHOP",
                    "duration": 1,
                    "duration_unit": "YEARS",
                    "remedy": "REFUND",
                    "supplier_cover_months": -1,
                },
                acting_user_id=admin.id,
                session=db_session,
            )

    def test_issue_821_inactive_custom_policy_keeps_feature_accessible(self, db_session):
        """An inactive custom policy keeps the warranty feature accessible so merchant can reactivate it."""
        ConfigService.set("warranty_enabled", False)
        # Clear any active policies
        db_session.query(WarrantyPolicy).delete()
        db_session.commit()

        # Seed custom inactive policy
        custom_inactive = WarrantyPolicy(
            name="Custom Inactive Policy",
            warranty_type="SHOP",
            duration=1,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            is_active=False,
            is_template=False,
        )
        db_session.add(custom_inactive)
        db_session.commit()

        assert WarrantyService.is_enabled(session=db_session) is True

    def test_issue_821_model_localized_accessors_fallback(self):
        """WarrantyPolicy localized accessors fall back to English and handle unexpected languages safely."""
        policy = WarrantyPolicy(
            name="1 Year Shop",
            name_si="වසර 1 සාප්පු වගකීම",
            name_ta=None,
            warranty_type="SHOP",
            duration=1,
            duration_unit="YEARS",
            remedy="REPAIR_OR_REPLACE",
            terms_text="English terms",
            terms_text_si=None,
            terms_text_ta="Tamil terms",
            exclusions_text="English exclusions",
        )

        assert policy.get_display_name("en") == "1 Year Shop"
        assert policy.get_display_name("si") == "වසර 1 සාප්පු වගකීම"
        assert policy.get_display_name("ta") == "1 Year Shop"  # Fallback to EN

        assert policy.get_terms("en") == "English terms"
        assert policy.get_terms("si") == "English terms"  # Fallback to EN
        assert policy.get_terms("ta") == "Tamil terms"

        assert policy.get_exclusions("en") == "English exclusions"
        assert policy.get_exclusions("si") == "English exclusions"
        assert policy.get_exclusions("ta") == "English exclusions"
