"""Translated display labels for codes stored in the database (#583).

Permissions, permission groups, built-in roles and Activity Log event types are stored as
English codes/names. They are translated here at display time, so databases created before
these labels existed show correctly without a migration.
"""

from cbpos.i18n import _t

# Built-in role names as seeded by DatabaseSetupService / scripts/seed.py -> i18n key
BUILTIN_ROLE_KEYS = {
    "Admin": "roles.admin",
    "Manager": "roles.manager",
    "Cashier": "roles.cashier",
}


def _t_or(key: str, fallback: str) -> str:
    """Translate `key`, or return `fallback` when no language has it (_t returns the raw key)."""
    text = _t(key)
    return fallback if text == key else text


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def permission_label(code: str, description: str | None = None) -> str:
    """Translated label for a permission code, e.g. "sales.add_item" -> "Add items to a bill".

    Unknown codes fall back to the stored description, then the code itself.
    """
    return _t_or(f"permission.code.{code}", description or code)


def permission_group_label(group: str | None) -> str:
    """Translated label for a stored permission group ("Data Safety" -> "permission.group.data_safety")."""
    if not group:
        return _t("permission.group.other")
    return _t_or(f"permission.group.{_slug(group)}", group)


def display_role_name(role) -> str:
    """Translated name for a built-in role (Admin/Manager/Cashier); custom roles show as typed.

    Accepts a Role (anything with `.name`) or a plain name string.
    """
    name = role if isinstance(role, str) else getattr(role, "name", None)
    if not name:
        return ""
    key = BUILTIN_ROLE_KEYS.get(name)
    return _t(key) if key else name


def event_type_label(event_type: str | None) -> str:
    """Translated Activity Log event type ("SECURITY" -> user.event_security); unknown types as stored."""
    if not event_type:
        return ""
    return _t_or(f"user.event_{_slug(event_type)}", event_type)
