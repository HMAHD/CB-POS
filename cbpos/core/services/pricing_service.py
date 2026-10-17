from datetime import datetime
from decimal import Decimal
from typing import Any

from cbpos.core.database import Database
from cbpos.core.models import Customer, PriceListItem, Product, Promotion
from cbpos.core.services.config_service import ConfigService
from cbpos.core.services.price_list_service import live_price_list_condition


class PricingService:
    """Service to calculate the actual selling price of a product

    based on Price Lists and Promotions.
    """

    @staticmethod
    def calculate_price(
        product: Product,
        customer: Customer | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Calculate the final price for a product.

        Args:
            product: The product to price.
            customer: The customer (optional) for price list lookup.
            now: The current datetime (optional, defaults to datetime.now()).

        Returns:
            Dict containing:
                - final_price: Decimal
                - original_price: Decimal
                - applied_rule: str (Description of why price changed)
        """
        if now is None:
            now = datetime.now()

        original_price = product.price
        final_price = original_price
        applied_rule = "Standard Price"

        stack_enabled = bool(ConfigService.get("promotion_stack_with_price_lists"))

        db = Database()
        with db.get_session() as session:
            # 1. Check Price List
            price_list_price: Decimal | None = None
            price_list_name: str | None = None

            if customer and customer.price_list_id:
                price_list_item = (
                    session.query(PriceListItem)
                    .join(PriceListItem.price_list)
                    .filter(
                        PriceListItem.product_id == product.id,
                        PriceListItem.price_list_id == customer.price_list_id,
                        live_price_list_condition(now),
                    )
                    .first()
                )

                if price_list_item:
                    price_list_price = price_list_item.price
                    price_list_name = price_list_item.price_list.name

            # 2. Check Promotions
            current_day = str(now.weekday())  # 0=Mon, 6=Sun
            current_time = now.time()

            promotions = (
                session.query(Promotion)
                .filter(
                    Promotion.is_active.is_(True),
                    Promotion.start_time <= now,
                    Promotion.end_time >= now,
                )
                .all()
            )

            # Determine base price for promotions
            promo_base_price = price_list_price if (stack_enabled and price_list_price is not None) else original_price

            best_promo_price: Decimal | None = None
            best_promo_name: str | None = None

            for promo in promotions:
                # Check days of week if specified
                if promo.days_of_week and current_day not in promo.days_of_week:
                    continue

                # Check daily time window if specified
                if promo.daily_start is not None and promo.daily_end is not None:
                    if promo.daily_start <= promo.daily_end:
                        # Standard intra-day window (e.g. 14:00 - 18:00)
                        if not (promo.daily_start <= current_time <= promo.daily_end):
                            continue
                    else:
                        # Overnight window (e.g. 22:00 - 04:00)
                        if not (current_time >= promo.daily_start or current_time <= promo.daily_end):
                            continue

                # A category-scoped promotion only applies to products in that category
                if promo.category_id is not None and promo.category_id != product.category_id:
                    continue

                # Calculate potential new price
                temp_price = promo_base_price
                if promo.type == "PERCENTAGE":
                    discount = (promo_base_price * promo.value) / Decimal("100")
                    temp_price = promo_base_price - discount
                elif promo.type == "FIXED_AMOUNT":
                    temp_price = promo_base_price - Decimal(str(promo.value))

                # Ensure we don't go negative
                if temp_price < 0:
                    temp_price = Decimal("0.00")

                # Apply if better than current best promo price
                if best_promo_price is None or temp_price < best_promo_price:
                    best_promo_price = temp_price
                    best_promo_name = promo.name

            # 3. Combine Price List and Promotion according to mode
            if stack_enabled:
                if price_list_price is not None and best_promo_price is not None:
                    final_price = best_promo_price
                    applied_rule = f"Price List: {price_list_name} + Promo: {best_promo_name}"
                elif price_list_price is not None:
                    final_price = price_list_price
                    applied_rule = f"Price List: {price_list_name}"
                elif best_promo_price is not None:
                    final_price = best_promo_price
                    applied_rule = f"Promo: {best_promo_name}"
                else:
                    final_price = original_price
                    applied_rule = "Standard Price"
            else:
                # Best-of (cheapest) mode:
                candidates: list[tuple[Decimal, str]] = []
                if price_list_price is not None:
                    candidates.append((price_list_price, f"Price List: {price_list_name}"))
                if best_promo_price is not None and best_promo_price < original_price:
                    candidates.append((best_promo_price, f"Promo: {best_promo_name}"))
                candidates.append((original_price, "Standard Price"))

                candidates.sort(key=lambda c: c[0])
                final_price, applied_rule = candidates[0]

        return {
            "final_price": final_price,
            "original_price": original_price,
            "applied_rule": applied_rule,
        }
