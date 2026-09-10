"""Shared logic for turning an arbitrary logo image into real thermal output.

Both the receipt printer (escpos_driver.py) and the Settings receipt
preview need the same answer to "what will this logo actually look like
once the printer converts it to 1-bit black/white dots" -- a full-color
or greyscale photo commonly turns into an unreadable grey blob under a
naive monochrome conversion, which a shop owner would otherwise only
discover after printing (and wasting) real receipt paper (#330).
"""

from PIL import Image

# Standard ESC/POS thermal printer dot-column counts at 203dpi.
PAPER_DOT_WIDTH = {"58mm": 384, "80mm": 576}


def dither_for_thermal_print(image: Image.Image, paper_width: str = "80mm") -> Image.Image:
    """Return the real 1-bit black/white image a thermal printer will produce.

    Resizes to the configured paper's dot-column width (58mm and 80mm
    have different physical dot widths -- a single fixed pixel cap
    doesn't fit both), then converts through greyscale to 1-bit using
    Pillow's default Floyd-Steinberg dithering, so the app controls (and
    can preview) this step instead of leaving it entirely to
    python-escpos's own internal conversion.
    """
    max_width = PAPER_DOT_WIDTH.get(paper_width, PAPER_DOT_WIDTH["80mm"])
    img = image.convert("L")
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = max(1, round(img.height * ratio))
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
    return img.convert("1")
