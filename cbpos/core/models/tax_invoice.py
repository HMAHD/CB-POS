"""SQLAlchemy models for Sri Lankan VAT Tax Invoices and Credit Notes.

Implements statutory requirements under VAT Act No. 14 of 2002 Section 20,
Gazette Extraordinary No. 2481/22, and Gazette Extraordinary No. 2500/106.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cbpos.core.database import Base

if TYPE_CHECKING:
    from cbpos.core.models import Product, Sale, User


class TaxInvoice(Base):
    """An official VAT Tax Invoice issued pursuant to VAT Act No. 14 of 2002 Section 20.

    Preserves immutable snapshots of seller, buyer, line items, and monetary facts
    so reprints remain legally and factually identical over the mandatory 5-year retention period.
    """

    __tablename__ = "tax_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), unique=True, index=True, nullable=False)
    serial: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    supply_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    issued_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Immutable Supplier Snapshots
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_address: Mapped[str] = mapped_column(Text, nullable=False)
    supplier_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    supplier_tin: Mapped[str] = mapped_column(String(20), nullable=False)

    # Immutable Buyer Snapshots
    buyer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_address: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    buyer_tin: Mapped[str] = mapped_column(String(20), nullable=False)

    # Document State & Metadata
    issue_language: Mapped[str] = mapped_column(String(5), default="en", server_default="en", nullable=False)
    print_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    original_printed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Monetary & Tax Reconciliation (Decimal, 2 decimal places)
    subtotal_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_in_words: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    # Relationships
    sale: Mapped["Sale"] = relationship("Sale")
    issued_by_user: Mapped["User"] = relationship("User")
    lines: Mapped[list["TaxInvoiceLine"]] = relationship("TaxInvoiceLine", back_populates="tax_invoice")

    @property
    def serial_number(self) -> str:
        """Alias for serial column."""
        return self.serial


class TaxInvoiceLine(Base):
    """An immutable line item on an official VAT Tax Invoice."""

    __tablename__ = "tax_invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    tax_invoice_id: Mapped[int] = mapped_column(
        ForeignKey("tax_invoices.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    item_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    item_code_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_snapshot: Mapped[str] = mapped_column(String(20), default="pcs", server_default="pcs", nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    tax_invoice: Mapped["TaxInvoice"] = relationship("TaxInvoice", back_populates="lines")
    product: Mapped["Product | None"] = relationship("Product")


class TaxInvoiceSequence(Base):
    """Tracks sequence numbers per monthly prefix for atomic YYMMM_QQQQ_XXXXX generation."""

    __tablename__ = "tax_invoice_sequences"

    id: Mapped[int] = mapped_column(primary_key=True)
    prefix: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    last_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class TaxCreditNote(Base):
    """An official VAT Tax Credit Note issued pursuant to VAT Act No. 14 of 2002 Section 25."""

    __tablename__ = "tax_credit_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tax_invoice_id: Mapped[int] = mapped_column(
        ForeignKey("tax_invoices.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    refund_sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), unique=True, index=True, nullable=False)
    serial: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    issued_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_in_words: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    tax_invoice: Mapped["TaxInvoice"] = relationship("TaxInvoice")
    refund_sale: Mapped["Sale"] = relationship("Sale")
    issued_by_user: Mapped["User"] = relationship("User")
