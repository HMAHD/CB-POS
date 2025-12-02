from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from cbpos.config import Config


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class Database:
    """
    Singleton Database Manager.
    Handles engine creation and session management.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the database engine and session factory."""
        connect_args = {}
        if "sqlite" in Config.DB_URI:
            connect_args = {"check_same_thread": False}
            pool_args = {}
        else:
            pool_args = {
                "pool_size": 10,
                "max_overflow": 20,
            }

        self.engine = create_engine(
            Config.DB_URI,
            echo=False,
            pool_pre_ping=True,
            connect_args=connect_args,
            **pool_args,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)

    def create_tables(self):
        """Create all tables defined in Base metadata."""
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions.
        Ensures sessions are closed and transactions are handled.
        """
        session = self.SessionLocal()
        try:
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
