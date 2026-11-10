"""Tests for issue #908: honest merged receipt lines and accurate savings calculation.

When merge_items is True:
- Only items with identical (product_id, unit_price, original_price, is_manual_price) merge.
- Items with different unit prices remain separate lines so qty x unit_price == subtotal always holds.
- Printed savings reflect actual customer savings ((original_price - unit_price) * qty), never inflated.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from cbpos.core.models import Product, Sale, SaleItem
from cbpos.core.services.sales_receipt_builder import SalesReceiptBuilder

pytestmark = pytest.mark.domain


def _make_sale_with_items(items: list[SaleItem]) -> Sale:
    total = sum(i.subtotal for i in items)
    sale = Sale(
        id=101,
        document_number="INV-2026-00101",
        date=datetime(2026, 11, 10, 16, 0),
        total_amount=total,
        tax_vat=Decimal("0.00"),
        payment_method="CASH",
    )
    sale.items = items
    sale.payments = []
    return sale


def test_issue_908_different_prices_not_merged_and_savings_correct():
    """Two lines of one product at 300 and 350 do not merge, and printed saving is 50."""
    prod = Product(id=42, name_en="Fair Trade Coffee", barcode="4791111111111", price=Decimal("350.00"))

    # Line 1: discounted unit price 300 (was 350), qty 1, subtotal 300
    item1 = SaleItem(
        id=1,
        product_id=42,
        product=prod,
        qty=Decimal("1"),
        unit_price=Decimal("300.00"),
        original_price=Decimal("350.00"),
        subtotal=Decimal("300.00"),
        is_manual_price=False,
    )

    # Line 2: normal MRP unit price 350, qty 2, subtotal 700
    item2 = SaleItem(
        id=2,
        product_id=42,
        product=prod,
        qty=Decimal("2"),
        unit_price=Decimal("350.00"),
        original_price=Decimal("350.00"),
        subtotal=Decimal("700.00"),
        is_manual_price=False,
    )

    sale = _make_sale_with_items([item1, item2])

    commands = SalesReceiptBuilder.build_receipt(
        sale,
        config_override={"merge_items": True, "show_barcode": False},
    )

    # Extract all rows that display item details or savings
    rows = [c for c in commands if "left_val" in c]

    # 1. The two items must NOT be merged into a single '3 x 300.00' line
    # They must remain separate lines
    qty_price_rows = [r for r in rows if "x" in r.get("left_val", "")]
    assert len(qty_price_rows) == 2, f"Expected 2 separate lines, got {qty_price_rows}"

    line_300 = next(r for r in qty_price_rows if "300.00" in r["left_val"])
    assert "1 x" in line_300["left_val"] or "1.000 x" in line_300["left_val"]
    assert "300.00" in line_300["right_val"]

    line_350 = next(r for r in qty_price_rows if "350.00" in r["left_val"])
    assert "2 x" in line_350["left_val"] or "2.000 x" in line_350["left_val"]
    assert "700.00" in line_350["right_val"]

    # 2. Check savings line: saving must be 50.00 (from Line 1 only), not inflated to 150.00
    savings_rows = [r for r in rows if r.get("right_val", "").startswith("-")]
    # Exactly one saving row for the discounted line
    assert len(savings_rows) == 1
    assert "50.00" in savings_rows[0]["right_val"], f"Expected saving of 50.00, got {savings_rows[0]['right_val']}"
    assert "150.00" not in savings_rows[0]["right_val"]


def test_issue_908_identical_prices_merged():
    """Two lines of one product with identical unit_price and original_price do merge."""
    prod = Product(id=42, name_en="Fair Trade Coffee", barcode="4791111111111", price=Decimal("350.00"))

    item1 = SaleItem(
        id=1,
        product_id=42,
        product=prod,
        qty=Decimal("1"),
        unit_price=Decimal("300.00"),
        original_price=Decimal("350.00"),
        subtotal=Decimal("300.00"),
        is_manual_price=False,
    )
    item2 = SaleItem(
        id=2,
        product_id=42,
        product=prod,
        qty=Decimal("2"),
        unit_price=Decimal("300.00"),
        original_price=Decimal("350.00"),
        subtotal=Decimal("600.00"),
        is_manual_price=False,
    )

    sale = _make_sale_with_items([item1, item2])

    commands = SalesReceiptBuilder.build_receipt(
        sale,
        config_override={"merge_items": True, "show_barcode": False},
    )

    rows = [c for c in commands if "left_val" in c]
    qty_price_rows = [r for r in rows if "x" in r.get("left_val", "")]
    # Identical prices merge into 1 line
    assert len(qty_price_rows) == 1
    assert "3 x" in qty_price_rows[0]["left_val"] or "3.000 x" in qty_price_rows[0]["left_val"]
    assert "900.00" in qty_price_rows[0]["right_val"]

    # Savings = (350 - 300) * 3 = 150.00
    savings_rows = [r for r in rows if r.get("right_val", "").startswith("-")]
    assert len(savings_rows) == 1
    assert "150.00" in savings_rows[0]["right_val"]
