"""Tests for LabelService barcode label generation."""

from decimal import Decimal
from unittest.mock import MagicMock

from cbpos.core.services.label_service import LabelLayout, LabelOptions, LabelService


def _make_product(name: str = "Test Product", barcode: str = "1234567890", price: Decimal = Decimal("350.00")):
    """Create a mock product for testing."""
    product = MagicMock()
    product.name_en = name
    product.name_si = ""
    product.name_ta = ""
    product.barcode = barcode
    product.price = price

    def _get_display_name(lang: str | None = None) -> str:
        lang = (lang or "en").lower()
        if lang == "si" and (product.name_si or "").strip():
            return product.name_si.strip()
        if lang == "ta" and (product.name_ta or "").strip():
            return product.name_ta.strip()
        return (product.name_en or "").strip()

    product.get_display_name = _get_display_name
    return product


class TestLabelService:
    """Unit tests for LabelService."""

    def test_build_single_label(self):
        """Test that a single label has all required commands."""
        product = _make_product()
        commands = LabelService._build_single_label(product)

        types = [c["type"] for c in commands]
        assert "text" in types
        assert "barcode" in types
        assert "cut" in types
        assert "feed" in types

        # Product name is first
        assert commands[0]["val"] == "Test Product"
        assert commands[0]["align"] == "center"

        # Barcode command
        barcode_cmd = next(c for c in commands if c["type"] == "barcode")
        assert barcode_cmd["val"] in ("1234567890", "{C1234567890")
        assert barcode_cmd["code"] == "CODE128"

    def test_generate_label_commands_quantity(self):
        """Test that correct number of label copies are generated."""
        product = _make_product()
        labels = LabelService.generate_label_commands(product, quantity=3)
        assert len(labels) == 3
        for label in labels:
            assert isinstance(label, list)
            assert len(label) > 0

    def test_generate_label_commands_default_qty(self):
        """Test default quantity is 1."""
        product = _make_product()
        labels = LabelService.generate_label_commands(product)
        assert len(labels) == 1

    def test_generate_batch_commands(self):
        """Test batch command generation for multiple products."""
        p1 = _make_product("Product A", "AAA", Decimal("100"))
        p2 = _make_product("Product B", "BBB", Decimal("200"))

        items = [
            {"product": p1, "quantity": 2},
            {"product": p2, "quantity": 1},
        ]

        commands = LabelService.generate_batch_commands(items)

        # 3 labels total, each has 6 commands (text, barcode, text, text, feed, cut)
        assert len(commands) == 3 * 6

        # Verify cut commands count matches total labels
        cuts = [c for c in commands if c["type"] == "cut"]
        assert len(cuts) == 3

    def test_batch_and_single_consistency(self):
        """Test that batch uses same command structure as single."""
        product = _make_product()
        single = LabelService._build_single_label(product)
        batch = LabelService.generate_batch_commands([{"product": product, "quantity": 1}])
        assert single == batch

    def test_generate_batch_empty(self):
        """Test batch with empty list."""
        commands = LabelService.generate_batch_commands([])
        assert commands == []

    def test_issue_819_label_layout_model_and_shared_options(self):
        """Preview and print consume the same immutable layout model."""
        product = _make_product(name="Ceylon Tea 100g", barcode="4006381333931", price=Decimal("450.00"))
        opts = LabelOptions(preset="50x30", width_mm=50.0, height_mm=30.0, language="en")
        layout = LabelService.create_layout(product, opts)

        assert isinstance(layout, LabelLayout)
        assert layout.options == opts
        assert layout.product_name == "Ceylon Tea 100g"
        assert layout.barcode_value == "4006381333931"
        assert layout.barcode_symbology == "EAN13"
        assert "450.00" in layout.price_text
        assert len(layout.commands) > 0
        assert layout.is_fallback is False

    def test_issue_819_ean13_and_code128_symbology_selection(self):
        """Valid 13-digit EAN-13 uses EAN13; non-EAN uses CODE128 matching choose_barcode."""
        ean_prod = _make_product(name="EAN Prod", barcode="4006381333931")
        code128_prod = _make_product(name="Code128 Prod", barcode="4791234567890")
        alpha_prod = _make_product(name="Alpha Prod", barcode="TEA-001")

        layout_ean = LabelService.create_layout(ean_prod)
        assert layout_ean.barcode_symbology == "EAN13"
        assert layout_ean.barcode_payload == "4006381333931"

        layout_c128 = LabelService.create_layout(code128_prod)
        assert layout_c128.barcode_symbology == "CODE128"
        assert layout_c128.barcode_payload == "{B4791234567890"

        layout_alpha = LabelService.create_layout(alpha_prod)
        assert layout_alpha.barcode_symbology == "CODE128"
        assert layout_alpha.barcode_payload == "{BTEA-001"

    def test_issue_819_no_hash_fake_barcode_remains(self):
        """Fake hash-based barcode generator must be completely removed."""
        import cbpos.ui.dialogs.label_preview_dialog as lpd

        assert not hasattr(lpd, "_code128_bars")

    def test_issue_819_preset_and_custom_dimensions_affect_commands(self):
        """Presets (40x25, 50x30, 58mm) and custom sizes scale barcode height/width and feed lines."""
        prod = _make_product()
        layout_small = LabelService.create_layout(prod, LabelOptions(preset="40x25", width_mm=40.0, height_mm=25.0))
        layout_large = LabelService.create_layout(prod, LabelOptions(preset="58mm", width_mm=58.0, height_mm=40.0))

        bc_small = next(c for c in layout_small.commands if c["type"] == "barcode")
        bc_large = next(c for c in layout_large.commands if c["type"] == "barcode")
        assert bc_small["height"] < bc_large["height"]

        feed_small = next(c for c in layout_small.commands if c["type"] == "feed")
        feed_large = next(c for c in layout_large.commands if c["type"] == "feed")
        assert feed_small["lines"] <= feed_large["lines"]

    def test_issue_819_dimension_validation(self):
        """Validate custom dimensions against printable width; reject invalid sizes."""
        ok, err = LabelService.validate_dimensions(50.0, 30.0, max_printable_width_mm=80.0)
        assert ok is True
        assert err is None

        ok, err = LabelService.validate_dimensions(85.0, 30.0, max_printable_width_mm=80.0)
        assert ok is False
        assert err is not None

        ok, err = LabelService.validate_dimensions(15.0, 10.0, max_printable_width_mm=80.0)
        assert ok is False
        assert err is not None

    def test_issue_819_sinhala_tamil_uses_display_name_and_raster(self):
        """Sinhala and Tamil names use ProductService.display_name and trigger raster on print."""
        from cbpos.infrastructure.hardware.text_raster import needs_raster

        prod = _make_product(name="English Tea")
        prod.name_si = "ලංකා තේ"
        prod.name_ta = "இலங்கை தேநீர்"

        layout_si = LabelService.create_layout(prod, LabelOptions(language="si"))
        assert layout_si.product_name == "ලංකා තේ"
        assert layout_si.is_fallback is False
        assert needs_raster(layout_si.product_name) is True

        layout_ta = LabelService.create_layout(prod, LabelOptions(language="ta"))
        assert layout_ta.product_name == "இலங்கை தேநீர்"
        assert layout_ta.is_fallback is False
        assert needs_raster(layout_ta.product_name) is True

    def test_issue_819_missing_local_name_fallback(self):
        """Missing local name visibly falls back to English and never prints blank."""
        prod = _make_product(name="English Only Tea")
        prod.name_si = ""
        prod.name_ta = None

        layout_si = LabelService.create_layout(prod, LabelOptions(language="si"))
        assert layout_si.is_fallback is True
        assert layout_si.product_name == "English Only Tea"
        assert len(layout_si.product_name) > 0

        layout_ta = LabelService.create_layout(prod, LabelOptions(language="ta"))
        assert layout_ta.is_fallback is True
        assert layout_ta.product_name == "English Only Tea"
        assert len(layout_ta.product_name) > 0

    def test_issue_819_bilingual_options(self):
        """English + Sinhala/Tamil produces primary and secondary names."""
        prod = _make_product(name="English Tea")
        prod.name_si = "ලංකා තේ"

        layout_bi = LabelService.create_layout(prod, LabelOptions(language="en+si"))
        assert layout_bi.product_name == "English Tea"
        assert layout_bi.secondary_name == "ලංකා තේ"
        assert layout_bi.is_fallback is False

        prod_no_si = _make_product(name="English Tea")
        prod_no_si.name_si = ""
        layout_bi_missing = LabelService.create_layout(prod_no_si, LabelOptions(language="en+si"))
        assert layout_bi_missing.product_name == "English Tea"
        assert layout_bi_missing.secondary_name is None
        assert layout_bi_missing.is_fallback is True

    def test_issue_819_barcode_image_generation(self):
        """python-barcode generates real PNG bytes for preview."""
        png_ean = LabelService.render_barcode_image("4006381333931", "EAN13")
        assert png_ean is not None
        assert png_ean.startswith(b"\x89PNG")

        png_c128 = LabelService.render_barcode_image("ABC-123", "CODE128")
        assert png_c128 is not None
        assert png_c128.startswith(b"\x89PNG")

        assert LabelService.render_barcode_image("", "CODE128") is None
