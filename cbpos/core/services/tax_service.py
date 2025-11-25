from decimal import Decimal
from typing import Dict

class TaxService:
    """
    Service to handle Sri Lankan Tax Logic (Backward Calculation).
    """
    VAT_RATE = Decimal("0.18")
    SSCL_RATE = Decimal("0.025")
    SSCL_TURNOVER_PCT = Decimal("0.5") # SSCL is on 50% of turnover for Retail

    @staticmethod
    def calculate_taxes(total_mrp: Decimal) -> Dict[str, Decimal]:
        """
        Calculate tax breakdown from the MRP (Tax Inclusive Price).
        
        Formula:
        1. SSCL Liability = (MRP * 0.5) * 0.025
        2. VAT Liable Base = MRP / 1.18
        3. VAT Amount = MRP - VAT Liable Base
        4. Net Revenue = MRP - VAT - SSCL
        
        Args:
            total_mrp (Decimal): The total transaction amount.
            
        Returns:
            dict: {'vat': Decimal, 'sscl': Decimal, 'net': Decimal}
        """
        # 1. SSCL
        # Note: In strict accounting, SSCL might be part of the VAT base, 
        # but for simple retail backward calc, we often treat them as components extracted from MRP.
        # However, the user prompt specified: "The user enters the Final Price. The System divides by 1.18 (for VAT)..."
        # And "SSCL: Calculated on 50% of Turnover at 2.5%."
        
        # Let's follow the standard interpretation for "Backward Calculation":
        # The MRP includes VAT. So we first strip VAT.
        
        # VAT Calculation
        # Base + VAT = MRP
        # Base * 1.18 = MRP
        # Base = MRP / 1.18
        vat_liable_base = total_mrp / (Decimal("1") + TaxService.VAT_RATE)
        vat_amount = total_mrp - vat_liable_base
        
        # SSCL Calculation
        # SSCL is usually a turnover tax, calculated on the gross receipt.
        sscl_amount = (total_mrp * TaxService.SSCL_TURNOVER_PCT) * TaxService.SSCL_RATE
        
        # Net Revenue (What the shop keeps)
        # Revenue = Total - Taxes
        net_revenue = total_mrp - vat_amount - sscl_amount
        
        return {
            'vat': vat_amount.quantize(Decimal("0.01")),
            'sscl': sscl_amount.quantize(Decimal("0.01")),
            'net': net_revenue.quantize(Decimal("0.01"))
        }
