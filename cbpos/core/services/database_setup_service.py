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
from cbpos.core.constants.status import PaymentMethodKind
from cbpos.core.database import Base, Database
from cbpos.core.models import (
    PaymentMethod,
    Permission,
    Role,
    Unit,
    User,
    VoidReason,
    WarrantyPolicy,
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
    def stamp_alembic_head(db_uri: str | None = None) -> None:
        """Stamp the database with the current Alembic head revision.

        Called after ``create_all()`` so that future Alembic migrations
        know the schema is already up to date and don't try to re-apply.
        """
        try:
            from cbpos.core.database import Database
            from cbpos.core.services.schema_migration_service import SchemaMigrationService

            target_uri = db_uri
            if target_uri is None:
                db = Database()
                target_uri = str(db.engine.url)
            SchemaMigrationService.stamp_head(target_uri)
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

            # 0. Local database identity (#866)
            import uuid

            from cbpos.core.models import LocalIdentity

            if session.query(LocalIdentity).count() == 0:
                session.add(LocalIdentity(db_instance_id=str(uuid.uuid4())))

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
                "Warranty",
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
            cashier_role.permissions.append(perm_map[Permissions.SALES_REPRINT])
            cashier_role.permissions.append(perm_map[Permissions.WARRANTY_VIEW])

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
                PaymentMethod(name="Cash", kind=PaymentMethodKind.CASH, is_cash=True, open_drawer=True, is_active=True),
                PaymentMethod(name="Card", kind=PaymentMethodKind.CARD, is_active=True, shortcut="F11"),
                PaymentMethod(name="Credit", kind=PaymentMethodKind.CREDIT, is_active=True),
                PaymentMethod(name="QR/Mobile", kind=PaymentMethodKind.QR, is_active=True),
                PaymentMethod(name="Cheque", kind=PaymentMethodKind.CHEQUE, is_active=True),
                PaymentMethod(name="Bank Transfer", kind=PaymentMethodKind.TRANSFER, is_active=True),
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

            # 7. Default inactive warranty templates (#821)
            templates = [
                WarrantyPolicy(
                    name="7 days shop replacement",
                    name_si="දින 7ක කඩේ ආදේශනය",
                    name_ta="7 நாட்கள் கடை மாற்று உத்தரவாதம்",
                    warranty_type="SHOP",
                    duration=7,
                    duration_unit="DAYS",
                    remedy="REPLACE_ONLY",
                    provider_name=None,
                    terms_text="Item must be returned with complete original packaging, accessories and proof of purchase within 7 days. Physical damage or liquid ingress voids coverage.",
                    terms_text_si="මුල් ඇසුරුම, අමතර කොටස් සහ මිලදී ගැනීමේ සාක්ෂි සහිතව දින 7ක් ඇතුළත භාණ්ඩය ආපසු ලබා දිය යුතුය. භෞතික හානි හෝ දියර කාන්දු වීම් ආවරණය නොවේ.",
                    terms_text_ta="பொருள் 7 நாட்களுக்குள் முழுமையான அசல் பேக்கேஜிங், பாகங்கள் மற்றும் கொள்முதல் சான்றுடன் திரும்பப் பெறப்பட வேண்டும். உடல் சேதம் அல்லது திரவ உட்செலுத்துதல் உத்தரவாதத்தை ரத்து செய்கிறது.",
                    exclusions_text="Physical damage, liquid damage, customer misuse, unauthorized repair attempts.",
                    exclusions_text_si="භෞතික හානි, දියර කාන්දු වීම, පාරිභෝගික අනිසි භාවිතය, අනවසර අලුත්වැඩියා උත්සාහයන්.",
                    exclusions_text_ta="உடல் சேதம், திரவ சேதம், வாடிக்கையாளர் தவறான பயன்பாடு, அங்கீகரிக்கப்படாத பழுது முயற்சிகள்.",
                    supplier_cover_months=0,
                    is_active=False,
                    is_template=True,
                ),
                WarrantyPolicy(
                    name="6 months shop warranty",
                    name_si="මාස 6ක කඩේ වගකීම",
                    name_ta="6 மாத கடை உத்தரவாதம்",
                    warranty_type="SHOP",
                    duration=6,
                    duration_unit="MONTHS",
                    remedy="REPAIR_OR_REPLACE",
                    provider_name=None,
                    terms_text="Free repair service provided for manufacturing defects within 6 months. Replacement provided if repair is not feasible within 14 working days.",
                    terms_text_si="මාස 6ක් ඇතුළත නිෂ්පාදන දෝෂ සඳහා නොමිලේ අලුත්වැඩියා සේවාව සැපයේ. වැඩ කරන දින 14ක් ඇතුළත අලුත්වැඩියා කළ නොහැකි නම් ආදේශනයක් ලබා දේ.",
                    terms_text_ta="6 மாதங்களுக்குள் உற்பத்தி குறைபாடுகளுக்கு இலவச பழுதுபார்க்கும் சேவை வழங்கப்படும். 14 வேலை நாட்களுக்குள் பழுதுபார்க்க முடியாவிட்டால் மாற்று வழங்கப்படும்.",
                    exclusions_text="Normal wear and tear, cosmetic damage, accidental drops, power surges, pest infestation.",
                    exclusions_text_si="සාමාන්‍ය ගෙවීම් සහ කැඩීම්, මතුපිට හානි, අහඹු වැටීම්, විදුලි සැර වැඩිවීම්, පළිබෝධ හානි.",
                    exclusions_text_ta="இயல்பான தேய்மானம், ஒப்பனை சேதம், தற்செயலான வீழ்ச்சி, மின் ஏற்ற இறக்கங்கள், பூச்சி தொல்லை.",
                    supplier_cover_months=6,
                    is_active=False,
                    is_template=True,
                ),
                WarrantyPolicy(
                    name="1 year shop warranty",
                    name_si="වසර 1ක කඩේ වගකීම",
                    name_ta="1 வருட கடை உத்தரவாதம்",
                    warranty_type="SHOP",
                    duration=1,
                    duration_unit="YEARS",
                    remedy="REPAIR_OR_REPLACE",
                    provider_name=None,
                    terms_text="Comprehensive 1-year shop warranty covering parts and labor for manufacturing defects. Free repair or like-for-like replacement at shop discretion.",
                    terms_text_si="නිෂ්පාදන දෝෂ සඳහා කොටස් සහ ශ්‍රමය ආවරණය වන සම්පූර්ණ වසර 1ක කඩේ වගකීම. කඩයේ තීරණය මත නොමිලේ අලුත්වැඩියාව හෝ සමාන ආදේශනයක්.",
                    terms_text_ta="உற்பத்தி குறைபாடுகளுக்கான உதிரிபாகங்கள் மற்றும் உழைப்பை உள்ளடக்கிய விரிவான 1 வருட கடை உத்தரவாதம். கடையின் விருப்பப்படி இலவச பழுதுபார்ப்பு அல்லது சமமான மாற்று.",
                    exclusions_text="Unauthorized modification, root/jailbreak, burnt components from lightning/surge, water damage.",
                    exclusions_text_si="අනවසර වෙනස්කම් කිරීම්, රූට්/ජේල්බ්‍රේක්, අකුණු/විදුලි සැරෙන් දැවී ගිය කොටස්, ජල හානි.",
                    exclusions_text_ta="அங்கீகரிக்கப்படாத மாற்றம், ரூட்/ஜெயில்பிரேக், மின்னல்/மின் ஏற்றத்தால் எரிந்த பாகங்கள், நீர் சேதம்.",
                    supplier_cover_months=12,
                    is_active=False,
                    is_template=True,
                ),
                WarrantyPolicy(
                    name="1 year manufacturer warranty",
                    name_si="වසර 1ක නිෂ්පාදක වගකීම",
                    name_ta="1 வருட உற்பத்தியாளர் உத்தரவாதம்",
                    warranty_type="MANUFACTURER",
                    duration=1,
                    duration_unit="YEARS",
                    remedy="REPAIR_OR_REPLACE",
                    provider_name="Authorized Service Center",
                    terms_text="Claims must be routed to the manufacturer authorized service center with original invoice. Shop acts as forwarding agent where requested.",
                    terms_text_si="හිමිකම් පෑම් මුල් ඉන්වොයිසිය සමඟ නිෂ්පාදකයාගේ බලයලත් සේවා මධ්‍යස්ථානය වෙත යොමු කළ යුතුය. ඉල්ලීමක් ඇති විට කඩය යොමු කිරීමේ නියෝජිතයෙකු ලෙස ක්‍රියා කරයි.",
                    terms_text_ta="அசல் இன்வாய்ஸுடன் உற்பத்தியாளர் அங்கீகரிக்கப்பட்ட சேவை மையத்திற்கு கோரிக்கைகள் அனுப்பப்பட வேண்டும். கோரப்பட்டால் கடை முன்னனுப்புதல் முகவராக செயல்படும்.",
                    exclusions_text="Manufacturer exclusions apply. Void if serial label removed, defaced or altered.",
                    exclusions_text_si="නිෂ්පාදකයාගේ බැහැර කිරීම් අදාළ වේ. අනුක්‍රමික අංක ලේබලය ඉවත් කර, විකෘති කර හෝ වෙනස් කර ඇත්නම් අවලංගු වේ.",
                    exclusions_text_ta="உற்பத்தியாளர் விலக்குகள் பொருந்தும். வரிசை எண் லேபிள் அகற்றப்பட்டால், அழிக்கப்பட்டால் அல்லது மாற்றப்பட்டால் செல்லாது.",
                    supplier_cover_months=12,
                    is_active=False,
                    is_template=True,
                ),
            ]
            session.add_all(templates)

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
