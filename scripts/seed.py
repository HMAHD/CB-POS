import sys
from pathlib import Path
from decimal import Decimal
import hashlib

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from cbpos.core.database import Database, Base  # noqa: E402
from cbpos.core.models import (  # noqa: E402
    User,
    Category,
    Product,
    Role,
    Permission,
    Customer,
    CompositeItem,
    PriceList,
    Supplier,
    VoidReason,
    PaymentMethod,
)
from cbpos.core.constants.permissions import Permissions  # noqa: E402
import cbpos.core.models  # noqa: F401


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def seed_data():
    db = Database()
    # Drop all tables to ensure clean slate for new schema
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)

    with db.get_session() as session:
        print("Seeding Permissions...")
        perm_map = {}
        groups = Permissions.get_groups()

        for group, codes in groups.items():
            for code in codes:
                perm = Permission(code=code, description=code.replace(".", " ").title(), group=group)
                session.add(perm)
                perm_map[code] = perm
        session.flush()

        print("Seeding Roles...")
        # Admin (Level 9) - All Permissions
        admin_role = Role(name="Admin", access_level=9)
        for perm in perm_map.values():
            admin_role.permissions.append(perm)

        # Manager (Level 5) - Sales + Inventory + Reports + Documents
        manager_role = Role(name="Manager", access_level=5)
        for code in groups["Sales"] + groups["Inventory"] + groups["Reports"] + groups["Documents"]:
            manager_role.permissions.append(perm_map[code])

        # Cashier (Level 1) - Sales Only (Restricted)
        cashier_role = Role(name="Cashier", access_level=1)
        # Cashier gets basic sales view and add item, but maybe not void/discount
        cashier_role.permissions.append(perm_map[Permissions.SALES_VIEW])
        cashier_role.permissions.append(perm_map[Permissions.SALES_ADD_ITEM])
        cashier_role.permissions.append(perm_map[Permissions.DOCUMENTS_VIEW])

        session.add_all([admin_role, manager_role, cashier_role])
        session.flush()

        print("Seeding Users...")
        admin = User(username="admin", pin_hash=hash_pin("1234"), role_id=admin_role.id)
        manager = User(username="manager", pin_hash=hash_pin("5678"), role_id=manager_role.id)
        cashier = User(username="cashier", pin_hash=hash_pin("0000"), role_id=cashier_role.id)
        session.add_all([admin, manager, cashier])
        session.flush()

        print("Seeding Void Reasons...")
        void_reasons = [
            VoidReason(code="MISTAKE", description="Cashier Mistake"),
            VoidReason(code="RETURN", description="Customer Return"),
            VoidReason(code="DAMAGED", description="Damaged Goods"),
            VoidReason(code="CHANGED_MIND", description="Customer Changed Mind"),
            VoidReason(code="ACCIDENTAL", description="Accidental Entry"),
            VoidReason(code="MANAGER", description="Manager Override"),
        ]
        session.add_all(void_reasons)

        print("Seeding Price Lists...")
        price_lists = [
            PriceList(name="Standard", is_active=True),
            PriceList(name="Wholesale", is_active=True),
            PriceList(name="Happy Hour", is_active=True),
        ]
        session.add_all(price_lists)
        session.flush()

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

        print("Seeding Suppliers...")
        suppliers = [
            Supplier(
                company_name="Munchee Distributors",
                contact_person="Kamal Perera",
                phone="0112223333",
                tax_number="TAX-MUNCHEE-001",
            ),
            Supplier(
                company_name="City Imports",
                contact_person="Nimal Silva",
                phone="0114445555",
                tax_number="TAX-CITY-002",
            ),
        ]
        session.add_all(suppliers)
        session.flush()

        print("Seeding Products...")
        products = [
            Product(
                barcode="47920240",
                name_en="Munchee Super Cream Cracker 490g",
                price=Decimal("650.00"),
                cost=Decimal("500.00"),
                stock_qty=Decimal("100.000"),
                reorder_point=Decimal("20.000"),
                preferred_qty=Decimal("100.000"),
                category=cat_map["Biscuits"],
                default_supplier_id=suppliers[0].id,
            ),
            Product(
                barcode="47900001",
                name_en="Highland Full Cream Milk 1L",
                price=Decimal("520.00"),
                cost=Decimal("450.00"),
                stock_qty=Decimal("50.000"),
                reorder_point=Decimal("10.000"),
                preferred_qty=Decimal("50.000"),
                category=cat_map["Beverages"],
                default_supplier_id=suppliers[1].id,
            ),
            Product(
                barcode="1001",
                name_en="Sugar 1kg",
                name_si="සීනි",
                price=Decimal("350.00"),
                cost=Decimal("300.00"),
                stock_qty=Decimal("100.000"),
                reorder_point=Decimal("20.000"),
                preferred_qty=Decimal("100.000"),
                category=cat_map["Essentials"],
                default_supplier_id=suppliers[0].id,
            ),
            # Service Item (no inventory tracking)
            Product(
                barcode="SVC001",
                name_en="Delivery Charge",
                name_si="බෙදාහැරීමේ ගාස්තුව",
                price=Decimal("350.00"),
                cost=Decimal("0.00"),
                stock_qty=Decimal("0.000"),
                is_service=True,
                category=cat_map["Essentials"],
            ),
            # Low Stock Item (for reorder testing)
            Product(
                barcode="8901234567890",
                name_en="Samaposha Powder 500g",
                name_si="සමපෝෂා",
                price=Decimal("1250.00"),
                cost=Decimal("1100.00"),
                stock_qty=Decimal("2.000"),  # Below reorder point
                reorder_point=Decimal("10.000"),
                preferred_qty=Decimal("50.000"),
                category=cat_map["Essentials"],
                default_supplier_id=suppliers[1].id,
            ),
            # Weighted Item
            Product(
                barcode="2001",
                name_en="Red Onion (Per KG)",
                price=Decimal("380.00"),
                cost=Decimal("320.00"),
                stock_qty=Decimal("50.500"),
                is_weighted=True,
                reorder_point=Decimal("10.000"),
                preferred_qty=Decimal("100.000"),
                category=cat_map["Vegetables"],
                default_supplier_id=suppliers[0].id,
            ),
            Product(
                barcode="3001",
                name_en="Sunlight Soap",
                price=Decimal("110.00"),
                cost=Decimal("90.00"),
                stock_qty=Decimal("200.000"),
                reorder_point=Decimal("50.000"),
                preferred_qty=Decimal("200.000"),
                category=cat_map["Essentials"],
            ),
        ]
        session.add_all(products)
        session.flush()

        # Link products to suppliers
        products[0].suppliers.append(suppliers[0])  # Munchee -> Munchee
        products[1].suppliers.append(suppliers[1])  # Highland -> City Imports

        print("Seeding Customers...")
        customer = Customer(
            name="John Doe",
            phone="0771234567",
            credit_limit=Decimal("5000.00"),
            price_list_id=price_lists[1].id,  # Wholesale
        )
        session.add(customer)
        session.flush()

        print("Seeding Composite Items...")
        # Hamper = 2x Biscuits + 1x Soap
        biscuit = products[0]
        soap = products[6]

        hamper = Product(
            barcode="HAMPER001",
            name_en="New Year Hamper",
            price=Decimal("1500.00"),
            cost=Decimal("1090.00"),  # 2*500 + 90
            stock_qty=Decimal("0.000"),  # Virtual stock, depends on children
            category=cat_map["Essentials"],
            is_composite=True,
        )
        session.add(hamper)
        session.flush()

        comps = [
            CompositeItem(
                parent_product_id=hamper.id,
                child_product_id=biscuit.id,
                qty=Decimal("2.000"),
            ),
            CompositeItem(
                parent_product_id=hamper.id,
                child_product_id=soap.id,
                qty=Decimal("1.000"),
            ),
        ]
        session.add_all(comps)
        session.flush()

        session.add_all(comps)
        session.flush()

        print("Seeding Payment Methods...")
        payment_methods = [
            PaymentMethod(name="Cash", is_cash=True, open_drawer=True, shortcut="F12"),
            PaymentMethod(name="Card", is_cash=False, open_drawer=False),
            PaymentMethod(name="Credit", is_cash=False, open_drawer=False),
            PaymentMethod(name="QR/Mobile", is_cash=False, open_drawer=False),
            PaymentMethod(name="Cheque", is_cash=False, open_drawer=False),
            PaymentMethod(name="Transfer", is_cash=False, open_drawer=False),
        ]
        session.add_all(payment_methods)
        session.flush()

        session.commit()

    print("Seeding Complete!")


if __name__ == "__main__":
    seed_data()
