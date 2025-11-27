import hashlib
from typing import List, Optional
from sqlalchemy.orm import joinedload
from cbpos.core.database import Database
from cbpos.core.models import User, Role


class UserService:
    """
    Service to manage users and roles.
    """

    @staticmethod
    def get_all_users() -> List[User]:
        """Get all users with their roles."""
        db = Database()
        with db.get_session() as session:
            users = session.query(User).options(joinedload(User.role)).all()
            session.expunge_all()
            return users

    @staticmethod
    def get_all_roles() -> List[Role]:
        """Get all available roles."""
        db = Database()
        with db.get_session() as session:
            roles = session.query(Role).all()
            session.expunge_all()
            return roles

    @staticmethod
    def create_user(username: str, pin: str, role_id: int) -> User:
        """Create a new user."""
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()

        db = Database()
        with db.get_session() as session:
            user = User(
                username=username, pin_hash=pin_hash, role_id=role_id, is_active=True
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            # Eager load role before expunging
            session.query(User).options(joinedload(User.role)).filter(
                User.id == user.id
            ).one()
            session.expunge_all()
            return user

    @staticmethod
    def update_user(
        user_id: int,
        username: str,
        pin: Optional[str] = None,
        role_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[User]:
        """Update an existing user."""
        db = Database()
        with db.get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return None

            user.username = username
            if pin:
                user.pin_hash = hashlib.sha256(pin.encode()).hexdigest()
            if role_id is not None:
                user.role_id = role_id
            if is_active is not None:
                user.is_active = is_active

            session.commit()
            session.refresh(user)
            # Eager load role before expunging
            session.query(User).options(joinedload(User.role)).filter(
                User.id == user.id
            ).one()
            session.expunge_all()
            return user
