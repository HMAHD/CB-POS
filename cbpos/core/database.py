import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

from cbpos.config import Config
from cbpos.core.services.config_service import ConfigService

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class Database:
    """Singleton Database Manager with Engine Factory.

    Supports both Standalone (SQLite) and Network (PostgreSQL) modes.

    Network mode includes:
    - Configurable transaction isolation level
    - Pool pre-ping to detect stale connections
    """

    _instance = None

    def __new__(cls):
        """Return the singleton instance, initializing the engine/session factory on first call."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the database engine and session factory."""
        db_mode = ConfigService.get("db_mode") or "standalone"
        self._db_mode = db_mode

        if db_mode == "standalone":
            db_uri = self._get_sqlite_uri()
            connect_args = {"check_same_thread": False}
            pool_args = {}
        else:  # network mode
            db_uri = self._get_postgres_uri()
            statement_timeout = ConfigService.get("db_statement_timeout") or 30
            timeout_ms = int(statement_timeout) * 1000
            connect_args = {"options": f"-c statement_timeout={timeout_ms}"}
            pool_args = {
                "poolclass": QueuePool,
                "pool_size": 10,
                "max_overflow": 20,
                "pool_pre_ping": True,
            }

        self.engine = create_engine(
            db_uri,
            echo=False,
            connect_args=connect_args,
            **pool_args,
        )

        # Configure SQLite PRAGMAs for performance and safety
        if db_mode == "standalone":

            @event.listens_for(self.engine, "connect")
            def _set_sqlite_pragmas(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    def _get_sqlite_uri(self) -> str:
        """Generate SQLite database URI."""
        return Config.DB_URI

    def _get_postgres_uri(self) -> str:
        """Generate PostgreSQL database URI from network settings."""
        return ConfigService.get_postgres_uri()

    @staticmethod
    def test_connection(
        mode: str = "standalone",
        host: str | None = None,
        port: int | None = None,
        dbname: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> tuple[bool, str]:
        """Test database connection without modifying the singleton instance.

        Args:
            mode: "standalone" or "network"
            host: Database host (for network mode)
            port: Database port (for network mode)
            dbname: Database name (for network mode)
            user: Database username (for network mode)
            password: Database password (for network mode)

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if mode == "standalone":
                test_uri = Config.DB_URI
                test_engine = create_engine(test_uri, echo=False)
            else:
                if not all([host, port, dbname, user]):
                    return False, "Missing required connection parameters"

                url_obj = URL.create(
                    drivername="postgresql+psycopg2",
                    username=user,
                    password=password,
                    host=host,
                    port=port,
                    database=dbname,
                )
                test_engine = create_engine(url_obj, echo=False, pool_pre_ping=True)

            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            test_engine.dispose()
            return True, "Connection successful"

        except Exception as e:
            return False, f"Connection failed: {e!s}"

    def create_tables(self):
        """Create all tables defined in Base metadata."""
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self, serializable: bool = False) -> Generator[Session, None, None]:
        """Context manager for database sessions.

        Ensures sessions are closed and transactions are handled.

        Args:
            serializable: If True and running in network (PostgreSQL) mode,
                          use SERIALIZABLE isolation level for this session.
                          Use for financial operations that must not have
                          phantom reads (stock checks, credit updates,
                          document number generation).
        """
        session = self.SessionLocal()
        try:
            # Set isolation level for PostgreSQL when requested
            if serializable and self._db_mode == "network":
                session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))

            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def get_db_session():
    """Helper to get a database session."""
    return Database().get_session()
