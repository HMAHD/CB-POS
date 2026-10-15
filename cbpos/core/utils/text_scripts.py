"""Which text needs drawing as an image: Sinhala and Tamil (no Qt here)."""

# Unicode blocks with no ESC/POS code page and no ReportLab shaping: Tamil, Sinhala.
_RASTER_RANGES = ((0x0B80, 0x0BFF), (0x0D80, 0x0DFF))


def needs_raster(text: str) -> bool:
    """True if *text* has Sinhala/Tamil characters, which printers and ReportLab can't render as text."""
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in _RASTER_RANGES)
