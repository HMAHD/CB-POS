from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cbpos.config import Config
from cbpos.core.database import Base, Database
from cbpos.core.models import Product, Role, User
from cbpos.core.services.purchase_service import PurchaseService
from cbpos.core.services.supplier_service import SupplierService

# Use in-memory database for testing
Config.DB_URI = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_session():
    """
    Fixture to set up an in-memory database for each test.
    """
    db = Database()
    # Force StaticPool for in-memory DB to persist data across sessions
    db.engine = create_engine(Config.DB_URI, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.SessionLocal = sessionmaker(bind=db.engine, autocommit=False, autoflush=False, expire_on_commit=False)

    db.create_tables()

    with db.get_session() as session:
        yield session

    # Teardown
    Base.metadata.drop_all(bind=db.engine)


def test_create_supplier(db_session):
    supplier = SupplierService.create_supplier(
        company_name="Test Supplier", phone="1234567890", contact_person="John Doe"
    )
    assert supplier.id is not None
    assert supplier.company_name == "Test Supplier"
    assert supplier.phone == "1234567890"


def test_purchase_flow(db_session):
    # 1. Setup Data
    # Create User
    role = Role(name="Admin")
    db_session.add(role)
    db_session.commit()

    user = User(username="admin", pin_hash="hash", role_id=role.id)
    db_session.add(user)
    db_session.commit()
    user_id = user.id

    # Create Product (Initial Stock: 10 @ 100.00)
    product = Product(
        barcode="1001",
        name_en="Test Product",
        price=150.00,
        cost=100.00,
        stock_qty=10.000,
    )
    db_session.add(product)
    db_session.commit()
    product_id = product.id

    # Create Supplier
    supplier = SupplierService.create_supplier("Supplier A")

    # 2. Create Purchase Draft
    # Receive 10 more @ 120.00
    # 2. Create Purchase Draft
    # Receive 10 more @ 120.00
    purchase = PurchaseService.create_purchase(supplier_id=supplier.id, reference_external="INV-001", user_id=user_id)

    assert purchase.status == "DRAFT"
    assert purchase.total_cost == Decimal("0.00")

    # 3. Commit Purchase
    items_data = [{"product_id": product_id, "qty": Decimal("10.000"), "cost": Decimal("120.00")}]
    committed_purchase = PurchaseService.commit_purchase(purchase.id, items_data)

    assert committed_purchase.status == "COMPLETED"
    assert committed_purchase.total_cost == Decimal("1200.00")

    # 4. Verify Stock and Cost
    # Refresh product from DB
    db_session.refresh(product)

    # New Qty = 10 + 10 = 20
    assert product.stock_qty == Decimal("20.000")

    # New Cost = ((10 * 100) + (10 * 120)) / 20 = (1000 + 1200) / 20 = 2200 / 20 = 110.00
    assert product.cost == Decimal("110.00")


def test_weighted_average_cost_complex(db_session):
    # Test with different quantities
    role = Role(name="Admin")
    db_session.add(role)
    db_session.commit()
    user = User(username="admin", pin_hash="hash", role_id=role.id)
    db_session.add(user)
    db_session.commit()

    # Initial: 5 @ 100.00
    product = Product(barcode="1002", name_en="Widget", price=200.00, cost=100.00, stock_qty=5.000)
    db_session.add(product)
    db_session.commit()

    supplier = SupplierService.create_supplier("Supplier B")

    # Receive: 15 @ 200.00
    # Receive: 15 @ 200.00
    purchase = PurchaseService.create_purchase(supplier.id, "INV-002", user.id)

    items_data = [{"product_id": product.id, "qty": Decimal("15.000"), "cost": Decimal("200.00")}]
    PurchaseService.commit_purchase(purchase.id, items_data)

    db_session.refresh(product)

    # Total Value = (5 * 100) + (15 * 200) = 500 + 3000 = 3500
    # Total Qty = 20
    # Avg Cost = 3500 / 20 = 175.00
    assert product.stock_qty == Decimal("20.000")
    assert product.cost == Decimal("175.00")
