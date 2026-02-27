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
    def generate_label_commands(product: Product, quantity: int = 1) -> List[List[Dict[str, Any]]]:
        """
        Generate label print commands for a product.

        Each label contains: product name, barcode (CODE128), and price.
        Returns a list of label command lists (one per copy).

        Args:
            product: Product model instance.
            quantity: Number of labels to print.

        Returns:
            List of command lists, one per label copy.
        """
        labels = []

        for _ in range(quantity):
            commands: List[Dict[str, Any]] = []

            # Product name
            commands.append({"type": "text", "val": product.name_en, "align": "center"})

            # Barcode
            commands.append(
                {
                    "type": "barcode",
                    "val": product.barcode,
                    "code": "CODE128",
                    "align": "center",
                }
            )

            # Barcode text
            commands.append({"type": "text", "val": product.barcode, "align": "center"})

            # Price
            commands.append(
                {
                    "type": "text",
                    "val": format_currency(product.price),
                    "align": "center",
                }
            )

            # Feed and cut between labels
            commands.append({"type": "feed", "lines": 1})
            commands.append({"type": "cut"})

            labels.append(commands)

        return labels

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
                all_commands.append({"type": "text", "val": product.name_en, "align": "center"})
                all_commands.append(
                    {
                        "type": "barcode",
                        "val": product.barcode,
                        "code": "CODE128",
                        "align": "center",
                    }
                )
                all_commands.append({"type": "text", "val": product.barcode, "align": "center"})
                all_commands.append({"type": "text", "val": format_currency(product.price), "align": "center"})
                all_commands.append({"type": "feed", "lines": 1})
                all_commands.append({"type": "cut"})

        return all_commands
