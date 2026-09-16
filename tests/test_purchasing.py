import sys
from decimal import Decimal
from pathlib import Path

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from cbpos.core.database import Database  # noqa: E402
from cbpos.core.models import Product, StockMovement, User  # noqa: E402
from cbpos.core.services.purchase_service import PurchaseService  # noqa: E402
from cbpos.core.services.supplier_service import SupplierService  # noqa: E402


def test_purchasing():
    print("Testing Purchasing Module...")

    db = Database()
    with db.get_session() as session:
        # 1. Setup Data
        # Get Admin User
        admin = session.query(User).filter_by(username="admin").first()
        if not admin:
            print("Admin user not found. Seeding required.")
            return

        # Create Supplier
        supplier = SupplierService.create_supplier(
            company_name="Test Supplier Ltd",
            contact_person="Mr. Test",
            phone="0779998888",
        )
        print(f"Created Supplier: {supplier.company_name}")

        # Get Product (Cream Cracker)
        product = session.query(Product).filter(Product.barcode == "47920240").first()
        if not product:
            print("Product not found.")
            return

        initial_qty = product.stock_qty
        initial_cost = product.cost
        print(f"Product: {product.name_en}")
        print(f"Initial Stock: {initial_qty}, Cost: {initial_cost}")

        # 2. Create GRN (Draft)
        purchase = PurchaseService.create_purchase(
            supplier_id=supplier.id,
            reference_external="INV-TEST-001",
            user_id=admin.id,
        )
        print(f"Created Draft GRN: {purchase.document_number}")

        # 3. Commit GRN
        # Receive 100 units at 600.00 (Higher than initial 500.00)
        new_qty = Decimal("100.000")
        new_cost = Decimal("600.00")

        items_data = [{"product_id": product.id, "qty": new_qty, "cost": new_cost}]

        PurchaseService.commit_purchase(purchase.id, items_data)
        print("Committed GRN.")

        # 4. Verify Results
        # Re-fetch product
        session.refresh(product)

        final_qty = product.stock_qty
        final_cost = product.cost

        print(f"Final Stock: {final_qty}")
        print(f"Final Cost: {final_cost}")

        # Verify Stock Increase
        assert final_qty == initial_qty + new_qty

        # Verify AVCO
        # Old Value = 100 * 500 = 50000
        # New Value = 100 * 600 = 60000
        # Total Value = 110000
        # Total Qty = 200
        # Avg Cost = 110000 / 200 = 550.00
        expected_cost = ((initial_qty * initial_cost) + (new_qty * new_cost)) / (initial_qty + new_qty)
        print(f"Expected Cost: {expected_cost}")

        # Allow small rounding diff
        assert abs(final_cost - expected_cost) < Decimal("0.01")

        # Verify Stock Movement
        movement = session.query(StockMovement).filter_by(document_id=purchase.id).first()
        assert movement is not None
        assert movement.qty_change == new_qty
        print("Stock Movement Verified.")

    print("Purchasing Tests Passed!")


if __name__ == "__main__":
    test_purchasing()
