from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from cbpos.core.database import Base

class Role(Base):
    __tablename__ = 'roles'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    permissions: Mapped[List["Permission"]] = relationship(secondary="role_permissions")

class Permission(Base):
    __tablename__ = 'permissions'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200))

class RolePermission(Base):
    __tablename__ = 'role_permissions'
    
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey('permissions.id'), primary_key=True)

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role_id: Mapped[Optional[int]] = mapped_column(ForeignKey('roles.id'), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    role: Mapped["Role"] = relationship()
    sales: Mapped[List["Sale"]] = relationship(back_populates="cashier")

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    user: Mapped["User"] = relationship()

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#FFFFFF")

    products: Mapped[List["Product"]] = relationship(back_populates="category")

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
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))

    category: Mapped["Category"] = relationship(back_populates="products")

class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tax_vat: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    tax_sscl: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    net_revenue: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED") # COMPLETED, VOID
    cashier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    cashier: Mapped["User"] = relationship(back_populates="sales")
    items: Mapped[List["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")

class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship("Product")

class SuspendedTransaction(Base):
    __tablename__ = "suspended_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    data: Mapped[str] = mapped_column(String, nullable=False) # JSON string of cart items
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

class CompositeItem(Base):
    __tablename__ = "composite_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    child_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)

    parent: Mapped["Product"] = relationship("Product", foreign_keys=[parent_product_id])
    child: Mapped["Product"] = relationship("Product", foreign_keys=[child_product_id])
