"""Warranty claim models for Phase 9 (#826, #820)."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cbpos.core.database import Base
from cbpos.core.models import Document

if TYPE_CHECKING:
    from cbpos.core.models import Customer, Product, User, Warranty


class WarrantyClaim(Document):
    """Warranty claim document tracking intake, defect, inspection, supplier dispatch, resolution, and collection (#826)."""

    __tablename__ = "warranty_claims"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    warranty_id: Mapped[int | None] = mapped_column(
        ForeignKey("warranties.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    customer_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_phone_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    item_serial: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claim_status: Mapped[str] = mapped_column(String(30), nullable=False, default="INTAKE", index=True)
    intake_date: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), nullable=False, index=True
    )
    defect_description: Mapped[str] = mapped_column(Text, nullable=False)
    item_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    accessories_received: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_covered: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(30), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    replacement_warranty_id: Mapped[int | None] = mapped_column(
        ForeignKey("warranties.id", ondelete="SET NULL"), nullable=True, index=True
    )
    replacement_serial: Mapped[str | None] = mapped_column(String(64), nullable=True)
    repair_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    charge_customer: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    collected_by_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    warranty: Mapped[Optional["Warranty"]] = relationship(
        "Warranty", foreign_keys=[warranty_id], back_populates="claims"
    )
    product: Mapped[Optional["Product"]] = relationship("Product", foreign_keys=[product_id])
    customer: Mapped[Optional["Customer"]] = relationship("Customer", foreign_keys=[customer_id])
    resolved_by_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[resolved_by_user_id])
    replacement_warranty: Mapped[Optional["Warranty"]] = relationship(
        "Warranty", foreign_keys=[replacement_warranty_id]
    )
    events: Mapped[list["WarrantyClaimEvent"]] = relationship(
        "WarrantyClaimEvent",
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="WarrantyClaimEvent.event_time",
    )

    __mapper_args__ = {
        "polymorphic_identity": "warranty_claim",
    }

    __table_args__ = (
        CheckConstraint(
            "claim_status IN ('INTAKE', 'IN_INSPECTION', 'SUPPLIER_DISPATCHED', 'SUPPLIER_RETURNED', 'RESOLVED', 'COLLECTED', 'REJECTED', 'VOID', 'CANCELLED')",
            name="ck_warranty_claims_status",
        ),
        CheckConstraint(
            "resolution IS NULL OR resolution IN ('REPAIRED', 'REPLACED_SAME', 'REPLACED_DIFFERENT', 'REFUNDED', 'REJECTED_UNCOVERED')",
            name="ck_warranty_claims_resolution",
        ),
        Index(
            "uq_warranty_active_claim",
            "warranty_id",
            unique=True,
            sqlite_where=text(
                "claim_status NOT IN ('COLLECTED', 'REJECTED', 'VOID', 'CANCELLED') AND warranty_id IS NOT NULL"
            ),
            postgresql_where=text(
                "claim_status NOT IN ('COLLECTED', 'REJECTED', 'VOID', 'CANCELLED') AND warranty_id IS NOT NULL"
            ),
        ),
    )


class WarrantyClaimEvent(Base):
    """Audit event for claim lifecycle transitions (#826)."""

    __tablename__ = "warranty_claim_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("warranty_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    event_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    claim: Mapped["WarrantyClaim"] = relationship("WarrantyClaim", back_populates="events")
    user: Mapped["User"] = relationship("User")
