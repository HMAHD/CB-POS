"""Tests for #805: Thermal receipts always print English item names.

Receipt item lines must use the configured receipt language (si/ta),
falling back to English when the localized name is empty, across all receipt
builders (SalesReceiptBuilder, VoidReceiptBuilder, RefundReceiptBuilder) and
the A4 invoice (InvoiceService).
"""

from decimal import Decimal

from cbpos.core.models import Product, Sale, SaleItem
from cbpos.core.services.invoice_service import InvoiceService
from cbpos.core.services.product_service import ProductService
from cbpos.core.services.refund_receipt_builder import RefundReceiptBuilder
from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder
from cbpos.core.services.void_receipt_builder import VoidReceiptBuilder
from cbpos.infrastructure.hardware.text_raster import needs_raster


class TestProductServiceDisplayName:
    """ProductService.display_name(product, lang) rule tests."""

    def test_product_service_display_name_si_with_localized_name(self):
        p = Product(name_en="Sugar 1kg", name_si="සීනි 1kg", name_ta="சர்க்கரை 1kg")
        assert ProductService.display_name(p, "si") == "සීනි 1kg"

    def test_product_service_display_name_si_fallback_to_en(self):
        p = Product(name_en="Sugar 1kg", name_si="", name_ta="சர்க்கரை 1kg")
        assert ProductService.display_name(p, "si") == "Sugar 1kg"

    def test_product_service_display_name_ta_with_localized_name(self):
        p = Product(name_en="Sugar 1kg", name_si="සීනි 1kg", name_ta="சர்க்கரை 1kg")
        assert ProductService.display_name(p, "ta") == "சர்க்கரை 1kg"

    def test_product_service_display_name_ta_fallback_to_en(self):
        p = Product(name_en="Sugar 1kg", name_si="සීනි 1kg", name_ta=None)
        assert ProductService.display_name(p, "ta") == "Sugar 1kg"

    def test_product_service_display_name_en(self):
        p = Product(name_en="Sugar 1kg", name_si="සීනි 1kg", name_ta="சர்க்கரை 1kg")
        assert ProductService.display_name(p, "en") == "Sugar 1kg"

    def test_product_service_display_name_none_or_empty(self):
        assert ProductService.display_name(None, "si") == ""


def _create_mock_sale_with_products():
    p_localized = Product(id=1, name_en="Tea", name_si="තේ කොළ", name_ta="தேயிலை", price=250.0)
    p_fallback = Product(id=2, name_en="Milk Powder", name_si=None, name_ta="", price=500.0)

    sale = Sale(
        id=101,
        document_number="REC-805",
        total_amount=Decimal("750.00"),
        payment_method="CASH",
        status="COMPLETED",
    )
    item1 = SaleItem(
        id=1,
        sale_id=101,
        product_id=1,
        product=p_localized,
        qty=Decimal("1"),
        unit_price=Decimal("250.00"),
        subtotal=Decimal("250.00"),
    )
    item2 = SaleItem(
        id=2,
        sale_id=101,
        product_id=2,
        product=p_fallback,
        qty=Decimal("1"),
        unit_price=Decimal("500.00"),
        subtotal=Decimal("500.00"),
    )
    sale.items = [item1, item2]
    return sale, p_localized, p_fallback


class TestReceiptBuildersItemNames:
    """Test localized product names and fallback in receipt builders."""

    def test_sales_receipt_builder_si_localized_and_fallback(self):
        sale, _, _ = _create_mock_sale_with_products()
        commands = SalesReceiptBuilder.build_receipt(sale, config_override={"receipt_language": "si"})

        texts = [c["val"] for c in commands if c.get("type") == "text"]
        # Localized item line must contain Sinhala name
        loc_line = next(t for t in texts if "01 " in t)
        assert "තේ කොළ" in loc_line
        assert needs_raster(loc_line) is True

        # Fallback item line must contain English name
        fb_line = next(t for t in texts if "02 " in t)
        assert "Milk Powder" in fb_line

    def test_sales_receipt_builder_ta_localized_and_fallback(self):
        sale, _, _ = _create_mock_sale_with_products()
        commands = SalesReceiptBuilder.build_receipt(sale, config_override={"receipt_language": "ta"})

        texts = [c["val"] for c in commands if c.get("type") == "text"]
        loc_line = next(t for t in texts if "01 " in t)
        assert "தேயிலை" in loc_line
        assert needs_raster(loc_line) is True

        fb_line = next(t for t in texts if "02 " in t)
        assert "Milk Powder" in fb_line

    def test_sales_receipt_builder_merged_items_localized(self):
        sale, p_loc, _ = _create_mock_sale_with_products()
        # Add duplicate line
        item_dup = SaleItem(
            id=3,
            sale_id=101,
            product_id=1,
            product=p_loc,
            qty=Decimal("2"),
            unit_price=Decimal("250.00"),
            subtotal=Decimal("500.00"),
        )
        sale.items.append(item_dup)

        commands = SalesReceiptBuilder.build_receipt(
            sale, config_override={"receipt_language": "si", "merge_items": True}
        )
        texts = [c["val"] for c in commands if c.get("type") == "text"]
        loc_line = next(t for t in texts if "01 " in t)
        assert "තේ කොළ" in loc_line

    def test_void_receipt_builder_si_and_ta(self):
        sale, _, _ = _create_mock_sale_with_products()
        # Sinhala
        commands_si = VoidReceiptBuilder.build_void_receipt(sale, config_override={"receipt_language": "si"})
        texts_si = [c["val"] for c in commands_si if c.get("type") == "text"]
        assert "තේ කොළ" in texts_si
        assert "Milk Powder" in texts_si

        # Tamil
        commands_ta = VoidReceiptBuilder.build_void_receipt(sale, config_override={"receipt_language": "ta"})
        texts_ta = [c["val"] for c in commands_ta if c.get("type") == "text"]
        assert "தேயிலை" in texts_ta
        assert "Milk Powder" in texts_ta

    def test_refund_receipt_builder_si_and_ta(self):
        sale, _, _ = _create_mock_sale_with_products()
        # Sinhala
        commands_si = RefundReceiptBuilder.build_refund_receipt(sale, config_override={"receipt_language": "si"})
        texts_si = [c["val"] for c in commands_si if c.get("type") == "text"]
        assert "තේ කොළ" in texts_si
        assert "Milk Powder" in texts_si

        # Tamil
        commands_ta = RefundReceiptBuilder.build_refund_receipt(sale, config_override={"receipt_language": "ta"})
        texts_ta = [c["val"] for c in commands_ta if c.get("type") == "text"]
        assert "தேயிலை" in texts_ta
        assert "Milk Powder" in texts_ta


class TestInvoiceServiceDisplayNameRefactor:
    """InvoiceService uses ProductService.display_name for lines."""

    def test_invoice_service_build_lines_uses_product_service_display_name(self):
        sale, _, _ = _create_mock_sale_with_products()
        lines_si = InvoiceService.invoice_lines(sale, lang="si")
        assert lines_si[0].description == "තේ කොළ"
        assert lines_si[1].description == "Milk Powder"

        lines_ta = InvoiceService.invoice_lines(sale, lang="ta")
        assert lines_ta[0].description == "தேயிலை"
        assert lines_ta[1].description == "Milk Powder"
