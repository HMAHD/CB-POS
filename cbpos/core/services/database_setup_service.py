"""
Service to initialize the database for first-run scenarios.

Provides two modes:
- Empty database: Creates tables + minimal data (roles, permissions, admin user)
- Demo database: Full seed with sample products, customers, sales, etc.
"""

import logging
from enum import Enum
from pathlib import Path

from sqlalchemy import inspect, text

from cbpos.core.constants.permissions import Permissions
from cbpos.core.database import Base, Database
from cbpos.core.models import (
    PaymentMethod,
    Permission,
    Role,
    Unit,
    User,
    VoidReason,
)
from cbpos.core.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class SetupState(Enum):
    """Represents the readiness state of the database schema."""

    NEEDS_SETUP = "needs_setup"
    READY = "ready"


class DatabaseUnavailableError(Exception):
    """Raised when database availability or schema state cannot be determined safely."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"Database unavailable [{code}]: {detail}" if detail else f"Database unavailable [{code}]")
        self.code = code
        self.detail = detail


class DatabaseNotEmptyError(Exception):
    """Raised when a destructive setup or demo load is attempted on a populated database."""


class DatabaseSetupService:
    """Handles first-run database initialization."""

    @staticmethod
    def stamp_alembic_head() -> None:
        """Stamp the database with the current Alembic head revision.

        Called after ``create_all()`` so that future Alembic migrations
        know the schema is already up to date and don't try to re-apply.
        """
        try:
            from alembic.config import Config as AlembicConfig

            from alembic import command
            from cbpos.config import Config

            alembic_cfg = AlembicConfig(str(Config.BASE_DIR / "alembic.ini"))
            alembic_cfg.set_main_option("script_location", str(Config.BASE_DIR / "alembic"))
            alembic_cfg.set_main_option("sqlalchemy.url", Config.DB_URI)
            command.stamp(alembic_cfg, "head")
        except Exception as e:
            logger.warning("Could not stamp alembic version: %s", e)

    @classmethod
    def check_setup_state(cls) -> SetupState:
        """Determine whether the database needs initial setup or is ready.

        Fails closed by raising DatabaseUnavailableError on any inspection or query error.
        """
        db = Database()
        engine = db.engine

        # 1. If SQLite and the DB file does not exist (or has 0 bytes), setup is needed
        if engine.dialect.name == "sqlite":
            db_file = engine.url.database
            if db_file and db_file != ":memory:":
                path = Path(db_file)
                if not path.exists() or path.stat().st_size == 0:
                    return SetupState.NEEDS_SETUP

        # 2. Inspect tables
        try:
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
        except Exception as e:
            raise DatabaseUnavailableError("unreachable", str(e)) from e

        # Filter out internal/system tables
        app_tables = {t for t in tables if t != "alembic_version" and not t.startswith("sqlite_")}

        if not app_tables:
            return SetupState.NEEDS_SETUP

        if "users" not in app_tables:
            raise DatabaseUnavailableError(
                "partial_schema",
                f"Database contains tables {sorted(app_tables)} but 'users' table is missing",
            )

        # 3. Query user count using Core text() query (avoids ORM column selection issues)
        try:
            with engine.connect() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
                if count == 0:
                    return SetupState.NEEDS_SETUP
                return SetupState.READY
        except Exception as e:
            raise DatabaseUnavailableError("unreadable", str(e)) from e

    @classmethod
    def needs_setup(cls) -> bool:
        """Check if the database needs initial setup (no tables or no users).

        Wrapper around check_setup_state() that returns True if SetupState.NEEDS_SETUP.
        Raises DatabaseUnavailableError if the database is in an error or partial state.
        """
        return cls.check_setup_state() is SetupState.NEEDS_SETUP

    @classmethod
    def _assert_database_empty(cls) -> None:
        """Verify that the database has zero rows in core business tables.

        Raises:
            DatabaseNotEmptyError: If users, documents, products, or customers have rows.
            DatabaseUnavailableError: If database cannot be inspected or queried.
        """
        engine = Database().engine
        try:
            inspector = inspect(engine)
            existing_tables = set(inspector.get_table_names())
        except Exception as e:
            raise DatabaseUnavailableError("unreachable", str(e)) from e

        tables_to_check = ["users", "documents", "products", "customers"]
        with engine.connect() as conn:
            for table in tables_to_check:
                if table in existing_tables:
                    try:
                        count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                        if count and count > 0:
                            raise DatabaseNotEmptyError(
                                f"Cannot run destructive database initialization: table '{table}' contains {count} record(s)."
                            )
                    except DatabaseNotEmptyError:
                        raise
                    except Exception as e:
                        raise DatabaseUnavailableError("unreadable", str(e)) from e

    @classmethod
    def create_empty_database(cls, admin_pin: str | None = None) -> None:
        """Create tables with only the minimum data needed to log in.

        Creates: permissions, roles (Admin/Manager/Cashier), default admin
        user (with admin_pin or 1234), void reasons, payment methods, and units.
        """
        import cbpos.core.models  # noqa: F401 — ensure all models are imported

        db = Database()
        Base.metadata.create_all(db.engine)
        cls._assert_database_empty()

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
                "Loyalty",
                "Purchase",
                "Stock Take",
                "Cash",
                "Screens",
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
            effective_pin = admin_pin or "1234"
            admin = User(username="admin", pin_hash=AuthService.hash_pin(effective_pin), role_id=admin_role.id)
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

            # 5. Payment methods (no Cash key: the payment dialog's F12
            # already quick-pays cash, and a method on F12 disables it, #640)
            payment_methods = [
                PaymentMethod(name="Cash", is_cash=True, open_drawer=True, is_active=True),
                PaymentMethod(name="Card", is_active=True, shortcut="F11"),
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

        # Stamp the alembic version so future migrations apply correctly
        cls.stamp_alembic_head()
        logger.info("Empty database initialized with default admin (admin/1234).")

    @classmethod
    def create_demo_database(cls, admin_pin: str | None = None) -> None:
        """Create tables and populate with full demo/sample data.

        Runs the same seed logic as scripts/seed.py.
        """
        cls._assert_database_empty()
        import sys
        from pathlib import Path

        # Add project root to path so seed.py imports work
        project_root = Path(__file__).parent.parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from scripts.seed import seed_data

        seed_data()
        if admin_pin is not None:
            db = Database()
            with db.get_session() as session:
                admin = session.query(User).filter(User.username == "admin").first()
                if not admin:
                    raise RuntimeError("Failed to set admin PIN: admin user not found in demo database")
                admin.pin_hash = AuthService.hash_pin(admin_pin)

        # Stamp the alembic version so future migrations apply correctly
        cls.stamp_alembic_head()
        logger.info("Demo database created with sample data.")
