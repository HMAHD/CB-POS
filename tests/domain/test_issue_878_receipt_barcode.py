"""Tests for issue #878: CODE128 invoice barcode sizing and scaling to paper width.

Decision D10: CODE128 for receipt barcode using code set {B, with dimensions
calculated to fit the document number on 58mm and 80mm paper.
"""

import logging
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from cbpos.core.models import Product, Sale, SaleItem
from cbpos.core.services.document_service import DOC_NUMBER_MAX_LENGTH
from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder
from cbpos.core.utils.barcode import (
    calculate_barcode_width,
    code128_module_count,
)
from cbpos.core.utils.thermal_image import PAPER_DOT_WIDTH
from cbpos.infrastructure.hardware.escpos_driver import ESCPOSDriver

pytestmark = pytest.mark.domain


def _make_dummy_sale(doc_number: str = "INV-2026-00001") -> Sale:
    """Create a lightweight Sale instance with document_number."""
    prod = Product(id=1, name_en="Test Product", barcode="4791234567890", price=Decimal("1000.00"))
    sale = Sale(
        id=999,
        document_number=doc_number,
        date=datetime(2026, 11, 10, 14, 30),
        total_amount=Decimal("1000.00"),
        tax_vat=Decimal("0.00"),
        payment_method="CASH",
    )
    sale.items = [
        SaleItem(
            product_id=1,
            product=prod,
            qty=Decimal("1"),
            unit_price=Decimal("1000.00"),
            original_price=Decimal("1000.00"),
            subtotal=Decimal("1000.00"),
        )
    ]
    sale.payments = []
    return sale


def test_issue_878_longest_doc_number_fits_58_and_80mm(caplog):
    """Document numbers scaled to paper width satisfy width * modules <= PAPER_DOT_WIDTH."""
    # 1. Standard receipt pattern: INV-2026-00001 (14 chars)
    std_doc = "INV-2026-00001"
    mod_std = code128_module_count(std_doc)
    w_58 = calculate_barcode_width(std_doc, "58mm")
    w_80 = calculate_barcode_width(std_doc, "80mm")
    assert w_58 is not None and w_80 is not None
    assert w_58 * mod_std <= PAPER_DOT_WIDTH["58mm"]
    assert w_80 * mod_std <= PAPER_DOT_WIDTH["80mm"]
    assert w_58 == 2
    assert w_80 == 3

    # 2. Sync prefix pattern: TILL01-INV-2026-00001 (21 chars)
    till_doc = "TILL01-INV-2026-00001"
    mod_till = code128_module_count(till_doc)
    w_till_58 = calculate_barcode_width(till_doc, "58mm")
    w_till_80 = calculate_barcode_width(till_doc, "80mm")
    assert w_till_58 is not None and w_till_80 is not None
    assert w_till_58 * mod_till <= PAPER_DOT_WIDTH["58mm"]
    assert w_till_80 * mod_till <= PAPER_DOT_WIDTH["80mm"]
    assert w_till_58 == 1
    assert w_till_80 == 2

    # 3. Maximum alphanumeric document numbers that fit on each paper width
    # 58mm: max 31 chars (376 modules <= 384 dots)
    doc_31 = "A" * 31
    mod_31 = code128_module_count(doc_31)
    w_31 = calculate_barcode_width(doc_31, "58mm")
    assert w_31 == 1
    assert w_31 * mod_31 <= PAPER_DOT_WIDTH["58mm"]

    # 80mm: max 49 chars (574 modules <= 576 dots)
    doc_49 = "A" * 49
    mod_49 = code128_module_count(doc_49)
    w_49 = calculate_barcode_width(doc_49, "80mm")
    assert w_49 == 1
    assert w_49 * mod_49 <= PAPER_DOT_WIDTH["80mm"]

    # 4. DOC_NUMBER_MAX_LENGTH (50 chars) exceeds paper width even at width=1
    assert DOC_NUMBER_MAX_LENGTH == 50
    doc_max = "X" * DOC_NUMBER_MAX_LENGTH
    assert calculate_barcode_width(doc_max, "58mm") is None
    assert calculate_barcode_width(doc_max, "80mm") is None

    # When barcode does not fit, receipt omits barcode, prints text only, and logs warning
    sale_max = _make_dummy_sale(doc_number=doc_max)
    with caplog.at_level(logging.WARNING):
        commands_58 = SalesReceiptBuilder.build_receipt(
            sale_max,
            config_override={"paper_width": "58mm", "show_barcode": True},
        )
    bc_cmds_58 = [c for c in commands_58 if c.get("type") == "barcode" and c.get("code") != "QR"]
    assert len(bc_cmds_58) == 0  # Barcode omitted
    # Document number text is still printed
    text_cmds = [c for c in commands_58 if c.get("type") == "text" and c.get("val") == doc_max]
    assert len(text_cmds) == 1
    assert any("exceeds" in rec.message or "too long" in rec.message for rec in caplog.records)


def test_issue_878_receipt_uses_code128():
    """Receipt builder emits CODE128 barcode with calculated width and height 60."""
    sale = _make_dummy_sale(doc_number="TILL01-INV-2026-00001")
    commands_80 = SalesReceiptBuilder.build_receipt(
        sale,
        config_override={"paper_width": "80mm", "show_barcode": True},
    )
    bc_cmds = [c for c in commands_80 if c.get("type") == "barcode" and c.get("code") != "QR"]
    assert len(bc_cmds) == 1
    bc = bc_cmds[0]
    assert bc["code"] == "CODE128"
    assert bc["width"] == 2
    assert bc["height"] == 60
    assert bc["align"] == "center"
    # Encodes document number, not sale.id (999)
    assert "TILL01-INV-2026-00001" in bc["val"]
    assert "999" not in bc["val"]


def test_issue_878_escpos_driver_prints_code128_with_dimensions():
    """ESCPOSDriver passes width and height kwargs to python-escpos."""
    driver = ESCPOSDriver()
    driver.printer = MagicMock()
    cmd = {
        "type": "barcode",
        "val": "{BTILL01-INV-2026-00001",
        "code": "CODE128",
        "align": "center",
        "width": 2,
        "height": 60,
    }
    driver.print_commands([cmd])
    driver.printer.barcode.assert_called_once_with(
        "{BTILL01-INV-2026-00001",
        "CODE128",
        function_type="B",
        width=2,
        height=60,
    )


def test_issue_878_code128_code_set_c_module_count():
    """Code Set C encodes pairs of digits, needing fewer modules than Code Set B."""
    # 12 digits in Code Set C takes 6 data symbols (both {C prefix formats)
    assert code128_module_count("{C123456789012") == 11 * (6 + 3) + 2  # 101 modules
    assert code128_module_count("{C123456789012}") == 11 * (6 + 3) + 2

    # 30-digit numeric barcode without prefix is also recognized as Code Set C
    numeric_30 = "123456789012345678901234567890"
    mod_num = code128_module_count(numeric_30)
    assert mod_num == 11 * (15 + 3) + 2  # 200 modules
    # In Code Set B it would have been 11 * (30 + 3) + 2 = 365
    assert mod_num < 365
    # Fits on 58mm (384 dots)
    assert calculate_barcode_width(numeric_30, "58mm") is not None


def test_issue_878_preview_strips_prefix_only_for_code128():
    """Prefix stripping in receipt preview applies only to CODE128 barcodes."""
    from cbpos.ui.widgets.receipt_preview_widget import ReceiptPreviewWidget

    parts_c39 = []
    ReceiptPreviewWidget._render_command({"type": "barcode", "code": "CODE39", "val": "{ABC123"}, 48, parts_c39)
    html_c39 = "".join(parts_c39)
    assert "{ABC123" in html_c39

    parts_c128 = []
    ReceiptPreviewWidget._render_command({"type": "barcode", "code": "CODE128", "val": "{BINV-001"}, 48, parts_c128)
    html_c128 = "".join(parts_c128)
    assert "INV-001" in html_c128
    assert "{BINV-001" not in html_c128
