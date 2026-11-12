"""Service for generating barcode label print commands and layout for thermal printers."""

import io
import logging
from dataclasses import dataclass, field
from typing import Any

from cbpos.core.services.product_service import ProductService
from cbpos.core.utils.barcode import choose_barcode
from cbpos.core.utils.formatters import format_currency

logger = logging.getLogger(__name__)

MIN_WIDTH_MM = 25.0
MIN_HEIGHT_MM = 15.0

PRESET_DIMENSIONS: dict[str, tuple[float, float]] = {
    "50x30": (50.0, 30.0),
    "40x25": (40.0, 25.0),
    "58mm": (58.0, 40.0),
}


@dataclass(frozen=True)
class LabelOptions:
    """Immutable configuration options for barcode label generation."""

    preset: str = "50x30"  # "50x30", "40x25", "58mm", "custom"
    width_mm: float = 50.0
    height_mm: float = 30.0
    language: str = "en"  # "en", "si", "ta", "en+si", "en+ta"


@dataclass(frozen=True)
class LabelLayout:
    """Immutable label layout model consumed by both preview and printing (#819)."""

    options: LabelOptions
    product_id: int | None = None
    product_name: str = ""
    secondary_name: str | None = None
    is_fallback: bool = False
    barcode_value: str = ""
    barcode_symbology: str = "CODE128"
    barcode_payload: str = ""
    price_text: str = ""
    commands: list[dict[str, Any]] = field(default_factory=list)


class LabelService:
    """Generates barcode label commands and preview layouts for thermal printer output."""

    @classmethod
    def create_layout(cls, product: Any, options: LabelOptions | None = None) -> LabelLayout:
        """Create a unified immutable layout for preview and printing."""
        if options is None:
            options = LabelOptions()

        lang = (options.language or "en").lower().replace("_", "+")
        is_fallback = False
        secondary_name: str | None = None

        if lang == "en":
            primary_name = ProductService.display_name(product, "en")
        elif lang == "si":
            raw_si = (getattr(product, "name_si", None) or "").strip()
            if raw_si:
                primary_name = ProductService.display_name(product, "si")
            else:
                primary_name = ProductService.display_name(product, "en")
                is_fallback = True
        elif lang == "ta":
            raw_ta = (getattr(product, "name_ta", None) or "").strip()
            if raw_ta:
                primary_name = ProductService.display_name(product, "ta")
            else:
                primary_name = ProductService.display_name(product, "en")
                is_fallback = True
        elif lang == "en+si":
            primary_name = ProductService.display_name(product, "en")
            raw_si = (getattr(product, "name_si", None) or "").strip()
            if raw_si:
                secondary_name = ProductService.display_name(product, "si")
            else:
                is_fallback = True
        elif lang == "en+ta":
            primary_name = ProductService.display_name(product, "en")
            raw_ta = (getattr(product, "name_ta", None) or "").strip()
            if raw_ta:
                secondary_name = ProductService.display_name(product, "ta")
            else:
                is_fallback = True
        else:
            primary_name = ProductService.display_name(product, "en")

        if not primary_name:
            primary_name = "Product"

        raw_barcode = str(getattr(product, "barcode", "") or "").strip()
        symbology, payload = choose_barcode(raw_barcode) if raw_barcode else ("CODE128", "")

        price = getattr(product, "price", 0)
        price_text = format_currency(price) if price is not None else ""

        # Scale dimensions for barcode and feed
        bc_height = 40 if options.height_mm <= 25.0 else (55 if options.height_mm <= 30.0 else 70)
        bc_width = 2 if options.width_mm <= 45.0 else 3
        feed_lines = 1 if options.height_mm <= 30.0 else 2

        commands: list[dict[str, Any]] = [
            {"type": "text", "val": primary_name, "align": "center", "bold": True},
        ]
        if secondary_name:
            commands.append({"type": "text", "val": secondary_name, "align": "center"})

        if raw_barcode:
            commands.extend(
                [
                    {
                        "type": "barcode",
                        "val": payload,
                        "code": symbology,
                        "align": "center",
                        "width": bc_width,
                        "height": bc_height,
                    },
                    {"type": "text", "val": raw_barcode, "align": "center"},
                ]
            )

        commands.extend(
            [
                {"type": "text", "val": price_text, "align": "center", "bold": True},
                {"type": "feed", "lines": feed_lines},
                {"type": "cut", "partial": True},
            ]
        )

        return LabelLayout(
            options=options,
            product_id=getattr(product, "id", None),
            product_name=primary_name,
            secondary_name=secondary_name,
            is_fallback=is_fallback,
            barcode_value=raw_barcode,
            barcode_symbology=symbology,
            barcode_payload=payload,
            price_text=price_text,
            commands=commands,
        )

    @classmethod
    def _build_single_label(
        cls,
        product: Any,
        options: LabelOptions | None = None,
    ) -> list[dict[str, Any]]:
        """Build print commands for a single barcode label."""
        layout = cls.create_layout(product, options)
        return list(layout.commands)

    @classmethod
    def generate_label_commands(
        cls,
        product: Any,
        quantity: int = 1,
        options: LabelOptions | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Generate label print commands for a product (one command list per copy)."""
        single = cls._build_single_label(product, options)
        return [list(single) for _ in range(quantity)]

    @classmethod
    def generate_batch_commands(
        cls,
        products_with_qty: list[dict[str, Any]],
        options: LabelOptions | None = None,
    ) -> list[dict[str, Any]]:
        """Generate all label commands as a single flat command list."""
        all_commands: list[dict[str, Any]] = []

        for item in products_with_qty:
            product = item["product"]
            qty = item.get("quantity", 1)
            single = cls._build_single_label(product, options)

            for _ in range(qty):
                all_commands.extend(single)

        return all_commands

    @staticmethod
    def validate_dimensions(
        width_mm: float,
        height_mm: float,
        max_printable_width_mm: float = 80.0,
    ) -> tuple[bool, str | None]:
        """Validate label dimensions against printer printable width."""
        if width_mm < MIN_WIDTH_MM or height_mm < MIN_HEIGHT_MM:
            return False, "err_dimensions_min"
        if width_mm > max_printable_width_mm:
            return False, "err_width_exceeds"
        return True, None

    @staticmethod
    def render_barcode_image(barcode_val: str, symbology: str = "CODE128") -> bytes | None:
        """Render a barcode image as PNG bytes using python-barcode."""
        val = str(barcode_val or "").strip()
        if not val:
            return None
        try:
            import barcode
            from barcode.writer import ImageWriter

            sym = symbology.lower()
            if sym in ("ean13", "ean-13"):
                bc_cls = barcode.get_barcode_class("ean13")
            else:
                bc_cls = barcode.get_barcode_class("code128")

            bc = bc_cls(val, writer=ImageWriter())
            buf = io.BytesIO()
            bc.write(buf, options={"write_text": False, "quiet_zone": 1.5})
            return buf.getvalue()
        except Exception as e:
            logger.warning("Failed to generate barcode image for %r: %s", barcode_val, e)
            return None
