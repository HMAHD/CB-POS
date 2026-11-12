"""
Service for managing product categories.
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from cbpos.core.constants.audit import WARRANTY_EVENT
from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Category, Role, User, WarrantyPolicy
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.utils.terminal_guard import require_catalog_writable

logger = logging.getLogger(__name__)


def _require_inventory_edit(session, acting_user_id: int | None) -> None:
    effective_actor_id = acting_user_id
    if effective_actor_id is None:
        curr = AuthService.get_current_user()
        if curr:
            effective_actor_id = curr.id

    if effective_actor_id is not None:
        user = session.get(User, effective_actor_id, options=[joinedload(User.role).joinedload(Role.permissions)])
        if not user or not PermissionService.user_has_permission(user, Permissions.INVENTORY_EDIT):
            raise PermissionError("Permission denied: inventory.edit required")


def _require_admin_settings(session, acting_user_id: int | None) -> int:
    effective_actor_id = acting_user_id
    if effective_actor_id is None:
        curr = AuthService.get_current_user()
        if curr:
            effective_actor_id = curr.id

    if effective_actor_id is None:
        raise PermissionError("Permission denied: admin.settings required")

    user = session.get(User, effective_actor_id, options=[joinedload(User.role).joinedload(Role.permissions)])
    if not user or not PermissionService.user_has_permission(user, Permissions.ADMIN_SETTINGS):
        raise PermissionError("Permission denied: admin.settings required")
    return effective_actor_id


def _require_warranty_edit(session, acting_user_id: int | None) -> int:
    effective_actor_id = acting_user_id
    if effective_actor_id is None:
        curr = AuthService.get_current_user()
        if curr:
            effective_actor_id = curr.id

    if effective_actor_id is None:
        raise PermissionError("Permission denied: warranty.edit required")

    user = session.get(User, effective_actor_id, options=[joinedload(User.role).joinedload(Role.permissions)])
    if not user or not PermissionService.user_has_permission(user, Permissions.WARRANTY_EDIT):
        raise PermissionError("Permission denied: warranty.edit required")
    return effective_actor_id


class CategoryService:
    """CRUD operations for product categories."""

    @staticmethod
    def get_all(active_only: bool = True) -> list[Category]:
        """Get all categories, ordered by name.

        Args:
            active_only: Currently unused (categories have no is_active flag),
                         kept for API consistency.

        Returns:
            List of all categories.
        """
        db = Database()
        with db.get_session() as session:
            stmt = select(Category).order_by(Category.name)
            results = list(session.scalars(stmt).all())
            for cat in results:
                session.expunge(cat)
            return results

    @staticmethod
    def get_tree() -> list[Category]:
        """Get all categories for tree building (includes parent_id info).

        Returns:
            List of all categories with id, name, parent_id, color loaded.
        """
        db = Database()
        with db.get_session() as session:
            stmt = select(Category).order_by(Category.parent_id.nulls_first(), Category.name)
            results = list(session.scalars(stmt).all())
            for cat in results:
                session.expunge(cat)
            return results

    @staticmethod
    def get_by_id(category_id: int) -> Category | None:
        """Get a single category by ID.

        Args:
            category_id: ID of the category.

        Returns:
            The Category, or None if not found.
        """
        db = Database()
        with db.get_session() as session:
            category = session.get(Category, category_id)
            if category:
                session.expunge(category)
            return category

    @staticmethod
    def get_top_level() -> list[Category]:
        """Get all top-level categories (parent_id is None).

        Returns:
            List of categories sorted by name.
        """
        db = Database()
        with db.get_session() as session:
            stmt = select(Category).where(Category.parent_id.is_(None)).order_by(Category.name)
            results = list(session.execute(stmt).scalars().all())
            for cat in results:
                session.expunge(cat)
            return results

    @staticmethod
    def get_top_level_with_subcategories() -> list[Category]:
        """Get root categories with subcategories eagerly loaded, ordered by name.

        Returns:
            List of top-level categories with subcategories loaded.
        """
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(Category)
                .options(joinedload(Category.subcategories))
                .where(Category.parent_id.is_(None))
                .order_by(Category.name)
            )
            results = list(session.execute(stmt).unique().scalars().all())
            for cat in results:
                for sub in cat.subcategories:
                    session.expunge(sub)
                session.expunge(cat)
            return results

    @staticmethod
    def get_top_level_with_subcategories_and_products() -> list[Category]:
        """Get root categories with subcategories and products eagerly loaded.

        Used by CategoryManagerDialog for product counts.

        Returns:
            List of top-level categories with subcategories and products loaded.
        """
        db = Database()
        with db.get_session() as session:
            stmt = (
                select(Category)
                .options(
                    joinedload(Category.subcategories).joinedload(Category.products),
                    joinedload(Category.products),
                )
                .where(Category.parent_id.is_(None))
                .order_by(Category.name)
            )
            results = list(session.execute(stmt).unique().scalars().all())
            for cat in results:
                for sub in cat.subcategories:
                    session.expunge(sub)
                session.expunge(cat)
            return results

    @staticmethod
    def get_descendant_ids(category_id: int) -> set[int]:
        """Get all descendant category IDs (not including the given ID).

        Args:
            category_id: ID of the root category.

        Returns:
            Set of all descendant category IDs.
        """
        db = Database()
        with db.get_session() as session:
            # Build children map
            all_cats = session.execute(select(Category.id, Category.parent_id)).all()
            children_map: dict[int | None, list[int]] = {}
            for cid, pid in all_cats:
                children_map.setdefault(pid, []).append(cid)

            # BFS
            result: set[int] = set()
            queue = list(children_map.get(category_id, []))
            while queue:
                current = queue.pop(0)
                result.add(current)
                queue.extend(children_map.get(current, []))
            return result

    @staticmethod
    def get_product_count_for_ids(category_ids: set[int]) -> int:
        """Count products with category_id in the given set.

        Args:
            category_ids: Set of category IDs to check.

        Returns:
            Number of products in those categories.
        """
        if not category_ids:
            return 0

        from sqlalchemy import func

        from cbpos.core.models import Product

        db = Database()
        with db.get_session() as session:
            count = session.execute(
                select(func.count(Product.id)).where(Product.category_id.in_(category_ids))
            ).scalar()
            return count or 0

    @staticmethod
    def delete_with_descendants(category_id: int, acting_user_id: int | None = None) -> None:
        """Delete a category and all its descendants (deepest first).

        Args:
            category_id: ID of the category to delete.
            acting_user_id: Optional ID of user performing the deletion.

        Raises:
            ValueError: If category not found.
        """
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            _require_inventory_edit(session, acting_user_id)
            category = session.get(Category, category_id)
            if not category:
                raise ValueError(f"Category ID {category_id} not found.")

            # Collect all IDs including self
            all_cats = session.execute(select(Category.id, Category.parent_id)).all()
            children_map: dict[int | None, list[int]] = {}
            for cid, pid in all_cats:
                children_map.setdefault(pid, []).append(cid)

            # BFS to get all descendant IDs
            all_ids = {category_id}
            queue = list(children_map.get(category_id, []))
            while queue:
                current = queue.pop(0)
                all_ids.add(current)
                queue.extend(children_map.get(current, []))

            # Delete deepest first
            cats = list(session.scalars(select(Category).where(Category.id.in_(all_ids))).all())
            cats_by_id = {c.id: c for c in cats}
            for cid in sorted(all_ids, reverse=True):
                cat = cats_by_id.get(cid)
                if cat:
                    session.delete(cat)

    @staticmethod
    def effective_flags(category_id: int | None, session: Session | None = None) -> dict[str, bool]:
        """Return effective VAT and SSCL exemption flags for a category, resolving inheritance."""
        if category_id is None or not isinstance(category_id, int):
            return {"vat_exempt": False, "sscl_exempt": False}

        def _resolve(s: Session) -> dict[str, bool]:
            cat = s.get(Category, category_id)
            if not cat:
                return {"vat_exempt": False, "sscl_exempt": False}
            vat_exempt = bool(cat.tax_exempt)
            sscl_exempt = bool(cat.sscl_exempt)
            if (not vat_exempt or not sscl_exempt) and cat.parent_id:
                parent = s.get(Category, cat.parent_id)
                if parent:
                    if not vat_exempt and parent.tax_exempt:
                        vat_exempt = True
                    if not sscl_exempt and parent.sscl_exempt:
                        sscl_exempt = True
            return {"vat_exempt": vat_exempt, "sscl_exempt": sscl_exempt}

        if session is not None:
            return _resolve(session)
        with Database().get_session() as s:
            return _resolve(s)

    @staticmethod
    def create(
        name: str,
        parent_id: int | None = None,
        color: str | None = None,
        tax_exempt: bool | None = None,
        sscl_exempt: bool | None = None,
        vat_exempt: bool | None = None,
        acting_user_id: int | None = None,
        default_warranty_policy_id: int | None = None,
    ) -> Category:
        """Create a new category.

        Args:
            name: Category name.
            parent_id: Optional parent category ID for subcategories.
            color: Optional hex color string (e.g. '#FF0000').
            tax_exempt: Whether items in this category are VAT exempt.
            sscl_exempt: Whether items in this category are SSCL exempt.
            vat_exempt: Alias for tax_exempt.
            acting_user_id: Optional ID of user creating the category.

        Returns:
            The newly created Category.

        Raises:
            ValueError: If a category with the same name already exists.
            PermissionError: If tax exemption flags are set without admin.settings.
        """
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            _require_inventory_edit(session, acting_user_id)
            existing = session.query(Category).filter(Category.name == name).first()
            if existing:
                raise ValueError(f"Category '{name}' already exists.")

            if parent_id is not None:
                parent = session.get(Category, parent_id)
                if not parent:
                    raise ValueError(f"Parent category ID {parent_id} not found.")
                if parent.parent_id is not None:
                    raise ValueError("category_too_deep")

            effective_vat_exempt = vat_exempt if vat_exempt is not None else tax_exempt
            if effective_vat_exempt or sscl_exempt:
                actor_id = _require_admin_settings(session, acting_user_id)
            else:
                actor_id = acting_user_id or (
                    AuthService.get_current_user().id if AuthService.get_current_user() else None
                )

            warr_actor_id = None
            if default_warranty_policy_id is not None:
                warr_actor_id = _require_warranty_edit(session, acting_user_id)
                pol = session.get(WarrantyPolicy, default_warranty_policy_id)
                if not pol:
                    raise ValueError(f"Warranty policy {default_warranty_policy_id} not found")
                if not pol.is_active:
                    raise ValueError("Cannot assign inactive warranty policy")

            category = Category(
                name=name,
                parent_id=parent_id,
                color=color or "#FFFFFF",
                tax_exempt=bool(effective_vat_exempt),
                sscl_exempt=bool(sscl_exempt),
                default_warranty_policy_id=default_warranty_policy_id,
            )
            session.add(category)
            session.flush()

            if default_warranty_policy_id is not None:
                w_audit = AuditLog(
                    user_id=warr_actor_id,
                    action="CATEGORY_DEFAULT_WARRANTY",
                    event_type=WARRANTY_EVENT,
                    details=json.dumps({"category_id": category.id, "policy_id": default_warranty_policy_id}),
                )
                session.add(w_audit)
                session.flush()

            if effective_vat_exempt or sscl_exempt:
                audit = AuditLog(
                    user_id=actor_id,
                    action="CATEGORY_TAX_FLAG_CHANGED",
                    event_type="CATEGORY",
                    details=json.dumps(
                        {
                            "category_id": category.id,
                            "category_name": category.name,
                            "old": {"vat_exempt": False, "sscl_exempt": False},
                            "new": {"vat_exempt": bool(effective_vat_exempt), "sscl_exempt": bool(sscl_exempt)},
                        }
                    ),
                )
                session.add(audit)
                session.flush()

            session.expunge(category)
            return category

    @staticmethod
    def update(
        category_id: int,
        name: str | None = None,
        color: str | None = None,
        parent_id: object = ...,
        tax_exempt: bool | None = None,
        sscl_exempt: bool | None = None,
        vat_exempt: bool | None = None,
        acting_user_id: int | None = None,
        default_warranty_policy_id: object = ...,
    ) -> Category:
        """Update an existing category.

        Args:
            category_id: ID of the category to update.
            name: New name (if provided).
            color: New color hex string (if provided).
            parent_id: New parent ID. Use None for root, omit (``...``) to leave unchanged.
            tax_exempt: New tax_exempt flag (if provided).
            sscl_exempt: New sscl_exempt flag (if provided).
            vat_exempt: Alias for tax_exempt.
            acting_user_id: Optional ID of user updating the category.

        Returns:
            The updated Category.

        Raises:
            ValueError: If category not found or duplicate name.
            PermissionError: If tax exemption flags are changed without admin.settings.
        """
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            _require_inventory_edit(session, acting_user_id)
            category = session.get(Category, category_id)
            if not category:
                raise ValueError(f"Category ID {category_id} not found.")

            if name is not None:
                # Check uniqueness excluding self
                dup = session.query(Category).filter(Category.name == name, Category.id != category_id).first()
                if dup:
                    raise ValueError(f"Category '{name}' already exists.")
                category.name = name

            if color is not None:
                category.color = color

            if parent_id is not ...:
                if parent_id is not None:
                    if parent_id == category_id:
                        raise ValueError("cannot be its own parent")
                    parent = session.get(Category, parent_id)
                    if not parent:
                        raise ValueError(f"Parent category ID {parent_id} not found.")
                    if parent.parent_id is not None:
                        raise ValueError("category_too_deep")
                    has_children = session.query(Category).filter(Category.parent_id == category_id).first() is not None
                    if has_children:
                        raise ValueError("category_too_deep")
                category.parent_id = parent_id

            if (
                default_warranty_policy_id is not ...
                and default_warranty_policy_id != category.default_warranty_policy_id
            ):
                warr_actor_id = _require_warranty_edit(session, acting_user_id)
                if default_warranty_policy_id is not None:
                    pol = session.get(WarrantyPolicy, default_warranty_policy_id)
                    if not pol:
                        raise ValueError(f"Warranty policy {default_warranty_policy_id} not found")
                    if not pol.is_active:
                        raise ValueError("Cannot assign inactive warranty policy")
                category.default_warranty_policy_id = default_warranty_policy_id
                w_audit = AuditLog(
                    user_id=warr_actor_id,
                    action="CATEGORY_DEFAULT_WARRANTY",
                    event_type=WARRANTY_EVENT,
                    details=json.dumps({"category_id": category.id, "policy_id": default_warranty_policy_id}),
                )
                session.add(w_audit)

            effective_vat_exempt = vat_exempt if vat_exempt is not None else tax_exempt
            vat_changed = effective_vat_exempt is not None and effective_vat_exempt != category.tax_exempt
            sscl_changed = sscl_exempt is not None and sscl_exempt != category.sscl_exempt

            if vat_changed or sscl_changed:
                actor_id = _require_admin_settings(session, acting_user_id)
                old_vat = category.tax_exempt
                old_sscl = category.sscl_exempt
                if effective_vat_exempt is not None:
                    category.tax_exempt = bool(effective_vat_exempt)
                if sscl_exempt is not None:
                    category.sscl_exempt = bool(sscl_exempt)
                audit = AuditLog(
                    user_id=actor_id,
                    action="CATEGORY_TAX_FLAG_CHANGED",
                    event_type="CATEGORY",
                    details=json.dumps(
                        {
                            "category_id": category.id,
                            "category_name": category.name,
                            "old": {"vat_exempt": old_vat, "sscl_exempt": old_sscl},
                            "new": {"vat_exempt": category.tax_exempt, "sscl_exempt": category.sscl_exempt},
                        }
                    ),
                )
                session.add(audit)

            session.flush()
            session.expunge(category)
            return category

    @staticmethod
    def delete(category_id: int, acting_user_id: int | None = None) -> None:
        """Delete a category. Checks for products first.

        Args:
            category_id: ID of the category to delete.
            acting_user_id: Optional ID of user deleting the category.

        Raises:
            ValueError: If category not found or has products assigned.
        """
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            _require_inventory_edit(session, acting_user_id)
            category = session.get(Category, category_id)
            if not category:
                raise ValueError(f"Category ID {category_id} not found.")

            from cbpos.core.models import Product

            product_count = session.query(Product).filter(Product.category_id == category_id).count()
            if product_count > 0:
                raise ValueError(f"Cannot delete: {product_count} product(s) use this category.")

            session.delete(category)

    @staticmethod
    def reparent(category_id: int, new_parent_id: int | None, acting_user_id: int | None = None) -> Category:
        """Move a category under a new parent.

        Args:
            category_id: ID of the category to move.
            new_parent_id: ID of the new parent, or None for root.
            acting_user_id: Optional ID of user reparenting the category.

        Returns:
            The updated Category.

        Raises:
            ValueError: If category or parent not found, or circular reference.
        """
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            _require_inventory_edit(session, acting_user_id)
            category = session.get(Category, category_id)
            if not category:
                raise ValueError(f"Category ID {category_id} not found.")

            if new_parent_id is not None:
                parent = session.get(Category, new_parent_id)
                if not parent:
                    raise ValueError(f"Parent category ID {new_parent_id} not found.")

                # Prevent circular reference
                if new_parent_id == category_id:
                    raise ValueError("A category cannot be its own parent.")

            category.parent_id = new_parent_id
            session.flush()
            session.expunge(category)
            return category
