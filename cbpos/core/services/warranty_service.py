"""Warranty Service owning policy management, resolution precedence,
feature gating, permissions, audit trails, and calendar-aware end-date calculations.
"""

import json
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import (
    AuditLog,
    Category,
    Product,
    Role,
    Sale,
    SaleItem,
    User,
    Warranty,
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


def _require_permission(session: Session, perm_code: str, acting_user_id: int | None = None) -> int:
    """Check that the acting user (or current session user) holds the required permission fail-closed."""
    return WarrantyService._resolve_actor(acting_user_id, perm_code, session=session)


class WarrantyService:
    """Service owning warranty policy CRUD, resolution, and calendar arithmetic."""

    @staticmethod
    def _resolve_actor(acting_user_id: int | None, perm_code: str, session: Session | None = None) -> int:
        """Resolve acting user and verify permission fail-closed. Never skips check."""
        user_id = acting_user_id
        if user_id is None:
            curr = AuthService.get_current_user()
            if curr:
                user_id = curr.id

        if user_id is None:
            raise PermissionError(f"Permission denied: {perm_code} required (no authenticated actor)")

        if session is not None:
            user = session.get(User, user_id, options=[joinedload(User.role).joinedload(Role.permissions)])
            if not user or not PermissionService.user_has_permission(user, perm_code):
                raise PermissionError(f"Permission denied: {perm_code} required")
        else:
            db = Database()
            with db.get_session() as s:
                user = s.get(User, user_id, options=[joinedload(User.role).joinedload(Role.permissions)])
                if not user or not PermissionService.user_has_permission(user, perm_code):
                    raise PermissionError(f"Permission denied: {perm_code} required")
        return user_id

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
    def resolve_policies_for_products(
        cls,
        session: Session,
        product_ids: list[int],
    ) -> dict[int, WarrantyPolicy | None]:
        """Batched policy resolution for checkout (Decision D30).

        Runs at most 1-2 batched queries across all products.
        Enforces Decision D30:
        - Inactive policy on product (POLICY override) produces None without category fallthrough.
        - Inactive default policy on category produces None without parent category fallthrough.
        - Weighted products produce None.
        Returns dict mapping product_id -> WarrantyPolicy or None.
        """
        if not product_ids:
            return {}

        unique_ids = list(set(product_ids))
        products = session.query(Product).filter(Product.id.in_(unique_ids)).all()
        prod_map = {p.id: p for p in products}

        # Collect policies and categories needed
        direct_policy_ids = set()
        needed_category_ids = set()

        for p in products:
            if p.is_weighted:
                continue
            override = p.warranty_override or "INHERIT"
            if override == "NONE":
                continue
            if override == "POLICY" and p.warranty_policy_id:
                direct_policy_ids.add(p.warranty_policy_id)
            elif override == "INHERIT" and p.category_id:
                needed_category_ids.add(p.category_id)

        # Batch load category ancestors
        category_map: dict[int, Category] = {}
        while needed_category_ids:
            cats = session.query(Category).filter(Category.id.in_(list(needed_category_ids))).all()
            needed_category_ids = set()
            for c in cats:
                category_map[c.id] = c
                if c.default_warranty_policy_id:
                    direct_policy_ids.add(c.default_warranty_policy_id)
                elif c.parent_id and c.parent_id not in category_map:
                    needed_category_ids.add(c.parent_id)

        # Batch load all referenced policies
        policy_map: dict[int, WarrantyPolicy] = {}
        if direct_policy_ids:
            policies = session.query(WarrantyPolicy).filter(WarrantyPolicy.id.in_(list(direct_policy_ids))).all()
            policy_map = {pol.id: pol for pol in policies}

        result: dict[int, WarrantyPolicy | None] = {}
        for pid in unique_ids:
            p = prod_map.get(pid)
            if not p or p.is_weighted:
                result[pid] = None
                continue

            override = p.warranty_override or "INHERIT"
            if override == "NONE":
                result[pid] = None
                continue

            if override == "POLICY":
                pol = policy_map.get(p.warranty_policy_id) if p.warranty_policy_id else None
                # D30: Inactive policy produces None; never falls through
                result[pid] = pol if (pol and pol.is_active) else None
                continue

            # override == "INHERIT"
            curr_cat_id = p.category_id
            resolved_pol = None
            visited = set()
            while curr_cat_id and curr_cat_id not in visited:
                visited.add(curr_cat_id)
                cat = category_map.get(curr_cat_id)
                if not cat:
                    break
                if cat.default_warranty_policy_id:
                    cpol = policy_map.get(cat.default_warranty_policy_id)
                    # D30: If category has a policy, inspect is_active.
                    # If active: use it. If inactive: return None immediately (no parent fallthrough!)
                    resolved_pol = cpol if (cpol and cpol.is_active) else None
                    break
                curr_cat_id = cat.parent_id

            result[pid] = resolved_pol

        return result

    @classmethod
    def register_for_sale_in_session(
        cls,
        session: Session,
        sale: Sale,
        sale_items_with_policies: list[
            tuple[SaleItem, WarrantyPolicy] | tuple[SaleItem, WarrantyPolicy, list[str | None]]
        ],
        receipt_lang: str | None = None,
        item_serials: dict[int, list[str | None]] | None = None,
    ) -> list[Warranty]:
        """Create per-unit Warranty rows for sold lines in the current session.

        - Validates that qty is an exact integer.
        - Generates codes: <sale.document_number>-01..NN across all warranty units of the sale.
        - Sets unit_index per line (1..int(qty)).
        - Assigns serial_number per unit in order if provided.
        - Computes start_date = sale.date.date(), end_date = compute_end_date(...).
        - Snapshots terms/exclusions in receipt language (falling back to English).
        - Snapshots customer name and phone.
        - In-memory collection attachment on sale_item.warranties and sale.warranties.
        - Emits an atomic WARRANTY audit log entry.
        """
        if not sale_items_with_policies:
            return []

        # Resolve receipt language
        lang = receipt_lang
        if not lang:
            try:
                from cbpos.i18n import get_language

                lang = get_language()
            except Exception:
                lang = "en"
        lang = (lang or "en").lower()
        if lang not in ("en", "si", "ta"):
            lang = "en"

        customer_name = None
        customer_phone = None
        if sale.customer:
            customer_name = sale.customer.name
            customer_phone = sale.customer.phone

        start_date = sale.date.date() if sale.date else date.today()
        created_warranties = []
        global_seq = 0

        for entry in sale_items_with_policies:
            if len(entry) == 3:
                sale_item, policy, line_serials = entry
            else:
                sale_item, policy = entry
                line_serials = None

            if line_serials is None and item_serials and sale_item.id in item_serials:
                line_serials = item_serials[sale_item.id]
            if line_serials is None:
                line_serials = getattr(sale_item, "_serials", None) or getattr(sale_item, "serials", None) or []

            qty = sale_item.qty
            if qty <= Decimal("0") or qty % Decimal("1") != Decimal("0"):
                from cbpos.i18n import _t

                raise ValueError(
                    _t("errors.warranty_whole_units", default="Warranty items must be sold in whole units")
                )

            unit_count = int(qty)
            end_date = cls.compute_end_date(start_date, policy.duration, policy.duration_unit)

            # Snapshots in receipt language
            terms_snapshot = policy.get_terms(lang)
            exclusions_snapshot = policy.get_exclusions(lang)

            line_warranties = []
            for unit_idx in range(1, unit_count + 1):
                global_seq += 1
                code = f"{sale.document_number}-{global_seq:02d}"

                sn = None
                if line_serials and unit_idx <= len(line_serials):
                    raw_sn = line_serials[unit_idx - 1]
                    if raw_sn and str(raw_sn).strip():
                        sn = str(raw_sn).strip().upper()

                warranty = Warranty(
                    code=code,
                    unit_index=unit_idx,
                    sale_id=sale.id,
                    sale_item_id=sale_item.id,
                    product_id=sale_item.product_id,
                    customer_id=sale.customer_id,
                    policy_id=policy.id,
                    customer_name_snapshot=customer_name,
                    customer_phone_snapshot=customer_phone,
                    serial_number=sn,
                    warranty_type=policy.warranty_type,
                    duration=policy.duration,
                    duration_unit=policy.duration_unit,
                    remedy=policy.remedy,
                    provider_name=policy.provider_name,
                    terms_text=terms_snapshot,
                    exclusions_text=exclusions_snapshot,
                    lang=lang,
                    start_date=start_date,
                    end_date=end_date,
                    status="ACTIVE",
                    terminal_id=sale.terminal_id,
                    synced=False,
                )
                session.add(warranty)
                line_warranties.append(warranty)
                created_warranties.append(warranty)

            # In-memory attachment to avoid lazy query during receipt printing
            if hasattr(sale_item, "warranties"):
                if sale_item.warranties is None:
                    sale_item.warranties = []
                sale_item.warranties.extend(line_warranties)

        # In-memory attachment on sale as well
        if hasattr(sale, "warranties"):
            if sale.warranties is None:
                sale.warranties = []
            sale.warranties.extend(created_warranties)

        # Audit log
        user_id = sale.user_id
        session.add(
            AuditLog(
                user_id=user_id,
                action="REGISTER_WARRANTIES",
                event_type=WARRANTY_EVENT,
                details=f"Registered {len(created_warranties)} warranties for sale {sale.document_number} (ID {sale.id})",
            )
        )

        return created_warranties

    @classmethod
    def find_active_warranties_by_serials(
        cls,
        product_id: int,
        serials: list[str],
        session: Session | None = None,
    ) -> dict[str, str]:
        """Find active warranties for a product with matching serials.

        Returns mapping of {serial_number: sale_document_number} for advisory warnings.
        """
        clean_serials = [str(s).strip().upper() for s in serials if s and str(s).strip()]
        if not clean_serials:
            return {}

        with _session_scope(session) as s:
            stmt = (
                select(Warranty.serial_number, Sale.document_number)
                .join(Sale, Sale.id == Warranty.sale_id)
                .where(
                    Warranty.product_id == product_id,
                    Warranty.serial_number.in_(clean_serials),
                    Warranty.status == "ACTIVE",
                )
            )
            rows = s.execute(stmt).all()
            return {r[0]: (r[1] or str(r[0])) for r in rows if r[0]}

    @classmethod
    def void_sale_warranties_in_session(
        cls,
        session: Session,
        sale_id: int,
        actor_id: int,
    ) -> int:
        """Atomically transition all ACTIVE warranties for sale_id to VOID."""
        stmt = (
            select(Warranty)
            .where(
                Warranty.sale_id == sale_id,
                Warranty.status == "ACTIVE",
            )
            .with_for_update()
        )
        active_warranties = list(session.scalars(stmt).all())
        if not active_warranties:
            return 0

        now = datetime.now()
        for w in active_warranties:
            w.status = "VOID"
            w.last_modified = now

        session.add(
            AuditLog(
                user_id=actor_id,
                action="VOID_WARRANTIES",
                event_type=WARRANTY_EVENT,
                details=f"Voided {len(active_warranties)} warranties for sale ID {sale_id}",
            )
        )
        return len(active_warranties)

    @classmethod
    def cancel_units_for_refund_in_session(
        cls,
        session: Session,
        refund_sale: Sale,
        refund_lines: list[tuple[int, Decimal]],  # (sale_item_id, qty)
        actor_id: int,
    ) -> list[Warranty]:
        """Cancel ACTIVE warranties per refunded line item (highest unit_index first)."""
        cancelled_warranties = []
        now = datetime.now()

        for sale_item_id, qty in refund_lines:
            if qty <= Decimal("0"):
                continue

            # Check if this line item has any warranties at all
            total_warranties = session.scalar(
                select(func.count(Warranty.id)).where(Warranty.sale_item_id == sale_item_id)
            )
            if not total_warranties:
                # Non-warranty line item, cleanly skip
                continue

            if qty % Decimal("1") != Decimal("0"):
                from cbpos.i18n import _t

                raise ValueError(
                    _t("errors.warranty_whole_units", default="Warranty items must be sold in whole units")
                )

            units_to_cancel = int(qty)

            # Query active warranties with row locking, highest unit_index first
            stmt = (
                select(Warranty)
                .where(
                    Warranty.sale_item_id == sale_item_id,
                    Warranty.status == "ACTIVE",
                )
                .order_by(Warranty.unit_index.desc())
                .with_for_update()
            )
            active_units = list(session.scalars(stmt).all())

            if len(active_units) < units_to_cancel:
                raise ValueError(
                    f"insufficient_active_warranties: {len(active_units)} active warranties available for line {sale_item_id}, {units_to_cancel} requested"
                )

            for w in active_units[:units_to_cancel]:
                w.status = "CANCELLED"
                w.cancelled_by_sale_id = refund_sale.id
                w.last_modified = now
                cancelled_warranties.append(w)

        if cancelled_warranties:
            session.add(
                AuditLog(
                    user_id=actor_id,
                    action="CANCEL_WARRANTIES",
                    event_type=WARRANTY_EVENT,
                    details=f"Cancelled {len(cancelled_warranties)} warranties by refund sale {refund_sale.document_number} (ID {refund_sale.id})",
                )
            )

        return cancelled_warranties

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

        scm_raw = data.get("supplier_cover_months")
        if scm_raw is not None:
            supplier_cover_months = int(scm_raw)
            if supplier_cover_months < 0:
                raise ValueError("supplier_cover_months cannot be negative")
        else:
            supplier_cover_months = 0

        with _session_scope(session) as s:
            actor_id = _require_permission(s, Permissions.WARRANTY_MANAGE_POLICIES, acting_user_id)

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
                user_id=actor_id,
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
            actor_id = _require_permission(s, Permissions.WARRANTY_MANAGE_POLICIES, acting_user_id)

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
                if scm < 0:
                    raise ValueError("supplier_cover_months cannot be negative")
                changes["supplier_cover_months"] = {"old": policy.supplier_cover_months, "new": scm}
                policy.supplier_cover_months = scm

            if "is_active" in data:
                act = bool(data["is_active"])
                changes["is_active"] = {"old": policy.is_active, "new": act}
                policy.is_active = act

            s.flush()

            audit = AuditLog(
                user_id=actor_id,
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
            actor_id = _require_permission(s, Permissions.WARRANTY_MANAGE_POLICIES, acting_user_id)

            policy = s.get(WarrantyPolicy, policy_id)
            if not policy:
                raise ValueError(f"Policy {policy_id} not found")

            policy.is_active = False
            s.flush()

            audit = AuditLog(
                user_id=actor_id,
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
            actor_id = _require_permission(s, Permissions.WARRANTY_MANAGE_POLICIES, acting_user_id)

            policy = s.get(WarrantyPolicy, policy_id)
            if not policy:
                raise ValueError(f"Policy {policy_id} not found")

            policy.is_active = True
            s.flush()

            audit = AuditLog(
                user_id=actor_id,
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
            actor_id = _require_permission(s, Permissions.WARRANTY_EDIT, acting_user_id)

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
                if policy_id != prod.warranty_policy_id and not policy.is_active:
                    raise ValueError("Cannot assign inactive warranty policy")
                prod.warranty_policy_id = policy_id
            else:
                prod.warranty_policy_id = None

            prod.warranty_override = clean_override
            s.flush()

            audit = AuditLog(
                user_id=actor_id,
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
            actor_id = _require_permission(s, Permissions.WARRANTY_EDIT, acting_user_id)

            cat = s.get(Category, category_id)
            if not cat:
                raise ValueError(f"Category {category_id} not found")

            if policy_id is not None:
                policy = s.get(WarrantyPolicy, policy_id)
                if not policy:
                    raise ValueError(f"Policy {policy_id} not found")
                if policy_id != cat.default_warranty_policy_id and not policy.is_active:
                    raise ValueError("Cannot assign inactive warranty policy")

            cat.default_warranty_policy_id = policy_id
            s.flush()

            audit = AuditLog(
                user_id=actor_id,
                action="SET_CATEGORY_WARRANTY",
                event_type=WARRANTY_EVENT,
                details=json.dumps({"category_id": cat.id, "default_policy_id": policy_id}),
            )
            s.add(audit)
            s.flush()
            return cat

    @classmethod
    def validate_warranty_assignment(
        cls,
        override: str,
        policy_id: int | None,
        is_weighted: bool = False,
        existing_policy_id: int | None = None,
        session: Session | None = None,
        serial_mode: str | None = None,
        category_id: int | None = None,
    ) -> None:
        """Validate product/category warranty assignment rules."""
        clean_override = (override or "INHERIT").strip().upper()
        if clean_override not in VALID_OVERRIDES:
            raise ValueError(f"Invalid warranty override: {override}")
        if is_weighted and (clean_override == "POLICY" or policy_id is not None):
            raise ValueError("Weighted products cannot have warranty policies")
        if clean_override == "POLICY" and policy_id is None:
            raise ValueError("Specific policy requires a warranty policy ID")
        if clean_override != "POLICY" and policy_id is not None:
            raise ValueError(f"Warranty policy ID cannot be set when override is {clean_override}")
        if policy_id is not None and policy_id != existing_policy_id:
            pol = session.get(WarrantyPolicy, policy_id) if session else cls.get_policy(policy_id)
            if not pol:
                raise ValueError(f"Warranty policy {policy_id} not found")
            if not pol.is_active:
                raise ValueError("Cannot assign inactive warranty policy")

        # Serial mode validation and policy coupling (#823)
        if serial_mode is not None:
            clean_serial = str(serial_mode).strip().upper()
            if clean_serial not in ("OFF", "OPTIONAL", "REQUIRED"):
                raise ValueError(f"Invalid serial mode: {serial_mode}")
            if is_weighted and clean_serial != "OFF":
                raise ValueError("Weighted products cannot have serial tracking")
            if clean_serial != "OFF":
                if clean_override == "NONE":
                    raise ValueError("Serial tracking requires an active warranty policy")
                elif clean_override == "POLICY":
                    if not policy_id:
                        raise ValueError("Serial tracking requires an active warranty policy")
                elif clean_override == "INHERIT":
                    cat_pol = None
                    if category_id:
                        from cbpos.core.services.category_service import CategoryService

                        cat = (
                            session.get(Category, category_id) if session else CategoryService.get_category(category_id)
                        )
                        while cat:
                            if cat.default_warranty_policy_id:
                                cat_pol = (
                                    session.get(WarrantyPolicy, cat.default_warranty_policy_id)
                                    if session
                                    else cls.get_policy(cat.default_warranty_policy_id)
                                )
                                break
                            cat = cat.parent if cat.parent_id else None
                    if not cat_pol or not cat_pol.is_active:
                        raise ValueError("Serial tracking requires an active warranty policy")
