"""
Helper utility to check user permissions with automatic manager override prompt.

This module uses a pluggable override handler so that the core layer never
imports UI components directly.  The default handler is registered at
application startup (see main.py / MainWindow) via ``set_override_handler``.
"""

import logging
from collections.abc import Callable

from cbpos.core.models import User
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService

logger = logging.getLogger(__name__)

# Type alias for the override handler callback.
# Signature: (permission_code: str, parent: Any) -> Optional[User]
OverrideHandler = Callable[..., User | None]

_override_handler: OverrideHandler | None = None


def set_override_handler(handler: OverrideHandler) -> None:
    """Register the UI-level override handler at application startup.

    Args:
        handler: A callable that prompts for manager override and returns the
                 authorizing User, or None if cancelled.
    """
    global _override_handler
    _override_handler = handler


def check_permission_with_override(permission_code: str, parent_widget=None) -> User | None:
    """Check if current user has the given permission.

    If not, delegates to the registered override handler (typically a dialog).

    Args:
        permission_code: The permission code to check (e.g. 'sales.void_item').
        parent_widget: Parent widget passed through to the override handler.

    Returns:
        The authorized User if permission granted (current or override),
        or None if denied/cancelled.
    """
    current_user = AuthService.get_current_user()
    if not current_user:
        return None

    if PermissionService.user_has_permission(current_user, permission_code):
        return current_user

    # Need override — delegate to the registered handler
    if _override_handler is None:
        logger.warning(
            "Permission override required for '%s' but no handler registered",
            permission_code,
        )
        return None

    authorized_user = _override_handler(permission_code, parent_widget)
    if authorized_user is not None:
        logger.info(
            "Manager override granted by %s for permission '%s'",
            authorized_user.username,
            permission_code,
        )
    return authorized_user
