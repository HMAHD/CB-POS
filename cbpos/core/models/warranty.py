"""Warranty policy model for Phase 9 (#821, #820)."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cbpos.core.database import Base


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, index=True, nullable=False
    )

    __table_args__ = (
        CheckConstraint("duration > 0", name="ck_warranty_policy_duration"),
        CheckConstraint("duration_unit IN ('DAYS', 'MONTHS', 'YEARS')", name="ck_warranty_policy_unit"),
        CheckConstraint("warranty_type IN ('SHOP', 'MANUFACTURER', 'EXTENDED')", name="ck_warranty_policy_type"),
        CheckConstraint(
            "remedy IN ('REPAIR_OR_REPLACE', 'REPAIR_ONLY', 'REPLACE_ONLY', 'REFUND')",
            name="ck_warranty_policy_remedy",
        ),
    )

    def get_display_name(self, lang: str | None = None) -> str:
        """Return the policy name in the requested or active language with fallbacks."""
        if lang is None:
            try:
                from cbpos.i18n import get_language

                lang = get_language()
            except Exception:
                lang = "en"
        lang = (lang or "en").lower()
        if lang == "si":
            name = (self.name_si or "").strip()
            if name:
                return name
        elif lang == "ta":
            name = (self.name_ta or "").strip()
            if name:
                return name
        return self.name

    def get_terms(self, lang: str | None = None) -> str:
        """Return terms text in the requested or active language with fallback to English."""
        if lang is None:
            try:
                from cbpos.i18n import get_language

                lang = get_language()
            except Exception:
                lang = "en"
        lang = (lang or "en").lower()
        if lang == "si":
            terms = (self.terms_text_si or "").strip()
            if terms:
                return terms
        elif lang == "ta":
            terms = (self.terms_text_ta or "").strip()
            if terms:
                return terms
        return self.terms_text or ""

    def get_exclusions(self, lang: str | None = None) -> str:
        """Return exclusions text in the requested or active language with fallback to English."""
        if lang is None:
            try:
                from cbpos.i18n import get_language

                lang = get_language()
            except Exception:
                lang = "en"
        lang = (lang or "en").lower()
        if lang == "si":
            ex = (self.exclusions_text_si or "").strip()
            if ex:
                return ex
        elif lang == "ta":
            ex = (self.exclusions_text_ta or "").strip()
            if ex:
                return ex
        return self.exclusions_text or ""
