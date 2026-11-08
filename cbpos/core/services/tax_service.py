import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from cbpos.core.services.config_service import ConfigService
from cbpos.core.utils.money import round_money

logger = logging.getLogger(__name__)

SSCL_PRESETS: dict[str, Decimal] = {
    "RETAIL": Decimal("50.0"),
    "MANUFACTURER": Decimal("85.0"),
    "DISTRIBUTOR": Decimal("25.0"),
}


@dataclass(frozen=True)
class TaxLine:
    """Represents a sale line's post-discount amount and taxability flags (#831)."""

    amount: Decimal
    vat_exempt: bool = False
    sscl_exempt: bool = False


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
    def is_sscl_active() -> bool:
        """Single source of truth: is SSCL enabled for this business? (#831)"""
        config = ConfigService.get_all()
        val = config.get("sscl_registered")
        if val is None:
            return bool(config.get("vat_registered", False))
        return bool(val)

    @staticmethod
    def resolve_historical_vat_rate(sale: Any) -> Decimal:
        """Resolve the VAT rate for a sale (stored snapshot with fallback for unmigrated rows) (#811).

        Args:
            sale: Sale instance or duck-typed object with vat_rate and document_number.

        Returns:
            Decimal: The effective VAT rate percentage (e.g. Decimal("18.00")).
        """
        vat_rate = getattr(sale, "vat_rate", None)
        if vat_rate is not None:
            return Decimal(str(vat_rate))

        doc_num = getattr(sale, "document_number", None) or getattr(sale, "id", "unknown")
        logger.warning(
            "Document %s missing stored vat_rate, falling back to current setting",
            doc_num,
        )
        current = ConfigService.get("tax_vat_rate")
        if current is None:
            current = 18.0
        return Decimal(str(current))

    @staticmethod
    def format_rate(rate: Any) -> str:
        """Format a tax rate percentage cleanly: 18 -> "18", 18.5 -> "18.5", 0 -> "0"."""
        if rate is None:
            return ""
        try:
            d = Decimal(str(rate))
            if d == d.to_integral():
                return f"{int(d)}"
            s = f"{d:f}".rstrip("0").rstrip(".")
            return s if s else "0"
        except (InvalidOperation, TypeError, ValueError):
            return str(rate)

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

        preset = str(config.get("sscl_turnover_preset", "RETAIL")).upper()
        if preset in SSCL_PRESETS:
            turnover_pct = SSCL_PRESETS[preset]
        else:
            turnover_pct = config.get("tax_sscl_turnover_pct", 50.0)

        # Convert to Decimal safely
        # Rate = Percentage / 100
        vat_rate = Decimal(str(vat_pct)) / Decimal("100")
        sscl_rate = Decimal(str(sscl_pct)) / Decimal("100")
        turnover_rate = Decimal(str(turnover_pct)) / Decimal("100")

        return vat_rate, sscl_rate, turnover_rate

    @staticmethod
    def distribute_bill_discount(
        line_amounts: list[Decimal],
        total_discount: Decimal,
    ) -> list[Decimal]:
        """Distribute bill-level discount proportionally across lines (#831).

        Args:
            line_amounts: The gross amount of each line.
            total_discount: Total bill-level discount (cart + loyalty) to distribute.

        Returns:
            list[Decimal]: The post-discount amount for each line, summing exactly
                to sum(line_amounts) - total_discount (or 0 if discount >= subtotal).
        """
        subtotal = sum(line_amounts, Decimal("0.00"))
        if subtotal <= Decimal("0.00") or total_discount <= Decimal("0.00"):
            return [round_money(a) for a in line_amounts]
        if total_discount >= subtotal:
            return [Decimal("0.00") for _ in line_amounts]

        ratio = total_discount / subtotal
        discounts = [round_money(amt * ratio) for amt in line_amounts]
        diff = total_discount - sum(discounts)
        if diff != Decimal("0.00") and discounts:
            max_idx = max(range(len(discounts)), key=lambda i: discounts[i])
            discounts[max_idx] += diff

        return [max(Decimal("0.00"), amt - disc) for amt, disc in zip(line_amounts, discounts, strict=False)]

    @staticmethod
    def calculate_taxes(
        total_mrp: Decimal | None = None,
        taxable_amount: Decimal | None = None,
        lines: list[TaxLine] | None = None,
    ) -> dict[str, Decimal]:
        """
        Calculate tax breakdown from the MRP (Tax Inclusive Price).

        Formula (#810, #797, #831):
        1. VAT: for lines not vat_exempt, vat = round_money(taxable_mrp * r / (1 + r))
           if vat_registered, else 0.
        2. SSCL: for lines not sscl_exempt:
           - if vat_registered and not vat_exempt: base = line.amount / (1 + r)
           - otherwise (vat_exempt or not vat_registered): base = line.amount
           sscl = round_money(sscl_base * turnover_rate * sscl_rate) if sscl_registered, else 0.
        3. Net Revenue = Total - VAT - SSCL (what the shop keeps).

        Args:
            total_mrp (Decimal, optional): Total transaction amount.
            taxable_amount (Decimal, optional): Legacy parameter for taxable portion.
            lines (list[TaxLine], optional): Individual line items with amounts and flags.

        Returns:
            dict: {'vat': Decimal, 'sscl': Decimal, 'net': Decimal,
                   'taxable_amount': Decimal, 'exempt_amount': Decimal,
                   'sscl_base': Decimal}
        """
        config = ConfigService.get_all()
        vat_registered = bool(config.get("vat_registered", False))
        sscl_registered_val = config.get("sscl_registered")
        sscl_registered = bool(vat_registered if sscl_registered_val is None else sscl_registered_val)

        # Build lines if not provided (legacy call support)
        if lines is None:
            mrp_val = total_mrp if total_mrp is not None else Decimal("0.00")
            if taxable_amount is not None:
                tax_base = taxable_amount
                exempt_base = mrp_val - taxable_amount
                lines = [
                    TaxLine(amount=tax_base, vat_exempt=False, sscl_exempt=False),
                    TaxLine(amount=exempt_base, vat_exempt=True, sscl_exempt=True),
                ]
            else:
                lines = [TaxLine(amount=mrp_val, vat_exempt=False, sscl_exempt=False)]
        else:
            total_mrp = sum((line.amount for line in lines), Decimal("0.00"))

        total_mrp_rounded = round_money(total_mrp)
        vat_rate, sscl_rate, turnover_rate = TaxService._get_rates()

        # 1. VAT calculation
        taxable_mrp = sum((line.amount for line in lines if not line.vat_exempt), Decimal("0.00"))
        exempt_mrp = sum((line.amount for line in lines if line.vat_exempt), Decimal("0.00"))

        if vat_registered and taxable_mrp != Decimal("0.00"):
            vat_amount = round_money(taxable_mrp * vat_rate / (Decimal("1") + vat_rate))
            taxable_amount_val = round_money(taxable_mrp)
            exempt_amount_val = round_money(exempt_mrp)
        else:
            vat_amount = Decimal("0.00")
            taxable_amount_val = round_money(taxable_mrp) if vat_registered else Decimal("0.00")
            exempt_amount_val = round_money(exempt_mrp) if vat_registered else Decimal("0.00")

        # 2. SSCL calculation
        if sscl_registered:
            sscl_bases = []
            for line in lines:
                if line.sscl_exempt:
                    continue
                if vat_registered and not line.vat_exempt:
                    sscl_bases.append(line.amount / (Decimal("1") + vat_rate))
                else:
                    sscl_bases.append(line.amount)
            total_sscl_base = sum(sscl_bases, Decimal("0.00"))
            sscl_amount = round_money(total_sscl_base * turnover_rate * sscl_rate)
            sscl_base_val = round_money(total_sscl_base)
        else:
            sscl_amount = Decimal("0.00")
            sscl_base_val = Decimal("0.00")

        # 3. Net Revenue (what the shop keeps)
        net_revenue = total_mrp_rounded - vat_amount - sscl_amount

        return {
            "vat": vat_amount,
            "sscl": sscl_amount,
            "net": net_revenue,
            "taxable_amount": taxable_amount_val,
            "exempt_amount": exempt_amount_val,
            "sscl_base": sscl_base_val,
        }
