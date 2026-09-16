"""Tests for LabelService barcode label generation."""

from decimal import Decimal
from unittest.mock import MagicMock

from cbpos.core.services.label_service import LabelService


def _make_product(name: str = "Test Product", barcode: str = "1234567890", price: Decimal = Decimal("350.00")):
    """Create a mock product for testing."""
    product = MagicMock()
    product.name_en = name
    product.barcode = barcode
    product.price = price
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
        assert barcode_cmd["val"] == "1234567890"
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
