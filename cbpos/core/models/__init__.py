from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    String,
    Boolean,
    ForeignKey,
    DateTime,
    Date,
    Numeric,
    Integer,
    Text,
    UniqueConstraint,
    Table,
    Column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
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
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    access_level: Mapped[int] = mapped_column(Integer, default=0)
    permissions: Mapped[List["Permission"]] = relationship(secondary=role_permissions, back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200))
    group: Mapped[str] = mapped_column(String(50), default="General")

    roles: Mapped[List["Role"]] = relationship(secondary=role_permissions, back_populates="permissions")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role_id: Mapped[Optional[int]] = mapped_column(ForeignKey("roles.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    role: Mapped["Role"] = relationship()


# --- Pricing Engine ---
class PriceList(Base):
    __tablename__ = "price_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    items: Mapped[List["PriceListItem"]] = relationship(back_populates="price_list", cascade="all, delete-orphan")


class PriceListItem(Base):
    __tablename__ = "price_list_items"
    __table_args__ = (UniqueConstraint("price_list_id", "product_id", name="uq_pricelist_product"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    price_list_id: Mapped[int] = mapped_column(ForeignKey("price_lists.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    price_list: Mapped["PriceList"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    days_of_week: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # JSON or CSV: "0,1,2" (Mon,Tue,Wed)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # PERCENTAGE, FIXED_AMOUNT, BOGO
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# --- Unified Document Architecture ---
class VoidReason(Base):
    __tablename__ = "void_reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")  # COMPLETED, VOID, DRAFT
    reference_external: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    void_reason_id: Mapped[Optional[int]] = mapped_column(ForeignKey("void_reasons.id"), nullable=True)

    user: Mapped["User"] = relationship()
    void_reason: Mapped["VoidReason"] = relationship()

    __mapper_args__ = {
        "polymorphic_on": type,
        "polymorphic_identity": "document",
    }


class Sale(Document):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tax_vat: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    tax_sscl: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    net_revenue: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    additional_discount_type: Mapped[str] = mapped_column(String(20), default="NONE")
    additional_discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)  # Primary method
    refund_of_sale_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sales.id"), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="sales")
    items: Mapped[List["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    payments: Mapped[List["SalePayment"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    refund_of_sale: Mapped["Sale"] = relationship("Sale", remote_side=[id], foreign_keys=[refund_of_sale_id])

    __mapper_args__ = {
        "polymorphic_identity": "sale",
    }


class Purchase(Document):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    supplier: Mapped["Supplier"] = relationship(back_populates="purchases")
    items: Mapped[List["PurchaseItem"]] = relationship(back_populates="purchase", cascade="all, delete-orphan")

    __mapper_args__ = {
        "polymorphic_identity": "purchase",
    }


class Proforma(Document):
    __tablename__ = "proformas"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_vat: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    tax_sscl: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    validity_days: Mapped[int] = mapped_column(Integer, default=30)
    expiry_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    converted_sale_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sales.id"), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    customer: Mapped["Customer"] = relationship("Customer")
    items: Mapped[List["ProformaItem"]] = relationship(back_populates="proforma", cascade="all, delete-orphan")
    converted_sale: Mapped["Sale"] = relationship("Sale", foreign_keys=[converted_sale_id])

    __mapper_args__ = {
        "polymorphic_identity": "proforma",
    }


class ProformaItem(Base):
    __tablename__ = "proforma_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    proforma_id: Mapped[int] = mapped_column(ForeignKey("proformas.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(20), default="NONE")
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
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

    products: Mapped[List["Product"]] = relationship(back_populates="unit")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#FFFFFF")
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)

    products: Mapped[List["Product"]] = relationship(back_populates="category")
    parent: Mapped["Category"] = relationship("Category", remote_side=[id], back_populates="subcategories")
    subcategories: Mapped[List["Category"]] = relationship("Category", back_populates="parent")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_si: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    name_ta: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    stock_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=0)
    is_weighted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_composite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_service: Mapped[bool] = mapped_column(Boolean, default=False)
    reorder_point: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=0)
    preferred_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=0)
    image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)
    default_supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("units.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # Optimistic Locking

    category: Mapped["Category"] = relationship(back_populates="products")
    unit: Mapped[Optional["Unit"]] = relationship(back_populates="products")
    parent: Mapped["Product"] = relationship("Product", remote_side=[id], back_populates="variants")
    variants: Mapped[List["Product"]] = relationship("Product", back_populates="parent")
    components: Mapped[List["CompositeItem"]] = relationship(
        "CompositeItem",
        foreign_keys="CompositeItem.parent_product_id",
        back_populates="parent",
    )
    suppliers: Mapped[List["Supplier"]] = relationship(secondary=product_suppliers, back_populates="products")
    default_supplier: Mapped[Optional["Supplier"]] = relationship("Supplier", foreign_keys=[default_supplier_id])

    __mapper_args__ = {"version_id_col": version_id}  # Enable Optimistic Locking


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_company: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    current_debt: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    payment_terms: Mapped[int] = mapped_column(Integer, default=0)  # Days
    loyalty_points: Mapped[int] = mapped_column(default=0)
    loyalty_card_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    price_list_id: Mapped[Optional[int]] = mapped_column(ForeignKey("price_lists.id"), nullable=True)

    sales: Mapped[List["Sale"]] = relationship(back_populates="customer")
    price_list: Mapped["PriceList"] = relationship()
    contacts: Mapped[List["CustomerContact"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class CustomerContact(Base):
    __tablename__ = "customer_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="contacts")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    contact_person: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    tax_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    contact_details: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # Extra details
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    purchases: Mapped[List["Purchase"]] = relationship(back_populates="supplier")
    products: Mapped[List["Product"]] = relationship(secondary=product_suppliers, back_populates="suppliers")


# --- Details & Logs ---
class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    original_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(20), default="NONE")  # NONE, PERCENTAGE, FIXED
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    is_manual_price: Mapped[bool] = mapped_column(Boolean, default=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship("Product")


class SalePayment(Base):
    __tablename__ = "sale_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)  # Cash, Card, Credit
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="payments")


class PurchaseItem(Base):
    __tablename__ = "purchase_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty_received: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    purchase: Mapped["Purchase"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship("Product")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    qty_change: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # SALE, PURCHASE, ADJUSTMENT, RETURN, VOID

    product: Mapped["Product"] = relationship()
    user: Mapped["User"] = relationship()
    document: Mapped["Document"] = relationship()


class CompositeItem(Base):
    __tablename__ = "composite_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    child_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)

    parent: Mapped["Product"] = relationship("Product", foreign_keys=[parent_product_id], back_populates="components")
    child: Mapped["Product"] = relationship("Product", foreign_keys=[child_product_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # LOGIN, LOGOUT, TIMEOUT
    terminal_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    user: Mapped["User"] = relationship()


class InventoryLog(Base):
    __tablename__ = "inventory_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty_change: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    new_qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    product: Mapped["Product"] = relationship()
    user: Mapped["User"] = relationship()


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    expected_cash: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    actual_cash: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN, CLOSED

    user: Mapped["User"] = relationship()


class CashMovement(Base):
    __tablename__ = "cash_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shifts.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # IN, OUT, DROP, PAYOUT
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    user: Mapped["User"] = relationship()
    shift: Mapped["Shift"] = relationship()


class SuspendedTransaction(Base):
    __tablename__ = "suspended_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    data: Mapped[str] = mapped_column(String, nullable=False)  # JSON string of cart items
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class CustomerPayment(Base):
    __tablename__ = "customer_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)  # Cash, Card, Transfer, Cheque
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Cheque#, transfer ref
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    customer: Mapped["Customer"] = relationship()
    user: Mapped["User"] = relationship()


class CustomerLedgerEntry(Base):
    __tablename__ = "customer_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SALE, PAYMENT, ADJUSTMENT
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # positive=debt, negative=payment
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # Running balance
    reference_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # sale_id or payment_id
    reference_doc: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Document number
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    customer: Mapped["Customer"] = relationship()
    user: Mapped["User"] = relationship()


class StockCount(Document):
    """Physical stock count document using joined table inheritance."""

    __tablename__ = "stock_counts"

    id: Mapped[int] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    total_variance_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    items: Mapped[List["StockCountItem"]] = relationship(back_populates="stock_count", cascade="all, delete-orphan")

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
    counted_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    variance_qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    variance_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    stock_count: Mapped["StockCount"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False)
    open_drawer: Mapped[bool] = mapped_column(Boolean, default=False)
    shortcut: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
