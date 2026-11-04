"""CB-POS domain and persistence models.

Contains SQLAlchemy declarative ORM models spanning users, authentication, products,
inventory, suppliers, price lists, promotions, sales, documents, and audit logging.
"""

from datetime import datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cbpos.core.constants.status import PaymentMethodKind
from cbpos.core.database import Base

# --- Association Tables ---
product_suppliers = Table(
    "product_suppliers",
    Base.metadata,
    Column("product_id", Integer, ForeignKey("products.id"), primary_key=True),
    Column("supplier_id", Integer, ForeignKey("suppliers.id"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)


# --- Auth & Permissions ---
class Role(Base):
    """A named permission bundle (Admin/Manager/Cashier, or custom) assigned to users."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    access_level: Mapped[int] = mapped_column(Integer, default=0)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)
    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions, back_populates="roles")


class Permission(Base):
    """A single grantable permission code; `group` clusters codes for UI display (see `Permissions` constants)."""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))
    group: Mapped[str] = mapped_column(String(50), default="General")
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    roles: Mapped[list["Role"]] = relationship(secondary=role_permissions, back_populates="permissions")


class User(Base):
    """A login account (cashier, manager, or admin) with PIN-based auth and database-backed brute-force lockout."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Brute-force protection (database-backed, survives restarts)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    role: Mapped["Role"] = relationship()


# --- Pricing Engine ---
class PriceList(Base):
    """A named, optionally time-boxed set of per-product price overrides (e.g. wholesale, VIP), assignable to customers."""

    __tablename__ = "price_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    items: Mapped[list["PriceListItem"]] = relationship(back_populates="price_list", cascade="all, delete-orphan")


class PriceListItem(Base):
    """One product's price override within a `PriceList`."""

    __tablename__ = "price_list_items"
    __table_args__ = (UniqueConstraint("price_list_id", "product_id", name="uq_pricelist_product"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    price_list_id: Mapped[int] = mapped_column(ForeignKey("price_lists.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    price_list: Mapped["PriceList"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class Promotion(Base):
    """A scheduled discount rule (percentage/fixed/BOGO) scoped to one category, or store-wide when `category_id` is NULL."""

    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    days_of_week: Mapped[str | None] = mapped_column(String(50), nullable=True)  # JSON or CSV: "0,1,2" (Mon,Tue,Wed)
    daily_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    daily_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # PERCENTAGE, FIXED_AMOUNT, BOGO
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Scopes the promotion to one category's products; NULL means store-wide (all products).
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    category: Mapped[Optional["Category"]] = relationship()


# --- Unified Document Architecture ---
class VoidReason(Base):
    """A selectable reason code required when voiding a document, kept for audit purposes."""

    __tablename__ = "void_reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)


class Document(Base):
    """Base class for all transactional documents via joined-table inheritance.

    Sale, Purchase, Proforma, and StockCount all extend this, sharing document
    numbering, the ``type`` polymorphic discriminator, voiding, and audit fields.
    See CLAUDE.md's Document Polymorphism section.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED", index=True)  # COMPLETED, VOID, DRAFT
    reference_external: Mapped[str | None] = mapped_column(String(100), nullable=True)
    void_reason_id: Mapped[int | None] = mapped_column(ForeignKey("void_reasons.id"), nullable=True)

    terminal_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    origin_terminal_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    user: Mapped["User"] = relationship()
    void_reason: Mapped["VoidReason"] = relationship()

    __mapper_args__ = {
        "polymorphic_on": type,
        "polymorphic_identity": "document",
    }


class Sale(Document):
    """A completed (or voided/refunded) point-of-sale transaction: line items, payments, tax breakdown, and an optional link back to the original sale for refunds."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax_sscl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    net_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    additional_discount_type: Mapped[str] = mapped_column(String(20), default="NONE")
    additional_discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    loyalty_points_redeemed: Mapped[int] = mapped_column(Integer, default=0)
    loyalty_points_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    loyalty_points_earned: Mapped[int] = mapped_column(Integer, default=0)
    loyalty_points_balance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)  # Primary method
    refund_of_sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), nullable=True)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True, index=True)

    customer: Mapped["Customer"] = relationship(back_populates="sales")
    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    payments: Mapped[list["SalePayment"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    refund_of_sale: Mapped["Sale"] = relationship("Sale", remote_side=[id], foreign_keys=[refund_of_sale_id])
    shift: Mapped["Shift | None"] = relationship("Shift")

    @property
    def tendered(self) -> Decimal | None:
        """Total amount tendered across all payments, if any payment was overtendered."""
        if not hasattr(self, "payments") or not self.payments:
            return None
        has_overtender = any(p.tendered_amount is not None for p in self.payments)
        if not has_overtender:
            return None
        return sum((p.tendered_amount if p.tendered_amount is not None else p.amount) for p in self.payments)

    @property
    def change(self) -> Decimal | None:
        """Total change given, if any payment was overtendered."""
        tendered_val = self.tendered
        if tendered_val is None:
            return None
        diff = tendered_val - (self.total_amount or Decimal("0.00"))
        return diff if diff > 0 else Decimal("0.00")

    __mapper_args__ = {
        "polymorphic_identity": "sale",
    }


class Purchase(Document):
    """A goods-received transaction from a supplier; updates stock and the supplier's payable balance."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    input_vat: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0
    )  # VAT paid to supplier, from their invoice -- deductible against Output VAT
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), nullable=True)

    supplier: Mapped["Supplier"] = relationship(back_populates="purchases")
    items: Mapped[list["PurchaseItem"]] = relationship(back_populates="purchase", cascade="all, delete-orphan")
    purchase_order: Mapped["PurchaseOrder | None"] = relationship(foreign_keys=[purchase_order_id])

    __mapper_args__ = {
        "polymorphic_identity": "purchase",
    }


class PurchaseOrder(Document):
    """A supplier order awaiting receipt, created from Reorder suggestions.

    Tracked independently of the `Purchase` (GRN) row(s) that eventually
    receive it, so one order can be received in full or partially across
    multiple separate GRNs (#486).
    """

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))

    supplier: Mapped["Supplier"] = relationship("Supplier")
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )

    __mapper_args__ = {
        "polymorphic_identity": "purchase_order",
    }


class Proforma(Document):
    """A non-binding quote that can expire or be converted into a real `Sale`."""

    __tablename__ = "proformas"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax_sscl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    validity_days: Mapped[int] = mapped_column(Integer, default=30)
    expiry_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    converted_sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped["Customer"] = relationship("Customer")
    items: Mapped[list["ProformaItem"]] = relationship(back_populates="proforma", cascade="all, delete-orphan")
    converted_sale: Mapped["Sale"] = relationship("Sale", foreign_keys=[converted_sale_id])

    __mapper_args__ = {
        "polymorphic_identity": "proforma",
    }


class ProformaItem(Base):
    """One line item on a `Proforma`, denormalized (product name/price) so a historical quote stays accurate even if the product changes later."""

    __tablename__ = "proforma_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    proforma_id: Mapped[int] = mapped_column(ForeignKey("proformas.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(20), default="NONE")
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    proforma: Mapped["Proforma"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship("Product")


# --- Core Business Entities ---
class Unit(Base):
    """Unit of measurement for products (e.g., kg, piece, liter, pack)."""

    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(10), nullable=False)
    decimal_places: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    products: Mapped[list["Product"]] = relationship(back_populates="unit")


class Category(Base):
    """A product category. Supports one level of parent/subcategory nesting and can be marked tax-exempt."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#FFFFFF")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    tax_exempt: Mapped[bool] = mapped_column(Boolean, default=False)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    products: Mapped[list["Product"]] = relationship(back_populates="category")
    parent: Mapped["Category"] = relationship("Category", remote_side=[id], back_populates="subcategories")
    subcategories: Mapped[list["Category"]] = relationship("Category", back_populates="parent")


class Product(Base):
    """A sellable/purchasable item: pricing, stock quantity, unit, category, and
    optional composite-item/variant relationships.

    Uses SQLAlchemy optimistic locking (`version_id`) to guard concurrent
    stock updates across terminals.
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_si: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name_ta: Mapped[str | None] = mapped_column(String(200), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    stock_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=0)
    is_weighted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_composite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_service: Mapped[bool] = mapped_column(Boolean, default=False)
    price_change_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    is_age_restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=0)
    preferred_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=0)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    default_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # Optimistic Locking
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    category: Mapped["Category"] = relationship(back_populates="products", lazy="joined")
    unit: Mapped[Optional["Unit"]] = relationship(back_populates="products", lazy="joined")
    parent: Mapped["Product"] = relationship("Product", remote_side=[id], back_populates="variants")
    variants: Mapped[list["Product"]] = relationship("Product", back_populates="parent")
    components: Mapped[list["CompositeItem"]] = relationship(
        "CompositeItem",
        foreign_keys="CompositeItem.parent_product_id",
        back_populates="parent",
    )
    suppliers: Mapped[list["Supplier"]] = relationship(secondary=product_suppliers, back_populates="products")
    default_supplier: Mapped[Optional["Supplier"]] = relationship("Supplier", foreign_keys=[default_supplier_id])

    __mapper_args__ = {"version_id_col": version_id}  # Enable Optimistic Locking

    def get_display_name(self, lang: str | None = None) -> str:
        """Return the product name in the requested or active language with fallbacks (#586)."""
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

        # Fallback to English, then whichever name is populated
        if (self.name_en or "").strip():
            return self.name_en.strip()
        if (self.name_si or "").strip():
            return self.name_si.strip()
        if (self.name_ta or "").strip():
            return self.name_ta.strip()
        return ""

    @property
    def display_name(self) -> str:
        """Product name in the current UI language, falling back to English or any populated name."""
        return self.get_display_name()


class Customer(Base):
    """A customer record, optionally a company, with credit-limit/current-debt tracking for the Credit Book and loyalty points."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_company: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String(50), nullable=True)  # VAT registration number
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)  # TIN (Taxpayer Identification Number)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    current_debt: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    payment_terms: Mapped[int] = mapped_column(Integer, default=0)  # Days
    loyalty_points: Mapped[int] = mapped_column(default=0)
    loyalty_card_code: Mapped[str | None] = mapped_column(String(50), unique=True, index=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    price_list_id: Mapped[int | None] = mapped_column(ForeignKey("price_lists.id"), nullable=True)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)
    # LAN Sync (#680): False only for a customer created on a till that the
    # Main PC doesn't have yet. Edits don't clear it -- the Main PC owns
    # customer details; tills push only the customers they create.
    synced: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    sales: Mapped[list["Sale"]] = relationship(back_populates="customer")
    price_list: Mapped["PriceList"] = relationship()
    contacts: Mapped[list["CustomerContact"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class CustomerContact(Base):
    """An additional contact person for a company customer (e.g. an accounts-payable contact)."""

    __tablename__ = "customer_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="contacts")


class Supplier(Base):
    """A goods supplier, with a running payable balance and the products they supply."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tax_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_details: Mapped[str | None] = mapped_column(String(200), nullable=True)  # Extra details
    current_payable: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    payment_terms: Mapped[int] = mapped_column(Integer, default=0)  # Days
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)

    purchases: Mapped[list["Purchase"]] = relationship(back_populates="supplier")
    products: Mapped[list["Product"]] = relationship(secondary=product_suppliers, back_populates="suppliers")


# --- Details & Logs ---
class SaleItem(Base):
    """One product line within a `Sale`, capturing the price actually charged (post-discount/manual-override) alongside the original price for reporting."""

    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    original_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(20), default="NONE")  # NONE, PERCENTAGE, FIXED
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    is_manual_price: Mapped[bool] = mapped_column(Boolean, default=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)  # internal-only, never printed

    sale: Mapped["Sale"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship("Product")


class SalePayment(Base):
    """One payment applied to a `Sale`; a sale can be split across multiple payment methods."""

    __tablename__ = "sale_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)  # Display snapshot
    method_kind: Mapped[str] = mapped_column(
        String(20),
        default=PaymentMethodKind.OTHER,
        server_default=PaymentMethodKind.OTHER,
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tendered_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    sale: Mapped["Sale"] = relationship(back_populates="payments")

    def __init__(self, *args, **kwargs):
        if "method_kind" not in kwargs and "payment_method" in kwargs:
            from cbpos.core.services.payment_service import classify_method_name

            kwargs["method_kind"] = classify_method_name(kwargs.get("payment_method"))
        super().__init__(*args, **kwargs)


class PurchaseItem(Base):
    """One product line received in a `Purchase`, at the cost paid to the supplier."""

    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    qty_received: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    purchase_order_item_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_items.id"), nullable=True)

    purchase: Mapped["Purchase"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship("Product")
    purchase_order_item: Mapped["PurchaseOrderItem | None"] = relationship()


class PurchaseOrderItem(Base):
    """One product line on a `PurchaseOrder`, with the running quantity received against it (#486)."""

    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    qty_ordered: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    qty_received: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=0)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship("Product")


class StockMovement(Base):
    """An audit-trail row for every stock quantity change: the reason (`MovementType`) and the running balance immediately after the change."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    qty_change: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # SALE, PURCHASE, ADJUSTMENT, RETURN, VOID
    terminal_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    product: Mapped["Product"] = relationship()
    user: Mapped["User"] = relationship()
    document: Mapped["Document"] = relationship()


class CompositeItem(Base):
    """A bill-of-materials line: how many units of a child product make up one unit of a composite/bundle parent product."""

    __tablename__ = "composite_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    child_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)

    parent: Mapped["Product"] = relationship("Product", foreign_keys=[parent_product_id], back_populates="components")
    child: Mapped["Product"] = relationship("Product", foreign_keys=[child_product_id])


class AuditLog(Base):
    """A record of a security-relevant or critical action (login, logout, timeout, void, etc.) for compliance auditing."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # LOGIN, LOGOUT, TIMEOUT
    terminal_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    details: Mapped[str | None] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    user: Mapped[Optional["User"]] = relationship()


class LoginThrottle(Base):
    """Tracks consecutive authentication failures and lockout time per terminal."""

    __tablename__ = "login_throttle"

    terminal_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class InventoryLog(Base):
    """A human-readable log entry for manual stock adjustments, capturing the reason and who made the change."""

    __tablename__ = "inventory_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty_change: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    new_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), index=True)

    product: Mapped["Product"] = relationship()
    user: Mapped["User"] = relationship()


class Shift(Base):
    """A cashier's cash-drawer session from open to close: starting float versus expected and actual cash counted at close."""

    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    actual_cash: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)  # OPEN, CLOSED
    terminal_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reason_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped["User"] = relationship()


class CashMovement(Base):
    """A non-sale cash-drawer event (cash in/out, safe drop, payout) recorded against a shift."""

    __tablename__ = "cash_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # IN, OUT, DROP, PAYOUT
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    user: Mapped["User"] = relationship()
    shift: Mapped["Shift"] = relationship()


class SuspendedTransaction(Base):
    """A cart set aside mid-sale (a "hold") for later resumption; the cart contents are serialized as JSON in `data`."""

    __tablename__ = "suspended_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    data: Mapped[str] = mapped_column(String, nullable=False)  # JSON string of cart items
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)

    customer: Mapped[Optional["Customer"]] = relationship()


class CustomerPayment(Base):
    """A payment received from a customer against their credit balance (Credit Book)."""

    __tablename__ = "customer_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)  # Cash, Card, Transfer, Cheque
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Cheque#, transfer ref
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    customer: Mapped["Customer"] = relationship()
    user: Mapped["User"] = relationship()


class CustomerLedgerEntry(Base):
    """A running-balance ledger row for customer credit: a sale increases debt, a payment decreases it."""

    __tablename__ = "customer_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    # SALE, PAYMENT, ADJUSTMENT, VOID / REFUND (credit given back by a void or refund, #715)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # positive=debt, negative=payment
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # Running balance
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # sale_id or payment_id
    reference_doc: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Document number
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    customer: Mapped["Customer"] = relationship()
    user: Mapped["User"] = relationship()


class LoyaltyLedgerEntry(Base):
    """One change to a customer's loyalty points (#716).

    Points move by event so LAN Sync can carry them: a till pushes each row,
    the Main PC adds ``points`` to its ``Customer.loyalty_points`` once, and a
    till's figure is the Main PC's plus its own rows not pushed yet.
    """

    __tablename__ = "loyalty_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)  # EARN, REVERSAL, ADJUSTMENT, REDEEM
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # positive=earned, negative=taken off
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)  # Points on this machine afterwards
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # sale_id for EARN, REVERSAL, REDEEM
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    customer: Mapped["Customer"] = relationship()


class StockCount(Document):
    """Physical stock count document using joined table inheritance."""

    __tablename__ = "stock_counts"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    total_variance_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    items: Mapped[list["StockCountItem"]] = relationship(back_populates="stock_count", cascade="all, delete-orphan")

    __mapper_args__ = {
        "polymorphic_identity": "stock_count",
    }


class StockCountItem(Base):
    """Individual item line in a stock count."""

    __tablename__ = "stock_count_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_count_id: Mapped[int] = mapped_column(ForeignKey("stock_counts.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    expected_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    counted_qty: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    variance_qty: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    variance_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    stock_count: Mapped["StockCount"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class SupplierPayment(Base):
    """Record of a payment made to a supplier."""

    __tablename__ = "supplier_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    supplier: Mapped["Supplier"] = relationship()
    user: Mapped["User"] = relationship()


class SupplierLedgerEntry(Base):
    """Ledger entry for supplier payable tracking."""

    __tablename__ = "supplier_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)  # PURCHASE, PAYMENT, ADJUSTMENT
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # positive=payable, negative=payment
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_doc: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    synced: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    supplier: Mapped["Supplier"] = relationship()
    user: Mapped["User"] = relationship()


class PaymentMethod(Base):
    """A configurable payment method available at checkout (e.g. Cash, Card, a custom mobile wallet), with drawer-opening and keyboard-shortcut behavior."""

    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    # kind is authoritative; is_cash is kept in sync on save (is_cash = kind == PaymentMethodKind.CASH)
    kind: Mapped[str] = mapped_column(
        String(20),
        default=PaymentMethodKind.OTHER,
        server_default=PaymentMethodKind.OTHER,
        nullable=False,
        index=True,
    )
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False)
    open_drawer: Mapped[bool] = mapped_column(Boolean, default=False)
    shortcut: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_modified: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)


# --- Multi-Terminal Sync ---
class SyncLog(Base):
    """Tracks completed sync operations between terminals and the Main PC."""

    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    terminal_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # PUSH or PULL
    sync_type: Mapped[str] = mapped_column(String(30), nullable=False)  # CATALOG, TRANSACTIONS, FULL
    records_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="SUCCESS")  # SUCCESS, FAILED, PARTIAL
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SyncQueue(Base):
    """Outgoing items waiting to be pushed to the Main PC.

    When a terminal creates a transaction (sale, payment, etc.) while
    offline or before the next sync cycle, a queue entry is created.
    The SyncClient processes the queue and marks items as sent.
    """

    __tablename__ = "sync_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # INSERT, UPDATE, DELETE
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON serialized record
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)  # PENDING, SENT, FAILED
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SyncIdMap(Base):
    """Main PC side: which server row a till's own row id became (#671).

    Every till numbers its rows from 1, so a pushed row's ``id`` only means
    something together with the till that sent it. The Main PC inserts each
    pushed row under an id of its own and records the pair here; a re-sent
    row is found again through this table instead of by its raw id.

    ``table_name`` is the id space, not always the literal table: sales and
    purchases share ``documents`` ids (joined-table inheritance), so all
    three use ``"documents"``.
    """

    __tablename__ = "sync_id_map"
    __table_args__ = (
        UniqueConstraint(
            "origin_terminal_id",
            "origin_db_instance_id",
            "table_name",
            "local_id",
            name="uq_sync_id_map_origin_instance_local",
        ),
        # "is this server row already some till's mapped row?" (legacy adoption check)
        Index("ix_sync_id_map_table_server", "table_name", "server_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    origin_terminal_id: Mapped[str] = mapped_column(String(50), nullable=False)
    origin_db_instance_id: Mapped[str] = mapped_column(String(36), nullable=False, default="legacy")
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    local_id: Mapped[int] = mapped_column(Integer, nullable=False)
    server_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LocalIdentity(Base):
    """Local database identity (#866). Single row with a UUID instance id."""

    __tablename__ = "local_identity"

    db_instance_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class SyncTerminal(Base):
    """Main PC registry of connected tills (#866, #867)."""

    __tablename__ = "sync_terminals"

    terminal_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    db_instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    last_ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    released: Mapped[bool] = mapped_column(Boolean, default=False)


class SyncDeletion(Base):
    """Tracks deletions of catalog records on the Main PC so they propagate to tills (#871)."""

    __tablename__ = "sync_deletions"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True, nullable=False)
    natural_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    __table_args__ = (Index("ix_sync_deletions_table_row", "table_name", "row_id"),)


class ShopMeta(Base):
    """Cluster-wide metadata for the shared shop database (#799).

    Stores settings such as the designated schema owner host (schema_owner_host)
    so tills and terminals know which machine is responsible for migrations.
    """

    __tablename__ = "shop_meta"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), nullable=False)


# Registers the session hook that re-sends a till row to the Main PC when it
# changes after its first push (#677). Imported here so it is active wherever
# the models are.
from cbpos.core.services import sync_change_tracking  # noqa: E402, F401
