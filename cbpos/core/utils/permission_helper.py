"""
Helper utility to check user permissions with automatic manager override prompt.
"""

import logging
from typing import Optional
from cbpos.core.services.auth_service import AuthService
from cbpos.core.services.permission_service import PermissionService
from cbpos.core.models import User

logger = logging.getLogger(__name__)


def check_permission_with_override(permission_code: str, parent_widget=None) -> Optional[User]:
    """
    Check if current user has the given permission.
    If not, show ManagerOverrideDialog to request manager PIN.

    Args:
        permission_code: The permission code to check (e.g. 'can_void_sale').
        parent_widget: Parent QWidget for the override dialog.

    Returns:
        The authorized User if permission granted (current or override),
        or None if denied/cancelled.
    """
    current_user = AuthService.get_current_user()
    if not current_user:
        return None

    if PermissionService.user_has_permission(current_user, permission_code):
        return current_user

    # Need override
    from cbpos.ui.dialogs.manager_override_dialog import ManagerOverrideDialog

    dialog = ManagerOverrideDialog(permission_code, parent_widget)
    if dialog.exec():
        logger.info(
            f"Manager override granted by {dialog.authorized_user.username} " f"for permission '{permission_code}'"
        )
        return dialog.authorized_user

    return None
