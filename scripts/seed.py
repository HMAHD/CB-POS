"""
Seed script for CB-POS — populates the database with realistic Sri Lankan
retail data for testing and demonstration purposes.

Usage:
    python scripts/seed.py          # Full reset + seed
"""

import sys
import random
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta

import bcrypt

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from cbpos.core.database import Database, Base  # noqa: E402
from cbpos.core.services.database_setup_service import DatabaseSetupService  # noqa: E402
from cbpos.core.models import (  # noqa: E402
    User,
    Category,
    Product,
    Role,
    Permission,
    Customer,
    CompositeItem,
    PriceList,
    PriceListItem,
    Supplier,
    VoidReason,
    PaymentMethod,
    Unit,
    Sale,
    SaleItem,
    SalePayment,
    Purchase,
    PurchaseItem,
    StockMovement,
    Shift,
    CashMovement,
    AuditLog,
    InventoryLog,
    Promotion,
)
from cbpos.core.constants.permissions import Permissions  # noqa: E402
import cbpos.core.models  # noqa: E402,F401


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed_data():  # noqa: C901
    db = Database()
    # Drop all tables to ensure clean slate for new schema
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    # Stamp alembic_version at head — tables above were created directly
    # from the current models, bypassing migrations, so future
    # `alembic upgrade head` calls must not try to re-create them.
    DatabaseSetupService.stamp_alembic_head()

    with db.get_session() as session:
        # =============================================================
        # 1. PERMISSIONS
        # =============================================================
        print("Seeding Permissions...")
        perm_map = {}
        groups = Permissions.get_groups()

        for group, codes in groups.items():
            for code in codes:
                perm = Permission(code=code, description=code.replace(".", " ").title(), group=group)
                session.add(perm)
                perm_map[code] = perm
        session.flush()

        # =============================================================
        # 2. ROLES
        # =============================================================
        print("Seeding Roles...")
        admin_role = Role(name="Admin", access_level=9)
        for perm in perm_map.values():
            admin_role.permissions.append(perm)

        manager_role = Role(name="Manager", access_level=5)
        manager_groups = [
            "Sales",
            "Inventory",
            "Reports",
            "Documents",
            "Credit",
            "Purchase",
            "Stock Take",
            "Cash",
        ]
        for grp in manager_groups:
            for code in groups.get(grp, []):
                manager_role.permissions.append(perm_map[code])

        cashier_role = Role(name="Cashier", access_level=1)
        cashier_role.permissions.append(perm_map[Permissions.SALES_VIEW])
        cashier_role.permissions.append(perm_map[Permissions.SALES_ADD_ITEM])
        cashier_role.permissions.append(perm_map[Permissions.DOCUMENTS_VIEW])
        cashier_role.permissions.append(perm_map[Permissions.CREDIT_RECEIVE_PAYMENT])
        cashier_role.permissions.append(perm_map[Permissions.CASH_OPEN_DRAWER])

        session.add_all([admin_role, manager_role, cashier_role])
        session.flush()

        # =============================================================
        # 3. USERS
        # =============================================================
        print("Seeding Users...")
        admin = User(username="admin", pin_hash=hash_pin("1234"), role_id=admin_role.id)
        manager = User(username="manager", pin_hash=hash_pin("5678"), role_id=manager_role.id)
        cashier = User(username="cashier", pin_hash=hash_pin("0000"), role_id=cashier_role.id)
        cashier2 = User(username="nimal", pin_hash=hash_pin("1111"), role_id=cashier_role.id)
        session.add_all([admin, manager, cashier, cashier2])
        session.flush()

        users = [admin, manager, cashier, cashier2]

        # =============================================================
        # 4. VOID REASONS
        # =============================================================
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
        session.flush()

        # =============================================================
        # 5. PRICE LISTS
        # =============================================================
        print("Seeding Price Lists...")
        price_lists = [
            PriceList(name="Standard", is_active=True),
            PriceList(name="Wholesale", is_active=True),
            PriceList(name="Happy Hour", is_active=True),
        ]
        session.add_all(price_lists)
        session.flush()
        pl_standard, pl_wholesale, pl_happy = price_lists

        # =============================================================
        # 6. UNITS OF MEASUREMENT
        # =============================================================
        print("Seeding Units of Measurement...")
        units = [
            Unit(name="Piece", abbreviation="pcs", decimal_places=0),
            Unit(name="Kilogram", abbreviation="kg", decimal_places=3),
            Unit(name="Gram", abbreviation="g", decimal_places=0),
            Unit(name="Liter", abbreviation="L", decimal_places=3),
            Unit(name="Meter", abbreviation="m", decimal_places=2),
            Unit(name="Pack", abbreviation="pk", decimal_places=0),
            Unit(name="Box", abbreviation="box", decimal_places=0),
            Unit(name="Dozen", abbreviation="dz", decimal_places=0),
        ]
        session.add_all(units)
        session.flush()
        unit_map = {u.name: u for u in units}

        # =============================================================
        # 7. CATEGORIES (hierarchical — parent + sub-categories)
        # =============================================================
        print("Seeding Categories...")
        # Parent categories
        cat_food = Category(name="Food & Grocery", color="#FF9800")
        cat_beverage = Category(name="Beverages", color="#00BCEB")
        cat_household = Category(name="Household", color="#9C27B0")
        cat_personal = Category(name="Personal Care", color="#E91E63")
        cat_dairy = Category(name="Dairy & Chilled", color="#4CAF50")
        cat_snacks = Category(name="Snacks & Confectionery", color="#FFD700")
        cat_pharmacy = Category(name="Pharmacy", color="#F44336", tax_exempt=True)
        cat_produce = Category(name="Fresh Produce", color="#39FF14")
        cat_stationery = Category(name="Stationery", color="#607D8B")
        cat_electronics = Category(name="Electronics", color="#2196F3")

        session.add_all(
            [
                cat_food,
                cat_beverage,
                cat_household,
                cat_personal,
                cat_dairy,
                cat_snacks,
                cat_pharmacy,
                cat_produce,
                cat_stationery,
                cat_electronics,
            ]
        )
        session.flush()

        # Sub-categories
        sub_rice = Category(name="Rice & Flour", color="#FFC107", parent_id=cat_food.id)
        sub_spices = Category(name="Spices & Condiments", color="#FF5722", parent_id=cat_food.id)
        sub_canned = Category(name="Canned & Packaged", color="#795548", parent_id=cat_food.id)
        sub_oil = Category(name="Cooking Oil", color="#CDDC39", parent_id=cat_food.id)
        sub_soft = Category(name="Soft Drinks", color="#03A9F4", parent_id=cat_beverage.id)
        sub_tea = Category(name="Tea & Coffee", color="#8D6E63", parent_id=cat_beverage.id)
        sub_cleaning = Category(name="Cleaning", color="#AB47BC", parent_id=cat_household.id)
        sub_laundry = Category(name="Laundry", color="#CE93D8", parent_id=cat_household.id)
        sub_veg = Category(name="Vegetables", color="#66BB6A", parent_id=cat_produce.id)
        sub_fruit = Category(name="Fruits", color="#AED581", parent_id=cat_produce.id)

        session.add_all(
            [
                sub_rice,
                sub_spices,
                sub_canned,
                sub_oil,
                sub_soft,
                sub_tea,
                sub_cleaning,
                sub_laundry,
                sub_veg,
                sub_fruit,
            ]
        )
        session.flush()

        # =============================================================
        # 8. SUPPLIERS
        # =============================================================
        print("Seeding Suppliers...")
        suppliers = [
            Supplier(
                company_name="Munchee (Pvt) Ltd",
                contact_person="Kamal Perera",
                phone="0112223333",
                email="orders@munchee.lk",
                address="No. 25, Dambulla Rd, Kurunegala",
                tax_number="TAX-123456789",
                current_payable=Decimal("45000.00"),
                payment_terms=30,
            ),
            Supplier(
                company_name="Ceylon Biscuits Limited (CBL)",
                contact_person="Nimal Jayawardena",
                phone="0114445555",
                email="sales@cbl.lk",
                address="No. 10, Minuwangoda Rd, Ja-Ela",
                tax_number="TAX-987654321",
                current_payable=Decimal("28500.00"),
                payment_terms=30,
            ),
            Supplier(
                company_name="Unilever Sri Lanka",
                contact_person="Priya Fernando",
                phone="0112445566",
                email="orders@unilever.lk",
                address="No. 258, Grandpass Rd, Colombo 14",
                tax_number="TAX-UNI-001",
                current_payable=Decimal("62000.00"),
                payment_terms=45,
            ),
            Supplier(
                company_name="Lanka Soy (Pvt) Ltd",
                contact_person="Suresh Bandara",
                phone="0372223344",
                email="sales@lankasoy.lk",
                address="Nelumpathvila, Anuradhapura",
                tax_number="TAX-LSOY-001",
                current_payable=Decimal("0.00"),
                payment_terms=14,
            ),
            Supplier(
                company_name="CIC Agri Business",
                contact_person="Dilan Wijesinghe",
                phone="0112008800",
                email="agri@cic.lk",
                address="No. 199, Kew Rd, Colombo 02",
                tax_number="TAX-CIC-001",
                current_payable=Decimal("15000.00"),
                payment_terms=30,
            ),
            Supplier(
                company_name="Dambulla Economic Centre",
                contact_person="Mahinda Gunawardena",
                phone="0662284567",
                address="Dambulla Manning Market",
                current_payable=Decimal("8500.00"),
                payment_terms=7,
            ),
            Supplier(
                company_name="Hemas Holdings PLC",
                contact_person="Ranjith de Silva",
                phone="0112691691",
                email="trade@hemas.lk",
                address="No. 75, Braybrooke Pl, Colombo 02",
                tax_number="TAX-HEMAS-001",
                current_payable=Decimal("0.00"),
                payment_terms=30,
            ),
            Supplier(
                company_name="Prima Ceylon (Pvt) Ltd",
                contact_person="Asanka Jayasuriya",
                phone="0112300300",
                email="supply@prima.lk",
                address="No. 52, Beira Lake Rd, Colombo 01",
                tax_number="TAX-PRIMA-001",
                current_payable=Decimal("22000.00"),
                payment_terms=30,
            ),
        ]
        session.add_all(suppliers)
        session.flush()
        sup_map = {s.company_name: s for s in suppliers}

        # =============================================================
        # 9. PRODUCTS — 80+ realistic Sri Lankan retail products
        # =============================================================
        print("Seeding Products...")

        products_data = [
            # ---- Rice & Flour ----
            dict(
                barcode="4796001550018",
                name_en="Nipuna Rice Flour 1kg",
                name_si="නිපුණ හාල් පිටි",
                name_ta="நிபுனா அரிசி மா",
                price="320.00",
                cost="270.00",
                stock=150,
                reorder=30,
                preferred=200,
                cat=sub_rice,
                supplier="Prima Ceylon (Pvt) Ltd",
                unit="Pack",
            ),
            dict(
                barcode="4796001550025",
                name_en="Araliya Nadu Rice 5kg",
                name_si="අරලිය නාඩු සහල්",
                name_ta="அரளியா நாடு அரிசி",
                price="1850.00",
                cost="1650.00",
                stock=80,
                reorder=20,
                preferred=100,
                cat=sub_rice,
                supplier="Prima Ceylon (Pvt) Ltd",
                unit="Pack",
            ),
            dict(
                barcode="4796001550032",
                name_en="Araliya White Raw Rice 5kg",
                name_si="අරලිය සුදු කැකුළු",
                name_ta="அரளியா வெள்ளை அரிசி",
                price="1750.00",
                cost="1550.00",
                stock=60,
                reorder=15,
                preferred=80,
                cat=sub_rice,
                supplier="Prima Ceylon (Pvt) Ltd",
                unit="Pack",
            ),
            dict(
                barcode="4796001550049",
                name_en="Prima Wheat Flour 1kg",
                name_si="ප්‍රිමා පිටි",
                name_ta="பிரிமா கோதுமை மா",
                price="250.00",
                cost="210.00",
                stock=120,
                reorder=30,
                preferred=150,
                cat=sub_rice,
                supplier="Prima Ceylon (Pvt) Ltd",
                unit="Pack",
            ),
            dict(
                barcode="4796001550056",
                name_en="MDK String Hoppers Flour 1kg",
                name_si="MDK ඉඳිආප්ප පිටි",
                name_ta="MDK இடியாப்ப மா",
                price="380.00",
                cost="320.00",
                stock=90,
                reorder=25,
                preferred=120,
                cat=sub_rice,
                supplier="Prima Ceylon (Pvt) Ltd",
                unit="Pack",
            ),
            # ---- Spices & Condiments ----
            dict(
                barcode="4796003260011",
                name_en="MA's Chilli Powder 250g",
                name_si="MA's මිරිස් කුඩු",
                name_ta="MA's மிளகாய் தூள்",
                price="420.00",
                cost="350.00",
                stock=100,
                reorder=25,
                preferred=120,
                cat=sub_spices,
                supplier="CIC Agri Business",
                unit="Pack",
            ),
            dict(
                barcode="4796003260028",
                name_en="MA's Turmeric Powder 100g",
                name_si="MA's කහ කුඩු",
                name_ta="MA's மஞ்சள் தூள்",
                price="180.00",
                cost="145.00",
                stock=80,
                reorder=20,
                preferred=100,
                cat=sub_spices,
                supplier="CIC Agri Business",
                unit="Pack",
            ),
            dict(
                barcode="4796003260035",
                name_en="MA's Curry Powder 250g",
                name_si="MA's කුළු බඩු",
                name_ta="MA's கறி தூள்",
                price="520.00",
                cost="430.00",
                stock=70,
                reorder=20,
                preferred=100,
                cat=sub_spices,
                supplier="CIC Agri Business",
                unit="Pack",
            ),
            dict(
                barcode="4796003260042",
                name_en="Knorr Chicken Cube 10g x6",
                name_si="Knorr චිකන් කියුබ්",
                name_ta="Knorr சிக்கன் க்யூப்",
                price="260.00",
                cost="210.00",
                stock=150,
                reorder=40,
                preferred=200,
                cat=sub_spices,
                supplier="Unilever Sri Lanka",
                unit="Pack",
            ),
            dict(
                barcode="4796003260059",
                name_en="Maggi Coconut Milk Powder 300g",
                name_si="මැගී පොල් කිරි පිටි",
                name_ta="மேகி தேங்காய்ப்பால் தூள்",
                price="480.00",
                cost="400.00",
                stock=65,
                reorder=15,
                preferred=80,
                cat=sub_spices,
                unit="Pack",
            ),
            # ---- Canned & Packaged ----
            dict(
                barcode="4796005100011",
                name_en="Raigam Soya Meat Curry 90g",
                name_si="රයිගම් සෝයා මීට්",
                name_ta="ரெய்கம் சோயா மீட்",
                price="150.00",
                cost="120.00",
                stock=200,
                reorder=50,
                preferred=250,
                cat=sub_canned,
                supplier="Lanka Soy (Pvt) Ltd",
                unit="Pack",
            ),
            dict(
                barcode="4796005100028",
                name_en="Samaposha Cereal 500g",
                name_si="සමපෝෂා",
                name_ta="சமபோஷா",
                price="1250.00",
                cost="1100.00",
                stock=45,
                reorder=10,
                preferred=50,
                cat=sub_canned,
                supplier="Lanka Soy (Pvt) Ltd",
                unit="Pack",
            ),
            dict(
                barcode="4796005100035",
                name_en="Dhal (Red Lentils) 500g",
                name_si="පරිප්පු",
                name_ta="பருப்பு",
                price="350.00",
                cost="290.00",
                stock=120,
                reorder=30,
                preferred=150,
                cat=sub_canned,
                supplier="CIC Agri Business",
                unit="Pack",
            ),
            dict(
                barcode="4796005100042",
                name_en="Maldive Fish Chips 100g",
                name_si="උම්බලකඩ",
                name_ta="மாலத்தீவு மீன்",
                price="680.00",
                cost="580.00",
                stock=40,
                reorder=10,
                preferred=50,
                cat=sub_canned,
                unit="Pack",
            ),
            dict(
                barcode="4796005100059",
                name_en="Anchor Canned Fish 425g",
                name_si="ඇන්කර් මාළු ටින්",
                name_ta="ஆங்கர் மீன் டின்",
                price="750.00",
                cost="650.00",
                stock=80,
                reorder=20,
                preferred=100,
                cat=sub_canned,
                unit="Piece",
            ),
            # ---- Cooking Oil ----
            dict(
                barcode="4796007100017",
                name_en="Fortune Coconut Oil 750ml",
                name_si="ෆෝචූන් පොල් තෙල්",
                name_ta="பார்ச்சூன் தேங்காய் எண்ணெய்",
                price="890.00",
                cost="780.00",
                stock=70,
                reorder=15,
                preferred=80,
                cat=sub_oil,
                unit="Piece",
            ),
            dict(
                barcode="4796007100024",
                name_en="Turkey Vegetable Oil 1L",
                name_si="ටර්කි එළවළු තෙල්",
                name_ta="டர்கி தாவர எண்ணெய்",
                price="780.00",
                cost="680.00",
                stock=55,
                reorder=15,
                preferred=70,
                cat=sub_oil,
                unit="Piece",
            ),
            # ---- Snacks & Biscuits ----
            dict(
                barcode="4792049000108",
                name_en="Munchee Super Cream Cracker 490g",
                name_si="මන්චි සුපර් ක්‍රීම් ක්‍රැකර්",
                price="650.00",
                cost="500.00",
                stock=120,
                reorder=30,
                preferred=150,
                cat=cat_snacks,
                supplier="Munchee (Pvt) Ltd",
                unit="Pack",
            ),
            dict(
                barcode="4792049000115",
                name_en="Munchee Lemon Puff 200g",
                name_si="මන්චි ලෙමන් පෆ්",
                price="350.00",
                cost="280.00",
                stock=100,
                reorder=25,
                preferred=120,
                cat=cat_snacks,
                supplier="Munchee (Pvt) Ltd",
                unit="Pack",
            ),
            dict(
                barcode="4792049000122",
                name_en="Munchee Chocolate Biscuit 200g",
                name_si="මන්චි චොකලට් බිස්කට්",
                price="380.00",
                cost="300.00",
                stock=90,
                reorder=20,
                preferred=100,
                cat=cat_snacks,
                supplier="Munchee (Pvt) Ltd",
                unit="Pack",
            ),
            dict(
                barcode="4792049000139",
                name_en="CBL Marie Biscuit 400g",
                name_si="CBL මේරි බිස්කට්",
                price="290.00",
                cost="230.00",
                stock=110,
                reorder=25,
                preferred=130,
                cat=cat_snacks,
                supplier="Ceylon Biscuits Limited (CBL)",
                unit="Pack",
            ),
            dict(
                barcode="4792049000146",
                name_en="Maliban Gold Marie 330g",
                name_si="මාලිබන් ගෝල්ඩ් මේරි",
                price="310.00",
                cost="250.00",
                stock=95,
                reorder=25,
                preferred=120,
                cat=cat_snacks,
                supplier="Ceylon Biscuits Limited (CBL)",
                unit="Pack",
            ),
            dict(
                barcode="4792049000153",
                name_en="Maliban Cream Wafer Chocolate 225g",
                name_si="මාලිබන් ක්‍රීම් වේෆර්",
                price="320.00",
                cost="260.00",
                stock=75,
                reorder=20,
                preferred=100,
                cat=cat_snacks,
                supplier="Ceylon Biscuits Limited (CBL)",
                unit="Pack",
            ),
            dict(
                barcode="4792049000160",
                name_en="KitKat 2 Finger 17g",
                price="120.00",
                cost="95.00",
                stock=300,
                reorder=50,
                preferred=400,
                cat=cat_snacks,
                unit="Piece",
            ),
            dict(
                barcode="4792049000177",
                name_en="Tipi Tip Chilli Chips 55g",
                name_si="ටිපි ටිප්",
                price="100.00",
                cost="78.00",
                stock=250,
                reorder=60,
                preferred=300,
                cat=cat_snacks,
                supplier="Munchee (Pvt) Ltd",
                unit="Pack",
            ),
            # ---- Beverages — Soft Drinks ----
            dict(
                barcode="5449000131805",
                name_en="Coca-Cola 1.5L",
                price="490.00",
                cost="420.00",
                stock=80,
                reorder=20,
                preferred=100,
                cat=sub_soft,
                unit="Piece",
            ),
            dict(
                barcode="5449000131812",
                name_en="Coca-Cola 400ml",
                price="180.00",
                cost="150.00",
                stock=200,
                reorder=50,
                preferred=250,
                cat=sub_soft,
                unit="Piece",
            ),
            dict(
                barcode="5449000131829",
                name_en="Sprite 1.5L",
                price="490.00",
                cost="420.00",
                stock=60,
                reorder=15,
                preferred=80,
                cat=sub_soft,
                unit="Piece",
            ),
            dict(
                barcode="5449000131836",
                name_en="Elephant House Cream Soda 400ml",
                name_si="එලිපන්ට් හවුස් ක්‍රීම් සෝඩා",
                price="150.00",
                cost="120.00",
                stock=180,
                reorder=40,
                preferred=200,
                cat=sub_soft,
                unit="Piece",
            ),
            dict(
                barcode="5449000131843",
                name_en="Elephant House Ginger Beer 400ml",
                name_si="එලිපන්ට් හවුස් ජින්ජර් බියර්",
                price="150.00",
                cost="120.00",
                stock=160,
                reorder=40,
                preferred=200,
                cat=sub_soft,
                unit="Piece",
            ),
            dict(
                barcode="5449000131850",
                name_en="Elephant House Necto 200ml",
                name_si="නෙක්ටෝ",
                price="80.00",
                cost="60.00",
                stock=250,
                reorder=50,
                preferred=300,
                cat=sub_soft,
                unit="Piece",
            ),
            # ---- Beverages — Tea & Coffee ----
            dict(
                barcode="4796002000011",
                name_en="Dilmah Ceylon Tea 50 bags",
                name_si="ඩිල්මා තේ",
                name_ta="டில்மா தேயிலை",
                price="580.00",
                cost="480.00",
                stock=90,
                reorder=20,
                preferred=100,
                cat=sub_tea,
                unit="Box",
            ),
            dict(
                barcode="4796002000028",
                name_en="Zesta Premium Tea 200g",
                name_si="සෙස්ටා තේ",
                price="650.00",
                cost="540.00",
                stock=70,
                reorder=15,
                preferred=80,
                cat=sub_tea,
                unit="Pack",
            ),
            dict(
                barcode="4796002000035",
                name_en="Nescafe Classic 100g",
                price="1350.00",
                cost="1150.00",
                stock=40,
                reorder=10,
                preferred=50,
                cat=sub_tea,
                unit="Piece",
            ),
            dict(
                barcode="4796002000042",
                name_en="Ratthi Milk Powder 400g",
                name_si="රත්ති කිරි පිටි",
                name_ta="ரத்தி பால் தூள்",
                price="850.00",
                cost="720.00",
                stock=65,
                reorder=15,
                preferred=80,
                cat=sub_tea,
                unit="Pack",
            ),
            dict(
                barcode="4796002000059",
                name_en="Highland Full Cream Milk 1L",
                name_si="හයිලන්ඩ් කිරි",
                name_ta="ஹைலாந்து பால்",
                price="520.00",
                cost="450.00",
                stock=50,
                reorder=10,
                preferred=50,
                cat=cat_dairy,
                unit="Piece",
            ),
            # ---- Dairy & Chilled ----
            dict(
                barcode="4796009000011",
                name_en="Highland Curd 400g",
                name_si="හයිලන්ඩ් මීකිරි",
                name_ta="ஹைலாந்து தயிர்",
                price="250.00",
                cost="200.00",
                stock=30,
                reorder=10,
                preferred=40,
                cat=cat_dairy,
                unit="Piece",
            ),
            dict(
                barcode="4796009000028",
                name_en="Anchor Butter 227g",
                name_si="ඇන්කර් බටර්",
                price="980.00",
                cost="850.00",
                stock=25,
                reorder=8,
                preferred=30,
                cat=cat_dairy,
                unit="Piece",
            ),
            dict(
                barcode="4796009000035",
                name_en="Kotmale Yoghurt Strawberry 80g",
                name_si="කොත්මලේ යෝගට්",
                price="85.00",
                cost="65.00",
                stock=60,
                reorder=20,
                preferred=80,
                cat=cat_dairy,
                unit="Piece",
            ),
            dict(
                barcode="4796009000042",
                name_en="Pelwatte Margarine 250g",
                name_si="පැල්වත්ත මාගරින්",
                price="450.00",
                cost="380.00",
                stock=40,
                reorder=10,
                preferred=50,
                cat=cat_dairy,
                unit="Piece",
            ),
            # ---- Household — Cleaning ----
            dict(
                barcode="4796011000015",
                name_en="Sunlight Dishwash Liquid 500ml",
                name_si="සන්ලයිට් බඳුන් සෝදන",
                price="520.00",
                cost="430.00",
                stock=80,
                reorder=20,
                preferred=100,
                cat=sub_cleaning,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            dict(
                barcode="4796011000022",
                name_en="Vim Scouring Powder 500g",
                name_si="විම් පිරිසිදු කුඩු",
                price="280.00",
                cost="230.00",
                stock=60,
                reorder=15,
                preferred=80,
                cat=sub_cleaning,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            dict(
                barcode="4796011000039",
                name_en="Harpic Toilet Cleaner 500ml",
                price="680.00",
                cost="570.00",
                stock=45,
                reorder=10,
                preferred=60,
                cat=sub_cleaning,
                unit="Piece",
            ),
            dict(
                barcode="4796011000046",
                name_en="Dettol Antiseptic Liquid 250ml",
                price="850.00",
                cost="720.00",
                stock=35,
                reorder=10,
                preferred=40,
                cat=sub_cleaning,
                unit="Piece",
            ),
            # ---- Household — Laundry ----
            dict(
                barcode="4796012000012",
                name_en="Sunlight Washing Powder 1kg",
                name_si="සන්ලයිට් සෝදන කුඩු",
                price="480.00",
                cost="400.00",
                stock=100,
                reorder=25,
                preferred=120,
                cat=sub_laundry,
                supplier="Unilever Sri Lanka",
                unit="Pack",
            ),
            dict(
                barcode="4796012000029",
                name_en="Surf Excel Washing Powder 1kg",
                name_si="සර්ෆ් එක්සෙල්",
                price="620.00",
                cost="520.00",
                stock=70,
                reorder=20,
                preferred=90,
                cat=sub_laundry,
                supplier="Unilever Sri Lanka",
                unit="Pack",
            ),
            dict(
                barcode="4796012000036",
                name_en="Sunlight Bar Soap 115g",
                name_si="සන්ලයිට් සබන්",
                price="110.00",
                cost="90.00",
                stock=200,
                reorder=50,
                preferred=250,
                cat=sub_laundry,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            dict(
                barcode="4796012000043",
                name_en="Comfort Fabric Softener 200ml",
                name_si="කම්ෆට්",
                price="350.00",
                cost="290.00",
                stock=55,
                reorder=15,
                preferred=70,
                cat=sub_laundry,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            # ---- Personal Care ----
            dict(
                barcode="4796013000019",
                name_en="Signal Toothpaste 120g",
                name_si="සිග්නල් දන්ත පේස්ට්",
                price="380.00",
                cost="310.00",
                stock=80,
                reorder=20,
                preferred=100,
                cat=cat_personal,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            dict(
                barcode="4796013000026",
                name_en="Closeup Toothpaste 120g",
                price="350.00",
                cost="290.00",
                stock=65,
                reorder=15,
                preferred=80,
                cat=cat_personal,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            dict(
                barcode="4796013000033",
                name_en="Lifebuoy Soap 100g",
                name_si="ලයිෆ්බෝයි සබන්",
                price="160.00",
                cost="130.00",
                stock=150,
                reorder=40,
                preferred=200,
                cat=cat_personal,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            dict(
                barcode="4796013000040",
                name_en="Lux Beauty Soap 100g",
                name_si="ලක්ස් සබන්",
                price="195.00",
                cost="160.00",
                stock=120,
                reorder=30,
                preferred=150,
                cat=cat_personal,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            dict(
                barcode="4796013000057",
                name_en="Sunsilk Shampoo 80ml",
                name_si="සන්සිල්ක් ශැම්පූ",
                price="280.00",
                cost="230.00",
                stock=70,
                reorder=20,
                preferred=90,
                cat=cat_personal,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            dict(
                barcode="4796013000064",
                name_en="Vaseline Petroleum Jelly 100ml",
                price="450.00",
                cost="380.00",
                stock=40,
                reorder=10,
                preferred=50,
                cat=cat_personal,
                supplier="Unilever Sri Lanka",
                unit="Piece",
            ),
            # ---- Pharmacy (Tax Exempt) ----
            dict(
                barcode="4796015000013",
                name_en="Paracetamol 500mg x10",
                name_si="පැරසිටමෝල්",
                name_ta="பாராசிட்டமால்",
                price="50.00",
                cost="30.00",
                stock=300,
                reorder=50,
                preferred=400,
                cat=cat_pharmacy,
                supplier="Hemas Holdings PLC",
                unit="Pack",
            ),
            dict(
                barcode="4796015000020",
                name_en="Vitamin C 500mg x30",
                name_si="විටමින් C",
                price="450.00",
                cost="350.00",
                stock=60,
                reorder=15,
                preferred=80,
                cat=cat_pharmacy,
                supplier="Hemas Holdings PLC",
                unit="Pack",
            ),
            dict(
                barcode="4796015000037",
                name_en="Siddhalepa Balm 5g",
                name_si="සිද්ධාලේප",
                price="180.00",
                cost="140.00",
                stock=80,
                reorder=20,
                preferred=100,
                cat=cat_pharmacy,
                unit="Piece",
            ),
            dict(
                barcode="4796015000044",
                name_en="Band-Aid Strips 10pcs",
                price="220.00",
                cost="170.00",
                stock=50,
                reorder=15,
                preferred=60,
                cat=cat_pharmacy,
                supplier="Hemas Holdings PLC",
                unit="Pack",
            ),
            # ---- Fresh Produce — Vegetables (Weighted) ----
            dict(
                barcode="2000100",
                name_en="Red Onion (Per KG)",
                name_si="රතු ලූනු",
                name_ta="சிவப்பு வெங்காயம்",
                price="380.00",
                cost="320.00",
                stock="50.500",
                reorder=10,
                preferred=100,
                cat=sub_veg,
                supplier="Dambulla Economic Centre",
                unit="Kilogram",
                weighted=True,
            ),
            dict(
                barcode="2000200",
                name_en="Potato (Per KG)",
                name_si="අල",
                name_ta="உருளைக்கிழங்கு",
                price="350.00",
                cost="280.00",
                stock="40.000",
                reorder=10,
                preferred=80,
                cat=sub_veg,
                supplier="Dambulla Economic Centre",
                unit="Kilogram",
                weighted=True,
            ),
            dict(
                barcode="2000300",
                name_en="Tomato (Per KG)",
                name_si="තක්කාලි",
                name_ta="தக்காளி",
                price="450.00",
                cost="350.00",
                stock="25.500",
                reorder=8,
                preferred=50,
                cat=sub_veg,
                supplier="Dambulla Economic Centre",
                unit="Kilogram",
                weighted=True,
            ),
            dict(
                barcode="2000400",
                name_en="Green Chilli (Per KG)",
                name_si="අමු මිරිස්",
                name_ta="பச்சை மிளகாய்",
                price="680.00",
                cost="550.00",
                stock="15.000",
                reorder=5,
                preferred=30,
                cat=sub_veg,
                supplier="Dambulla Economic Centre",
                unit="Kilogram",
                weighted=True,
            ),
            dict(
                barcode="2000500",
                name_en="Carrot (Per KG)",
                name_si="කැරට්",
                name_ta="கேரட்",
                price="420.00",
                cost="340.00",
                stock="18.500",
                reorder=5,
                preferred=40,
                cat=sub_veg,
                supplier="Dambulla Economic Centre",
                unit="Kilogram",
                weighted=True,
            ),
            dict(
                barcode="2000600",
                name_en="Beans (Per KG)",
                name_si="බෝංචි",
                name_ta="பீன்ஸ்",
                price="520.00",
                cost="420.00",
                stock="12.000",
                reorder=5,
                preferred=30,
                cat=sub_veg,
                supplier="Dambulla Economic Centre",
                unit="Kilogram",
                weighted=True,
            ),
            # ---- Fresh Produce — Fruits (Weighted) ----
            dict(
                barcode="2001100",
                name_en="Banana - Ambul (Per KG)",
                name_si="ඇඹුල් කෙසෙල්",
                name_ta="வாழை",
                price="320.00",
                cost="250.00",
                stock="30.000",
                reorder=10,
                preferred=50,
                cat=sub_fruit,
                supplier="Dambulla Economic Centre",
                unit="Kilogram",
                weighted=True,
            ),
            dict(
                barcode="2001200",
                name_en="Papaya (Per KG)",
                name_si="පැපොල්",
                name_ta="பப்பாளி",
                price="280.00",
                cost="200.00",
                stock="15.000",
                reorder=5,
                preferred=30,
                cat=sub_fruit,
                supplier="Dambulla Economic Centre",
                unit="Kilogram",
                weighted=True,
            ),
            dict(
                barcode="2001300",
                name_en="Mango (Per KG)",
                name_si="අඹ",
                name_ta="மாம்பழம்",
                price="650.00",
                cost="500.00",
                stock="20.000",
                reorder=5,
                preferred=40,
                cat=sub_fruit,
                supplier="Dambulla Economic Centre",
                unit="Kilogram",
                weighted=True,
            ),
            # ---- Essentials / General ----
            dict(
                barcode="4796018000016",
                name_en="White Sugar 1kg",
                name_si="සුදු සීනි",
                name_ta="வெள்ளை சர்க்கரை",
                price="350.00",
                cost="300.00",
                stock=100,
                reorder=20,
                preferred=120,
                cat=cat_food,
                unit="Pack",
            ),
            dict(
                barcode="4796018000023",
                name_en="Salt 500g",
                name_si="ලුණු",
                name_ta="உப்பு",
                price="80.00",
                cost="55.00",
                stock=150,
                reorder=40,
                preferred=200,
                cat=cat_food,
                unit="Pack",
            ),
            dict(
                barcode="4796018000030",
                name_en="Dried Chilli 100g",
                name_si="වියළි මිරිස්",
                name_ta="காய்ந்த மிளகாய்",
                price="280.00",
                cost="230.00",
                stock=60,
                reorder=15,
                preferred=80,
                cat=sub_spices,
                unit="Pack",
            ),
            dict(
                barcode="4796018000047",
                name_en="Tamarind 200g",
                name_si="සියඹලා",
                name_ta="புளி",
                price="180.00",
                cost="140.00",
                stock=50,
                reorder=15,
                preferred=60,
                cat=sub_spices,
                unit="Pack",
            ),
            # ---- Stationery ----
            dict(
                barcode="4796020000010",
                name_en="Atlas A4 Book 200 Pages",
                name_si="ඇට්ලස් පොත",
                price="320.00",
                cost="260.00",
                stock=100,
                reorder=20,
                preferred=120,
                cat=cat_stationery,
                unit="Piece",
            ),
            dict(
                barcode="4796020000027",
                name_en="Atlas A5 Exercise Book 80 Pages",
                name_si="ඇට්ලස් කුඩා පොත",
                price="120.00",
                cost="95.00",
                stock=200,
                reorder=50,
                preferred=250,
                cat=cat_stationery,
                unit="Piece",
            ),
            dict(
                barcode="4796020000034",
                name_en="Cello Pen Blue",
                price="35.00",
                cost="22.00",
                stock=300,
                reorder=50,
                preferred=400,
                cat=cat_stationery,
                unit="Piece",
            ),
            dict(
                barcode="4796020000041",
                name_en="Eraser White",
                price="25.00",
                cost="15.00",
                stock=200,
                reorder=50,
                preferred=300,
                cat=cat_stationery,
                unit="Piece",
            ),
            # ---- Electronics ----
            dict(
                barcode="4796022000014",
                name_en="Eveready Battery AA 2-Pack",
                price="280.00",
                cost="220.00",
                stock=80,
                reorder=20,
                preferred=100,
                cat=cat_electronics,
                unit="Pack",
            ),
            dict(
                barcode="4796022000021",
                name_en="Wipro LED Bulb 9W",
                price="350.00",
                cost="270.00",
                stock=40,
                reorder=10,
                preferred=50,
                cat=cat_electronics,
                unit="Piece",
            ),
            # ---- Service Items ----
            dict(
                barcode="SVC001",
                name_en="Delivery Charge",
                name_si="බෙදාහැරීමේ ගාස්තුව",
                name_ta="டெலிவரி கட்டணம்",
                price="350.00",
                cost="0.00",
                stock=0,
                cat=cat_food,
                service=True,
            ),
            dict(
                barcode="SVC002",
                name_en="Carry Bag - Large",
                name_si="කවරය - විශාල",
                price="20.00",
                cost="12.00",
                stock=500,
                reorder=100,
                preferred=600,
                cat=cat_household,
                unit="Piece",
            ),
        ]

        product_objs = []
        for pd in products_data:
            p = Product(
                barcode=pd["barcode"],
                name_en=pd["name_en"],
                name_si=pd.get("name_si"),
                name_ta=pd.get("name_ta"),
                price=Decimal(pd["price"]),
                cost=Decimal(pd["cost"]),
                stock_qty=Decimal(str(pd["stock"])),
                is_weighted=pd.get("weighted", False),
                is_service=pd.get("service", False),
                reorder_point=Decimal(str(pd.get("reorder", 0))),
                preferred_qty=Decimal(str(pd.get("preferred", 0))),
                category=pd.get("cat"),
                unit=unit_map.get(pd.get("unit")) if pd.get("unit") else None,
            )
            # Link to supplier
            sup_name = pd.get("supplier")
            if sup_name and sup_name in sup_map:
                p.default_supplier_id = sup_map[sup_name].id
            product_objs.append(p)

        session.add_all(product_objs)
        session.flush()

        # Link products to suppliers (many-to-many)
        for p, pd in zip(product_objs, products_data):
            sup_name = pd.get("supplier")
            if sup_name and sup_name in sup_map:
                p.suppliers.append(sup_map[sup_name])
        session.flush()

        # Build product lookup by barcode
        prod_map = {p.barcode: p for p in product_objs}

        # =============================================================
        # 10. COMPOSITE ITEMS
        # =============================================================
        print("Seeding Composite Items...")
        hamper = Product(
            barcode="HAMPER001",
            name_en="New Year Hamper",
            name_si="අලුත් අවුරුදු තිළිණය",
            price=Decimal("1500.00"),
            cost=Decimal("1090.00"),
            stock_qty=Decimal("0.000"),
            category=cat_snacks,
            is_composite=True,
        )
        session.add(hamper)
        session.flush()

        biscuit = prod_map["4792049000108"]  # Munchee Cream Cracker
        soap = prod_map["4796012000036"]  # Sunlight Bar Soap
        comps = [
            CompositeItem(parent_product_id=hamper.id, child_product_id=biscuit.id, qty=Decimal("2.000")),
            CompositeItem(parent_product_id=hamper.id, child_product_id=soap.id, qty=Decimal("1.000")),
        ]
        session.add_all(comps)
        session.flush()

        product_objs.append(hamper)
        prod_map[hamper.barcode] = hamper

        # =============================================================
        # 11. CUSTOMERS (15 realistic Sri Lankan customers)
        # =============================================================
        print("Seeding Customers...")
        customers = [
            Customer(
                name="Kasun Perera",
                phone="0771234567",
                address="No. 45, Galle Rd, Panadura",
                credit_limit=Decimal("10000.00"),
                current_debt=Decimal("2500.00"),
                loyalty_points=150,
            ),
            Customer(
                name="Nimali Fernando",
                phone="0712345678",
                email="nimali.f@gmail.com",
                address="No. 12, Station Rd, Gampaha",
                credit_limit=Decimal("5000.00"),
                current_debt=Decimal("0.00"),
                loyalty_points=80,
            ),
            Customer(
                name="Saman Kumara",
                phone="0761234567",
                address="No. 78, Main St, Kandy",
                credit_limit=Decimal("15000.00"),
                current_debt=Decimal("7200.00"),
                loyalty_points=320,
                price_list_id=pl_wholesale.id,
            ),
            Customer(
                name="Malini Jayawardena",
                phone="0701234567",
                address="No. 3, Temple Rd, Matara",
                credit_limit=Decimal("8000.00"),
                loyalty_points=45,
            ),
            Customer(
                name="Ruwan Silva",
                phone="0781234567",
                email="ruwan.silva@yahoo.com",
                address="No. 56, Kandy Rd, Kadawatha",
                credit_limit=Decimal("20000.00"),
                current_debt=Decimal("12500.00"),
                loyalty_points=520,
                price_list_id=pl_wholesale.id,
            ),
            Customer(
                name="Chaminda Bandara",
                phone="0751234567",
                address="No. 22, Lake Rd, Kurunegala",
                credit_limit=Decimal("5000.00"),
                current_debt=Decimal("4800.00"),
                loyalty_points=15,
            ),
            Customer(
                name="Dilini Rathnayake",
                phone="0721234567",
                email="dilini.r@outlook.com",
                credit_limit=Decimal("3000.00"),
                loyalty_points=200,
            ),
            # B2B Company Customers
            Customer(
                name="Sampath Herath",
                company_name="Herath Grocery Mart",
                is_company=True,
                phone="0112567890",
                email="info@herathmart.lk",
                address="No. 150, Colombo Rd, Negombo",
                vat_number="VAT-HGM-2024-001",
                tax_id="TIN-123456789",
                credit_limit=Decimal("100000.00"),
                current_debt=Decimal("35000.00"),
                payment_terms=30,
                price_list_id=pl_wholesale.id,
            ),
            Customer(
                name="Lakshman Wijesinghe",
                company_name="LW Supermarket",
                is_company=True,
                phone="0332267890",
                email="orders@lwsuper.lk",
                address="No. 88, Main St, Chilaw",
                vat_number="VAT-LWSM-2024-002",
                tax_id="TIN-987654321",
                credit_limit=Decimal("150000.00"),
                current_debt=Decimal("62000.00"),
                payment_terms=45,
                price_list_id=pl_wholesale.id,
            ),
            Customer(
                name="Priyantha Mendis",
                company_name="Mendis Restaurant",
                is_company=True,
                phone="0412234567",
                address="No. 5, Beach Rd, Galle",
                credit_limit=Decimal("50000.00"),
                current_debt=Decimal("18000.00"),
                payment_terms=14,
                price_list_id=pl_wholesale.id,
            ),
            Customer(
                name="Anjali Gunawardena",
                phone="0741234567",
                address="No. 67, Hill St, Nuwara Eliya",
                credit_limit=Decimal("5000.00"),
                loyalty_points=90,
            ),
            Customer(
                name="Thilina Karunaratne",
                phone="0691234567",
                credit_limit=Decimal("3000.00"),
                current_debt=Decimal("1200.00"),
            ),
            Customer(
                name="Sachini Weerasinghe",
                phone="0681234567",
                email="sachini.w@gmail.com",
                address="No. 34, Flower Rd, Colombo 07",
                loyalty_points=450,
            ),
            Customer(
                name="Jagath Kumara",
                phone="0651234567",
                address="No. 91, Gampola Rd, Peradeniya",
                credit_limit=Decimal("8000.00"),
                current_debt=Decimal("3500.00"),
            ),
            Customer(
                name="Walk-in Customer",
                phone="0000000000",
                credit_limit=Decimal("0.00"),
            ),
        ]
        session.add_all(customers)
        session.flush()

        # =============================================================
        # 12. PRICE LIST ITEMS (wholesale prices for popular products)
        # =============================================================
        print("Seeding Price List Items...")
        wholesale_discounts = [
            ("4796001550025", "1700.00"),  # Araliya Nadu Rice
            ("4796001550032", "1600.00"),  # Araliya White Rice
            ("4796005100028", "1150.00"),  # Samaposha
            ("4796005100035", "310.00"),  # Dhal
            ("4792049000108", "580.00"),  # Munchee Cream Cracker
            ("4792049000139", "260.00"),  # CBL Marie
            ("4796012000012", "430.00"),  # Sunlight Powder
            ("4796012000029", "560.00"),  # Surf Excel
            ("4796013000019", "340.00"),  # Signal
            ("4796002000042", "770.00"),  # Ratthi
            ("4796018000016", "320.00"),  # Sugar
        ]
        for barcode, price in wholesale_discounts:
            if barcode in prod_map:
                session.add(
                    PriceListItem(
                        price_list_id=pl_wholesale.id,
                        product_id=prod_map[barcode].id,
                        price=Decimal(price),
                    )
                )
        session.flush()

        # =============================================================
        # 13. PROMOTIONS
        # =============================================================
        print("Seeding Promotions...")
        now = datetime.now()
        promotions = [
            Promotion(
                name="Weekend 5% Off All Snacks",
                start_time=now - timedelta(days=3),
                end_time=now + timedelta(days=30),
                days_of_week="5,6",  # Sat, Sun
                type="PERCENTAGE",
                value=Decimal("5.00"),
                is_active=True,
            ),
            Promotion(
                name="Evening Happy Hour - 10% Off Beverages",
                start_time=now - timedelta(days=7),
                end_time=now + timedelta(days=60),
                type="PERCENTAGE",
                value=Decimal("10.00"),
                is_active=True,
            ),
            Promotion(
                name="Rs.50 Off Sunlight Products",
                start_time=now - timedelta(days=1),
                end_time=now + timedelta(days=14),
                type="FIXED_AMOUNT",
                value=Decimal("50.00"),
                is_active=True,
            ),
        ]
        session.add_all(promotions)
        session.flush()

        # =============================================================
        # 14. PAYMENT METHODS
        # =============================================================
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

        # =============================================================
        # 15. HISTORICAL SALES (30 sales over last 14 days)
        # =============================================================
        print("Seeding Sales History...")
        sale_products = [p for p in product_objs if not p.is_composite and not p.is_service]
        sale_counter = 0

        for days_ago in range(14, -1, -1):
            # 2 sales per day on average
            num_sales = random.randint(1, 4)
            for _ in range(num_sales):
                sale_counter += 1
                sale_date = datetime.now() - timedelta(
                    days=days_ago,
                    hours=random.randint(8, 20),
                    minutes=random.randint(0, 59),
                )
                sale_user = random.choice([cashier, cashier2, manager])
                sale_customer = random.choice(customers[:7] + [None, None, None])  # 30% chance walk-in

                # Pick 1-6 random items
                num_items = random.randint(1, 6)
                chosen = random.sample(sale_products, min(num_items, len(sale_products)))

                items = []
                total = Decimal("0.00")
                for prod in chosen:
                    qty = Decimal(str(random.randint(1, 5)))
                    if prod.is_weighted:
                        qty = Decimal(str(round(random.uniform(0.25, 3.0), 3)))
                    subtotal = (prod.price * qty).quantize(Decimal("0.01"))
                    total += subtotal
                    items.append(
                        SaleItem(
                            product_id=prod.id,
                            qty=qty,
                            unit_price=prod.price,
                            original_price=prod.price,
                            subtotal=subtotal,
                        )
                    )

                # Tax calculation (backward from MRP)
                vat_base = total / Decimal("1.18")
                tax_vat = (total - vat_base).quantize(Decimal("0.01"))
                tax_sscl = ((total * Decimal("0.5")) * Decimal("0.025")).quantize(Decimal("0.01"))
                net_revenue = (total - tax_vat - tax_sscl).quantize(Decimal("0.01"))

                # Payment method
                method = random.choices(
                    ["Cash", "Card", "Credit", "QR/Mobile"],
                    weights=[60, 20, 10, 10],
                )[0]

                doc_number = f"INV-2026-{sale_counter:05d}"
                sale = Sale(
                    document_number=doc_number,
                    date=sale_date,
                    user_id=sale_user.id,
                    status="COMPLETED",
                    customer_id=sale_customer.id if sale_customer else None,
                    total_amount=total,
                    tax_vat=tax_vat,
                    tax_sscl=tax_sscl,
                    net_revenue=net_revenue,
                    payment_method=method,
                    items=items,
                    payments=[SalePayment(payment_method=method, amount=total)],
                )
                session.add(sale)

        session.flush()

        # Add one voided sale
        sale_counter += 1
        void_date = datetime.now() - timedelta(days=2, hours=14)
        void_sale = Sale(
            document_number=f"INV-2026-{sale_counter:05d}",
            date=void_date,
            user_id=manager.id,
            status="VOID",
            void_reason_id=void_reasons[0].id,  # Cashier Mistake
            total_amount=Decimal("1250.00"),
            tax_vat=Decimal("190.68"),
            tax_sscl=Decimal("15.63"),
            net_revenue=Decimal("1043.69"),
            payment_method="Cash",
            items=[
                SaleItem(
                    product_id=prod_map["4796005100028"].id,  # Samaposha
                    qty=Decimal("1.000"),
                    unit_price=Decimal("1250.00"),
                    original_price=Decimal("1250.00"),
                    subtotal=Decimal("1250.00"),
                ),
            ],
            payments=[SalePayment(payment_method="Cash", amount=Decimal("1250.00"))],
        )
        session.add(void_sale)
        session.flush()

        # =============================================================
        # 16. PURCHASE ORDERS (5 recent purchases)
        # =============================================================
        print("Seeding Purchase Orders...")
        purchases_data = [
            {
                "supplier": "Munchee (Pvt) Ltd",
                "days_ago": 10,
                "items": [
                    ("4792049000108", 50, "480.00"),  # Cream Cracker x50
                    ("4792049000115", 40, "265.00"),  # Lemon Puff x40
                    ("4792049000122", 30, "285.00"),  # Chocolate Biscuit x30
                    ("4792049000177", 100, "70.00"),  # Tipi Tip x100
                ],
            },
            {
                "supplier": "Unilever Sri Lanka",
                "days_ago": 7,
                "items": [
                    ("4796011000015", 40, "410.00"),  # Sunlight Dishwash
                    ("4796012000012", 50, "380.00"),  # Sunlight Powder
                    ("4796012000036", 100, "82.00"),  # Sunlight Soap
                    ("4796013000019", 30, "295.00"),  # Signal
                    ("4796013000033", 60, "120.00"),  # Lifebuoy
                    ("4796013000040", 50, "150.00"),  # Lux
                ],
            },
            {
                "supplier": "Prima Ceylon (Pvt) Ltd",
                "days_ago": 5,
                "items": [
                    ("4796001550018", 80, "255.00"),  # Rice Flour
                    ("4796001550025", 40, "1580.00"),  # Nadu Rice 5kg
                    ("4796001550049", 60, "195.00"),  # Wheat Flour
                ],
            },
            {
                "supplier": "Dambulla Economic Centre",
                "days_ago": 2,
                "items": [
                    ("2000100", 30, "290.00"),  # Red Onion 30kg
                    ("2000200", 25, "250.00"),  # Potato 25kg
                    ("2000300", 15, "310.00"),  # Tomato 15kg
                    ("2000400", 8, "490.00"),  # Green Chilli 8kg
                ],
            },
            {
                "supplier": "Hemas Holdings PLC",
                "days_ago": 3,
                "items": [
                    ("4796015000013", 200, "25.00"),  # Paracetamol
                    ("4796015000020", 30, "320.00"),  # Vitamin C
                    ("4796015000044", 25, "155.00"),  # Band-Aid
                ],
            },
        ]

        for po_idx, po_data in enumerate(purchases_data, 1):
            sup = sup_map[po_data["supplier"]]
            po_date = datetime.now() - timedelta(days=po_data["days_ago"])

            po_items = []
            po_total = Decimal("0.00")
            for barcode, qty, unit_cost in po_data["items"]:
                if barcode in prod_map:
                    cost = Decimal(unit_cost)
                    po_total += cost * Decimal(str(qty))
                    po_items.append(
                        PurchaseItem(
                            product_id=prod_map[barcode].id,
                            qty_received=Decimal(str(qty)),
                            unit_cost=cost,
                        )
                    )

            purchase = Purchase(
                document_number=f"GRN-2026-{po_idx:05d}",
                date=po_date,
                user_id=admin.id,
                status="COMPLETED",
                supplier_id=sup.id,
                total_cost=po_total,
                items=po_items,
            )
            session.add(purchase)
        session.flush()

        # =============================================================
        # 17. STOCK MOVEMENTS (for recent purchases)
        # =============================================================
        print("Seeding Stock Movements...")
        for po_data in purchases_data:
            for barcode, qty, _ in po_data["items"]:
                if barcode in prod_map:
                    prod = prod_map[barcode]
                    session.add(
                        StockMovement(
                            product_id=prod.id,
                            user_id=admin.id,
                            timestamp=datetime.now() - timedelta(days=po_data["days_ago"]),
                            qty_change=Decimal(str(qty)),
                            balance_after=prod.stock_qty,
                            type="PURCHASE",
                        )
                    )
        session.flush()

        # =============================================================
        # 18. SHIFTS (recent shift history)
        # =============================================================
        print("Seeding Shifts...")
        shifts = []
        for days_ago in range(7, 0, -1):
            shift_start = datetime.now() - timedelta(days=days_ago, hours=16)
            shift_end = datetime.now() - timedelta(days=days_ago, hours=6)
            shift_user = random.choice([cashier, cashier2])

            start_cash = Decimal("5000.00")
            # Simulate some variance
            expected = start_cash + Decimal(str(random.randint(8000, 25000)))
            actual = expected + Decimal(str(random.randint(-200, 100)))

            shift = Shift(
                user_id=shift_user.id,
                start_time=shift_start,
                end_time=shift_end,
                starting_cash=start_cash,
                expected_cash=expected,
                actual_cash=actual,
                status="CLOSED",
            )
            session.add(shift)
            shifts.append(shift)
        session.flush()

        # Current open shift
        open_shift = Shift(
            user_id=cashier.id,
            start_time=datetime.now() - timedelta(hours=3),
            starting_cash=Decimal("5000.00"),
            status="OPEN",
        )
        session.add(open_shift)
        session.flush()
        shifts.append(open_shift)

        # =============================================================
        # 19. CASH MOVEMENTS
        # =============================================================
        print("Seeding Cash Movements...")
        for shift in shifts[:5]:
            session.add(
                CashMovement(
                    shift_id=shift.id,
                    user_id=shift.user_id,
                    type="DROP",
                    amount=Decimal(str(random.randint(3000, 8000))),
                    reason="Safe drop — excess cash in drawer",
                    timestamp=shift.start_time + timedelta(hours=4),
                )
            )
        # Petty cash payout
        session.add(
            CashMovement(
                shift_id=shifts[2].id,
                user_id=manager.id,
                type="OUT",
                amount=Decimal("1500.00"),
                reason="Petty cash — tea and refreshments for staff",
                timestamp=shifts[2].start_time + timedelta(hours=2),
            )
        )
        session.flush()

        # =============================================================
        # 20. AUDIT LOGS
        # =============================================================
        print("Seeding Audit Logs...")
        audit_actions = []
        for days_ago in range(7, 0, -1):
            t = datetime.now() - timedelta(days=days_ago, hours=16)
            u = random.choice(users)
            audit_actions.append(
                AuditLog(
                    user_id=u.id,
                    action=f"User {u.username} logged in",
                    event_type="LOGIN",
                    timestamp=t,
                )
            )
            audit_actions.append(
                AuditLog(
                    user_id=u.id,
                    action=f"User {u.username} logged out",
                    event_type="LOGOUT",
                    timestamp=t + timedelta(hours=random.randint(4, 10)),
                )
            )

        # Some specific events
        audit_actions.append(
            AuditLog(
                user_id=admin.id,
                action="Voided sale INV-2026-00031 — Cashier Mistake",
                event_type="TRANSACTION",
                details="Void reason: MISTAKE, Amount: Rs. 1,250.00",
                timestamp=datetime.now() - timedelta(days=2, hours=14),
            )
        )
        audit_actions.append(
            AuditLog(
                user_id=admin.id,
                action="Price override: Munchee Cream Cracker 650.00 → 600.00",
                event_type="TRANSACTION",
                details="Customer: Saman Kumara, Reason: Bulk purchase discount",
                timestamp=datetime.now() - timedelta(days=3, hours=11),
            )
        )
        audit_actions.append(
            AuditLog(
                user_id=manager.id,
                action="Stock adjustment: Red Onion -2.500 kg (damaged)",
                event_type="TRANSACTION",
                details="Reason: Damaged goods — spoiled due to storage",
                timestamp=datetime.now() - timedelta(days=1, hours=9),
            )
        )

        session.add_all(audit_actions)
        session.flush()

        # =============================================================
        # 21. INVENTORY LOGS (stock adjustments)
        # =============================================================
        print("Seeding Inventory Logs...")
        inv_logs = [
            InventoryLog(
                product_id=prod_map["2000100"].id,
                qty_change=Decimal("-2.500"),
                new_qty=prod_map["2000100"].stock_qty,
                reason="Damaged — spoiled produce",
                user_id=manager.id,
                timestamp=datetime.now() - timedelta(days=1, hours=9),
            ),
            InventoryLog(
                product_id=prod_map["4792049000160"].id,
                qty_change=Decimal("-5.000"),
                new_qty=Decimal("295.000"),
                reason="Expired stock removed",
                user_id=admin.id,
                timestamp=datetime.now() - timedelta(days=4, hours=10),
            ),
            InventoryLog(
                product_id=prod_map["4796009000035"].id,
                qty_change=Decimal("-3.000"),
                new_qty=Decimal("57.000"),
                reason="Damaged — packaging torn",
                user_id=manager.id,
                timestamp=datetime.now() - timedelta(days=5, hours=15),
            ),
            InventoryLog(
                product_id=prod_map["4796018000016"].id,
                qty_change=Decimal("20.000"),
                new_qty=Decimal("120.000"),
                reason="Stock count correction — physical count higher",
                user_id=admin.id,
                timestamp=datetime.now() - timedelta(days=6, hours=8),
            ),
        ]
        session.add_all(inv_logs)
        session.flush()

        # =============================================================
        # COMMIT
        # =============================================================
        session.commit()

    # Final summary
    print("\n" + "=" * 50)
    print("  SEEDING COMPLETE!")
    print("=" * 50)
    print("  Users:            4  (admin/1234, manager/5678, cashier/0000, nimal/1111)")
    print(f"  Categories:       {10 + 10}  (10 parent + 10 sub)")
    print("  Suppliers:        8")
    print(f"  Products:         {len(product_objs)}  (incl. weighted, composite, service)")
    print(f"  Customers:        {len(customers)}  (incl. 3 B2B companies)")
    print(f"  Sales:            ~{sale_counter}")
    print("  Purchases:        5")
    print(f"  Shifts:           {len(shifts)}")
    print("  Promotions:       3")
    print("  Payment Methods:  6")
    print("=" * 50)


if __name__ == "__main__":
    seed_data()
