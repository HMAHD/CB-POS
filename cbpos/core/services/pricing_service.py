from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any
from cbpos.core.database import Database
from cbpos.core.models import Product, Customer, PriceListItem, Promotion


class PricingService:
    """
    Service to calculate the actual selling price of a product
    based on Price Lists and Promotions.
    """

    @staticmethod
    def calculate_price(product: Product, customer: Optional[Customer] = None) -> Dict[str, Any]:
        """
        Calculate the final price for a product.

        Args:
            product: The product to price.
            customer: The customer (optional) for price list lookup.

        Returns:
            Dict containing:
                - final_price: Decimal
                - original_price: Decimal
                - applied_rule: str (Description of why price changed)
        """
        original_price = product.price
        final_price = original_price
        applied_rule = "Standard Price"

        db = Database()
        with db.get_session() as session:
            # 1. Check Price List
            if customer and customer.price_list_id:
                # Re-query price list to ensure it's active and load items
                # Note: We query PriceListItem directly for efficiency
                price_list_item = (
                    session.query(PriceListItem)
                    .join(PriceListItem.price_list)
                    .filter(
                        PriceListItem.product_id == product.id,
                        PriceListItem.price_list_id == customer.price_list_id,
                        PriceListItem.price_list.has(is_active=True),
                    )
                    .first()
                )

                if price_list_item:
                    final_price = price_list_item.price
                    applied_rule = f"Price List: {price_list_item.price_list.name}"

            # 2. Check Promotions
            # Find active promotions for this time
            now = datetime.now()
            current_day = str(now.weekday())  # 0=Mon, 6=Sun

            promotions = (
                session.query(Promotion)
                .filter(
                    Promotion.is_active.is_(True),
                    Promotion.start_time <= now,
                    Promotion.end_time >= now,
                )
                .all()
            )

            best_promo_price = final_price
            promo_rule = None

            for promo in promotions:
                # Check days of week if specified
                if promo.days_of_week and current_day not in promo.days_of_week:
                    continue

                # Calculate potential new price
                temp_price = final_price
                if promo.type == "PERCENTAGE":
                    discount = (final_price * promo.value) / 100
                    temp_price = final_price - discount
                elif promo.type == "FIXED_AMOUNT":
                    temp_price = final_price - promo.value

                # Ensure we don't go negative
                if temp_price < 0:
                    temp_price = Decimal("0.00")

                # Apply if better than current best
                if temp_price < best_promo_price:
                    best_promo_price = temp_price
                    promo_rule = f"Promo: {promo.name}"

            if promo_rule:
                final_price = best_promo_price
                applied_rule = promo_rule

        return {
            "final_price": final_price,
            "original_price": original_price,
            "applied_rule": applied_rule,
        }
