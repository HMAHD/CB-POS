import sys
import os

sys.path.append(os.getcwd())

from cbpos.core.database import get_db_session, Database  # noqa: E402
from cbpos.core.models import Product, Category, User  # noqa: E402
from cbpos.core.services.stock_service import StockService  # noqa: E402
from decimal import Decimal  # noqa: E402


def verify_advanced_inventory():
    Database().create_tables()

    with get_db_session() as session:
        # Create a User for testing
        user = session.query(User).filter_by(username="admin").first()
        if not user:
            user = User(username="admin", pin_hash="1234")
            session.add(user)
            session.commit()
            print("Created admin user")

        # 1. Verify Category Hierarchy
        # Check if exists first to avoid unique constraint error on re-run
        parent_cat = session.query(Category).filter_by(name="Beverages").first()
        if not parent_cat:
            parent_cat = Category(name="Beverages", color="#FF0000")
            session.add(parent_cat)
            session.commit()

        child_cat = session.query(Category).filter_by(name="Soda").first()
        if not child_cat:
            child_cat = Category(name="Soda", parent_id=parent_cat.id, color="#00FF00")
            session.add(child_cat)
            session.commit()

        print(f"Created Category Hierarchy: {parent_cat.name} -> {child_cat.name}")
        assert child_cat.parent_id == parent_cat.id

        # 2. Verify Service Item (No Stock Tracking)
        service_item = session.query(Product).filter_by(barcode="SERV001").first()
        if not service_item:
            service_item = Product(
                barcode="SERV001",
                name_en="Delivery Fee",
                price=Decimal("500.00"),
                is_service=True,
                stock_qty=Decimal("0"),
            )
            session.add(service_item)
            session.commit()

        # Try to record movement for service item
        result = StockService.record_movement(
            service_item.id, Decimal("-1"), "SALE", "REC001", user.id
        )
        assert result is None
        print("Verified Service Item: No stock movement recorded")

        # 3. Verify Stock Movement & History
        product = session.query(Product).filter_by(barcode="PROD001").first()
        if not product:
            product = Product(
                barcode="PROD001",
                name_en="Coke 500ml",
                price=Decimal("150.00"),
                stock_qty=Decimal("100.00"),
                reorder_point=Decimal("10.00"),
                preferred_qty=Decimal("50.00"),
            )
            session.add(product)
            session.commit()
        else:
            # Reset stock for test
            product.stock_qty = Decimal("100.00")
            session.commit()

        # Record Movement
        StockService.record_movement(
            product.id, Decimal("-5"), "SALE", "REC002", user.id
        )

        # Verify Balance
        session.refresh(product)
        assert product.stock_qty == Decimal("95.00")
        print(f"Verified Stock Update: 100 - 5 = {product.stock_qty}")

        # Verify History
        history = StockService.get_history(product.id)
        # There might be previous history if re-run, just check if latest is correct
        latest = history[0]
        assert latest.qty_change == Decimal("-5")
        assert latest.balance_after == Decimal("95.00")
        print("Verified Stock History Record")

        # 4. Verify Reorder List
        product.stock_qty = Decimal("5.00")  # Below reorder point 10
        session.commit()

        reorder_list = StockService.get_reorder_list()
        # Check if product is in list (by id)
        found = any(p.id == product.id for p in reorder_list)
        assert found
        print("Verified Reorder List")


if __name__ == "__main__":
    try:
        verify_advanced_inventory()
        print("ALL CHECKS PASSED")
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback

        traceback.print_exc()
