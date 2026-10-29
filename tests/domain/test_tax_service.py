"""
Unit tests for TaxService — Sri Lankan backward tax calculation.

Tests VAT (backward calc from MRP), SSCL (Social Security Contribution Levy),
and net revenue derivation.
"""

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch

from cbpos.core.constants.status import Precision
from cbpos.core.services.tax_service import TaxService

# Default config rates for mocking (VAT-registered business)
DEFAULT_CONFIG = {
    "tax_vat_rate": 18.0,
    "tax_sscl_rate": 2.5,
    "tax_sscl_turnover_pct": 50.0,
    "vat_registered": True,
}


@contextmanager
def _mock_config(config: dict = None):
    """Patch ConfigService.get_all and .get for tax tests."""
    cfg = config or DEFAULT_CONFIG

    def _get_side_effect(key):
        return cfg.get(key)

    with (
        patch(
            "cbpos.core.services.tax_service.ConfigService.get_all",
            return_value=cfg,
        ),
        patch(
            "cbpos.core.services.tax_service.ConfigService.get",
            side_effect=_get_side_effect,
        ),
    ):
        yield


class TestTaxServiceVAT:
    """Tests for VAT backward calculation."""

    def test_vat_backward_calculation_1000(self):
        """VAT on Rs.1000 MRP: base = 1000/1.18, VAT = 1000 - base."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("1000.00"))
            # base = 1000 / 1.18 = 847.457627...
            # vat = 1000 - 847.46 = 152.54
            expected_base = Decimal("1000.00") / Decimal("1.18")
            expected_vat = Decimal("1000.00") - expected_base
            assert result["vat"] == expected_vat.quantize(Precision.MONEY)

    def test_vat_on_zero_amount(self):
        """Zero MRP yields zero VAT."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("0.00"))
            assert result["vat"] == Decimal("0.00")

    def test_vat_on_small_amount(self):
        """VAT on Rs.1.00 MRP — tests rounding to 2 decimals."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("1.00"))
            assert isinstance(result["vat"], Decimal)
            assert result["vat"] >= Decimal("0.00")
            # VAT = 1.00 - (1.00/1.18) = 1.00 - 0.847... = 0.15
            assert result["vat"] == Decimal("0.15")

    def test_vat_on_large_amount(self):
        """VAT on Rs.100,000 MRP."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("100000.00"))
            expected_base = Decimal("100000.00") / Decimal("1.18")
            expected_vat = Decimal("100000.00") - expected_base
            assert result["vat"] == expected_vat.quantize(Precision.MONEY)

    def test_vat_plus_base_equals_mrp(self):
        """VAT + base should equal MRP (backward calc identity)."""
        with _mock_config():
            mrp = Decimal("5000.00")
            result = TaxService.calculate_taxes(mrp)
            base = mrp - result["vat"]
            # base * (1 + rate) should be close to mrp
            reconstructed = base * Decimal("1.18")
            diff = abs(reconstructed - mrp)
            assert diff <= Decimal("0.02")  # Allow rounding tolerance


class TestTaxServiceSSCL:
    """Tests for SSCL (Social Security Contribution Levy)."""

    def test_sscl_calculation_1000(self):
        """SSCL on Rs.1000: (1000/1.18 * 0.50) * 0.025 = 10.59."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("1000.00"))
            # SSCL = (VAT-exclusive base * turnover_pct) * sscl_rate
            # = (1000/1.18 * 0.5) * 0.025 = 10.59
            vat_base = Decimal("1000.00") / Decimal("1.18")
            expected = (vat_base * Decimal("0.5") * Decimal("0.025")).quantize(Precision.MONEY)
            assert result["sscl"] == expected

    def test_sscl_on_zero_amount(self):
        """Zero MRP yields zero SSCL."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("0.00"))
            assert result["sscl"] == Decimal("0.00")

    def test_sscl_on_500(self):
        """SSCL on Rs.500: (500/1.18 * 0.50) * 0.025 = 5.30."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("500.00"))
            vat_base = Decimal("500.00") / Decimal("1.18")
            expected = (vat_base * Decimal("0.5") * Decimal("0.025")).quantize(Precision.MONEY)
            assert result["sscl"] == expected


class TestTaxServiceNet:
    """Tests for net revenue calculation."""

    def test_net_equals_mrp_minus_taxes(self):
        """Net = MRP - VAT - SSCL (within rounding tolerance)."""
        with _mock_config():
            mrp = Decimal("1000.00")
            result = TaxService.calculate_taxes(mrp)
            expected = mrp - result["vat"] - result["sscl"]
            assert abs(result["net"] - expected) <= Decimal("0.01")

    def test_net_always_positive(self):
        """Net revenue should always be positive for positive MRP."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("10.00"))
            assert result["net"] > Decimal("0.00")

    def test_all_keys_present(self):
        """Result dict must contain vat, sscl, net."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("1000.00"))
            assert "vat" in result
            assert "sscl" in result
            assert "net" in result

    def test_all_values_are_decimal(self):
        """All returned values must be Decimal type."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("2500.00"))
            for key in ("vat", "sscl", "net"):
                assert isinstance(result[key], Decimal), f"{key} is not Decimal"

    def test_values_quantized_to_2dp(self):
        """All values should be quantized to 2 decimal places."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("3333.33"))
            for key in ("vat", "sscl", "net"):
                # Check that the value equals itself quantized to 2dp
                assert result[key] == result[key].quantize(Precision.MONEY)


class TestTaxServiceCustomRates:
    """Tests with custom tax rates."""

    def test_zero_vat_rate(self):
        """With 0% VAT, VAT should be zero."""
        with _mock_config({**DEFAULT_CONFIG, "tax_vat_rate": 0.0}):
            result = TaxService.calculate_taxes(Decimal("1000.00"))
            assert result["vat"] == Decimal("0.00")

    def test_zero_sscl_rate(self):
        """With 0% SSCL, SSCL should be zero."""
        with _mock_config({**DEFAULT_CONFIG, "tax_sscl_rate": 0.0}):
            result = TaxService.calculate_taxes(Decimal("1000.00"))
            assert result["sscl"] == Decimal("0.00")

    def test_negative_mrp_for_refund(self):
        """Negative MRP (refund) should produce negative taxes."""
        with _mock_config():
            result = TaxService.calculate_taxes(Decimal("-1000.00"))
            assert result["vat"] < Decimal("0.00")
            assert result["sscl"] < Decimal("0.00")
            assert result["net"] < Decimal("0.00")

    def test_not_vat_registered_returns_zero_tax(self):
        """Non-registered businesses should have zero tax, full net revenue."""
        with _mock_config({**DEFAULT_CONFIG, "vat_registered": False}):
            result = TaxService.calculate_taxes(Decimal("1000.00"))
            assert result["vat"] == Decimal("0.00")
            assert result["sscl"] == Decimal("0.00")
            assert result["net"] == Decimal("1000.00")
