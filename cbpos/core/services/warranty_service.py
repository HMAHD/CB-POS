"""Warranty Service owning policy management, resolution precedence,
feature gating, permissions, audit trails, and calendar-aware end-date calculations.
"""

import json
import logging
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import (
    AuditLog,
    Category,
    Product,
    Role,
    User,
    WarrantyPolicy,
)
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.utils.terminal_guard import require_catalog_writable

logger = logging.getLogger(__name__)

VALID_DURATION_UNITS = ("DAYS", "MONTHS", "YEARS")
VALID_WARRANTY_TYPES = ("SHOP", "MANUFACTURER", "EXTENDED")
VALID_REMEDIES = ("REPAIR_OR_REPLACE", "REPAIR_ONLY", "REPLACE_ONLY", "REFUND")
VALID_OVERRIDES = ("INHERIT", "NONE", "POLICY")


@contextmanager
def _session_scope(session: Session | None):
    """Context manager yielding the provided session or creating and committing a new one."""
    if session is not None:
        with session.begin_nested():
            yield session
    else:
        db = Database()
        with db.get_session() as s:
            yield s
            s.commit()


def _require_permission(session: Session, perm_code: str, acting_user_id: int | None = None) -> None:
    """Check that the acting user (or current session user) holds the required permission."""
    user_id = acting_user_id
    if user_id is None:
        curr = AuthService.get_current_user()
        if curr:
            user_id = curr.id

    if user_id is not None:
        user = session.get(User, user_id, options=[joinedload(User.role).joinedload(Role.permissions)])
        if not user or not PermissionService.user_has_permission(user, perm_code):
            raise PermissionError(f"Permission denied: {perm_code} required")


class WarrantyService:
    """Service owning warranty policy CRUD, resolution, and calendar arithmetic."""

    @classmethod
    def is_enabled(cls, session: Session | None = None) -> bool:
        """Return True if warranty functionality is enabled via config or active/user policies."""
        cfg = ConfigService.get("warranty_enabled")
        if cfg is True or str(cfg).lower() in ("true", "1", "yes"):
            return True

        def _check(s: Session) -> bool:
            stmt = (
                select(WarrantyPolicy.id)
                .where((WarrantyPolicy.is_active == True) | (WarrantyPolicy.is_template == False))  # noqa: E712
                .limit(1)
            )
            return s.scalar(stmt) is not None

        if session is not None:
            return _check(session)
        db = Database()
        with db.get_session() as s:
            return _check(s)

    @classmethod
    def compute_end_date(cls, start_date: date, duration: int, unit: str) -> date:
        """Compute inclusive coverage end date: start + duration - 1 day."""
        if duration <= 0:
            raise ValueError("duration must be positive")

        unit_clean = (unit or "").strip().upper()
        if unit_clean not in VALID_DURATION_UNITS:
            raise ValueError(f"Invalid duration unit: {unit}")

        if unit_clean == "DAYS":
            delta = relativedelta(days=duration)
        elif unit_clean == "MONTHS":
            delta = relativedelta(months=duration)
        elif unit_clean == "YEARS":
            delta = relativedelta(years=duration)
        else:
            raise ValueError(f"Invalid duration unit: {unit}")

        return start_date + delta - timedelta(days=1)

    @classmethod
    def resolve_policy(
        cls,
        product: Product | int,
        session: Session | None = None,
    ) -> WarrantyPolicy | None:
        """Resolve effective warranty policy for a product following the precedence chain:
        Product explicit POLICY > Category default > Parent Category default > None.
        Explicit NONE blocks category inheritance.
        Weighted products never receive warranty coverage.
        """
        with _session_scope(session) as s:
            if isinstance(product, int):
                prod = s.get(Product, product)
                if not prod:
                    return None
            else:
                prod = product
                # If attached to a different session or detached, refresh/get from current session
                if prod.id and prod not in s:
                    fetched = s.get(Product, prod.id)
                    if fetched:
                        prod = fetched

            if prod.is_weighted:
                return None

            override = prod.warranty_override or "INHERIT"

            if override == "NONE":
                return None

            if override == "POLICY":
                if prod.warranty_policy_id:
                    return s.get(WarrantyPolicy, prod.warranty_policy_id)
                return None

            # override == "INHERIT"
            current_category_id = prod.category_id
            visited = set()
            while current_category_id and current_category_id not in visited:
                visited.add(current_category_id)
                cat = s.get(Category, current_category_id)
                if not cat:
                    break
                if cat.default_warranty_policy_id:
                    policy = s.get(WarrantyPolicy, cat.default_warranty_policy_id)
                    if policy and policy.is_active:
                        return policy
                current_category_id = cat.parent_id

            return None

    @classmethod
    def list_policies(
        cls,
        include_inactive: bool = False,
        session: Session | None = None,
    ) -> list[WarrantyPolicy]:
        """List warranty policies ordered by name."""
        with _session_scope(session) as s:
            stmt = select(WarrantyPolicy)
            if not include_inactive:
                stmt = stmt.where(WarrantyPolicy.is_active == True)  # noqa: E712
            stmt = stmt.order_by(WarrantyPolicy.name)
            policies = list(s.scalars(stmt).all())
            if session is None:
                for p in policies:
                    s.expunge(p)
            return policies

    @classmethod
    def get_policy(cls, policy_id: int, session: Session | None = None) -> WarrantyPolicy | None:
        """Get a warranty policy by ID."""
        with _session_scope(session) as s:
            policy = s.get(WarrantyPolicy, policy_id)
            if policy and session is None:
                s.expunge(policy)
            return policy

    @classmethod
    def create_policy(
        cls,
        data: dict[str, Any],
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> WarrantyPolicy:
        """Create a new warranty policy with validation, permissions and audit logging."""
        require_catalog_writable()

        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("English name is required")

        warranty_type = (data.get("warranty_type") or "").strip().upper()
        if warranty_type not in VALID_WARRANTY_TYPES:
            raise ValueError(f"Invalid warranty type: {warranty_type}")

        duration = data.get("duration")
        if not isinstance(duration, int) or duration <= 0:
            raise ValueError("duration must be positive")

        duration_unit = (data.get("duration_unit") or "").strip().upper()
        if duration_unit not in VALID_DURATION_UNITS:
            raise ValueError(f"Invalid duration unit: {duration_unit}")

        remedy = (data.get("remedy") or "").strip().upper()
        if remedy not in VALID_REMEDIES:
            raise ValueError(f"Invalid remedy: {remedy}")

        terms_text = (data.get("terms_text") or "").strip()
        terms_text_si = (data.get("terms_text_si") or "").strip()
        terms_text_ta = (data.get("terms_text_ta") or "").strip()
        if (terms_text_si or terms_text_ta) and not terms_text:
            raise ValueError("English terms must be provided when translations are present")

        exclusions_text = (data.get("exclusions_text") or "").strip()
        exclusions_text_si = (data.get("exclusions_text_si") or "").strip()
        exclusions_text_ta = (data.get("exclusions_text_ta") or "").strip()
        if (exclusions_text_si or exclusions_text_ta) and not exclusions_text:
            raise ValueError("English exclusions must be provided when translations are present")

        supplier_cover_months = int(data.get("supplier_cover_months") or 0)

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_MANAGE_POLICIES, acting_user_id)

            policy = WarrantyPolicy(
                name=name,
                name_si=(data.get("name_si") or "").strip() or None,
                name_ta=(data.get("name_ta") or "").strip() or None,
                warranty_type=warranty_type,
                duration=duration,
                duration_unit=duration_unit,
                remedy=remedy,
                provider_name=(data.get("provider_name") or "").strip() or None,
                terms_text=terms_text or None,
                terms_text_si=terms_text_si or None,
                terms_text_ta=terms_text_ta or None,
                exclusions_text=exclusions_text or None,
                exclusions_text_si=exclusions_text_si or None,
                exclusions_text_ta=exclusions_text_ta or None,
                supplier_cover_months=supplier_cover_months,
                is_active=bool(data.get("is_active", True)),
                is_template=bool(data.get("is_template", False)),
            )
            s.add(policy)
            s.flush()

            audit = AuditLog(
                user_id=acting_user_id,
                action="CREATE_POLICY",
                event_type=WARRANTY_EVENT,
                details=json.dumps(
                    {
                        "id": policy.id,
                        "name": policy.name,
                        "warranty_type": policy.warranty_type,
                        "duration": policy.duration,
                        "duration_unit": policy.duration_unit,
                        "remedy": policy.remedy,
                    }
                ),
            )
            s.add(audit)
            s.flush()
            return policy

    @classmethod
    def update_policy(
        cls,
        policy_id: int,
        data: dict[str, Any],
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> WarrantyPolicy:
        """Update an existing warranty policy with validation, permissions and audit logging."""
        require_catalog_writable()

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_MANAGE_POLICIES, acting_user_id)

            policy = s.get(WarrantyPolicy, policy_id)
            if not policy:
                raise ValueError(f"Policy {policy_id} not found")

            changes: dict[str, Any] = {}

            if "name" in data:
                name = (data["name"] or "").strip()
                if not name:
                    raise ValueError("English name is required")
                changes["name"] = {"old": policy.name, "new": name}
                policy.name = name

            if "name_si" in data:
                val = (data["name_si"] or "").strip() or None
                changes["name_si"] = {"old": policy.name_si, "new": val}
                policy.name_si = val

            if "name_ta" in data:
                val = (data["name_ta"] or "").strip() or None
                changes["name_ta"] = {"old": policy.name_ta, "new": val}
                policy.name_ta = val

            if "warranty_type" in data:
                wt = (data["warranty_type"] or "").strip().upper()
                if wt not in VALID_WARRANTY_TYPES:
                    raise ValueError(f"Invalid warranty type: {wt}")
                changes["warranty_type"] = {"old": policy.warranty_type, "new": wt}
                policy.warranty_type = wt

            if "duration" in data:
                dur = data["duration"]
                if not isinstance(dur, int) or dur <= 0:
                    raise ValueError("duration must be positive")
                changes["duration"] = {"old": policy.duration, "new": dur}
                policy.duration = dur

            if "duration_unit" in data:
                du = (data["duration_unit"] or "").strip().upper()
                if du not in VALID_DURATION_UNITS:
                    raise ValueError(f"Invalid duration unit: {du}")
                changes["duration_unit"] = {"old": policy.duration_unit, "new": du}
                policy.duration_unit = du

            if "remedy" in data:
                rem = (data["remedy"] or "").strip().upper()
                if rem not in VALID_REMEDIES:
                    raise ValueError(f"Invalid remedy: {rem}")
                changes["remedy"] = {"old": policy.remedy, "new": rem}
                policy.remedy = rem

            if "provider_name" in data:
                prov = (data["provider_name"] or "").strip() or None
                changes["provider_name"] = {"old": policy.provider_name, "new": prov}
                policy.provider_name = prov

            if "terms_text" in data or "terms_text_si" in data or "terms_text_ta" in data:
                terms_en = (data.get("terms_text", policy.terms_text) or "").strip()
                terms_si = (data.get("terms_text_si", policy.terms_text_si) or "").strip()
                terms_ta = (data.get("terms_text_ta", policy.terms_text_ta) or "").strip()
                if (terms_si or terms_ta) and not terms_en:
                    raise ValueError("English terms must be provided when translations are present")
                policy.terms_text = terms_en or None
                policy.terms_text_si = terms_si or None
                policy.terms_text_ta = terms_ta or None
                changes["terms_updated"] = True

            if "exclusions_text" in data or "exclusions_text_si" in data or "exclusions_text_ta" in data:
                excl_en = (data.get("exclusions_text", policy.exclusions_text) or "").strip()
                excl_si = (data.get("exclusions_text_si", policy.exclusions_text_si) or "").strip()
                excl_ta = (data.get("exclusions_text_ta", policy.exclusions_text_ta) or "").strip()
                if (excl_si or excl_ta) and not excl_en:
                    raise ValueError("English exclusions must be provided when translations are present")
                policy.exclusions_text = excl_en or None
                policy.exclusions_text_si = excl_si or None
                policy.exclusions_text_ta = excl_ta or None
                changes["exclusions_updated"] = True

            if "supplier_cover_months" in data:
                scm = int(data["supplier_cover_months"] or 0)
                changes["supplier_cover_months"] = {"old": policy.supplier_cover_months, "new": scm}
                policy.supplier_cover_months = scm

            if "is_active" in data:
                act = bool(data["is_active"])
                changes["is_active"] = {"old": policy.is_active, "new": act}
                policy.is_active = act

            s.flush()

            audit = AuditLog(
                user_id=acting_user_id,
                action="UPDATE_POLICY",
                event_type=WARRANTY_EVENT,
                details=json.dumps({"id": policy.id, "changes": changes}),
            )
            s.add(audit)
            s.flush()
            return policy

    @classmethod
    def deactivate_policy(
        cls,
        policy_id: int,
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> WarrantyPolicy:
        """Deactivate a warranty policy (soft deactivation)."""
        require_catalog_writable()

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_MANAGE_POLICIES, acting_user_id)

            policy = s.get(WarrantyPolicy, policy_id)
            if not policy:
                raise ValueError(f"Policy {policy_id} not found")

            policy.is_active = False
            s.flush()

            audit = AuditLog(
                user_id=acting_user_id,
                action="DEACTIVATE_POLICY",
                event_type=WARRANTY_EVENT,
                details=json.dumps({"id": policy.id, "name": policy.name}),
            )
            s.add(audit)
            s.flush()
            return policy

    @classmethod
    def activate_policy(
        cls,
        policy_id: int,
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> WarrantyPolicy:
        """Re-activate a previously deactivated warranty policy."""
        require_catalog_writable()

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_MANAGE_POLICIES, acting_user_id)

            policy = s.get(WarrantyPolicy, policy_id)
            if not policy:
                raise ValueError(f"Policy {policy_id} not found")

            policy.is_active = True
            s.flush()

            audit = AuditLog(
                user_id=acting_user_id,
                action="ACTIVATE_POLICY",
                event_type=WARRANTY_EVENT,
                details=json.dumps({"id": policy.id, "name": policy.name}),
            )
            s.add(audit)
            s.flush()
            return policy

    @classmethod
    def set_product_warranty(
        cls,
        product_id: int,
        override: str,  # 'INHERIT' | 'NONE' | 'POLICY'
        policy_id: int | None = None,
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> Product:
        """Set product warranty assignment. Rejects weighted products."""
        require_catalog_writable()

        clean_override = (override or "INHERIT").strip().upper()
        if clean_override not in VALID_OVERRIDES:
            raise ValueError(f"Invalid warranty override: {override}")

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_EDIT, acting_user_id)

            prod = s.get(Product, product_id)
            if not prod:
                raise ValueError(f"Product {product_id} not found")

            if prod.is_weighted:
                raise ValueError("Weighted products cannot receive a warranty policy")

            if clean_override == "POLICY":
                if not policy_id:
                    raise ValueError("policy_id required when override is POLICY")
                policy = s.get(WarrantyPolicy, policy_id)
                if not policy:
                    raise ValueError(f"Policy {policy_id} not found")
                prod.warranty_policy_id = policy_id
            else:
                prod.warranty_policy_id = None

            prod.warranty_override = clean_override
            s.flush()

            audit = AuditLog(
                user_id=acting_user_id,
                action="SET_PRODUCT_WARRANTY",
                event_type=WARRANTY_EVENT,
                details=json.dumps(
                    {
                        "product_id": prod.id,
                        "override": clean_override,
                        "policy_id": prod.warranty_policy_id,
                    }
                ),
            )
            s.add(audit)
            s.flush()
            return prod

    @classmethod
    def set_category_default_warranty(
        cls,
        category_id: int,
        policy_id: int | None = None,
        acting_user_id: int | None = None,
        session: Session | None = None,
    ) -> Category:
        """Set category default warranty policy."""
        require_catalog_writable()

        with _session_scope(session) as s:
            _require_permission(s, Permissions.WARRANTY_EDIT, acting_user_id)

            cat = s.get(Category, category_id)
            if not cat:
                raise ValueError(f"Category {category_id} not found")

            if policy_id is not None:
                policy = s.get(WarrantyPolicy, policy_id)
                if not policy:
                    raise ValueError(f"Policy {policy_id} not found")

            cat.default_warranty_policy_id = policy_id
            s.flush()

            audit = AuditLog(
                user_id=acting_user_id,
                action="SET_CATEGORY_WARRANTY",
                event_type=WARRANTY_EVENT,
                details=json.dumps({"category_id": cat.id, "default_policy_id": policy_id}),
            )
            s.add(audit)
            s.flush()
            return cat
