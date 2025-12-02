import sys
from pathlib import Path
from decimal import Decimal

# Add project root to python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from cbpos.core.database import Database  # noqa: E402
from cbpos.core.models import Product, Customer, PriceList, PriceListItem  # noqa: E402
from cbpos.core.services.pricing_service import PricingService  # noqa: E402
from cbpos.core.services.document_service import DocumentService  # noqa: E402
from cbpos.core.services.cart_service import CartService  # noqa: E402


def test_logic():
    print("Testing Logic Layer...")

    # Initialize Database (Create tables if not exist)
    Database().create_tables()

    # 1. Test Document Service
    doc_num = DocumentService.generate_number("SALE")
    print(f"Generated Document Number: {doc_num}")
    assert doc_num.startswith("INV-")

    # 2. Test Pricing Service
    db = Database()
    with db.get_session() as session:
        # Get a product
        product = session.query(Product).first()
        if not product:
            print("No products found to test pricing.")
            return

        print(f"Testing Product: {product.name_en} (Base Price: {product.price})")

        # Case A: No Customer
        price_a = PricingService.calculate_price(product, None)
        print(f"Price (No Customer): {price_a['final_price']} ({price_a['applied_rule']})")
        assert price_a["final_price"] == product.price

        # Case B: Wholesale Customer
        # Find wholesale list
        wholesale_list = session.query(PriceList).filter_by(name="Wholesale").first()
        if wholesale_list:
            # Add a price list item for this product
            # Check if exists first
            pli = session.query(PriceListItem).filter_by(price_list_id=wholesale_list.id, product_id=product.id).first()
            if not pli:
                pli = PriceListItem(
                    price_list_id=wholesale_list.id,
                    product_id=product.id,
                    price=product.price - Decimal("50.00"),  # Discounted
                )
                session.add(pli)
                session.commit()
                print(f"Added Wholesale Price: {pli.price}")

            customer = session.query(Customer).filter(Customer.price_list_id == wholesale_list.id).first()
            if customer:
                # Need to re-query product to ensure it's attached to session if needed,
                # but calculate_price handles its own session.
                # However, we passed 'product' which might be detached.
                # PricingService uses product.id, so it should be fine.
                price_b = PricingService.calculate_price(product, customer)
                print(f"Price (Wholesale Customer): {price_b['final_price']} " f"({price_b['applied_rule']})")
                assert price_b["final_price"] < product.price
                assert "Wholesale" in price_b["applied_rule"]
            else:
                print("No wholesale customer found.")

    # 3. Test Cart Service
    cart = CartService()
    cart.set_customer(customer)  # Set the wholesale customer
    cart.add_item(product, Decimal("2"))
    totals = cart.get_totals()
    print(f"Cart Total (2x {price_b['final_price']}): {totals['subtotal']}")

    print("Logic Layer Tests Passed!")


if __name__ == "__main__":
    test_logic()
