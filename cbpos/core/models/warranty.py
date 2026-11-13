"""Warranty and warranty policy models for Phase 9 (#821, #822, #820)."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cbpos.core.database import Base

if TYPE_CHECKING:
    from cbpos.core.models import Customer, Product, Sale, SaleItem


class WarrantyPolicy(Base):
    """Warranty policy defining coverage duration, provider, remedy, terms and supplier coverage."""

    __tablename__ = "warranty_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_si: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name_ta: Mapped[str | None] = mapped_column(String(100), nullable=True)
    warranty_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SHOP, MANUFACTURER, EXTENDED
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[str] = mapped_column(String(10), nullable=False)  # DAYS, MONTHS, YEARS
    remedy: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # REPAIR_OR_REPLACE, REPAIR_ONLY, REPLACE_ONLY, REFUND
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    terms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_text_si: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_text_ta: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusions_text_si: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusions_text_ta: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier_cover_months: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False, index=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), nullable=False
    )
    last_modified: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, index=True, nullable=False
    )

    __table_args__ = (
        CheckConstraint("duration > 0", name="ck_warranty_policy_duration"),
        CheckConstraint("duration_unit IN ('DAYS', 'MONTHS', 'YEARS')", name="ck_warranty_policy_unit"),
        CheckConstraint("warranty_type IN ('SHOP', 'MANUFACTURER', 'EXTENDED')", name="ck_warranty_policy_type"),
        CheckConstraint(
            "remedy IN ('REPAIR_OR_REPLACE', 'REPAIR_ONLY', 'REPLACE_ONLY', 'REFUND')",
            name="ck_warranty_policy_remedy",
        ),
        CheckConstraint("supplier_cover_months >= 0", name="ck_warranty_policy_supplier_cover_months"),
    )

    def _resolve_localized_field(self, field_base: str, lang: str | None = None) -> str:
        """Resolve localized field (e.g. 'name', 'terms_text', 'exclusions_text') with English fallback."""
        if lang is None:
            try:
                from cbpos.i18n import get_language

                lang = get_language()
            except (ImportError, LookupError, AttributeError):
                lang = "en"
        lang = (lang or "en").lower()
        if lang in ("si", "ta"):
            localized_val = getattr(self, f"{field_base}_{lang}", None)
            if localized_val and str(localized_val).strip():
                return str(localized_val).strip()
        default_val = getattr(self, field_base, None)
        return str(default_val).strip() if default_val else ""

    def get_display_name(self, lang: str | None = None) -> str:
        """Return the policy name in the requested or active language with fallbacks."""
        return self._resolve_localized_field("name", lang) or self.name

    def get_terms(self, lang: str | None = None) -> str:
        """Return terms text in the requested or active language with fallback to English."""
        return self._resolve_localized_field("terms_text", lang)

    def get_exclusions(self, lang: str | None = None) -> str:
        """Return exclusions text in the requested or active language with fallback to English."""
        return self._resolve_localized_field("exclusions_text", lang)


class Warranty(Base):
    """A per-unit warranty issued upon sale of a covered product (#822, #820)."""

    __tablename__ = "warranties"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    unit_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Foreign Keys (Restricted deletion to preserve transaction history)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"), index=True, nullable=False)
    sale_item_id: Mapped[int] = mapped_column(
        ForeignKey("sale_items.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("warranty_policies.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    # Customer Snapshots
    customer_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_phone_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Serial Number (Reserved for W3 #823; nullable in W2)
    serial_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Policy Snapshots (Immutable capture of terms at time of sale, CAA s.31(g))
    warranty_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SHOP, MANUFACTURER, EXTENDED
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[str] = mapped_column(String(10), nullable=False)  # DAYS, MONTHS, YEARS
    remedy: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # REPAIR_OR_REPLACE, REPAIR_ONLY, REPLACE_ONLY, REFUND
    provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    terms_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    # Coverage Dates (Inclusive end date: valid until end_date 23:59:59)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Lifecycle Status: ACTIVE, VOID, CANCELLED, REPLACED, CLOSED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)

    # Lifecycle Links
    cancelled_by_sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    covers_warranty_id: Mapped[int | None] = mapped_column(
        ForeignKey("warranties.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    replaces_warranty_id: Mapped[int | None] = mapped_column(
        ForeignKey("warranties.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    # Multi-terminal & Auditing
    terminal_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), nullable=False
    )
    last_modified: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now, nullable=False, index=True
    )

    # Relationships
    sale: Mapped["Sale"] = relationship("Sale", foreign_keys=[sale_id], back_populates="warranties")
    sale_item: Mapped["SaleItem"] = relationship("SaleItem", foreign_keys=[sale_item_id], back_populates="warranties")
    product: Mapped["Product"] = relationship("Product", foreign_keys=[product_id])
    customer: Mapped[Optional["Customer"]] = relationship("Customer", foreign_keys=[customer_id])
    policy: Mapped[Optional["WarrantyPolicy"]] = relationship("WarrantyPolicy", foreign_keys=[policy_id])
    cancelled_by_sale: Mapped[Optional["Sale"]] = relationship("Sale", foreign_keys=[cancelled_by_sale_id])
    covered_warranty: Mapped[Optional["Warranty"]] = relationship(
        "Warranty", foreign_keys=[covers_warranty_id], remote_side=[id]
    )
    replaced_warranty: Mapped[Optional["Warranty"]] = relationship(
        "Warranty", foreign_keys=[replaces_warranty_id], remote_side=[id]
    )

    __table_args__ = (
        CheckConstraint("duration > 0", name="ck_warranties_duration"),
        CheckConstraint("duration_unit IN ('DAYS', 'MONTHS', 'YEARS')", name="ck_warranties_duration_unit"),
        CheckConstraint("warranty_type IN ('SHOP', 'MANUFACTURER', 'EXTENDED')", name="ck_warranties_warranty_type"),
        CheckConstraint(
            "remedy IN ('REPAIR_OR_REPLACE', 'REPAIR_ONLY', 'REPLACE_ONLY', 'REFUND')",
            name="ck_warranties_remedy",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'VOID', 'CANCELLED', 'REPLACED', 'CLOSED')",
            name="ck_warranties_status",
        ),
        CheckConstraint("end_date >= start_date", name="ck_warranties_dates"),
        CheckConstraint("unit_index > 0", name="ck_warranties_unit_index"),
        Index("ix_warranties_sale_item_status_unit", "sale_item_id", "status", "unit_index"),
    )

    @property
    def is_expired(self) -> bool:
        """Derived property: return True if end_date has passed."""
        return date.today() > self.end_date
