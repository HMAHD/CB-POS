"""
Service for generating barcode label print commands for thermal printers.
"""

import logging
from typing import List, Dict, Any
from cbpos.core.models import Product
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)


class LabelService:
    """Generates barcode label commands for thermal printer output."""

    @staticmethod
    def _build_single_label(product: Product) -> List[Dict[str, Any]]:
        """
        Build print commands for a single barcode label.

        Each label contains: product name, barcode (CODE128), barcode text, and price.
        """
        return [
            {"type": "text", "val": product.name_en, "align": "center"},
            {
                "type": "barcode",
                "val": product.barcode,
                "code": "CODE128",
                "align": "center",
            },
            {"type": "text", "val": product.barcode, "align": "center"},
            {"type": "text", "val": format_currency(product.price), "align": "center"},
            {"type": "feed", "lines": 1},
            {"type": "cut"},
        ]

    @staticmethod
    def generate_label_commands(product: Product, quantity: int = 1) -> List[List[Dict[str, Any]]]:
        """
        Generate label print commands for a product.

        Returns a list of label command lists (one per copy).

        Args:
            product: Product model instance.
            quantity: Number of labels to print.

        Returns:
            List of command lists, one per label copy.
        """
        return [LabelService._build_single_label(product) for _ in range(quantity)]

    @staticmethod
    def generate_batch_commands(
        products_with_qty: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Generate all label commands as a single flat command list.

        Args:
            products_with_qty: List of dicts with 'product' and 'quantity' keys.

        Returns:
            Flat list of print commands for all labels.
        """
        all_commands: List[Dict[str, Any]] = []

        for item in products_with_qty:
            product = item["product"]
            qty = item.get("quantity", 1)

            for _ in range(qty):
                all_commands.extend(LabelService._build_single_label(product))

        return all_commands
