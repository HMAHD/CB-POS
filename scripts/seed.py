import sys
from pathlib import Path
from decimal import Decimal
import hashlib

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from cbpos.core.database import Database, Base
from cbpos.core.models import User, Category, Product, Role, Permission, Customer

def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()

def seed_data():
    db = Database()
    # Drop all tables to ensure clean slate for new schema
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)

    with db.get_session() as session:
        print("Seeding Permissions...")
        perm_void = Permission(code="can_void_sale", description="Can void completed sales")
        session.add(perm_void)
        session.flush()

        print("Seeding Roles...")
        admin_role = Role(name="Admin")
        admin_role.permissions.append(perm_void)
        
        cashier_role = Role(name="Cashier")
        session.add_all([admin_role, cashier_role])
        session.flush()

        print("Seeding Users...")
        admin = User(username="admin", pin_hash=hash_pin("1234"), role_id=admin_role.id)
        cashier = User(username="cashier", pin_hash=hash_pin("0000"), role_id=cashier_role.id)
        session.add_all([admin, cashier])
        
        print("Seeding Categories...")
        cats = [
            Category(name="Biscuits", color="#FFD700"),
            Category(name="Beverages", color="#00BCEB"),
            Category(name="Essentials", color="#FF4136"),
            Category(name="Vegetables", color="#39FF14"),
        ]
        session.add_all(cats)
        session.flush()
        
        cat_map = {c.name: c for c in cats}

        print("Seeding Products...")
        products = [
            Product(
                barcode="47920240",
                name_en="Munchee Super Cream Cracker 490g",
                price=Decimal("650.00"),
                cost=Decimal("500.00"),
                stock_qty=Decimal("100.000"),
                category=cat_map["Biscuits"]
            ),
            Product(
                barcode="47900001",
                name_en="Highland Full Cream Milk 1L",
                price=Decimal("520.00"),
                cost=Decimal("450.00"),
                stock_qty=Decimal("50.000"),
                category=cat_map["Beverages"]
            ),
            Product(
                barcode="1001",
                name_en="Keeris Samba 1kg",
                price=Decimal("320.00"),
                cost=Decimal("280.00"),
                stock_qty=Decimal("1000.000"),
                is_weighted=True,
                category=cat_map["Essentials"]
            ),
            Product(
                barcode="2001",
                name_en="Carrot",
                price=Decimal("450.00"),
                cost=Decimal("300.00"),
                stock_qty=Decimal("50.000"),
                is_weighted=True,
                category=cat_map["Vegetables"]
            ),
            Product(
                barcode="3001",
                name_en="Sunlight Soap",
                price=Decimal("110.00"),
                cost=Decimal("90.00"),
                stock_qty=Decimal("200.000"),
                category=cat_map["Essentials"]
            ),
        ]
        session.add_all(products)
        session.flush()

        print("Seeding Customers...")
        customer = Customer(name="John Doe", phone="0771234567", credit_limit=Decimal("5000.00"))
        session.add(customer)
        session.flush()

        session.commit()

    print("Seeding Complete!")

if __name__ == "__main__":
    seed_data()
