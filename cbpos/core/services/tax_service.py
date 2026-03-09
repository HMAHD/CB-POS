from decimal import Decimal
from typing import Dict
from cbpos.core.constants.status import Precision
from cbpos.core.services.config_service import ConfigService


class TaxService:
    """
    Service to handle Sri Lankan Tax Logic (Backward Calculation).
    Rates are fetched from ConfigService.
    """

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
    def calculate_taxes(total_mrp: Decimal) -> Dict[str, Decimal]:
        """
        Calculate tax breakdown from the MRP (Tax Inclusive Price).

        Formula:
        1. VAT Liable Base = MRP / (1 + VAT Rate)
        2. VAT Amount = MRP - VAT Liable Base
        3. SSCL Liability = (VAT Liable Base * Turnover%) * SSCL Rate
        4. Net Revenue = MRP - VAT - SSCL

        Args:
            total_mrp (Decimal): The total transaction amount.

        Returns:
            dict: {'vat': Decimal, 'sscl': Decimal, 'net': Decimal}
        """
        # Skip tax calculation for non-registered businesses
        if not ConfigService.get("vat_registered"):
            return {
                "vat": Decimal("0.00"),
                "sscl": Decimal("0.00"),
                "net": total_mrp.quantize(Precision.MONEY),
            }

        vat_rate, sscl_rate, turnover_rate = TaxService._get_rates()

        # 1. VAT Calculation
        # Base + VAT = MRP
        # Base * (1 + VAT_RATE) = MRP
        # Base = MRP / (1 + VAT_RATE)
        vat_liable_base = total_mrp / (Decimal("1") + vat_rate)
        vat_amount = total_mrp - vat_liable_base

        # 2. SSCL Calculation
        # SSCL is calculated on a percentage of VAT-exclusive turnover
        sscl_amount = (vat_liable_base * turnover_rate) * sscl_rate

        # 3. Net Revenue (What the shop keeps)
        # Revenue = Total - Taxes
        net_revenue = total_mrp - vat_amount - sscl_amount

        return {
            "vat": vat_amount.quantize(Precision.MONEY),
            "sscl": sscl_amount.quantize(Precision.MONEY),
            "net": net_revenue.quantize(Precision.MONEY),
        }
