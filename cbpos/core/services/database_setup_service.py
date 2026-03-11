"""
Service to initialize the database for first-run scenarios.

Provides two modes:
- Empty database: Creates tables + minimal data (roles, permissions, admin user)
- Demo database: Full seed with sample products, customers, sales, etc.
"""

import logging

import bcrypt

from cbpos.core.database import Database, Base
from cbpos.core.models import (
    User,
    Role,
    Permission,
    VoidReason,
    PaymentMethod,
    Unit,
)
from cbpos.core.constants.permissions import Permissions

logger = logging.getLogger(__name__)


def _hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


class DatabaseSetupService:
    """Handles first-run database initialization."""

    @staticmethod
    def needs_setup() -> bool:
        """Check if the database needs initial setup (no tables or no users)."""
        from cbpos.config import Config

        db_path = Config.DATA_DIR / "cbpos.db"
        if not db_path.exists():
            return True

        # DB file exists but might be empty — check for users table
        try:
            db = Database()
            with db.get_session() as session:
                count = session.query(User).count()
                return count == 0
        except Exception:
            return True

    @staticmethod
    def create_empty_database() -> None:
        """Create tables with only the minimum data needed to log in.

        Creates: permissions, roles (Admin/Manager/Cashier), default admin
        user (admin/1234), void reasons, payment methods, and units.
        """
        import cbpos.core.models  # noqa: F401 — ensure all models are imported

        db = Database()
        Base.metadata.create_all(db.engine)

        with db.get_session() as session:
            # Check if already seeded (idempotent)
            if session.query(User).count() > 0:
                return

            # 1. Permissions
            perm_map = {}
            groups = Permissions.get_groups()
            for group, codes in groups.items():
                for code in codes:
                    perm = Permission(
                        code=code,
                        description=code.replace(".", " ").title(),
                        group=group,
                    )
                    session.add(perm)
                    perm_map[code] = perm
            session.flush()

            # 2. Roles
            admin_role = Role(name="Admin", access_level=9)
            for perm in perm_map.values():
                admin_role.permissions.append(perm)

            manager_role = Role(name="Manager", access_level=5)
            manager_groups = [
                "Sales",
                "Inventory",
                "Reports",
                "Documents",
                "Credit",
                "Purchase",
                "Stock Take",
                "Cash",
            ]
            for grp in manager_groups:
                for code in groups.get(grp, []):
                    manager_role.permissions.append(perm_map[code])

            cashier_role = Role(name="Cashier", access_level=1)
            cashier_role.permissions.append(perm_map[Permissions.SALES_VIEW])
            cashier_role.permissions.append(perm_map[Permissions.SALES_ADD_ITEM])
            cashier_role.permissions.append(perm_map[Permissions.DOCUMENTS_VIEW])
            cashier_role.permissions.append(perm_map[Permissions.CREDIT_RECEIVE_PAYMENT])
            cashier_role.permissions.append(perm_map[Permissions.CASH_OPEN_DRAWER])

            session.add_all([admin_role, manager_role, cashier_role])
            session.flush()

            # 3. Default admin user
            admin = User(username="admin", pin_hash=_hash_pin("1234"), role_id=admin_role.id)
            session.add(admin)

            # 4. Void reasons
            void_reasons = [
                VoidReason(code="MISTAKE", description="Cashier Mistake"),
                VoidReason(code="RETURN", description="Customer Return"),
                VoidReason(code="DAMAGED", description="Damaged Goods"),
                VoidReason(code="CHANGED_MIND", description="Customer Changed Mind"),
                VoidReason(code="ACCIDENTAL", description="Accidental Entry"),
                VoidReason(code="MANAGER", description="Manager Override"),
            ]
            session.add_all(void_reasons)

            # 5. Payment methods
            payment_methods = [
                PaymentMethod(name="Cash", is_cash=True, open_drawer=True, is_active=True),
                PaymentMethod(name="Card", is_active=True),
                PaymentMethod(name="Credit", is_active=True),
                PaymentMethod(name="QR/Mobile", is_active=True),
                PaymentMethod(name="Cheque", is_active=True),
                PaymentMethod(name="Bank Transfer", is_active=True),
            ]
            session.add_all(payment_methods)

            # 6. Units of measurement
            units = [
                Unit(name="Piece", abbreviation="pcs", decimal_places=0),
                Unit(name="Kilogram", abbreviation="kg", decimal_places=3),
                Unit(name="Gram", abbreviation="g", decimal_places=0),
                Unit(name="Liter", abbreviation="L", decimal_places=3),
                Unit(name="Meter", abbreviation="m", decimal_places=2),
                Unit(name="Pack", abbreviation="pk", decimal_places=0),
                Unit(name="Box", abbreviation="box", decimal_places=0),
                Unit(name="Dozen", abbreviation="dz", decimal_places=0),
            ]
            session.add_all(units)

        logger.info("Empty database initialized with default admin (admin/1234).")

    @staticmethod
    def create_demo_database() -> None:
        """Create tables and populate with full demo/sample data.

        Runs the same seed logic as scripts/seed.py.
        """
        import sys
        from pathlib import Path

        # Add project root to path so seed.py imports work
        project_root = Path(__file__).parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from scripts.seed import seed_data

        seed_data()
        logger.info("Demo database created with sample data.")
