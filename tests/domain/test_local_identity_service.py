"""Tests for LocalIdentityService (#866)."""

import uuid

import pytest
from sqlalchemy import create_engine

from cbpos.core.database import Base
from cbpos.core.models import LocalIdentity
from cbpos.core.services.local_identity_service import LocalIdentityService


@pytest.fixture
def clean_identity(db_session):
    """Ensure clean local_identity table before test."""
    db_session.query(LocalIdentity).delete()
    db_session.commit()


def test_issue_866_get_initializes_and_persists_uuid(clean_identity, db_session):
    """LocalIdentityService.get() creates a UUID4 and returns the same ID across calls."""
    id1 = LocalIdentityService.get()
    assert id1
    # Verify it is a valid UUID
    uuid.UUID(id1)

    id2 = LocalIdentityService.get()
    assert id1 == id2

    # Check database row
    row = db_session.query(LocalIdentity).first()
    assert row is not None
    assert row.db_instance_id == id1


def test_issue_866_regenerate_creates_new_instance_id(clean_identity, db_session):
    """LocalIdentityService.regenerate() generates a fresh UUID replacing the old one."""
    initial_id = LocalIdentityService.get()
    new_id = LocalIdentityService.regenerate()

    assert initial_id != new_id
    uuid.UUID(new_id)

    # Next get() returns the new ID
    assert LocalIdentityService.get() == new_id

    # Exactly one row exists in local_identity
    assert db_session.query(LocalIdentity).count() == 1


def test_issue_866_regenerate_with_db_uri(tmp_path):
    """LocalIdentityService.regenerate(db_uri=...) works on a standalone DB file."""
    db_file = tmp_path / "standalone.db"
    db_uri = f"sqlite:///{db_file}"
    engine = create_engine(db_uri)
    Base.metadata.create_all(engine)
    engine.dispose()

    # Pre-condition: get returns an ID on that URI
    id1 = LocalIdentityService.get(db_uri=db_uri)
    assert id1
    uuid.UUID(id1)

    # Regenerate on db_uri
    id2 = LocalIdentityService.regenerate(db_uri=db_uri)
    assert id1 != id2
    assert LocalIdentityService.get(db_uri=db_uri) == id2
