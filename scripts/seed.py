import sys
from pathlib import Path
from decimal import Decimal

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from cbpos.core.database import Database
from cbpos.core.models import User, Category, Product

import hashlib

def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()

def seed_data():
    db = Database()
    db.create_tables()

    with db.get_session() as session:
        # 1. Users
        if not session.query(User).first():
            print("Seeding Users...")
            admin = User(name="Admin", pin_hash=hash_pin("1234"), role="admin")
            cashier = User(name="Cashier", pin_hash=hash_pin("0000"), role="cashier")
            session.add_all([admin, cashier])
        
        # 2. Categories
        if not session.query(Category).first():
            print("Seeding Categories...")
            cats = [
                Category(name="Biscuits", color="#FFD700"),
                Category(name="Beverages", color="#00BCEB"),
                Category(name="Essentials", color="#FF4136"),
                Category(name="Vegetables", color="#39FF14"),
            ]
            session.add_all(cats)
            session.flush() # Flush to get IDs for products

            # Map categories for easy access
            cat_map = {c.name: c for c in cats}

            # 3. Products
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

    print("Seeding Complete!")

if __name__ == "__main__":
    seed_data()
