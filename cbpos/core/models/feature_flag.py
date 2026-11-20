"""Feature flag model for database-backed feature toggles (#942)."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cbpos.core.database import Base

if TYPE_CHECKING:
    from cbpos.core.models import User


class FeatureFlag(Base):
    """Database-backed feature flag shared across terminals and synced via LAN catalog sync (#942)."""

    __tablename__ = "feature_flags"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        index=True,
        nullable=False,
    )
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    user: Mapped[Optional["User"]] = relationship("User")
