import hashlib
from typing import Optional
from sqlalchemy.orm import Session
from cbpos.core.database import Database
from cbpos.core.models import User

class AuthService:
    """
    Service to handle user authentication and session management.
    """
    _current_user: Optional[User] = None

    @staticmethod
    def verify_pin(pin: str) -> Optional[User]:
        """
        Verify the provided PIN against the database.
        
        Args:
            pin (str): The PIN entered by the user.
            
        Returns:
            Optional[User]: The User object if authentication is successful, else None.
        """
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        
        db = Database()
        with db.get_session() as session:
            user = session.query(User).filter(User.pin_hash == pin_hash, User.is_active == True).first()
            if user:
                # Detach user from session to keep it available after session closes
                session.expunge(user)
                AuthService._current_user = user
                return user
        return None

    @staticmethod
    def get_current_user() -> Optional[User]:
        """Return the currently logged-in user."""
        return AuthService._current_user

    @staticmethod
    def logout():
        """Clear the current user session."""
        AuthService._current_user = None
