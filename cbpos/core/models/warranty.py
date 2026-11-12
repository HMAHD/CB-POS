"""Warranty policy model for Phase 9 (#821, #820)."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func
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
