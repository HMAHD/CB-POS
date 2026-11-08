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


class TestIssue810RoundingAndDecimalRates:
    """Regression tests for Issue #810 / Decision D4."""

    def test_issue_810_half_up_boundaries(self):
        """round_money must round .005 up (not half-to-even)."""
        from cbpos.core.utils.money import round_money

        # 0.125 -> 0.13 (banker's rounding would round down to 0.12)
        assert round_money(Decimal("0.125")) == Decimal("0.13")
        # 0.375 -> 0.38
        assert round_money(Decimal("0.375")) == Decimal("0.38")
        # 0.625 -> 0.63 (banker's rounding would round down to 0.62)
        assert round_money(Decimal("0.625")) == Decimal("0.63")
        # 0.875 -> 0.88
        assert round_money(Decimal("0.875")) == Decimal("0.88")
        # Negative half-up boundaries: symmetric away from zero
        assert round_money(Decimal("-0.125")) == Decimal("-0.13")
        assert round_money(Decimal("-0.625")) == Decimal("-0.63")

    def test_issue_810_components_sum_to_total(self):
        """
        D4 invariant: for every sale, round_money(vat) + round_money(sscl) + net == total_amount.
        Tested across 1,000 totals from 0.01 to 99,999.99 with deterministic steps.
        """
        with _mock_config():
            step = (Decimal("99999.99") - Decimal("0.01")) / Decimal("999")
            for i in range(1000):
                total = (Decimal("0.01") + step * Decimal(i)).quantize(Decimal("0.01"))
                res = TaxService.calculate_taxes(total)
                assert res["vat"] + res["sscl"] + res["net"] == total, (
                    f"Mismatch at total={total}: vat={res['vat']}, "
                    f"sscl={res['sscl']}, net={res['net']} sum to "
                    f"{res['vat'] + res['sscl'] + res['net']}"
                )

    def test_issue_810_vat_rate_two_decimals(self):
        """VAT rate supports two decimals (e.g., 15.50%)."""
        with _mock_config({**DEFAULT_CONFIG, "tax_vat_rate": 15.50}):
            result = TaxService.calculate_taxes(Decimal("1000.00"))
            # base = 1000 / 1.155 = 865.8008658...
            # vat = 1000 * 0.155 / 1.155 = 134.199... -> round_money -> 134.20
            assert result["vat"] == Decimal("134.20")
            assert result["vat"] + result["sscl"] + result["net"] == Decimal("1000.00")


class TestIssue831IndependentSSCL:
    """Regression tests for Issue #831: Independent SSCL, presets, and receipt truth."""

    def _make_mixed_lines(self):
        """Create a mixed bill of 4 items:

        - Line A: 1,180.00 (VAT-taxable, SSCL-liable)
        - Line B: 500.00 (VAT-exempt, SSCL-liable)
        - Line C: 200.00 (VAT-taxable, SSCL-exempt)
        - Line D: 100.00 (VAT-exempt, SSCL-exempt)
        Total MRP = 1,980.00
        """
        from cbpos.core.services.tax_service import TaxLine

        return [
            TaxLine(amount=Decimal("1180.00"), vat_exempt=False, sscl_exempt=False),
            TaxLine(amount=Decimal("500.00"), vat_exempt=True, sscl_exempt=False),
            TaxLine(amount=Decimal("200.00"), vat_exempt=False, sscl_exempt=True),
            TaxLine(amount=Decimal("100.00"), vat_exempt=True, sscl_exempt=True),
        ]

    def test_issue_831_case1_vat_true_sscl_true(self):
        """Case 1: Both VAT and SSCL registered.

        Taxable MRP for VAT = Line A (1,180.00) + Line C (200.00) = 1,380.00.
        vat = round_money(1380.00 * 0.18 / 1.18) = 210.51.
        Exempt MRP for VAT = Line B (500.00) + Line D (100.00) = 600.00.

        SSCL base (VAT-exclusive turnover for non-exempt lines):
        - Line A (VAT-taxable): 1180.00 / 1.18 = 1000.00.
        - Line B (VAT-exempt): 500.00 (no VAT inside).
        - Line C and D are SSCL-exempt -> 0.00 base.
        Total sscl_base = 1000.00 + 500.00 = 1500.00.
        sscl = round_money(1500.00 * 0.50 * 0.025) = 18.75.

        Net revenue = 1980.00 - 210.51 - 18.75 = 1750.74.
        Invariant: 210.51 + 18.75 + 1750.74 == 1980.00.
        """
        cfg = {
            **DEFAULT_CONFIG,
            "vat_registered": True,
            "sscl_registered": True,
            "tax_vat_rate": 18.0,
            "tax_sscl_rate": 2.5,
            "tax_sscl_turnover_pct": 50.0,
        }
        with _mock_config(cfg):
            lines = self._make_mixed_lines()
            res = TaxService.calculate_taxes(lines=lines, total_mrp=Decimal("1980.00"))
            assert res["vat"] == Decimal("210.51")
            assert res["sscl"] == Decimal("18.75")
            assert res["net"] == Decimal("1750.74")
            assert res["taxable_amount"] == Decimal("1380.00")
            assert res["exempt_amount"] == Decimal("600.00")
            assert res["sscl_base"] == Decimal("1500.00")
            assert res["vat"] + res["sscl"] + res["net"] == Decimal("1980.00")

    def test_issue_831_case2_vat_true_sscl_false(self):
        """Case 2: VAT registered, SSCL NOT registered.

        VAT matches Case 1: 210.51.
        SSCL = 0.00.
        Net = 1980.00 - 210.51 = 1769.49.
        """
        cfg = {
            **DEFAULT_CONFIG,
            "vat_registered": True,
            "sscl_registered": False,
            "tax_vat_rate": 18.0,
            "tax_sscl_rate": 2.5,
            "tax_sscl_turnover_pct": 50.0,
        }
        with _mock_config(cfg):
            lines = self._make_mixed_lines()
            res = TaxService.calculate_taxes(lines=lines, total_mrp=Decimal("1980.00"))
            assert res["vat"] == Decimal("210.51")
            assert res["sscl"] == Decimal("0.00")
            assert res["net"] == Decimal("1769.49")
            assert res["taxable_amount"] == Decimal("1380.00")
            assert res["exempt_amount"] == Decimal("600.00")
            assert res["vat"] + res["sscl"] + res["net"] == Decimal("1980.00")

    def test_issue_831_case3_vat_false_sscl_true(self):
        """Case 3: VAT NOT registered, SSCL registered (Rs 36M-60M threshold shop).

        VAT = 0.00.
        SSCL base: since not VAT registered, no VAT is charged, so lines A & B have base = MRP.
        - Line A: 1180.00.
        - Line B: 500.00.
        Total sscl_base = 1180.00 + 500.00 = 1680.00.
        sscl = round_money(1680.00 * 0.50 * 0.025) = 21.00.

        Net = 1980.00 - 0.00 - 21.00 = 1959.00.
        """
        cfg = {
            **DEFAULT_CONFIG,
            "vat_registered": False,
            "sscl_registered": True,
            "tax_vat_rate": 18.0,
            "tax_sscl_rate": 2.5,
            "tax_sscl_turnover_pct": 50.0,
        }
        with _mock_config(cfg):
            lines = self._make_mixed_lines()
            res = TaxService.calculate_taxes(lines=lines, total_mrp=Decimal("1980.00"))
            assert res["vat"] == Decimal("0.00")
            assert res["sscl"] == Decimal("21.00")
            assert res["net"] == Decimal("1959.00")
            assert res["sscl_base"] == Decimal("1680.00")
            assert res["vat"] + res["sscl"] + res["net"] == Decimal("1980.00")

    def test_issue_831_case4_vat_false_sscl_false(self):
        """Case 4: Neither VAT nor SSCL registered.

        VAT = 0.00, SSCL = 0.00, Net = 1980.00.
        """
        cfg = {
            **DEFAULT_CONFIG,
            "vat_registered": False,
            "sscl_registered": False,
            "tax_vat_rate": 18.0,
            "tax_sscl_rate": 2.5,
            "tax_sscl_turnover_pct": 50.0,
        }
        with _mock_config(cfg):
            lines = self._make_mixed_lines()
            res = TaxService.calculate_taxes(lines=lines, total_mrp=Decimal("1980.00"))
            assert res["vat"] == Decimal("0.00")
            assert res["sscl"] == Decimal("0.00")
            assert res["net"] == Decimal("1980.00")
            assert res["vat"] + res["sscl"] + res["net"] == Decimal("1980.00")

    def test_issue_831_presets_map_to_turnover(self):
        """SSCL presets map to statutory turnover percentages."""
        from cbpos.core.services.tax_service import SSCL_PRESETS

        assert SSCL_PRESETS["RETAIL"] == Decimal("50.0")
        assert SSCL_PRESETS["MANUFACTURER"] == Decimal("85.0")
        assert SSCL_PRESETS["DISTRIBUTOR"] == Decimal("25.0")

        # Config with MANUFACTURER preset
        cfg = {
            **DEFAULT_CONFIG,
            "sscl_registered": True,
            "sscl_turnover_preset": "MANUFACTURER",
            "tax_sscl_turnover_pct": 50.0,
        }
        with _mock_config(cfg):
            _, _, turnover_rate = TaxService._get_rates()
            assert turnover_rate == Decimal("0.85")

        # Config with DISTRIBUTOR preset
        cfg["sscl_turnover_preset"] = "DISTRIBUTOR"
        with _mock_config(cfg):
            _, _, turnover_rate = TaxService._get_rates()
            assert turnover_rate == Decimal("0.25")

        # Config with CUSTOM preset uses tax_sscl_turnover_pct
        cfg["sscl_turnover_preset"] = "CUSTOM"
        cfg["tax_sscl_turnover_pct"] = 60.0
        with _mock_config(cfg):
            _, _, turnover_rate = TaxService._get_rates()
            assert turnover_rate == Decimal("0.60")

    def test_issue_831_upgrade_sets_sscl_registered_from_vat(self):
        """ConfigService key migration sets sscl_registered from vat_registered when missing."""
        from cbpos.core.services.config_service import ConfigService

        # 1. Missing sscl_registered, vat_registered is True -> True
        s1 = {"vat_registered": True}
        assert ConfigService._migrate_sscl_keys(s1) is True
        assert s1["sscl_registered"] is True

        # 2. Missing sscl_registered, vat_registered is False -> False
        s2 = {"vat_registered": False}
        assert ConfigService._migrate_sscl_keys(s2) is True
        assert s2["sscl_registered"] is False

        # 3. Already present -> not modified
        s3 = {"vat_registered": True, "sscl_registered": False}
        assert ConfigService._migrate_sscl_keys(s3) is False
        assert s3["sscl_registered"] is False

    @patch("cbpos.core.services.loyalty_service.LoyaltyService.get_sale_loyalty_figures", return_value=None)
    def test_issue_831_receipt_has_no_sscl_line(self, _mock_loyalty):
        """Customer receipts and invoices must unconditionally omit SSCL lines."""
        from unittest.mock import MagicMock

        from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder

        mock_sale = MagicMock()
        mock_sale.total_amount = Decimal("1980.00")
        mock_sale.tax_vat = Decimal("210.51")
        mock_sale.tax_sscl = Decimal("18.75")
        mock_sale.net_revenue = Decimal("1750.74")
        mock_sale.vat_exempt_amount = Decimal("600.00")
        mock_sale.taxable_amount = Decimal("1380.00")
        mock_sale.vat_rate = Decimal("18.00")
        mock_sale.sscl_rate = Decimal("2.50")
        mock_sale.invoice_number = "INV-001"
        mock_sale.receipt_number = "REC-001"
        mock_sale.payments = []
        mock_sale.items = []
        mock_sale.customer = None
        mock_sale.cashier = None
        mock_sale.cashier_name = None
        mock_sale.additional_discount_type = "NONE"
        mock_sale.additional_discount_value = Decimal("0.00")

        receipt = SalesReceiptBuilder.build_receipt(
            mock_sale,
            config_override={"show_tax_breakdown": True},
        )
        receipt_text = " ".join(str(cmd.get("val", "")) for cmd in receipt)
        assert "SSCL" not in receipt_text
        assert "sscl" not in receipt_text.lower()


class TestIssue811HistoricalVatRateOnReprint:
    """Issue #811: Reprints must use the stored historical VAT rate from the sale snapshot."""

    @patch("cbpos.core.services.loyalty_service.LoyaltyService.get_sale_loyalty_figures", return_value=None)
    def test_issue_811_reprint_uses_sale_rate_after_setting_change(self, _mock_loyalty, monkeypatch):
        from unittest.mock import MagicMock

        from cbpos.core.services.config_service import ConfigService
        from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder

        mock_sale = MagicMock()
        mock_sale.document_number = "REC-00811"
        mock_sale.total_amount = Decimal("1180.00")
        mock_sale.tax_vat = Decimal("180.00")
        mock_sale.tax_sscl = Decimal("0.00")
        mock_sale.net_revenue = Decimal("1000.00")
        mock_sale.vat_exempt_amount = Decimal("0.00")
        mock_sale.taxable_amount = Decimal("1180.00")
        mock_sale.vat_rate = Decimal("18.00")
        mock_sale.sscl_rate = Decimal("2.50")
        mock_sale.payments = []
        mock_sale.items = []
        mock_sale.customer = None
        mock_sale.cashier = None
        mock_sale.cashier_name = None
        mock_sale.additional_discount_type = "NONE"
        mock_sale.additional_discount_value = Decimal("0.00")

        # Now simulate setting changed to 15%
        monkeypatch.setattr(
            ConfigService, "get", lambda k, *a: 15.0 if k == "tax_vat_rate" else ConfigService.DEFAULTS.get(k)
        )

        # Shared rate resolver must return stored 18.00
        resolved_rate = TaxService.resolve_historical_vat_rate(mock_sale)
        assert resolved_rate == Decimal("18.00")

        # Thermal receipt must display 18%
        receipt = SalesReceiptBuilder.build_receipt(mock_sale, config_override={"show_tax_breakdown": True})
        receipt_text = " ".join(str(cmd.get("val", "")) for cmd in receipt)
        assert "VAT (18%):" in receipt_text or "VAT (18%)" in receipt_text
        assert "15%" not in receipt_text
        assert "SSCL" not in receipt_text

    def test_stored_zero_percent_remains_zero_percent(self, monkeypatch):
        from unittest.mock import MagicMock

        from cbpos.core.services.config_service import ConfigService

        mock_sale = MagicMock()
        mock_sale.document_number = "REC-ZERO"
        mock_sale.vat_rate = Decimal("0.00")

        monkeypatch.setattr(
            ConfigService, "get", lambda k, *a: 18.0 if k == "tax_vat_rate" else ConfigService.DEFAULTS.get(k)
        )

        resolved = TaxService.resolve_historical_vat_rate(mock_sale)
        assert resolved == Decimal("0.00")

    def test_null_legacy_rate_falls_back_and_logs_warning(self, monkeypatch, caplog):
        import logging
        from unittest.mock import MagicMock

        from cbpos.core.services.config_service import ConfigService

        mock_sale = MagicMock()
        mock_sale.document_number = "REC-LEGACY"
        mock_sale.vat_rate = None

        monkeypatch.setattr(
            ConfigService, "get", lambda k, *a: 18.0 if k == "tax_vat_rate" else ConfigService.DEFAULTS.get(k)
        )

        with caplog.at_level(logging.WARNING):
            resolved = TaxService.resolve_historical_vat_rate(mock_sale)

        assert resolved == Decimal("18.0")
        assert "REC-LEGACY" in caplog.text
        assert "falling back to current setting" in caplog.text
