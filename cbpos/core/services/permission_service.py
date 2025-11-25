from cbpos.core.models import User

class PermissionService:
    """
    Service to handle permission checks.
    """

    @staticmethod
    def user_has_permission(user: User, permission_code: str) -> bool:
        """
        Check if the user has a specific permission.
        
        Args:
            user (User): The user to check.
            permission_code (str): The code of the permission (e.g., 'can_void_sale').
            
        Returns:
            bool: True if authorized, False otherwise.
        """
        if not user or not user.role:
            return False
            
        # Admin has all permissions (optional override)
        if user.role.name == "Admin":
            return True
            
        for perm in user.role.permissions:
            if perm.code == permission_code:
                return True
                
        return False
