"""Local identity service for tracking database instance IDs (#866)."""

import logging
import uuid

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from cbpos.core.database import Database
from cbpos.core.models import LocalIdentity

logger = logging.getLogger(__name__)


class LocalIdentityService:
    """Manages the unique, persistent database instance UUID (db_instance_id).

    Every database instance gets a UUID upon creation or migration. When a till
    is restored from backup, the instance ID is regenerated so the Main PC knows
    this till represents a new database lifecycle (#866).
    """

    _ephemeral_id: str | None = None

    @classmethod
    def get(cls, db: Database | None = None, db_uri: str | None = None) -> str:
        """Return the current database's instance UUID, generating one if not set."""
        if db_uri:
            engine = create_engine(db_uri)
            try:
                with Session(engine) as session:
                    try:
                        row = session.execute(select(LocalIdentity)).scalar_one_or_none()
                    except Exception:
                        LocalIdentity.__table__.create(session.bind, checkfirst=True)
                        row = None
                    if row is not None:
                        return row.db_instance_id
                    new_id = str(uuid.uuid4())
                    session.add(LocalIdentity(db_instance_id=new_id))
                    session.commit()
                    return new_id
            finally:
                engine.dispose()

        try:
            active_db = db or Database()
            with active_db.get_session() as session:
                try:
                    row = session.query(LocalIdentity).first()
                except Exception:
                    session.rollback()
                    LocalIdentity.__table__.create(session.bind, checkfirst=True)
                    row = None
                if row is not None:
                    return row.db_instance_id
                new_id = str(uuid.uuid4())
                session.add(LocalIdentity(db_instance_id=new_id))
                session.commit()
                return new_id
        except Exception as e:
            logger.debug("Could not get persistent db_instance_id, using ephemeral: %s", e)
            if not cls._ephemeral_id:
                cls._ephemeral_id = str(uuid.uuid4())
            return cls._ephemeral_id

    @classmethod
    def regenerate(cls, db: Database | None = None, db_uri: str | None = None) -> str:
        """Generate a fresh UUID instance ID and persist it, replacing any old identity."""
        new_id = str(uuid.uuid4())
        if db_uri:
            engine = create_engine(db_uri)
            try:
                with Session(engine) as session:
                    session.execute(delete(LocalIdentity))
                    session.add(LocalIdentity(db_instance_id=new_id))
                    session.commit()
                    logger.info("Regenerated local database identity on %s to %s", db_uri, new_id)
                    return new_id
            finally:
                engine.dispose()

        active_db = db or Database()
        with active_db.get_session() as session:
            session.query(LocalIdentity).delete()
            session.add(LocalIdentity(db_instance_id=new_id))
            session.commit()
            logger.info("Regenerated local database identity to %s", new_id)
            return new_id
