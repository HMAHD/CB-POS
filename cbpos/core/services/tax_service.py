from decimal import Decimal

from cbpos.core.services.config_service import ConfigService
from cbpos.core.utils.money import round_money


class TaxService:
    """
    Service to handle Sri Lankan Tax Logic (Backward Calculation).
    Rates are fetched from ConfigService.
    """

    @staticmethod
    def is_vat_active() -> bool:
        """Single source of truth: is VAT enabled for this business?"""
        return bool(ConfigService.get("vat_registered"))

    @staticmethod
    def _get_rates():
        """
        Helper to fetch and convert rates from config.
        Returns Decimals: VAT (0.18), SSCL (0.025), Turnover% (0.5)
        """
        config = ConfigService.get_all()

        # Fetch values (defaults if missing)
        vat_pct = config.get("tax_vat_rate", 18.0)
        sscl_pct = config.get("tax_sscl_rate", 2.5)
        turnover_pct = config.get("tax_sscl_turnover_pct", 50.0)

        # Convert to Decimal safely
        # Rate = Percentage / 100
        vat_rate = Decimal(str(vat_pct)) / Decimal("100")
        sscl_rate = Decimal(str(sscl_pct)) / Decimal("100")
        turnover_rate = Decimal(str(turnover_pct)) / Decimal("100")

        return vat_rate, sscl_rate, turnover_rate

    @staticmethod
    def calculate_taxes(
        total_mrp: Decimal,
        taxable_amount: Decimal | None = None,
    ) -> dict[str, Decimal]:
        """
        Calculate tax breakdown from the MRP (Tax Inclusive Price).

        Formula:
        1. VAT Liable Base = MRP / (1 + VAT Rate)
        2. VAT Amount = MRP - VAT Liable Base
        3. SSCL Liability = (VAT Liable Base * Turnover%) * SSCL Rate
        4. Net Revenue = MRP - VAT - SSCL

        Args:
            total_mrp (Decimal): The total transaction amount.
            taxable_amount (Decimal, optional): If provided, only this portion
                of total_mrp is subject to tax (the rest is exempt).

        Returns:
            dict: {'vat': Decimal, 'sscl': Decimal, 'net': Decimal,
                   'exempt_amount': Decimal}
        """
        # Skip tax calculation for non-registered businesses
        if not ConfigService.get("vat_registered"):
            return {
                "vat": Decimal("0.00"),
                "sscl": Decimal("0.00"),
                "net": round_money(total_mrp),
                "exempt_amount": Decimal("0.00"),
                "sscl_base": round_money(total_mrp),
            }

        # Determine taxable vs exempt portions
        if taxable_amount is not None:
            tax_base_mrp = taxable_amount
            exempt_amt = total_mrp - taxable_amount
        else:
            tax_base_mrp = total_mrp
            exempt_amt = Decimal("0.00")

        vat_rate, sscl_rate, turnover_rate = TaxService._get_rates()

        # 1. VAT Calculation (statutory tax fraction r / (1 + r))
        if tax_base_mrp != Decimal("0"):
            vat_amount = round_money(tax_base_mrp * vat_rate / (Decimal("1") + vat_rate))
            vat_liable_base = tax_base_mrp / (Decimal("1") + vat_rate)
        else:
            vat_liable_base = Decimal("0")
            vat_amount = Decimal("0.00")

        # 2. SSCL Calculation
        # SSCL is calculated on a percentage of VAT-exclusive turnover
        sscl_unrounded = (vat_liable_base * turnover_rate) * sscl_rate
        sscl_amount = round_money(sscl_unrounded)

        # 3. Net Revenue (What the shop keeps)
        # Revenue = Total - Taxes (D4: net is never independently rounded)
        net_revenue = total_mrp - vat_amount - sscl_amount

        return {
            "vat": vat_amount,
            "sscl": sscl_amount,
            "net": net_revenue,
            "exempt_amount": round_money(exempt_amt),
            "sscl_base": round_money(vat_liable_base),
        }
