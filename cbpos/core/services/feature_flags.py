"""Service for managing database-backed feature flags and shop-type presets (#942)."""

import json
import logging
import threading

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from cbpos.core.constants.audit import FEATURE_FLAG_EVENT
from cbpos.core.constants.features import (
    PRESET_CATEGORIES,
    PRESET_MATRIX,
    PRESET_UNITS,
    ShopTypes,
)
from cbpos.core.constants.permissions import ADMIN_ROLE_NAME, Permissions
from cbpos.core.database import Database
from cbpos.core.models import AuditLog, Category, FeatureFlag, Role, Unit, User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.utils.terminal_guard import require_catalog_writable

logger = logging.getLogger(__name__)


def _require_features_permission(session: Session, acting_user_id: int | None) -> int:
    """Ensure acting user has settings.features or admin.settings permission, or is Admin role."""
    effective_id = acting_user_id
    if effective_id is None:
        curr = AuthService.get_current_user()
        if curr:
            effective_id = curr.id

    if effective_id is None:
        raise PermissionError("Authentication required: login as Admin to modify feature flags")

    user = session.get(User, effective_id, options=[joinedload(User.role).joinedload(Role.permissions)])
    if user and user.role:
        if user.role.name == ADMIN_ROLE_NAME:
            return effective_id
        if PermissionService.user_has_any_permission(user, (Permissions.SETTINGS_FEATURES, Permissions.ADMIN_SETTINGS)):
            return effective_id
    raise PermissionError("Permission denied: settings.features required")


class FeatureFlags:
    """Manages database-backed feature flags, caching, and shop-type preset applications (#942)."""

    _cache: dict[str, bool] | None = None
    _lock = threading.RLock()

    @classmethod
    def invalidate_cache(cls) -> None:
        """Clear the in-memory feature flags cache."""
        with cls._lock:
            cls._cache = None

    @classmethod
    def _load_cache(cls, session: Session) -> dict[str, bool]:
        """Load all feature flags from the database into a dictionary."""
        stmt = select(FeatureFlag.name, FeatureFlag.enabled)
        rows = session.execute(stmt).all()
        return dict(rows)

    @classmethod
    def is_on(cls, name: str) -> bool:
        """Return True if the feature flag is enabled in the database.

        Reads from an in-memory thread-safe cache, populating from the database on miss.
        """
        with cls._lock:
            if cls._cache is None:
                try:
                    db = Database()
                    with db.get_session() as session:
                        cls._cache = cls._load_cache(session)
                except Exception as e:
                    logger.debug("Failed to load feature flags from DB: %s", e)
                    return False
            return cls._cache.get(name, False)

    @classmethod
    def set(cls, name: str, enabled: bool, acting_user_id: int | None = None) -> None:
        """Enable or disable a feature flag.

        Audited, permission-checked (`settings.features`), catalog-guarded (fails on tills).
        """
        require_catalog_writable()
        db = Database()
        with db.get_session() as session:
            effective_user_id = _require_features_permission(session, acting_user_id)

            flag = session.get(FeatureFlag, name)
            old_enabled = flag.enabled if flag else False

            if flag is None:
                flag = FeatureFlag(name=name, enabled=enabled, updated_by=effective_user_id)
                session.add(flag)
            else:
                flag.enabled = enabled
                flag.updated_by = effective_user_id

            if name == "power_cut_autosave" and not enabled:
                from cbpos.core.services.cart_autosave_service import CartAutosaveService

                CartAutosaveService.delete_all_autosaves_in_session(session)

            # Write AuditLog
            log = AuditLog(
                user_id=effective_user_id,
                action="SET_FEATURE_FLAG",
                event_type=FEATURE_FLAG_EVENT,
                details=json.dumps(
                    {
                        "flag": name,
                        "old_enabled": old_enabled,
                        "new_enabled": enabled,
                    }
                ),
            )
            session.add(log)
            session.commit()

        with cls._lock:
            if cls._cache is not None:
                cls._cache[name] = enabled

    @classmethod
    def apply_preset(
        cls,
        shop_type: str,
        acting_user_id: int | None = None,
        language: str | None = None,
        session: Session | None = None,
    ) -> None:
        """Apply a shop-type preset: set feature flags, seed units and categories.

        Idempotent: skips existing flags, units, and categories without duplicate errors.
        """
        require_catalog_writable()
        normalized_type = (shop_type or ShopTypes.OTHER).lower().strip()
        if normalized_type not in PRESET_MATRIX:
            normalized_type = ShopTypes.OTHER

        def _apply(s: Session) -> None:
            effective_user_id = _require_features_permission(s, acting_user_id)

            # 1. Feature flags
            flags_matrix = PRESET_MATRIX[normalized_type]
            applied_flags = {}
            for flag_name, is_enabled in flags_matrix.items():
                flag = s.get(FeatureFlag, flag_name)
                if flag is None:
                    flag = FeatureFlag(name=flag_name, enabled=is_enabled, updated_by=effective_user_id)
                    s.add(flag)
                else:
                    flag.enabled = is_enabled
                    flag.updated_by = effective_user_id
                applied_flags[flag_name] = is_enabled

            # 2. Units (deduplicating by both name and abbreviation to prevent IntegrityError)
            units_to_seed = PRESET_UNITS.get(normalized_type, PRESET_UNITS[ShopTypes.OTHER])
            for name, abbr, decimals in units_to_seed:
                existing_unit = (
                    s.query(Unit)
                    .filter((func.lower(Unit.abbreviation) == abbr.lower()) | (func.lower(Unit.name) == name.lower()))
                    .first()
                )
                if existing_unit is None:
                    s.add(Unit(name=name, abbreviation=abbr, decimal_places=decimals, is_active=True))

            # 3. Categories (localized per Decision D35 Option A)
            lang = (language or ConfigService.get("language") or "en").lower().strip()
            lang_key = "si" if lang.startswith("si") else ("ta" if lang.startswith("ta") else "en")

            categories_to_seed = PRESET_CATEGORIES.get(normalized_type, [])
            for cat_def in categories_to_seed:
                cat_name = cat_def.get(lang_key) or cat_def.get("en", "")
                if not cat_name:
                    continue
                existing_cat = s.query(Category).filter(func.lower(Category.name) == cat_name.strip().lower()).first()
                if existing_cat is None:
                    s.add(
                        Category(
                            name=cat_name.strip(),
                            color=cat_def.get("color", "#FFFFFF"),
                            parent_id=None,
                        )
                    )

            # 4. Audit Log
            log = AuditLog(
                user_id=effective_user_id,
                action="APPLY_SHOP_PRESET",
                event_type=FEATURE_FLAG_EVENT,
                details=json.dumps(
                    {
                        "shop_type": normalized_type,
                        "language": lang_key,
                        "flags": applied_flags,
                    }
                ),
            )
            s.add(log)
            s.flush()

        if session is not None:
            _apply(session)
        else:
            db = Database()
            with db.get_session() as s:
                _apply(s)

        cls.invalidate_cache()


def feature_visible(name: str) -> bool:
    """Gating helper for UI code. Views must call this, never ConfigService (#942)."""
    return FeatureFlags.is_on(name)
